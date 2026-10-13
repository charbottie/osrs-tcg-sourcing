"""Generate shop_owners.json — which NPC card (if any) you need to trade with each shop.

Bronzeman TCG locks NPC interaction by the NPC's in-game name: buying from a shopkeeper needs that
shopkeeper's card when one exists (a "Shop keeper" / "Shop assistant" has no card, so general stores
stay open). item_sources.json / ingredient_info.json list shops by their wiki shop name ("Vanessa's Farming shop.",
"Wyson the gardener"), so this maps each one to its owner.

Source: the wiki's infobox_shop Bucket (page_name, owner) via wiki_api.get_json (action=bucket, never
action=parse), cached in cache/wiki_shop_owners.json. The owner's in-game name is the link text, or
the linked page without its "(disambiguation)" ("Dwarf (Dwarven shopping store)" -> Dwarf). A shop
with several owners ("Slayer Equipment": every Slayer master) needs any one of them.
Seller names are matched as written, then without a "(variant)" suffix ("...Store.(Karamja gloves)")
and with/without the trailing full stop. A seller that is itself an NPC card name ("Sir Renitee")
is its own owner. Production "facilities" that name a shop are mapped the same way.

Where the shop is: the Infobox Shop |location= links, each mapped to the area access it needs the
same way generate_monster_locations.py does (wiki leagueRegion -> REGION_ACCESS, plus the
slayer_curated.json / monster_locations_overrides.json per-place access fixes). Extra per-place gates
(quests to enter Lletya…) are monster_locations.json "_gates", applied by the planner.

Output: scripts/output/shop_owners.json
  { "<seller>": {"shop": "<wiki shop page>" | null, "owners": [in-game names], "cards": [NPC cards],
                 "locations": {"<place>": "<access key>" | null}} }
  (sellers with no match are left out = unknown, unrestricted)

Usage:
  python3 scripts/generate_shop_owners.py --card-json research/card-catalog-live.json
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from pathlib import Path

import wiki_api
from catalog_names import npc_names

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "cache" / "wiki_shop_owners.json"
_OUT = _HERE / "output" / "shop_owners.json"


def fetch() -> list[dict]:
    if _CACHE.exists():
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    out, off = [], 0
    while True:
        q = f"bucket('infobox_shop').select('page_name','owner','location').limit(500).offset({off}).run()"
        b = wiki_api.get_json("https://oldschool.runescape.wiki/api.php?action=bucket&format=json&query="
                              + urllib.parse.quote(q))["bucket"]
        out += b
        off += 500
        if len(b) < 500:
            break
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


def owner_names(owner: str) -> list[str]:
    """In-game names in an Infobox Shop |owner= value."""
    names = []
    for tgt, txt in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", owner or ""):
        n = (txt or re.sub(r"\s*\([^)]*\)$", "", tgt)).strip()
        if n:
            names.append(n)
    if not names:
        plain = re.sub(r"<[^>]+>|\{\{[^}]*\}\}", "", owner or "").strip()
        names += [x.strip() for x in re.split(r",|<br\s*/?>| and ", plain) if x.strip()]
    return names


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    npc = npc_names(cat)   # card names, wiki pages and version names -> NPC card
    shops: dict[str, list[str]] = {}
    places: dict[str, list[str]] = {}
    for row in fetch():
        shops.setdefault(row["page_name"], []).extend(owner_names(row.get("owner") or ""))
        for loc in re.findall(r"\[\[([^\]|#]+)", row.get("location") or ""):
            places.setdefault(row["page_name"], []).append(loc.strip())
    from generate_slayer import REGION_ACCESS, location_regions
    regions = location_regions(sorted({l for ls in places.values() for l in ls}))
    hand = json.loads((_HERE / "monster_locations_overrides.json").read_text(encoding="utf-8"))
    loc_access = {**json.loads((_HERE / "slayer_curated.json").read_text(encoding="utf-8")).get("locationAccess", {}),
                  **{k: v["access"] for k, v in hand.get("_locationAccess", {}).items()}}

    def access_of(loc):
        if loc in loc_access:
            return loc_access[loc]
        rs = [r for r in regions.get(loc, "").split("&") if r]
        keys = [REGION_ACCESS.get(r) for r in rs]
        return None if not rs or None in keys else keys[0]
    shops_lc = {k.lower(): k for k in shops}

    src = json.loads((_HERE / "output" / "item_sources.json").read_text(encoding="utf-8"))
    sellers = {s["seller"] for v in src.values() for s in (v.get("shops") or []) if s.get("seller")}
    ing = json.loads((_HERE / "ingredient_info.json").read_text(encoding="utf-8"))
    sellers |= {s["seller"] for v in ing.values() for s in (v.get("shops") or []) if s.get("seller")}
    sellers |= {v["production"]["facilities"] for v in list(src.values()) + list(ing.values())
                if v.get("production") and v["production"].get("facilities")}

    def shop_page(s: str) -> str | None:
        base = re.sub(r"\((?=[^)]*\)$)[^)]*\)$", "", s).strip()   # "...Store.(Karamja gloves)"
        for c in (s, base, s.rstrip("."), base.rstrip("."), s + ".", base + "."):
            if c.lower() in shops_lc:
                return shops_lc[c.lower()]
        return None

    out = {}
    for s in sorted(sellers):
        page = shop_page(s)
        if page:
            owners = list(dict.fromkeys(shops[page]))
        elif s.lower() in npc:
            owners = [npc[s.lower()]]
        else:
            continue
        cards = sorted({npc[o.lower()] for o in owners if o.lower() in npc})
        out[s] = {"shop": page, "owners": owners, "cards": cards,
                  "locations": {l: access_of(l) for l in dict.fromkeys(places.get(page, []))} if page else {}}
    _OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    n_card = sum(1 for v in out.values() if v["cards"])
    print(f"Wrote {_OUT}: {len(out)}/{len(sellers)} sellers/facilities matched, {n_card} need an NPC card")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
