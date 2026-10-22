"""Generate monster_locations.json — where every monster/NPC card is found, and the area
access each location needs (the card page's "Found at" box, combat-training reachability).

Sources:
  - A card covers its catalog id plus its TCG variant ids. Each id's wiki page comes from the wiki
    buckets infobox_monster (|id) / infobox_npc (|npc_id) (cached: cache/npc_id_pages.json), so a
    "Warrior" card gets every Warrior page, not only the one page the catalog names.
  - Each page's Infobox Monster / Infobox NPC versions (Switch infobox tabs and |versionN) and its
    {{LocLine}} rows (batched 50 per request, parsed + cached: cache/npc_page_versions.json). Only the
    versions whose ids the card covers count; a LocLine tagged with another version is skipped.
  - Non-combat quest copies of a combat NPC are skipped when they sit outside the card's TCG pack
    region (Guthan the Infested's Desert Treasure II version in the Ancient Vault).
  - Linked pages that aren't places (quests, items, NPCs) are dropped (wiki_page_types cache).
  - A link that is only a reference point ("South of the [[Farming Guild]]", "In front of the
    [[Warriors' Guild]]") becomes "<place> (nearby)": same area access, but not the place's entry gate.
  - monster_locations_overrides.json: per-card drop/add, per-place access fixes, pack-region notes.
  - Location -> region -> access: wiki leagueRegion + slayer_curated.json "locationAccess" overrides
    (REGION_ACCESS in generate_slayer.py), as before.
  It ends with a sanity check against the TCG packs: cards found only outside their pack's region(s).

Output: scripts/output/monster_locations.json
  { "<card>": { "<location>": "<access key>" | null },    (null = nothing needed to reach it)
    "_gates": { "<location>": {quests?, partialQuests?, diaries?, cards?, skills?, access?, …} } }
    (extra needs at that place: the Slayer verification's location gates merged with
    location_requirements.json — see location_reqs.py for the gate model)

Other inputs: slayer_curated.json "taskOverrides" location gates (non-monster-specific ones become
"_gates"), location_requirements.json (via location_reqs.py; validated against the outputs first),
and the region / page-type caches shared with generate_slayer.py / generate_diaries.py
(cache/location_regions.json, wiki_page_types cache). Delete cache/npc_page_versions.json (or bump
_CACHE_VERSION) to re-parse pages.

Usage:
  python3 scripts/generate_monster_locations.py --card-json research/card-catalog-live.json
"""

from __future__ import annotations

import argparse
import json
import wiki_api
import re
import urllib.parse
from collections import Counter
from pathlib import Path

from generate_slayer import REGION_ACCESS, location_regions

_HERE = Path(__file__).resolve().parent
_OUT = _HERE / "output" / "monster_locations.json"
_CACHE = _HERE / "cache" / "npc_page_versions.json"
_ID_CACHE = _HERE / "cache" / "npc_id_pages.json"
_OVERRIDES = _HERE / "monster_locations_overrides.json"
# Wiki page types that are never a place (a quest, item or NPC linked from a location field)
_NOT_PLACE = {"Quest", "Miniquest", "Item", "Bonuses", "NPC", "Monster", "Skill", "Spell", "Pet", "Currency", "Prayer", "Organisation"}
PACK_REGIONS = {"Misthalin", "Asgarnia", "Kandarin", "Karamja", "Fremennik", "Kourend", "Varlamore",
                "Morytania", "Desert", "Tirannwn", "Wilderness"}
# [[Target#anchor|display]] -> group 1 = target page
_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
# A link given only as a reference point ("South of the [[Farming Guild]]", "In front of the
# [[Warriors' Guild]]", "[[Lunar Sea]] - north-east of [[Brittle Isle]]") is not a place the NPC is
# IN: it is kept as "<place> (nearby)", which shares the place's area access but not its entry gate
# (location_requirements.json, Slayer location gates). A link followed by a capitalised word names a
# sub-place ("North-east of [[Miscellania]] Castle" is on Miscellania) and stays as it is.
NEARBY = " (nearby)"
_REL_RE = re.compile(r"(?:\b(?:north|south|east|west)(?:[- ]?(?:east|west))?(?:ern)?\s+(?:side\s+)?of|\boutside(?:\s+of)?|"
                     r"\bin front of|\bnear(?:by)?|\bnext to|\baround|\bbeside|\bbehind|\bopposite|\bacross from)"
                     r"\s*(?:the\s*)?$", re.I)
_CACHE_VERSION = 2   # 2: location links carry the "(nearby)" marker


def base_place(loc: str) -> str:
    """'Farming Guild (nearby)' -> 'Farming Guild' (for region / page-type / access lookups)."""
    return loc[:-len(NEARBY)] if loc.endswith(NEARBY) else loc


def _template_at(text: str, i: int) -> str:
    """Body of the balanced {{...}} template that starts at text[i]."""
    depth, j = 0, i
    while j < len(text):
        if text.startswith("{{", j):
            depth += 1
            j += 2
        elif text.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                return text[i + 2:j - 2]
        else:
            j += 1
    return text[i + 2:]


def _params(body: str) -> dict[str, str]:
    """Top-level |key = value parameters of a template body (nested {{ }} / [[ ]] kept intact)."""
    parts, depth, cur, k = [], 0, [], 0
    while k < len(body):
        two = body[k:k + 2]
        if two in ("{{", "[["):
            depth += 1; cur.append(two); k += 2; continue
        if two in ("}}", "]]"):
            depth -= 1; cur.append(two); k += 2; continue
        if body[k] == "|" and depth == 0:
            parts.append("".join(cur)); cur = []; k += 1; continue
        cur.append(body[k]); k += 1
    parts.append("".join(cur))
    out = {}
    for part in parts[1:]:
        if "=" in part:
            key, v = part.split("=", 1)
            out[key.strip().lower()] = v.strip()
    return out


def _links(v: str) -> list[str]:
    """Place links of a location value; reference-point links get the NEARBY suffix."""
    out, prev = [], 0
    v = v or ""
    for m in _LINK_RE.finditer(v):
        name = m.group(1).strip().replace("_", " ")
        pre, post = v[prev:m.start()], v[m.end():m.end() + 12]
        prev = m.end()
        if name.startswith(("File:", "Category:", ":")):
            continue
        if _REL_RE.search(pre) and not re.match(r"\s?[A-Z][a-z]", post):
            name += NEARBY
        out.append(name)
    return out


def parse_page(text: str) -> dict:
    """One NPC page → {"versions": [...], "loclines": [...]}.

    versions: every Infobox Monster / Infobox NPC version — each item of a {{Switch infobox}},
      and each |versionN of a multi-version infobox (|idN / |locationN … override the base value).
    loclines: every {{LocLine}} (the Locations table), with its version / dropversion / name tags."""
    boxes = []  # (switch tab text, infobox kind, params)
    for m in re.finditer(r"\{\{\s*Switch infobox", text, re.I):
        sw = _params(_template_at(text, m.start()))
        for key, v in sw.items():
            n = re.fullmatch(r"item(\d+)", key)
            ib = n and re.search(r"\{\{\s*Infobox (Monster|NPC)\b", v, re.I)
            if ib:
                boxes.append((sw.get("text" + n.group(1), ""), ib.group(1).title(), _params(_template_at(v, ib.start()))))
    if not boxes:
        for m in re.finditer(r"\{\{\s*Infobox (Monster|NPC)\s*\n?\|", text, re.I):
            boxes.append(("", m.group(1).title(), _params(_template_at(text, m.start()))))
    versions = []
    for tab, kind, p in boxes:
        nums = sorted({int(n.group(1)) for k in p for n in [re.fullmatch(r"version(\d+)", k)] if n})
        for n in nums or [None]:
            get = (lambda k, n=n: p.get(f"{k}{n}", p.get(k, ""))) if n else (lambda k: p.get(k, ""))
            versions.append({"label": get("version") if n else tab, "tab": tab, "kind": kind,
                             "ids": sorted({int(x) for x in re.findall(r"\d+", get("id"))}),
                             "locations": list(dict.fromkeys(_links(get("location")))),
                             "region": get("leagueregion"), "quest": get("quest"),
                             "dropversion": get("dropversion"), "name": get("name")})
    loclines = []
    for m in re.finditer(r"\{\{\s*LocLine", text, re.I):
        p = _params(_template_at(text, m.start()))
        loclines.append({"locations": _links(p.get("location")), "version": p.get("version", ""),
                         # "dropverison": a misspelling that occurs on some wiki pages
                         "dropversion": p.get("dropversion", "") or p.get("dropverison", ""),
                         "name": p.get("name", ""), "region": p.get("leagueregion", "")})
    return {"versions": versions, "loclines": loclines}


def npc_id_pages() -> dict[int, list[str]]:
    """NPC id → wiki pages whose Infobox Monster (|id) / Infobox NPC (|npc_id) lists it (wiki bucket; cached)."""
    if _ID_CACHE.exists():
        return {int(k): v for k, v in json.loads(_ID_CACHE.read_text(encoding="utf-8")).items()}
    out: dict[int, list[str]] = {}
    for bucket, field in (("infobox_monster", "id"), ("infobox_npc", "npc_id")):
        off = 0
        while True:
            q = f"bucket('{bucket}').select('page_name','{field}').limit(5000).offset({off}).run()"
            rows = wiki_api.get_json("https://oldschool.runescape.wiki/api.php?action=bucket&format=json&query="
                                     + urllib.parse.quote(q))["bucket"]
            for r in rows:
                for i in r.get(field) or []:
                    if str(i).strip().isdigit() and r["page_name"] not in out.setdefault(int(i), []):
                        out[int(i)].append(r["page_name"])
            if len(rows) < 5000:
                break
            off += 5000
    _ID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _ID_CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def page_versions(titles: list[str]) -> dict[str, dict]:
    """page → parse_page(its wikitext); batched 50 per request (action=query revisions), cached."""
    cache = json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    if cache.get("__version__") != _CACHE_VERSION:   # parsed with older rules: re-fetch
        cache = {"__version__": _CACHE_VERSION}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=revisions"
               "&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        q = wiki_api.get_json(url)["query"]
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            srcs = [pg["title"]] + back.get(pg["title"], [])
            for t in list(srcs):
                srcs += back.get(t, [])
            for t in srcs:
                cache[t] = parse_page(text)
        for t in batch:
            cache.setdefault(t, {"versions": [], "loclines": []})
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if (i // 50) % 5 == 0:
            print(f"  pages {min(i + 50, len(todo))}/{len(todo)}")
    return cache


def _norm(s: str) -> str:
    """Lowercase with non-word characters removed, for comparing version labels/tags."""
    return re.sub(r"\W", "", (s or "").lower())


def card_locations(page: str, ids: set[int], pages: dict[str, dict], id_pages: dict[int, list[str]],
                   pack: set[str], regions: dict[str, str], why: Counter) -> list[str]:
    """Locations of the NPC versions a card covers (its catalog id + TCG variant ids), across every
    wiki page those ids live on. Versions of other NPCs that merely share a page are skipped.

    Also skipped: a non-combat quest copy (an Infobox NPC with |quest=) of a card that has a combat
    version, when neither its locations' regions nor its own |leagueRegion fall in the card's TCG pack
    region(s) — e.g. Guthan the Infested's Desert Treasure II version in the Ancient Vault (Desert)."""
    titles = [page] + sorted({p for i in ids for p in id_pages.get(i, [])} - {page})
    chosen = []  # (page, version)
    for t in titles:
        vs = pages.get(t, {}).get("versions", [])
        sel = [v for v in vs if set(v["ids"]) & ids]
        if t == page and vs and not sel:
            sel = vs                          # no ids on the infobox: keep every version (old behaviour)
        chosen += [(t, v) for v in sel]

    def quest_copy_elsewhere(v):
        """True for a non-combat quest NPC version located wholly outside the card's pack region(s)."""
        if v["kind"] != "Npc" or v["quest"].strip() in ("", "No") or not v["locations"] or not pack:
            return False
        rs = [regions.get(base_place(l), "") for l in v["locations"]]
        if not all(rs) or any(set(r.split("&")) & pack for r in rs):
            return False
        own = {r.capitalize() for r in re.findall(r"[A-Za-z]+", v["region"])}
        return not own & pack
    if pack and any(v["kind"] == "Monster" and v["quest"].strip() in ("", "No") for _, v in chosen):
        keep = [(t, v) for t, v in chosen if not quest_copy_elsewhere(v)]
        if len(keep) < len(chosen):
            why["questCopyDropped"] += len(chosen) - len(keep)
        chosen = keep
    locs = []
    for t in titles:
        info = pages.get(t, {})
        vs = info.get("versions", [])
        sel = [v for tt, v in chosen if tt == t]
        if not sel and vs:
            continue
        if len(sel) == len(vs):
            for v in sel:
                locs += v["locations"]
            for l in info.get("loclines", []):
                locs += l["locations"]
            continue
        # Some versions only: keep a LocLine unless its tags name a version the card doesn't cover
        keys = {_norm(v[k]) for v in sel for k in ("label", "tab", "dropversion", "name") if v[k]}
        other = {_norm(v[k]) for v in vs if v not in sel for k in ("label", "tab", "dropversion", "name") if v[k]} - keys
        here = [l for v in sel for l in v["locations"]]
        for l in info.get("loclines", []):
            tags = {_norm(l[k]) for k in ("version", "dropversion", "name") if l[k]}
            if tags & other and not tags & keys:
                why["locLineOtherVersion"] += 1
                continue
            here += l["locations"]
        if not here and sel:
            # The card's versions state no place, but a sibling form on the same page does (Egg / Hatched,
            # NPC / In combat): the page usually gives the location once. Quest copies elsewhere excluded.
            here = [l for v in vs if v not in sel and not quest_copy_elsewhere(v) for l in v["locations"]]
            if here:
                why["siblingVersionLocation"] += 1
        locs += here
    return list(dict.fromkeys(locs))


def main() -> int:
    """Build and write monster_locations.json and print the version-filter / pack-region checks. Returns 0."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    cards = {x["name"]: ((x.get("wiki") or {}).get("page") or x["name"],
                         {x["id"]} | {v["id"] for v in (x.get("tcg") or {}).get("variants", [])})
             for x in cat["npcs"]}
    packs = {x["name"]: set(x.get("regions") or []) & PACK_REGIONS for x in cat["npcs"]}
    overrides = json.loads((_HERE / "slayer_curated.json").read_text(encoding="utf-8")).get("locationAccess", {})
    id_pages = npc_id_pages()
    titles = [pg for pg, ids in cards.values()] + [t for _, ids in cards.values() for i in ids for t in id_pages.get(i, [])]
    pages = page_versions(titles)
    why = Counter()
    regions = location_regions(sorted({base_place(l) for k, info in pages.items() if k != "__version__"
                                       for v in info["versions"] for l in v["locations"]}))
    found = {card: card_locations(pg, ids, pages, id_pages, packs[card], regions, why)
             for card, (pg, ids) in cards.items()}
    # Drop links that aren't places (quest / item / NPC pages linked from a location field)
    from generate_diaries import _page_types
    types = _page_types(sorted({base_place(l) for ls in found.values() for l in ls}))
    for card, ls in found.items():
        keep = [l for l in ls if types.get(base_place(l), "") not in _NOT_PLACE]
        if any(l.endswith(NEARBY) for l in keep):
            why["nearbyLinks"] += sum(1 for l in keep if l.endswith(NEARBY))
        # the place itself listed too ("Rat: Farming Guild" and "south of the Farming Guild"): drop the nearby copy
        keep = [l for l in keep if not (l.endswith(NEARBY) and base_place(l) in keep)]
        why["notAPlaceDropped"] += len(ls) - len(keep)
        found[card] = keep
    # Hand fixes (monster_locations_overrides.json): per card, locations to drop / add, with the wiki's word
    hand_all = json.loads(_OVERRIDES.read_text(encoding="utf-8")) if _OVERRIDES.exists() else {}
    hand = {k: v for k, v in hand_all.items() if not k.startswith("_")}
    # Per-place access fixes for this file only (same meaning as slayer_curated.json "locationAccess")
    # (used by access_of only; the _gates below still skip just slayer_curated's own locationAccess places)
    loc_access = {**overrides, **{k: v["access"] for k, v in hand_all.get("_locationAccess", {}).items()}}
    for card, o in hand.items():
        if card not in found:
            print(f"  WARNING override for unknown card {card!r}")
            continue
        missing = [l for l in o.get("drop", []) if l not in found[card]]
        if missing:
            print(f"  WARNING override {card!r}: drop {missing} not in its locations (stale?)")
        found[card] = [l for l in found[card] if l not in o.get("drop", [])] + \
            [l for l in o.get("add", []) if l not in found[card]]
    regions = location_regions([base_place(l) for ls in found.values() for l in ls])

    def access_of(loc):
        """access_routes.json key needed to reach `loc` (None = none); "(nearby)" uses the place's access."""
        loc = base_place(loc)   # a nearby place shares the place's area access
        if loc in loc_access:
            return loc_access[loc]
        rs = [r for r in regions.get(loc, "").split("&") if r]
        keys = [REGION_ACCESS.get(r) for r in rs]
        return None if not rs or None in keys else keys[0]

    # Per-location gates found by the Slayer verification (quests / cards / skills to reach a place)
    gates = {}
    for o in json.loads((_HERE / "slayer_curated.json").read_text(encoding="utf-8")).get("taskOverrides", {}).values():
        for g in o.get("locationGates", []):
            if g.get("monster"):
                continue  # monster-specific, not a property of the place
            if g["location"] in overrides:
                continue  # the place has its own access route (e.g. the Abyss: Enter the Abyss OR Fairytale II)
            gate = {k: g[k] for k in ("quests", "partialQuests", "diaries", "cards", "skills", "access") if g.get(k)}
            if gate:
                prev = gates.setdefault(g["location"], {})
                for k, v in gate.items():
                    if isinstance(v, list):
                        prev[k] = sorted(set(prev.get(k, [])) | set(v))
                    elif isinstance(v, dict):
                        prev[k] = {**prev.get(k, {}), **v}
                    else:
                        prev[k] = v
    # Entry requirements of the places themselves (location_requirements.json: guild levels, quests,
    # Sailing levels to dock, worn items…), merged into the Slayer-derived gates. Keyed by the name as
    # our data spells it ('Farming guild' too), plus every curated place (shops use these gates).
    import location_reqs
    probs = location_reqs.validate_with_outputs()
    for x in probs:
        print("  ! location_requirements.json: " + x)
    used = {l for ls in found.values() for l in ls} | set(location_reqs.load())
    added = Counter()
    for loc in sorted(used):
        lg = location_reqs.gate_for(loc)
        if not lg:
            continue
        before = json.dumps(gates.get(loc), sort_keys=True)
        gates[loc] = location_reqs.merge_gate(gates.get(loc), lg)
        if json.dumps(gates[loc], sort_keys=True) != before:
            added.update(k for k in lg)
    print(f"  location_requirements: {sum(1 for l in used if location_reqs.gate_for(l))} places gated; fields merged {dict(added)}")
    out = {"_gates": dict(sorted(gates.items()))}
    for card in sorted(cards):
        ls = found[card]
        if ls:
            out[card] = {l: access_of(l) for l in ls}
    _OUT.write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    gated = sum(1 for k, v in out.items() if not k.startswith("_") and v and all(a for a in v.values()))
    print(f"Wrote {_OUT}: {len(out) - 1} of {len(cards)} NPC cards have locations; {gated} only in gated areas")
    print(f"  version filter: {dict(why)}; {len(hand)} hand overrides")
    # Sanity check against the TCG's regional packs: cards none of whose locations sit in a pack region.
    # Most are region-boundary disagreements (GWD, Paterdomus, Stranglewood…); see the overrides file.
    # Places whose wiki leagueRegion is known to differ from the TCG's pack region are noted in the
    # overrides file ("_packRegionNotes") and not flagged.
    noted = hand_all.get("_packRegionNotes", {})
    off = [c for c, ls in out.items() if not c.startswith("_") and packs.get(c)
           and all(regions.get(base_place(l)) and not set(regions[base_place(l)].split("&")) & packs[c]
                   and base_place(l) not in noted for l in ls)]
    print(f"  pack check: {len(off)} cards found only outside their pack's region(s): {', '.join(off)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
