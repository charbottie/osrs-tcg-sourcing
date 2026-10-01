#!/usr/bin/env python3
"""
Apply tag priority ordering rules to card_categories.json.

Rules (in application order):
  - Specific overrides: Fishing bait, Rope, Clay, Soda ash, Bucket of sand, Tinderbox
  - Ores: Smithing first, remove Magic; Coal also remove Construction
  - Logs: Firemaking>Fletching>Construction>Woodcutting>Sailing; remove Prayer/Smithing/Magic/Crafting
  - Seeds: Farming first (excluding special seeds)
  - Clean herbs (Farming+Herblore): Herblore first
  - Potions (Herblore+Potion tag): Herblore first
  - Bones: Prayer first
  - Planks: Construction first
  - Nails: Construction first
  - Metal bars: Gold/Silver → Crafting first; Lead/Cupronickel → Sailing first; others → Smithing first
  - Raw food (Raw* with Cooking tag): Cooking first
  - Pickaxes: Mining>Tool; Melee/Weapon last; Clue items keep Clue first
  - Axes (woodcutting): remove Smithing; Woodcutting>Tool; Melee/Weapon last; Clue items keep Clue first
  - Bows/Crossbows: remove Construction; Ranged>Fletching; Weapon last; Clue items keep Clue first
  - Boss trophies (head/trophy items with combat stats + Construction): Construction first
  - General: F2P never first (move to end)

Usage:
  python3 scripts/reorder_categories.py [--dry-run]
"""

from __future__ import annotations
import argparse
import json
import pathlib

JSON_PATH = pathlib.Path(__file__).parent / "output" / "card_categories.json"


def prioritise(
    tags: list[str],
    first: list[str],
    last: list[str] | None = None,
    remove: set[str] | None = None,
) -> list[str]:
    """Reorder tags: `first` items in that order first, `last` items last, `remove` removed."""
    if remove:
        tags = [t for t in tags if t not in remove]
    if last is None:
        last = []
    head = [t for t in first if t in tags]
    tail = [t for t in last if t in tags]
    mid = [t for t in tags if t not in head and t not in tail]
    return head + mid + tail


def f2p_last(tags: list[str]) -> list[str]:
    """Move F2P to end (general fallback rule)."""
    if "F2P" not in tags or len(tags) <= 1:
        return tags
    return [t for t in tags if t != "F2P"] + ["F2P"]


# Tags that indicate a boss trophy mount / stuffed head
_COMBAT_STATS = {"Attack", "Defence", "Strength", "Magic", "Ranged", "Prayer"}

# Seeds that are NOT farming seeds (special items)
_SPECIAL_SEEDS = {
    "mithril seeds",
    "crystal weapon seed",
    "enhanced crystal teleport seed",
    "adamant seeds",
}

# Metal bars that get special treatment
_CRAFTING_FIRST_BARS = {"Gold bar", "Silver bar"}
_SAILING_FIRST_BARS = {"Lead bar", "Cupronickel bar"}
_BAR_SKIP = {"Chocolate bar", "Monkey bar"}

# Axe names that are NOT woodcutting tools (keep unchanged except Smithing removal)
_NON_WC_AXES = {"soulreaper axe", "zombie axe"}


def apply_rules(name: str, tags: list[str]) -> list[str]:  # noqa: C901
    if not tags:
        return tags

    tags = list(tags)
    n = name.lower()
    has_clue = "Clue" in tags

    # ── SPECIFIC ITEM OVERRIDES ───────────────────────────────────────────────

    if name == "Fishing bait":
        return ["Fishing", "F2P"]

    if name == "Rope":
        return ["Tool", "F2P"]

    if name == "Clay":
        t = [x for x in tags if x != "Magic"]
        # Crafting may not be tagged in source data — ensure it's present
        if "Crafting" not in t:
            t = ["Crafting"] + t
        return prioritise(t, ["Crafting", "Mining"], last=["F2P"])

    if name == "Soda ash":
        return [x for x in tags if x != "Magic"]  # already Crafting first

    if name == "Bucket of sand":
        t = [x for x in tags if x != "Magic"]
        return prioritise(t, ["Crafting"], last=["F2P"])

    if name == "Tinderbox":
        return prioritise(tags, ["Firemaking", "Tool"], last=["F2P"])

    if n.endswith("compost") and "Farming" in tags:
        return prioritise(tags, ["Farming"], last=["F2P"])

    # ── ORES ─────────────────────────────────────────────────────────────────

    if n.endswith(" ore") or n == "coal":
        remove = {"Magic"}
        if n == "coal":
            remove.add("Construction")
        t = [x for x in tags if x not in remove]
        if has_clue:
            inner = [x for x in t if x != "Clue"]
            return ["Clue"] + prioritise(inner, ["Smithing", "Mining", "Sailing"], last=["F2P"])
        return prioritise(t, ["Smithing", "Mining", "Sailing"], last=["F2P"])

    # ── LOGS ─────────────────────────────────────────────────────────────────

    if n.endswith(" logs") or n == "logs":
        remove = {"Prayer", "Smithing", "Magic", "Crafting"}
        t = [x for x in tags if x not in remove]
        # Keep Weapon tag (e.g. plain "Logs" which can be wielded) — it goes at the end
        return prioritise(t, ["Firemaking", "Fletching", "Construction", "Woodcutting", "Sailing"],
                          last=["Weapon", "F2P"])

    # ── SEEDS ─────────────────────────────────────────────────────────────────

    if (n.endswith(" seed") or n.endswith(" seeds")) and n not in _SPECIAL_SEEDS:
        return prioritise(tags, ["Farming"], last=["F2P"])

    # ── HERBS (clean herbs with both Farming and Herblore) ────────────────────

    if "Herblore" in tags and "Farming" in tags:
        return prioritise(tags, ["Herblore", "Farming"], last=["F2P"])

    # ── POTIONS ───────────────────────────────────────────────────────────────

    if ("Potion" in tags or n.endswith(" potion") or n.endswith(" brew")) and "Herblore" in tags:
        return prioritise(tags, ["Herblore", "Potion"], last=["F2P"])

    # ── BONES ─────────────────────────────────────────────────────────────────

    if n.endswith(" bones") or n == "bones":
        return prioritise(tags, ["Prayer"], last=["F2P"])

    if n.endswith(" ashes") and "Prayer" in tags:
        return prioritise(tags, ["Prayer"], last=["F2P"])

    # ── PLANKS ────────────────────────────────────────────────────────────────

    if n.endswith(" plank") or n == "plank":
        return prioritise(tags, ["Construction"], last=["F2P"])

    # ── NAILS ─────────────────────────────────────────────────────────────────

    if n.endswith(" nails"):
        return prioritise(tags, ["Construction"], last=["F2P"])

    # ── METAL BARS ────────────────────────────────────────────────────────────

    if n.endswith(" bar") and name not in _BAR_SKIP:
        if name in _CRAFTING_FIRST_BARS:
            return prioritise(tags, ["Crafting", "Smithing", "Construction", "Sailing"], last=["F2P"])
        if name in _SAILING_FIRST_BARS:
            return prioritise(tags, ["Sailing", "Construction", "Smithing"], last=["F2P"])
        # All other metal bars: Smithing first
        return prioritise(tags, ["Smithing", "Construction", "Crafting", "Sailing"], last=["F2P"])

    # ── RAW FOOD (starts with "Raw" and already has Cooking tag) ─────────────

    if n.startswith("raw ") and "Cooking" in tags:
        return prioritise(tags, ["Cooking"], last=["F2P"])

    # ── PICKAXES ──────────────────────────────────────────────────────────────

    if n.endswith(" pickaxe") or n == "pickaxe":
        if has_clue:
            inner = [x for x in tags if x != "Clue"]
            return ["Clue"] + prioritise(inner, ["Mining", "Tool"], last=["Melee", "Weapon", "F2P"])
        return prioritise(tags, ["Mining", "Tool"], last=["Melee", "Weapon", "F2P"])

    # ── AXES (woodcutting tools) ───────────────────────────────────────────────

    is_wc_axe = (
        (n.endswith(" axe") or n == "axe")
        and n not in _NON_WC_AXES
        and ("Tool" in tags or "Woodcutting" in tags)
    )
    if is_wc_axe:
        t = [x for x in tags if x != "Smithing"]  # remove Smithing
        if has_clue:
            inner = [x for x in t if x != "Clue"]
            return ["Clue"] + prioritise(inner, ["Woodcutting", "Tool"], last=["Melee", "Weapon", "F2P"])
        return prioritise(t, ["Woodcutting", "Tool"], last=["Melee", "Weapon", "F2P"])

    # ── BOWS / CROSSBOWS ──────────────────────────────────────────────────────

    is_bow = (
        n.endswith("bow")
        or "shortbow" in n
        or "longbow" in n
        or n.endswith("crossbow")
    )
    if is_bow:
        t = [x for x in tags if x != "Construction"]
        if has_clue:
            inner = [x for x in t if x != "Clue"]
            return ["Clue"] + prioritise(inner, ["Ranged", "Fletching"], last=["Weapon", "F2P"])
        return prioritise(t, ["Ranged", "Fletching"], last=["Weapon", "F2P"])

    # ── BOSS TROPHIES (mounted heads with combat stats + Construction) ────────

    if "Construction" in tags and _COMBAT_STATS & set(tags) and "head" in n:
        return prioritise(tags, ["Construction"], last=["F2P"])

    # ── GENERAL: F2P NEVER FIRST ──────────────────────────────────────────────

    return f2p_last(tags)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print changes without writing")
    args = ap.parse_args()

    data: dict[str, list[str]] = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    changed = 0
    result: dict[str, list[str]] = {}
    for name, tags in data.items():
        new_tags = apply_rules(name, tags)
        result[name] = new_tags
        if new_tags != tags:
            changed += 1
            if args.dry_run:
                print(f"  {name}:")
                print(f"    before: {tags}")
                print(f"    after:  {new_tags}")

    print(f"{'[DRY RUN] ' if args.dry_run else ''}{changed} items reordered out of {len(data)}")

    if not args.dry_run:
        JSON_PATH.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Written → {JSON_PATH}")


if __name__ == "__main__":
    main()
