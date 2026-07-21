#!/usr/bin/env python3
"""Generate sourcing data for the OSRS TCG sourcing panel.

Reads Card.json, fetches OSRS Wiki pages for each monster/quest card,
and writes three static JSON files for the plugin:

  monster_drops.json  — monster card -> TCG card drops with rarity
  item_sources.json   — item card -> monster/quest sources
  quest_chains.json   — quest -> prerequisites + involved cards

These files are generated at dev-time and bundled into the plugin JAR.
The shipped plugin makes ZERO wiki requests at runtime.

Usage:
  python scripts/generate_sources.py --card-json research/card-catalog.json
  python scripts/generate_sources.py --card-json research/card-catalog.json --limit 20
  python scripts/generate_sources.py --card-json research/card-catalog.json --monster "Abyssal demon"

Wiki access rules (non-negotiable, per wiki staff github issue #1 2026-07-18):
  - Plain page URLs only — never api.php?action=parse
  - ~1 req/sec for uncached fetches (wiki_fetcher enforces this)
  - Descriptive User-Agent (set in wiki_fetcher)
  - Cache every raw fetch in scripts/cache/wiki_html/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Ensure scripts/ is on the path so sibling modules import cleanly
sys.path.insert(0, str(Path(__file__).parent))

import item_scraper
import loot_parser
import quest_parser
import wiki_fetcher

_OUT_DIR = Path(__file__).parent / "output"
_OUT_DIR.mkdir(parents=True, exist_ok=True)
_CLUE_SOURCES = Path(__file__).parent / "clue_sources.json"
_GATHERING_JSON = Path(__file__).parent / "gathering_sources.json"

# Wiki-style bracket suffix: "Monkey (monster)" -> "Monkey"
_SUFFIX_RE = re.compile(r"^(.*?) \([^)]*\)$")


# ---------------------------------------------------------------------------
# Card.json helpers
# ---------------------------------------------------------------------------

def load_cards(card_json_path: str) -> list[dict]:
    with open(card_json_path, encoding="utf-8") as f:
        return json.load(f)


def monster_cards(cards: list[dict]) -> list[dict]:
    return [c for c in cards if "Monster" in c.get("category", [])]


def item_cards(cards: list[dict]) -> list[dict]:
    return [c for c in cards if "Resource" in c.get("category", [])]


def quest_item_cards(cards: list[dict]) -> list[dict]:
    return [c for c in item_cards(cards) if c.get("questItem")]


def card_name_set(cards: list[dict]) -> set[str]:
    """Return card names as a set, lowercased for matching."""
    return {c["name"].lower() for c in cards}


def wiki_page_name(card_name: str) -> str:
    """Convert a card name to the most likely wiki page name.

    Strips disambiguation suffixes: "Monkey (monster)" -> "Monkey"
    Keeps subpage separators intact for cases like "Chambers of Xeric/Loot".
    """
    m = _SUFFIX_RE.match(card_name)
    return (m.group(1) if m else card_name).replace(" ", "_")


# ---------------------------------------------------------------------------
# Step 1: Monster drops
# ---------------------------------------------------------------------------

def build_monster_drops(
    monsters: list[dict],
    item_names_lc: set[str],
    limit: int | None = None,
    only: str | None = None,
) -> dict[str, dict]:
    """Fetch loot tables for monster cards; filter to TCG item cards only."""
    result: dict[str, dict] = {}
    subset = monsters if only is None else [m for m in monsters if m["name"] == only]
    if limit:
        subset = subset[:limit]

    total = len(subset)
    for i, card in enumerate(subset, 1):
        name = card["name"]
        page = wiki_page_name(name)
        print(f"  [{i}/{total}] {name} -> /w/{page}")

        html, fetched_from = wiki_fetcher.fetch_with_loot_fallback(page)
        if html is None:
            print(f"    [SKIP] could not fetch page")
            result[name] = _empty_monster_entry(card)
            continue

        raw_drops = loot_parser.parse_drops(html)
        # Filter to only items that have a TCG card; split main vs RDT
        tcg_drops = [
            {
                "card": d["item"],
                "rarity": d["rarity"],
                "fraction": d["fraction"],
                "fromRdt": d["is_rdt"],
            }
            for d in raw_drops
            if d["item"].lower() in item_names_lc and d["rarity"] != "Unknown"
        ]

        monster_info = loot_parser.parse_monster_info(html)
        quests: list[str] = []  # populated later by quest pass

        result[name] = {
            "drops": tcg_drops,
            "slayerLevel": monster_info["slayerLevel"],
            "combatLevel": monster_info["combatLevel"],
            "quests": quests,
            "fetchedFrom": fetched_from if fetched_from != page else None,
        }
        if not tcg_drops:
            print(f"    [0 TCG drops found] ({len(raw_drops)} raw rows parsed)")
        else:
            print(f"    [{len(tcg_drops)} TCG drops] from {len(raw_drops)} raw rows")

    return result


def _empty_monster_entry(card: dict) -> dict:
    return {
        "drops": [],
        "slayerLevel": None,
        "combatLevel": None,
        "quests": [],
        "fetchedFrom": None,
    }


# ---------------------------------------------------------------------------
# Step 2: Item sources (inverted index)
# ---------------------------------------------------------------------------

def load_gathering() -> dict[str, dict]:
    """Load the static gathering_sources.json."""
    if not _GATHERING_JSON.exists():
        return {}
    with open(_GATHERING_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def build_item_sources(
    item_cards_list: list[dict],
    monster_drops: dict[str, dict],
    gathering: dict[str, dict],
) -> dict[str, dict]:
    """Build the item->sources index by inverting the monster_drops map."""
    # Start with empty entries for every item card
    result: dict[str, dict] = {
        c["name"]: {
            "monsters": [],
            "rdtMonsters": [],      # monsters that drop this via the shared Rare Drop Table
            "quests": [],
            "gathering": None,
            "production": None,     # wiki-sourced crafting/cooking/smithing/fletching etc.
            "spawns": [],           # ground spawn locations
            "shopBought": False,
            "shops": [],            # [{seller, price, currency}] from wiki store-locations-list
            "clueTiers": [],        # tiers this item appears in as a clue scroll reward
            "alwaysAvailable": False,
        }
        for c in item_cards_list
    }

    # Invert monster_drops — split main drops vs RDT drops
    for monster_name, data in monster_drops.items():
        for drop in data.get("drops", []):
            item_name = drop["card"]
            if item_name not in result:
                continue
            entry = {
                "card": monster_name,
                "rarity": drop["rarity"],
                "fraction": drop["fraction"],
            }
            if drop.get("fromRdt"):
                result[item_name]["rdtMonsters"].append(entry)
            else:
                result[item_name]["monsters"].append(entry)

    # Add gathering info
    for item_name, info in gathering.items():
        if item_name in result:
            result[item_name]["gathering"] = info

    return result


# ---------------------------------------------------------------------------
# Step 3: Quest chains
# ---------------------------------------------------------------------------

def build_quest_chains(
    quest_items: list[dict],
    item_names_lc: set[str],
    monster_names_lc: set[str],
    limit: int | None = None,
) -> dict[str, dict]:
    """Fetch quest pages and extract prerequisite chains."""
    # Deduplicate: many quest items may share a quest page
    seen_quests: set[str] = set()
    result: dict[str, dict] = {}

    subset = quest_items if not limit else quest_items[:limit]

    for card in subset:
        card_name = card["name"]
        # The card name IS typically the quest name for quest-item cards
        # e.g. card "Dragon Slayer I" corresponds to wiki page Dragon_Slayer_I
        page = wiki_page_name(card_name)

        if page in seen_quests:
            continue
        seen_quests.add(page)

        print(f"  [quest] {card_name} -> /w/{page}")
        html = wiki_fetcher.fetch(page)
        if html is None:
            print(f"    [SKIP]")
            continue

        info = quest_parser.parse_quest(html)
        reward_cards = [r for r in info["reward_items"] if r.lower() in item_names_lc]
        monster_cards_in_quest = [k for k in info["kills"] if k.lower() in monster_names_lc]

        result[card_name] = {
            "prerequisites": info["prerequisites"],
            "rewardCards": reward_cards,
            "monsterCards": monster_cards_in_quest,
            "questNpc": info["start_npc"],
        }

    return result


# ---------------------------------------------------------------------------
# Step 4: Enrich item_sources with quest data
# ---------------------------------------------------------------------------

def enrich_with_quests(
    item_sources: dict[str, dict],
    quest_chains: dict[str, dict],
) -> None:
    """Add quest names to item_sources[item]["quests"] in-place."""
    for quest_name, data in quest_chains.items():
        for reward_card in data.get("rewardCards", []):
            if reward_card in item_sources:
                if quest_name not in item_sources[reward_card]["quests"]:
                    item_sources[reward_card]["quests"].append(quest_name)

    # Also mark always-available items (shop-bought heuristic deferred —
    # Card.json doesn't have a shopBought field today; leave as False)


# ---------------------------------------------------------------------------
# Step 5: Item production + spawns (scraped from item wiki pages)
# ---------------------------------------------------------------------------

def _has_source(entry: dict) -> bool:
    """Return True if an item_sources entry already has any sourcing data."""
    return bool(
        entry.get("shopBought") or entry.get("spawns") or entry.get("gathering")
        or entry.get("monsters") or entry.get("rdtMonsters")
        or entry.get("production") or entry.get("questReward")
        or entry.get("clueTiers") or entry.get("alwaysAvailable")
    )


def build_production_spawns(
    item_cards_list: list[dict],
    item_sources: dict[str, dict],
    monster_names_lc: set[str] | None = None,
    limit: int | None = None,
) -> None:
    """Fetch item wiki pages; add production method, spawn, shop, and drop data in-place."""
    subset = item_cards_list if limit is None else item_cards_list[:limit]
    total = len(subset)
    backfilled = 0

    for i, card in enumerate(subset, 1):
        name = card["name"]
        if name not in item_sources:
            continue
        page = wiki_page_name(name)
        if i % 50 == 1:
            print(f"  [{i}/{total}] {name} -> /w/{page}")

        html = wiki_fetcher.fetch(page)
        if html is None:
            continue

        methods = item_scraper.parse_production(html)
        spawns  = item_scraper.parse_spawns(html)
        shops   = item_scraper.parse_shop_locations(html)

        if methods:
            item_sources[name]["production"] = methods[0]   # primary method only
        if spawns:
            item_sources[name]["spawns"] = spawns
        if shops:
            item_sources[name]["shops"] = shops
            item_sources[name]["shopBought"] = True

        # Backfill: for items that still have no sourcing, parse the wiki's
        # "Item sources" table and match sources against known monster card names.
        if not _has_source(item_sources[name]) and monster_names_lc is not None:
            wiki_srcs = item_scraper.parse_item_sources(html)
            added = 0
            for src in wiki_srcs:
                src_name = src["source"]
                if src_name.lower() not in monster_names_lc:
                    continue
                # Find the canonical card name (preserve original case)
                # monster_names_lc maps lowercase -> but we need the real name;
                # reconstruct from the source string (wiki titles are correctly cased)
                entry = {
                    "card":     src_name,
                    "rarity":   src.get("wiki_label") or "Unknown",
                    "fraction": src.get("fraction") or "",
                }
                item_sources[name]["monsters"].append(entry)
                added += 1
            if added:
                backfilled += 1

    if backfilled:
        print(f"  Backfilled item sources for {backfilled} items via wiki 'Item sources' table")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_json(path: Path, data: dict, label: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {path} ({len(data)} entries) — {label}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True,
                   help="Path to Card.json (e.g. research/card-catalog.json)")
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N monsters (for testing)")
    p.add_argument("--monster", type=str, default=None,
                   help="Process only this one monster card name (for testing)")
    p.add_argument("--skip-quests", action="store_true",
                   help="Skip the quest parsing pass")
    p.add_argument("--skip-items", action="store_true",
                   help="Skip the item production/spawns pass")
    p.add_argument("--out-dir", type=str, default=str(_OUT_DIR),
                   help="Output directory (default: scripts/output/)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.card_json}...")
    cards = load_cards(args.card_json)
    monsters = monster_cards(cards)
    items = item_cards(cards)
    quest_items = quest_item_cards(cards)

    print(f"  {len(monsters)} monster cards, {len(items)} item cards, "
          f"{len(quest_items)} quest-item cards")

    item_names_lc = card_name_set(items)
    monster_names_lc = card_name_set(monsters)

    # --- Pass 1: Monster drops ---
    print(f"\nPass 1: Monster loot tables ({args.limit or 'all'} monsters)...")
    monster_drops = build_monster_drops(
        monsters, item_names_lc,
        limit=args.limit,
        only=args.monster,
    )

    # Clean fetchedFrom=None entries before writing
    for v in monster_drops.values():
        if v.get("fetchedFrom") is None:
            v.pop("fetchedFrom", None)

    write_json(out_dir / "monster_drops.json", monster_drops, "monster drops")

    # --- Pass 2: Item sources ---
    print("\nPass 2: Building item sources index...")
    gathering = load_gathering()
    print(f"  {len(gathering)} gathering entries loaded")
    item_sources = build_item_sources(items, monster_drops, gathering)
    write_json(out_dir / "item_sources.json", item_sources, "item sources")

    # --- Pass 3: Quest chains ---
    if not args.skip_quests:
        print(f"\nPass 3: Quest chains ({len(quest_items)} quest-item cards)...")
        quest_chains = build_quest_chains(
            quest_items, item_names_lc, monster_names_lc,
            limit=args.limit,
        )
        enrich_with_quests(item_sources, quest_chains)
        write_json(out_dir / "quest_chains.json", quest_chains, "quest chains")
        # Re-write item_sources with quest enrichment
        write_json(out_dir / "item_sources.json", item_sources, "item sources (enriched)")
    else:
        quest_chains = {}
        write_json(out_dir / "quest_chains.json", quest_chains, "quest chains (skipped)")

    # --- Pass 4: Item production + spawns ---
    if not args.skip_items:
        print(f"\nPass 4: Item production & spawns ({len(items)} item cards)...")
        build_production_spawns(items, item_sources,
                               monster_names_lc=monster_names_lc,
                               limit=args.limit)
        write_json(out_dir / "item_sources.json", item_sources,
                   "item sources (with production + spawns)")
    else:
        print("\nPass 4: Skipped (--skip-items)")

    # --- Pass 5: Clue tiers ---
    if _CLUE_SOURCES.exists():
        print("\nPass 5: Clue tiers from clue_sources.json...")
        with open(_CLUE_SOURCES, encoding="utf-8") as f:
            clue_sources = json.load(f)
        patched = 0
        for item_name, tiers in clue_sources.items():
            if item_name in item_sources:
                item_sources[item_name]["clueTiers"] = tiers
                patched += 1
        print(f"  Patched clueTiers for {patched} items")
        write_json(out_dir / "item_sources.json", item_sources,
                   "item sources (with clue tiers)")
    else:
        print("\nPass 5: Skipped (clue_sources.json not found)")

    # --- Summary ---
    total_drops = sum(len(v["drops"]) for v in monster_drops.values())
    covered = sum(1 for v in monster_drops.values() if v["drops"])
    with_prod  = sum(1 for v in item_sources.values() if v.get("production"))
    with_spawn = sum(1 for v in item_sources.values() if v.get("spawns"))
    with_shops = sum(1 for v in item_sources.values() if v.get("shops"))
    with_clue  = sum(1 for v in item_sources.values() if v.get("clueTiers"))
    print(f"\nDone.")
    print(f"  Monsters with TCG drops: {covered}/{len(monster_drops)}")
    print(f"  Total drop entries: {total_drops}")
    print(f"  Quest chains: {len(quest_chains)}")
    print(f"  Items with production method: {with_prod}")
    print(f"  Items with ground spawns: {with_spawn}")
    print(f"  Items sold in shops: {with_shops}")
    print(f"  Items as clue rewards: {with_clue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
