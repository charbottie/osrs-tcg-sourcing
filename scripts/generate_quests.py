#!/usr/bin/env python3
"""Generate quests.json — completability data for all OSRS quests.

Scrapes the quest list from the OSRS Wiki, then fetches each quest page to
extract: prerequisites, skill requirements, items required, kills required,
reward items, quest points, and the starting NPC.

Output: scripts/output/quests.json

Usage:
  python scripts/generate_quests.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).parent))

from bs4 import BeautifulSoup

import quest_parser
import wiki_fetcher

_OUT = Path(__file__).parent / "output" / "quests.json"

# ── Quest list scraping ────────────────────────────────────────────────────────

class QuestListEntry:
    def __init__(self, name: str, page_slug: str, quest_points: int, members: bool):
        self.name = name
        self.page_slug = page_slug
        self.quest_points = quest_points
        self.members = members


def _fetch_quest_list() -> list[QuestListEntry]:
    """Return all quests from /w/List_of_quests.

    The page has three oqg-table tables: free quests, members quests, mini-quests.
    Each row has data-rowid="Quest Name" and:
      cells[0] = quest number
      cells[1] = name + link to wiki page
      cells[4] = quest points (for quests tables; not present for mini-quests)
    Members status is inferred from which table the quest is in.
    """
    html = wiki_fetcher.fetch("List_of_quests")
    if html is None:
        print("[ERROR] Could not fetch List_of_quests")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")
    entries: list[QuestListEntry] = []
    seen: set[str] = set()

    tables = soup.find_all("table", class_="oqg-table")
    # Table 0: free quests, Table 1: members quests, Table 2: mini-quests
    for t_idx, table in enumerate(tables):
        is_members = (t_idx == 1)
        is_mini = (t_idx == 2)

        for tr in table.find_all("tr"):
            name = tr.get("data-rowid", "").strip()
            if not name:
                continue

            cells = tr.find_all("td")
            page_slug = ""
            quest_points = 0

            # Quest name and link (cells[1] for quests, cells[0] for mini-quests)
            name_cell_idx = 0 if is_mini else 1
            if len(cells) > name_cell_idx:
                link = cells[name_cell_idx].find("a", href=True)
                if link:
                    href = link["href"]
                    page_slug = unquote(href.lstrip("/w/"))

            # Quest points (cells[4] for quests, not available for mini-quests)
            if not is_mini and len(cells) > 4:
                try:
                    quest_points = int(cells[4].get_text(strip=True))
                except ValueError:
                    quest_points = 0

            if not page_slug:
                page_slug = name.replace(" ", "_")

            if name not in seen:
                seen.add(name)
                entries.append(QuestListEntry(
                    name=name,
                    page_slug=page_slug,
                    quest_points=quest_points,
                    members=is_members,
                ))

    return entries


# ── Quest points extraction ────────────────────────────────────────────────────

def _extract_quest_points(rows: dict) -> int:
    """Extract the quest points value from infobox rows dict."""
    cell = rows.get("quest points", rows.get("quest point", ""))
    if not cell:
        return 0
    if isinstance(cell, str):
        return 0
    text = cell.get_text(strip=True)
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0


def _extract_members(rows: dict) -> bool:
    """Return True if this is a members quest."""
    cell = rows.get("members", "")
    if not cell:
        return False
    if isinstance(cell, str):
        return False
    text = cell.get_text(strip=True).lower()
    return "yes" in text or "members" in text


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N quests (for testing)")
    args = parser.parse_args()

    print("Fetching quest list from OSRS Wiki…")
    entries = _fetch_quest_list()
    total = len(entries)
    print(f"Found {total} quests\n")

    if args.limit:
        entries = entries[:args.limit]
        print(f"(Limited to first {args.limit})")

    result: dict[str, dict] = {}

    for i, entry in enumerate(entries, 1):
        name = entry.name
        page_slug = entry.page_slug
        print(f"  [{i}/{len(entries)}] {name}")

        html = wiki_fetcher.fetch(page_slug)
        if html is None:
            print(f"    [SKIP] could not fetch")
            result[name] = {
                "prerequisites": [],
                "skillRequirements": [],
                "itemsRequired": [],
                "killsRequired": [],
                "rewardItems": [],
                "questNpc": "",
                "questPoints": entry.quest_points,
                "members": entry.members,
                "wikiPage": page_slug,
            }
            continue

        info = quest_parser.parse_quest(html)

        result[name] = {
            "prerequisites":      info["prerequisites"],
            "skillRequirements":  info["skill_requirements"],
            "itemsRequired":      info["items_required"],
            "killsRequired":      info["kills"],
            "rewardItems":        info["reward_items"],
            "questNpc":           info["start_npc"],
            "questPoints":        entry.quest_points,
            "members":            entry.members,
            "wikiPage":           page_slug,
        }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Summary
    with_prereqs   = sum(1 for v in result.values() if v["prerequisites"])
    with_skills    = sum(1 for v in result.values() if v["skillRequirements"])
    with_items     = sum(1 for v in result.values() if v["itemsRequired"])
    with_kills     = sum(1 for v in result.values() if v["killsRequired"])
    with_rewards   = sum(1 for v in result.values() if v["rewardItems"])
    members_count  = sum(1 for v in result.values() if v["members"])
    total_qp       = sum(v["questPoints"] for v in result.values())

    print(f"\nWrote {_OUT} ({len(result)} quests)")
    print(f"  With prerequisites:    {with_prereqs}")
    print(f"  With skill reqs:       {with_skills}")
    print(f"  With items required:   {with_items}")
    print(f"  With kills required:   {with_kills}")
    print(f"  With reward items:     {with_rewards}")
    print(f"  Members quests:        {members_count}")
    print(f"  Total quest points:    {total_qp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
