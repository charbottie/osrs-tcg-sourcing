#!/usr/bin/env python3
"""Scan cached wiki quest pages for avoidable-combat markers.

For every quest in bm_quest_cards.json that has enemy requirements,
check the cached wiki HTML (scripts/cache/wiki_html/) for enemies
marked '(can be avoided)'.

Reports:
  - Quests where avoidable enemies are NOT yet marked optional: true  (action needed)
  - Quests where all avoidable enemies are already handled            (OK)
  - Quests with enemies but no cached wiki page                       (manual check)

Usage:
  python scripts/check_avoidable_combat.py
"""

from __future__ import annotations

import json
import pathlib
import sys

_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(_DIR))

import quest_parser  # noqa: E402

_CACHE_DIR   = _DIR / "cache" / "wiki_html"
_BM_QUEST    = _DIR / "output" / "bm_quest_cards.json"


def _wiki_cache_path(quest_name: str) -> pathlib.Path | None:
    """Return the cached HTML path for a quest, or None if absent."""
    safe = quest_name.replace(" ", "_").replace("/", "_")
    p = _CACHE_DIR / f"{safe}.html"
    return p if p.exists() else None


def main() -> None:
    data   = json.loads(_BM_QUEST.read_text(encoding="utf-8"))
    quests = data["quests"]

    needs_fix: list[tuple[str, list[str]]] = []   # (quest, [avoidable not yet marked])
    already_ok: list[str]                  = []    # wiki has avoidable kills, already marked
    clean: list[str]                       = []    # wiki has enemies, none avoidable
    no_cache: list[str]                    = []

    for quest in quests:
        enemy_reqs = [
            r
            for s in quest.get("sections", [])
            if s.get("label") == "Enemies"
            for r in s.get("requirements", [])
        ]
        if not enemy_reqs:
            continue  # no enemies to check

        name  = quest["name"]
        cache = _wiki_cache_path(name)
        if cache is None:
            no_cache.append(name)
            continue

        html                = cache.read_text(encoding="utf-8")
        _required, avoidable = quest_parser._extract_kills(
            _get_enemies_cell(html)
        )

        if not avoidable:
            clean.append(name)
            continue  # wiki shows no avoidable combat here

        # Compare: which avoidable wiki enemies are NOT already optional in json
        already_optional = {
            r["label"]
            for r in enemy_reqs
            if r.get("optional")
        }
        unhandled = [e for e in avoidable if e not in already_optional]

        if unhandled:
            needs_fix.append((name, unhandled))
        else:
            already_ok.append(name)

    # ── Report ────────────────────────────────────────────────────────────────
    if needs_fix:
        print(f"\n{'='*60}")
        print(f"NEEDS FIXING ({len(needs_fix)} quests)")
        print(f"{'='*60}")
        for quest_name, enemies in needs_fix:
            print(f"  {quest_name}")
            for e in enemies:
                print(f"    → {e}  (mark optional: true)")

    if already_ok:
        print(f"\n{'='*60}")
        print(f"ALREADY HANDLED ({len(already_ok)} quests)")
        print(f"{'='*60}")
        for quest_name in already_ok:
            print(f"  {quest_name}")

    if no_cache:
        print(f"\n{'='*60}")
        print(f"NO CACHED PAGE — check manually ({len(no_cache)} quests)")
        print(f"{'='*60}")
        for quest_name in no_cache:
            print(f"  {quest_name}")

    total_with_enemies = len(needs_fix) + len(already_ok) + len(clean) + len(no_cache)
    checked = len(needs_fix) + len(already_ok) + len(clean)
    print(f"\nSummary: {total_with_enemies} quests have enemy requirements — "
          f"{checked} checked against wiki ({len(clean)} clean, "
          f"{len(already_ok)} avoidable+handled, {len(needs_fix)} need fixes), "
          f"{len(no_cache)} missing cache.\n")


def _get_enemies_cell(html: str):
    """Return the 'Enemies to defeat' questdetails cell, or None."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    qd   = soup.find("table", class_="questdetails")
    if qd is None:
        return None
    for tr in qd.find_all("tr"):
        th = tr.find("th", class_="questdetails-header")
        td = tr.find("td", class_="questdetails-info")
        if th and td and "enemies" in th.get_text(strip=True).lower():
            return td
    return None


if __name__ == "__main__":
    main()
