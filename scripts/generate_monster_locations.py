"""Generate monster_locations.json — where every monster/NPC card is found, and the area
access each location needs (the card page's "Location" box).

Sources: each card's wiki page (Infobox Monster / Infobox NPC "location" field, batched 50
per request, cached), then the same location → region → access_routes.json mapping as
generate_slayer.py (wiki leagueRegion + slayer_curated.json "locationAccess" overrides).

Output: scripts/output/monster_locations.json
  { "<card>": { "<location>": "<access key>" | null },    (null = nothing needed to reach it)
    "_gates": { "<location>": {quests?, cards?, skills?, access?} } }   (extra needs at that place,
    from the Slayer verification's location gates)

Usage:
  python3 scripts/generate_monster_locations.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from generate_slayer import REGION_ACCESS, location_regions

_HERE = Path(__file__).resolve().parent
_OUT = _HERE / "output" / "monster_locations.json"
_CACHE = _HERE / "cache" / "npc_page_locations.json"
_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def page_locations(titles: list[str]) -> dict[str, list[str]]:
    """page → linked locations from its infobox "location" field(s); cached."""
    cache = json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=revisions"
               "&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read())["query"]
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            locs = []
            for m in re.finditer(r"\|\s*location\d*\s*=([^\n]*)", text):
                locs += [l.strip() for l in _LINK_RE.findall(m.group(1)) if not l.startswith(("File:", "Category:"))]
            srcs = [pg["title"]] + back.get(pg["title"], [])
            for t in list(srcs):
                srcs += back.get(t, [])
            for t in srcs:
                cache[t] = list(dict.fromkeys(locs))
        for t in batch:
            cache.setdefault(t, [])
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(1)
        if (i // 50) % 5 == 0:
            print(f"  pages {min(i + 50, len(todo))}/{len(todo)}")
    return cache


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    cards = {x["name"]: (x.get("wiki") or {}).get("page") or x["name"] for x in cat["npcs"]}
    overrides = json.loads((_HERE / "slayer_curated.json").read_text(encoding="utf-8")).get("locationAccess", {})
    locs = page_locations(list(cards.values()))
    regions = location_regions([l for ls in locs.values() for l in ls])

    def access_of(loc):
        if loc in overrides:
            return overrides[loc]
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
            gate = {k: g[k] for k in ("quests", "cards", "skills", "access") if g.get(k)}
            if gate:
                prev = gates.setdefault(g["location"], {})
                for k, v in gate.items():
                    if isinstance(v, list):
                        prev[k] = sorted(set(prev.get(k, [])) | set(v))
                    elif isinstance(v, dict):
                        prev[k] = {**prev.get(k, {}), **v}
                    else:
                        prev[k] = v
    out = {"_gates": dict(sorted(gates.items()))}
    for card, page in sorted(cards.items()):
        ls = locs.get(page, [])
        if ls:
            out[card] = {l: access_of(l) for l in ls}
    _OUT.write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    gated = sum(1 for k, v in out.items() if not k.startswith("_") and v and all(a for a in v.values()))
    print(f"Wrote {_OUT}: {len(out)} of {len(cards)} NPC cards have locations; {gated} only in gated areas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
