#!/usr/bin/env python3
"""Generate ingredient_info.json — production/shop/spawn data for non-card
ingredients referenced in item production recipes.

These items appear as ingredients in TCG card crafting recipes but are not
themselves TCG cards (e.g. unfinished potions, (u) bows, bolt tips, sacred
oil, etc.). This file lets the preview UI show the full unlock chain.

Usage:
  python scripts/generate_ingredient_info.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import item_scraper
import wiki_fetcher

_OUT = Path(__file__).parent / "ingredient_info.json"
_SOURCES = Path(__file__).parent / "output" / "item_sources.json"


def main() -> int:
    with open(_SOURCES, encoding="utf-8") as f:
        sources = json.load(f)

    card_names_lc = {k.lower() for k in sources.keys()}

    # Collect all unique non-card ingredients across all production recipes
    non_card: set[str] = set()
    for data in sources.values():
        prod = data.get("production")
        if not prod:
            continue
        for ing in prod.get("ingredients", []):
            if ing["item"].lower() not in card_names_lc:
                non_card.add(ing["item"])

    items = sorted(non_card)
    total = len(items)
    print(f"Found {total} non-card ingredients to scrape\n")

    result: dict[str, dict] = {}

    for i, name in enumerate(items, 1):
        page = name.replace(" ", "_")
        print(f"  [{i}/{total}] {name}")

        html = wiki_fetcher.fetch(page)
        if html is None:
            print(f"    [SKIP] could not fetch")
            result[name] = {}
            continue

        methods  = item_scraper.parse_production(html)
        spawns   = item_scraper.parse_spawns(html)
        shops    = item_scraper.parse_shop_locations(html)
        sources  = item_scraper.parse_item_sources(html)

        entry: dict = {}
        if methods:
            entry["production"] = methods[0]
        if spawns:
            entry["spawns"] = spawns
        if shops:
            entry["shops"] = shops
            entry["shopBought"] = True
        if sources:
            entry["itemSources"] = sources

        result[name] = entry

    with open(_OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with_prod    = sum(1 for v in result.values() if v.get("production"))
    with_shop    = sum(1 for v in result.values() if v.get("shops"))
    with_spawn   = sum(1 for v in result.values() if v.get("spawns"))
    with_sources = sum(1 for v in result.values() if v.get("itemSources"))
    empty        = sum(1 for v in result.values() if not v)

    print(f"\nWrote {_OUT} ({len(result)} entries)")
    print(f"  With production method: {with_prod}")
    print(f"  Shop-bought:            {with_shop}")
    print(f"  Ground spawns:          {with_spawn}")
    print(f"  With item sources:      {with_sources}")
    print(f"  No data found:          {empty}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
