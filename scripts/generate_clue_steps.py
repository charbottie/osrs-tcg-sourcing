#!/usr/bin/env python3
"""Scrape clue step data from the OSRS Wiki.

Produces scripts/output/clue_steps.json with three sections:
  emote    — emote clues per tier (items required for each step)
  sherlock — Sherlock tasks per tier (Elite / Master, items required)
  falo     — Falo the Bard steps (lyric → valid items)

Usage:
  python scripts/generate_clue_steps.py
  python scripts/generate_clue_steps.py --force-refresh   # re-fetch cached pages
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bs4 import BeautifulSoup, Tag
import wiki_fetcher

_OUT = Path(__file__).parent / "output" / "clue_steps.json"

EMOTE_TIERS = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]
SHERLOCK_TIERS = ["Elite", "Master"]

# Items listed in these columns are not actual equippable items — skip them
_SKILL_WORDS = frozenset({"None", "Completion", "completion", "required"})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cell_text(td: Tag) -> str:
    """Return normalised plain text for a cell, stripping footnote refs."""
    for tag in td.find_all(["sup", "ref"]):
        tag.decompose()
    return " ".join(td.get_text(" ").split())


def _links_in_cell(td: Tag) -> list[str]:
    """Return canonical item names from all wiki links in a <td>.

    Uses the `title` attribute of <a> tags (most reliable for canonical names).
    Skips red links (title ends with ' (page does not exist)').
    Skips file/template/category links.
    """
    items: list[str] = []
    for a in td.find_all("a", href=True):
        href: str = a["href"]
        if not href.startswith("/w/"):
            continue
        title = a.get("title", "").strip()
        if not title:
            continue
        if title.endswith("(page does not exist)"):
            # Red link — use the visible text instead
            title = a.get_text().strip()
        if ":" in title and not title.startswith("("):
            # File:, Category:, Template:, etc.
            continue
        if title and title not in items:
            items.append(title)
    return items


# ── Emote clues ───────────────────────────────────────────────────────────────

def _parse_emote_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Treasure_Trails/Guide/Emote_clues/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        if "clue" not in headers or "items" not in " ".join(headers):
            continue

        # Identify column indices
        col_clue  = next((i for i, h in enumerate(headers) if h == "clue"), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), 1)

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_clue, col_items):
                continue

            clue_td  = cells[col_clue]
            items_td = cells[col_items]

            clue_text = _cell_text(clue_td)
            items     = _links_in_cell(items_td)

            if not clue_text:
                continue

            steps.append({
                "tier":      tier,
                "clueText":  clue_text,
                "items":     items,
            })

    print(f"  Emote {tier}: {len(steps)} steps")
    return steps


def scrape_emote_clues(force_refresh: bool) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for tier in EMOTE_TIERS:
        result[tier] = _parse_emote_tier(tier, force_refresh)
    return result


# ── Sherlock ─────────────────────────────────────────────────────────────────

def _parse_sherlock_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Sherlock/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    tasks: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        joined  = " ".join(headers)
        if "task" not in joined and "skill" not in joined:
            continue

        # Find the "Items required" column index
        col_task  = next((i for i, h in enumerate(headers) if "task" in h), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), -1)
        if col_items < 0:
            continue

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_task, col_items):
                continue

            task_text = _cell_text(cells[col_task])
            items_td  = cells[col_items]

            # Items may be slash-separated links OR free text — gather links first
            items = _links_in_cell(items_td)
            # Fallback: split on "/" if there are no links but there is text
            if not items:
                raw = _cell_text(items_td)
                if raw and raw.lower() not in ("none", "-", ""):
                    for part in re.split(r"\s*/\s*", raw):
                        part = part.strip()
                        if part and part.lower() != "none":
                            items.append(part)

            if not task_text:
                continue

            tasks.append({
                "tier":     tier,
                "task":     task_text,
                "items":    items,
            })

    print(f"  Sherlock {tier}: {len(tasks)} tasks")
    return tasks


def scrape_sherlock(force_refresh: bool) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for tier in SHERLOCK_TIERS:
        result[tier] = _parse_sherlock_tier(tier, force_refresh)
    return result


# ── Falo the Bard ─────────────────────────────────────────────────────────────

def scrape_falo(force_refresh: bool) -> list[dict]:
    html = wiki_fetcher.fetch("Falo_the_Bard", force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch Falo_the_Bard")
        return []

    soup = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        joined  = " ".join(headers)
        if "lyric" not in joined and "item" not in joined:
            continue

        # Falo table uses rowspan on lyric cells for multi-item rows.
        # Strategy: walk rows, tracking current_lyric + remaining_rowspan.
        current_lyric: str = ""
        lyric_items:   list[str] = []
        remaining_rows: int = 0

        def _flush():
            nonlocal current_lyric, lyric_items
            if current_lyric and lyric_items:
                steps.append({"lyric": current_lyric, "items": list(lyric_items)})
            current_lyric = ""
            lyric_items   = []

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue  # header row

            if remaining_rows > 0:
                # Lyric cell is omitted (rowspan continuation) — only item cell present
                remaining_rows -= 1
                items = _links_in_cell(cells[0])
                lyric_items.extend(i for i in items if i not in lyric_items)
            else:
                # New lyric row
                _flush()
                if len(cells) < 2:
                    continue
                lyric_td = cells[0]
                item_td  = cells[1]

                # Check for rowspan attribute
                rowspan = int(lyric_td.get("rowspan", 1))
                remaining_rows = rowspan - 1

                current_lyric = _cell_text(lyric_td)
                items = _links_in_cell(item_td)
                lyric_items = list(items)

        _flush()
        break  # only one Falo table

    print(f"  Falo: {len(steps)} steps")
    return steps


# ── Reverse index: item → steps ───────────────────────────────────────────────

def _build_item_index(
    emote: dict[str, list[dict]],
    sherlock: dict[str, list[dict]],
    falo: list[dict],
) -> dict[str, list[dict]]:
    """Return {item_name: [step_ref, ...]} for fast lookup in the browser."""
    index: dict[str, list[dict]] = {}

    def _add(item: str, ref: dict):
        key = item.strip()
        if not key:
            return
        index.setdefault(key, []).append(ref)

    for tier, steps in emote.items():
        for step in steps:
            for item in step["items"]:
                _add(item, {"type": "emote", "tier": tier,
                            "clueText": step["clueText"],
                            "items": step["items"]})

    for tier, tasks in sherlock.items():
        for task in tasks:
            for item in task["items"]:
                _add(item, {"type": "sherlock", "tier": tier,
                            "task": task["task"],
                            "items": task["items"]})

    for step in falo:
        for item in step["items"]:
            _add(item, {"type": "falo",
                        "lyric": step["lyric"],
                        "items": step["items"]})

    return index


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force-refresh", action="store_true",
                   help="Re-fetch pages even if cached")
    args = p.parse_args()

    force = args.force_refresh

    print("Scraping emote clue steps…")
    emote = scrape_emote_clues(force)

    print("Scraping Sherlock tasks…")
    sherlock = scrape_sherlock(force)

    print("Scraping Falo the Bard…")
    falo = scrape_falo(force)

    print("Building item reverse index…")
    item_index = _build_item_index(emote, sherlock, falo)

    output = {
        "emote":     emote,
        "sherlock":  sherlock,
        "falo":      falo,
        "itemIndex": item_index,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

    total_emote    = sum(len(v) for v in emote.values())
    total_sherlock = sum(len(v) for v in sherlock.values())
    print(f"\nWrote {_OUT}")
    print(f"  Emote steps:    {total_emote}")
    print(f"  Sherlock tasks: {total_sherlock}")
    print(f"  Falo steps:     {len(falo)}")
    print(f"  Item index:     {len(item_index)} items")


if __name__ == "__main__":
    main()
