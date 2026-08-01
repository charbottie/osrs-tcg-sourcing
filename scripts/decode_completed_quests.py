#!/usr/bin/env python3
"""
Read RuneLite quest-completion screenshots and write scripts/output/completed_quests.json.

RuneLite's Screenshot plugin saves a file named:
  Quest(<quest name>) YYYY-MM-DD_HH-MM-SS.png
in ~/.runelite/screenshots/<player>/Quests/ whenever a quest is completed.

This script scans all player directories under that path, extracts the quest
names from the filenames, and writes them to completed_quests.json so the
preview tool can load them as a static file (no server needed).

Usage:
  python3 scripts/decode_completed_quests.py
  python3 scripts/decode_completed_quests.py --player lottie_tcg
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

SCREENSHOTS_BASE = pathlib.Path.home() / ".runelite" / "screenshots"
OUT_JSON = pathlib.Path(__file__).parent / "output" / "completed_quests.json"

PATTERN = re.compile(r'^Quest\((.+?)\)\s+\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.png$')


def scan_dir(quest_dir: pathlib.Path) -> dict[str, str]:
    """Return {quest_name: filename} for all quest completion screenshots in a dir."""
    found: dict[str, str] = {}
    if not quest_dir.is_dir():
        return found
    for f in quest_dir.iterdir():
        m = PATTERN.match(f.name)
        if m:
            name = m.group(1)
            # Keep the most recent screenshot per quest name
            if name not in found or f.name > found[name]:
                found[name] = f.name
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--player", default="",
                   help="Only scan this player's screenshots (default: all players)")
    args = p.parse_args()

    if not SCREENSHOTS_BASE.exists():
        print(f"ERROR: Screenshots directory not found: {SCREENSHOTS_BASE}")
        return 1

    all_found: dict[str, str] = {}

    if args.player:
        dirs = [SCREENSHOTS_BASE / args.player / "Quests"]
    else:
        dirs = [d / "Quests" for d in SCREENSHOTS_BASE.iterdir() if d.is_dir()]

    for quest_dir in dirs:
        found = scan_dir(quest_dir)
        if found:
            player = quest_dir.parent.name
            print(f"  {player}: {len(found)} completed quests")
            for name in sorted(found):
                print(f"    {name}")
            all_found.update(found)

    if not all_found:
        print("No quest completion screenshots found.")
        return 1

    completed = sorted(all_found.keys())
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"completedQuests": completed}, indent=2,
                                    ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nWrote {len(completed)} completed quest names → {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
