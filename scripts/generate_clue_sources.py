"""Generate the clue-scroll source and reward data the planner's Clues tab reads.

Outputs (paths and shapes kept from the original hand-made files; fields only added):

  scripts/clue_scroll_sources.json
      {tier: [{source, level, rarity, kind, card, ...}]}
      kind: monster | pickpocket | impling | chest | skilling | casket | npc-exchange | other
      card: the TCG card you must own to use the source (NPC card, impling jar / item card,
            Watson), or null when no card gates it (chests, skilling, caskets).
      optional: altRarity (wiki's second rate, e.g. Wilderness/on-task), versions (wiki drop-table
            versions merged into one row), rarity99 / nodes / skill / tool / quests (skilling),
            needs (npc-exchange), note.
  scripts/clue_sources.json
      {card name: [tiers]}  — reward items that are TCG item cards (read by generate_sources.py
      Pass 5 → item_sources[*].clueTiers, and by preview.html → clueRewardsByTier).
  scripts/clue_reward_rarities.json
      {tier: {name: fraction string}} — keyed by card name when the reward resolves to a card
      (doses, grimy herbs, … collapse onto the card, rates summed), else by the wiki item name.

Sources (wiki staff rules, see wiki_fetcher.py — never api.php?action=parse):
  - action=bucket 'dropsline' (the data behind every "Item sources" / drop table on the wiki):
    rows whose item is "Clue scroll (<tier>)", and rows on the "Reward casket (<tier>)" pages.
    Cached in scripts/cache/clue_sources_bucket.json.
  - Raw wikitext (?action=raw) of Clue geode / Clue nest / Clue bottle for the skilling
    base-chance tables and clue-tier modifiers (cached in scripts/cache/wikitext/).

Usage:
  python3 scripts/generate_clue_sources.py [--refresh]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import loot_parser  # noqa: E402
import wiki_api  # noqa: E402
import wiki_fetcher  # noqa: E402
from catalog_names import npc_names  # noqa: E402
from generate_diaries import _fetch_wikitext  # noqa: E402
import generate_sources as gs  # noqa: E402

_ROOT = _HERE.parent
_CATALOG = _ROOT / "research" / "card-catalog-live.json"
_ALIASES = _HERE / "output" / "card_aliases.json"
_VERSIONS = _HERE / "output" / "card_versions.json"
_BUCKET_CACHE = _HERE / "cache" / "clue_sources_bucket.json"
OUT_SCROLL = _HERE / "clue_scroll_sources.json"
OUT_SOURCES = _HERE / "clue_sources.json"
OUT_RARITIES = _HERE / "clue_reward_rarities.json"

TIERS = ["beginner", "easy", "medium", "hard", "elite", "master"]
SKILL_TIERS = TIERS[:5]  # no master geodes/nests/bottles

# ── Card lookup ────────────────────────────────────────────────────────────────────────────

_cat = json.loads(_CATALOG.read_text(encoding="utf-8"))
ITEM_LC = {i["name"].lower(): i["name"] for i in _cat["items"]}
NPC_LC = npc_names(_cat, versions=True)   # card names, wiki pages and version names -> NPC card
ALIASES: dict[str, str] = json.loads(_ALIASES.read_text(encoding="utf-8")) if _ALIASES.exists() else {}
VERSION_LC: dict[str, str] = {}  # version name / wiki page (lowercase) → card
if _VERSIONS.exists():
    for card, vs in json.loads(_VERSIONS.read_text(encoding="utf-8")).items():
        for v in vs:
            for k in (v.get("name"), v.get("page")):
                if k:
                    VERSION_LC.setdefault(k.lower(), card)
gs.set_variant_aliases(gs.load_variant_aliases(str(_CATALOG)))
_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def card_for_item(name: str) -> str | None:
    """Reward item → item card: exact / case-insensitive, card_aliases.json, catalog variants+doses."""
    lc = name.lower()
    if lc in ITEM_LC:
        return ITEM_LC[lc]
    if lc in ALIASES:
        return ALIASES[lc]
    charged = re.sub(r"\((\w+?)\d\)$", r"(\1)", lc)  # "Amulet of glory (t4)" → "(t)" card
    if charged != lc and charged in ITEM_LC:
        return ITEM_LC[charged]
    c = gs._card_for_drop(name, set(ITEM_LC))
    return ITEM_LC.get(c.lower(), c) if c else None


def card_for_npc(name: str) -> str | None:
    """Source page → NPC card: exact / case-insensitive, card versions, then strip ' (place)'."""
    for n in (name, _PAREN.sub("", name)):
        lc = n.lower()
        if lc in NPC_LC:
            return NPC_LC[lc]
        v = VERSION_LC.get(lc)
        if v and v.lower() in NPC_LC:
            return NPC_LC[v.lower()]
    return None


def card_for_source(name: str, kind: str) -> str | None:
    if name in SOURCE_CARDS:
        return SOURCE_CARDS[name]
    if kind in ("monster", "pickpocket"):
        return card_for_npc(name)
    if kind == "impling":  # caught impling → NPC card; looted jar → jar card (else the impling)
        if name.lower().endswith(" jar"):
            return card_for_item(name) or card_for_npc(name[:-4])
        return card_for_npc(name)
    if kind in ("other", "skilling"):  # e.g. Mystery box, Casket (Reward pool), Small salvage
        return card_for_item(name) or card_for_item(_PAREN.sub("", name)) or card_for_npc(name)
    return None  # chests, caskets: nothing to own


# ── Wiki data ──────────────────────────────────────────────────────────────────────────────

def _bucket_rows(where: str, cache: dict, refresh: bool) -> list[dict]:
    if where in cache and not refresh:
        return cache[where]
    out, off = [], 0
    while True:
        q = (f"bucket('dropsline').select('page_name','item_name','drop_json')"
             f".where({where}).limit(500).offset({off}).run()")
        url = "https://oldschool.runescape.wiki/api.php?action=bucket&format=json&query=" + urllib.parse.quote(q)
        b = wiki_api.get_json(url)["bucket"]
        out += b
        if len(b) < 500:
            break
        off += 500
    for r in out:
        r["drop"] = json.loads(r.pop("drop_json"))
    cache[where] = out
    return out


def _frac(s: str | None) -> float | None:
    """'11/8,856' → rate; 'Always' → 1; anything else (Rare, Varies, Once) → None."""
    if not s:
        return None
    s = s.replace(",", "").strip()
    if s.lower() == "always":
        return 1.0
    m = re.fullmatch(r"([\d.]+)\s*/\s*([\d.]+)", s)
    if not m or float(m.group(2)) == 0:
        return None
    return float(m.group(1)) / float(m.group(2))


def _fmt_one_in(rate: float) -> str:
    n = 1 / rate
    return f"1/{n:,.0f}" if n >= 10 else f"1/{n:.2f}".rstrip("0").rstrip(".")


def _min_level(s: str) -> int | None:
    nums = [int(x) for x in re.findall(r"\d+", s or "")]
    return min(nums) if nums else None


# ── Clue scroll drop sources ───────────────────────────────────────────────────────────────

_CHESTISH = re.compile(r"chest|coffin|casket|sarcophag|reward pool|pouch|gambles|offerings|^gold key", re.I)
# Sources whose wiki page isn't the card's name (boss pages named after the encounter).
SOURCE_CARDS = {"Grotesque Guardians": "Dusk", "Casket (Reward pool)": "Casket"}


def _kind(drop_type: str, name: str, tier: str) -> str:
    if re.fullmatch(r"Reward casket \(\w+\)", name):
        return "casket"
    if "impling" in name.lower():
        return "impling"
    if drop_type == "sailing":
        return "skilling"  # salvage (card-gated by the salvage item) / clue turtles
    if name in SOURCE_CARDS and not card_for_npc(SOURCE_CARDS[name]):
        return "other"  # an item card you open (Casket)
    if name.lower() in ITEM_LC:
        return "other"  # an item you open / hand in: Mystery box, Intricate pouch
    if _CHESTISH.search(name) and not card_for_npc(name):
        return "chest"
    if name == "Agility dispenser":
        return "other"
    if drop_type == "combat":
        return "monster"
    if drop_type == "hunter":
        return "impling"
    if drop_type == "thieving":
        return "chest" if _CHESTISH.search(name) else "pickpocket"
    if drop_type == "reward" and _CHESTISH.search(name):
        return "chest"
    return "other"


def scroll_sources(tier: str, rows: list[dict]) -> list[dict]:
    """Bucket rows for 'Clue scroll (tier)' → one entry per source page (versions merged)."""
    by_page: dict[str, dict] = {}
    for r in rows:
        d = r["drop"]
        frm = d.get("Dropped from") or r["page_name"]
        page, _, version = frm.partition("#")
        kind = _kind(d.get("Drop type", ""), page, tier)
        rate = _frac(d.get("Rarity"))
        e = by_page.get(page)
        if e is None:
            e = by_page[page] = {"source": page, "level": _min_level(d.get("Drop level")),
                                 "rarity": d.get("Rarity") or None, "kind": kind, "card": None,
                                 "_rate": rate}
            if kind == "skilling":
                e["skill"] = "Sailing"
        else:  # another version of the same page: keep the best rate, lowest level
            lv = _min_level(d.get("Drop level"))
            if lv is not None and (e["level"] is None or lv < e["level"]):
                e["level"] = lv
            if rate is not None and (e["_rate"] is None or rate > e["_rate"]):
                e["rarity"], e["_rate"] = d.get("Rarity"), rate
        if d.get("Alt Rarity") and _frac(d["Alt Rarity"]) and not e.get("altRarity"):
            e["altRarity"] = d["Alt Rarity"]
        if version:
            e.setdefault("versions", []).append(version)
    out = []
    for e in by_page.values():
        e.pop("_rate")
        e["card"] = card_for_source(e["source"], e["kind"])
        out.append(e)
    return out


# ── Skilling sources (clue geodes / nests / bottles) ───────────────────────────────────────

# Woodcutting level per tree row of the Clue nest base-chance table (wiki tree pages).
TREE_LEVELS = {
    "Achey tree": 1, "Tree": 1, "Oak tree": 15, "Willow tree": 30, "Teak tree": 35,
    "Jatoba tree": 40, "Juniper tree": 42, "Maple tree": 45, "Hollow tree": 45,
    "Mahogany tree": 50, "Arctic pine tree": 54, "Yew tree": 60, "Sulliuscep": 65,
    "Camphor tree": 66, "Magic tree": 75, "Ironwood tree": 80, "Redwood tree": 90,
    "Rosewood tree": 92,
}
# Fishing level + tool per fish row of the Clue bottle base-chance table (link target → …).
FISH = {
    "Raw shrimps": (1, "Small fishing net"), "Raw anchovies": (15, "Small fishing net"),
    "Raw karambwanji": (5, "Small fishing net"), "Raw sardine": (5, "Fishing rod"),
    "Raw herring": (10, "Fishing rod"), "Raw mackerel": (16, "Big fishing net"),
    "Raw cod": (23, "Big fishing net"), "Raw bass": (46, "Big fishing net"),
    "Raw trout": (20, "Fly fishing rod"), "Raw salmon": (30, "Fly fishing rod"),
    "Raw pike": (25, "Fishing rod"), "Raw rainbow fish": (38, "Fly fishing rod"),
    "Raw tuna": (35, "Harpoon"), "Raw swordfish": (50, "Harpoon"), "Raw lobster": (40, "Lobster pot"),
    "Aerial fishing": (43, "Cormorant's glove"), "Raw cave eel": (38, "Fishing rod"),
    "Raw monkfish": (62, "Small fishing net"), "Raw karambwan": (65, "Karambwan vessel"),
    "Leaping trout": (48, "Barbarian rod"), "Leaping salmon": (58, "Barbarian rod"),
    "Leaping sturgeon": (70, "Barbarian rod"), "Raw shark": (76, "Harpoon"),
    "Infernal eel": (80, "Oily fishing rod"), "Raw anglerfish": (82, "Fishing rod"),
    "Minnow": (82, "Small fishing net"), "Raw dark crab": (85, "Lobster pot"),
    "Sacred eel": (87, "Fishing rod"), "Raw guppy": (7, "Small fishing net"),
    "Raw cavefish": (20, "Small fishing net"), "Raw tetra": (33, "Small fishing net"),
    "Raw catfish": (46, "Big fishing net"),
    "Fishing spot (The Stranglewood)": (1, None), "Fishing spot (Civitas illa Fortis)": (1, None),
    "Raw swordtip squid": (52, "Harpoon"), "Raw jumbo squid": (69, "Harpoon"),
    # Sailing deep-sea trawling (fishing rod, or a trawling net built on the boat)
    "Raw giant krill": (69, "Fishing rod"), "Raw haddock": (73, "Fishing rod"),
    "Raw yellowfin": (79, "Fishing rod"), "Raw halibut": (83, "Fishing rod"),
    "Raw bluefin": (87, "Fishing rod"), "Raw marlin": (91, "Fishing rod"),
}
SKILLING = [  # (page, item prefix, skill, generic tool, base multiplier in the formula)
    ("Clue geode", "Clue geode", "Mining", "Pickaxe", 0.7),
    ("Clue nest", "Clue nest", "Woodcutting", "Axe", 1.0),
    ("Clue bottle", "Clue bottle", "Fishing", None, 1.0),
]


def _wikitable_after(text: str, heading_re: str) -> list[list[str]]:
    m = re.search(heading_re, text)
    if not m:
        return []
    start = text.find("{|", m.end())
    end = text.find("|}", start)
    rows = []
    for chunk in text[start:end].split("\n|-")[1:]:
        cells = [c.strip() for c in re.split(r"\n\|", "\n" + chunk.strip()) if c.strip()]
        cells = [c for c in cells if not c.startswith("!")]
        if cells:
            rows.append(cells)
    return rows


def _link_target(cell: str) -> str:
    m = re.search(r"\[\[([^\]|#]+)", cell) or re.search(r"\{\{plinkt?\|([^|}]+)", cell)
    return (m.group(1) if m else cell).replace("_", " ").strip()


def _num(cell: str) -> float | None:
    m = re.match(r"\s*([\d,.]+)", re.sub(r"\{\{.*", "", cell, flags=re.S))
    return float(m.group(1).replace(",", "")) if m else None


def skilling_tables(page: str, refresh: bool) -> tuple[dict[str, float], dict[str, float]]:
    """(base chance by node link target, clue-tier modifier by tier) from the page's wikitext."""
    text = _fetch_wikitext(page, refresh)
    base = {}
    for cells in _wikitable_after(text, r"=+\s*Base chance\s*=+"):
        if len(cells) >= 2 and _num(cells[1]):
            base[_link_target(cells[0])] = _num(cells[1])
    mods = {}
    for cells in _wikitable_after(text, r"=+\s*Clue tier\s*=+"):
        t = re.search(r"Clue scroll \((\w+)\)", cells[0])
        if t and len(cells) >= 2 and _num(cells[1]):
            mods[t.group(1).lower()] = _num(cells[1])
    return base, mods


def _rate(base: float, mult: float, level: int, mod: float) -> float:
    """1 / floor(floor(floor(base*mult) * CA(=1)) / (100+level) * tierMod)."""
    return 1 / max(1, math.floor(math.floor(base * mult) / (100 + level) * mod))


def skilling_sources(cache: dict, refresh: bool) -> tuple[dict[str, list[dict]], list[str]]:
    out: dict[str, list[dict]] = defaultdict(list)
    warn: list[str] = []
    for page, prefix, skill, tool, mult in SKILLING:
        base, mods = skilling_tables(page, refresh)
        if set(mods) != set(SKILL_TIERS):
            warn.append(f"{page}: clue-tier modifiers parsed {mods}")
        for tier in SKILL_TIERS:
            item = f"{prefix} ({tier})"
            rows = _bucket_rows(f"'item_name','{item}'", cache, refresh)
            nodes: list[dict] = []
            if skill == "Mining":  # bucket rows carry rock + level + rate; base table adds the 99 rate
                for r in rows:
                    d = r["drop"]
                    if d.get("Drop type") != "mining":
                        continue
                    name = d["Dropped from"].split("#")[0]
                    lvl = _min_level(d.get("Drop level")) or (10 if name == "Crashed Star" else 1)
                    b = base.get(name) or base.get(re.sub(r"\s*\(rock\)$", "", name))
                    n = {"name": name, "level": lvl, "tool": "Pickaxe",
                         "rarity": _fmt_one_in(_rate(b, mult, lvl, mods[tier])) if b else d.get("Rarity")}
                    if b:
                        n["rarity99"] = _fmt_one_in(_rate(b, mult, 99, mods[tier]))
                    nodes.append(n)
                if "Blast mine" in base:
                    nodes.append({"name": "Blast mine", "level": 43, "tool": None,
                                  "rarity": _fmt_one_in(_rate(base["Blast mine"], mult, 43, mods[tier])),
                                  "rarity99": _fmt_one_in(_rate(base["Blast mine"], mult, 99, mods[tier]))})
            else:
                levels = TREE_LEVELS if skill == "Woodcutting" else {k: v[0] for k, v in FISH.items()}
                for name, b in base.items():
                    if name not in levels:
                        if tier == SKILL_TIERS[0]:
                            warn.append(f"{page}: no {skill} level/tool for base-chance row '{name}' (skipped)")
                        continue
                    lvl = levels[name]
                    ntool = tool if skill == "Woodcutting" else FISH[name][1]
                    nodes.append({"name": name, "level": lvl, "tool": ntool,
                                  "rarity": _fmt_one_in(_rate(b, mult, lvl, mods[tier])),
                                  "rarity99": _fmt_one_in(_rate(b, mult, 99, mods[tier]))})
            # one source entry per tool, so the page can gate it on owning that tool
            by_tool: dict = defaultdict(list)
            for n in nodes:
                by_tool[n["tool"]].append(n)
            for t, ns in by_tool.items():
                if t is None:  # blast mining (dynamite) / fishing spots whose tool isn't known
                    if tier == SKILL_TIERS[0]:
                        warn.append(f"{page}: no tool for {[n['name'] for n in ns]} (left out)")
                    continue
                ns.sort(key=lambda n: (n["level"], -(_frac(n["rarity"]) or 0)))
                low = ns[0]
                best99 = max(ns, key=lambda n: _frac(n.get("rarity99") or n["rarity"]) or 0)
                e = {"source": item, "level": low["level"], "rarity": low["rarity"], "kind": "skilling",
                     "card": None, "skill": skill, "tool": t,
                     "rarity99": best99.get("rarity99") or best99["rarity"],
                     "nodes": [{k: v for k, v in n.items() if k != "tool"} for n in ns],
                     "note": (f"Any {skill} action rolls for a clue; rarity = {low['name']} at level "
                              f"{low['level']}, rarity99 = best node ({best99['name']}) at 99 {skill}")}
                out[tier].append(e)
            # non-skilling ways to get the vessel (e.g. Vale offerings reward)
            for r in rows:
                d = r["drop"]
                if d.get("Drop type") == "reward":
                    name = d["Dropped from"].split("#")[0]
                    out[tier].append({"source": name, "level": None, "rarity": d.get("Rarity"),
                                      "kind": "other", "card": card_for_source(name, "other"),
                                      "note": f"gives a {item}"})
        if skill == "Woodcutting":  # bird houses (Hunter) also give clue nests; rates unconfirmed
            for tier in SKILL_TIERS:
                out[tier].append({"source": "Bird house trapping", "level": 5, "rarity": None,
                                  "kind": "skilling", "card": None, "skill": "Hunter", "tool": "Bird house",
                                  "quests": ["Bone Voyage"],
                                  "note": f"gives a Clue nest ({tier}); wiki rates are unconfirmed estimates"})
    return out, warn


# ── Reward caskets ─────────────────────────────────────────────────────────────────────────

def casket_rewards(tier: str, rows: list[dict], html: str | None) -> dict[str, list[tuple[str, str]]]:
    """item → [(rarity, table)] — Standard table preferred; Entrana-only items kept.

    The bucket lacks the Mimic reward table (elite/master: Ring of 3rd age, Raw manta ray, …),
    so items on the rendered page that the bucket doesn't have are added from the HTML tables.
    """
    by_item: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        d = r["drop"]
        table = (d.get("Dropped from") or "").partition("#")[2] or "Standard"
        by_item[d["Dropped item"]].append((d.get("Rarity") or "", table))
    have = {k.lower() for k in by_item}
    for r in (loot_parser.parse_drops(html) if html else []):
        if r["item"].lower() not in have and r["fraction"]:
            by_item[r["item"]].append((r["fraction"], r["section"] or "html"))
    out = {}
    for item, lst in by_item.items():
        std = [x for x in lst if x[1] != "Entrana"]
        out[item] = std or lst
    return out


def _sum_rarities(rs: list[str]) -> str:
    if len(rs) == 1:
        return rs[0]
    dens = {re.sub(r"^[\d.]+/", "", r) for r in rs}
    nums = [re.match(r"^([\d.]+)/", r) for r in rs]
    if len(dens) == 1 and all(nums):
        total = sum(float(m.group(1)) for m in nums)
        return f"{total:g}/{dens.pop()}"
    rates = [_frac(r) for r in rs]
    if all(rates):
        return _fmt_one_in(min(1.0, sum(rates)))
    return max(rs, key=lambda r: _frac(r) or 0)


# ── Main ───────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch wiki data instead of using the cache")
    args = ap.parse_args()

    cache = json.loads(_BUCKET_CACHE.read_text(encoding="utf-8")) if _BUCKET_CACHE.exists() else {}

    # Clue scroll sources
    scroll: dict[str, list[dict]] = {}
    for tier in TIERS:
        scroll[tier] = scroll_sources(tier, _bucket_rows(f"'item_name','Clue scroll ({tier})'", cache, args.refresh))
    skill_src, warnings = skilling_sources(cache, args.refresh)
    for tier in SKILL_TIERS:
        scroll[tier] += skill_src[tier]
    scroll["master"].append({
        "source": "Watson", "level": None, "rarity": "Always", "kind": "npc-exchange", "card": "Watson",
        "needs": ["easy", "medium", "hard", "elite"],
        "note": "Hand Watson one Easy, Medium, Hard and Elite clue scroll for a Master clue"})
    kind_order = ["monster", "pickpocket", "impling", "chest", "skilling", "casket", "npc-exchange", "other"]
    for tier in TIERS:
        scroll[tier].sort(key=lambda e: (kind_order.index(e["kind"]), -(_frac(e["rarity"]) or 0), e["source"]))

    # Rewards
    clue_sources: dict[str, list[str]] = defaultdict(list)
    rarities: dict[str, dict[str, str]] = {}
    reward_unresolved: dict[str, list[str]] = {}
    merged: dict[str, list[str]] = {}
    for tier in TIERS:
        rows = _bucket_rows(f"'page_name','Reward casket ({tier})'", cache, args.refresh)
        html = wiki_fetcher.fetch(f"Reward casket ({tier})", force_refresh=args.refresh)
        rewards = casket_rewards(tier, rows, html)
        per_key: dict[str, list[str]] = defaultdict(list)
        raw_of: dict[str, list[str]] = defaultdict(list)
        unresolved = []
        for item, lst in rewards.items():
            card = card_for_item(item)
            key = card or item
            per_key[key] += [r for r, _ in lst if r]
            raw_of[key].append(item)
            if card:
                if tier not in clue_sources[card]:
                    clue_sources[card].append(tier)
            else:
                unresolved.append(item)
        rarities[tier] = {k: _sum_rarities(v) for k, v in sorted(per_key.items()) if v}
        reward_unresolved[tier] = sorted(unresolved)
        merged[tier] = [f"{k} ← {', '.join(v)}" for k, v in raw_of.items() if v != [k]]

    clue_sources = {k: sorted(v, key=TIERS.index) for k, v in sorted(clue_sources.items())}

    _BUCKET_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _BUCKET_CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    for path, data in ((OUT_SCROLL, scroll), (OUT_SOURCES, clue_sources), (OUT_RARITIES, rarities)):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Summary
    print("Clue scroll sources:")
    unresolved_src = Counter()
    for tier in TIERS:
        kinds = Counter(e["kind"] for e in scroll[tier])
        gated = [e for e in scroll[tier] if e["kind"] in ("monster", "pickpocket", "impling")]
        res = sum(1 for e in gated if e["card"])
        print(f"  {tier:9s} {len(scroll[tier]):4d} sources  {dict(kinds)}  "
              f"monster/pickpocket/impling → card: {res}/{len(gated)}")
        for e in gated:
            if not e["card"]:
                unresolved_src[e["source"]] += 1
    print(f"  unresolved NPC/impling sources ({len(unresolved_src)}): {sorted(unresolved_src)}")
    print("\nRewards:")
    for tier in TIERS:
        n_card = sum(1 for k in rarities[tier] if k in clue_sources and tier in clue_sources[k])
        print(f"  {tier:9s} {len(rarities[tier]):4d} rarity keys, {n_card} cards, "
              f"{len(merged[tier])} renamed/merged, {len(reward_unresolved[tier])} not cards")
    print(f"  clue_sources.json: {len(clue_sources)} reward cards")
    for tier in TIERS:
        print(f"  [{tier}] not cards: {reward_unresolved[tier]}")
        print(f"  [{tier}] renamed: {merged[tier]}")
    for w in warnings:
        print("  [warn]", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
