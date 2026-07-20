"""Parse OSRS Wiki quest infoboxes from HTML.

Quest pages have a sidebar infobox table with rows for Prerequisites,
Items required, Start point, Rewards, etc. We extract what's needed for
the sourcing panel: prerequisites, reward items, and the start NPC.

HTML structure (as of 2026-07):
  <table class="infobox-quest">
    <tbody>
      <tr class="infobox-row">
        <td class="infobox-header">Prerequisites</td>
        <td class="infobox-data">
          <a href="/w/Monkey_Madness_I">Monkey Madness I</a><br>
          <a href="/w/Tree_Gnome_Village">Tree Gnome Village</a>
        </td>
      </tr>
      <tr class="infobox-row">
        <td class="infobox-header">Start point</td>
        <td class="infobox-data">Speak to King Narnode Shareen...</td>
      </tr>
      <tr class="infobox-row">
        <td class="infobox-header">Rewards</td>
        <td class="infobox-data">...</td>
      </tr>
    </tbody>
  </table>

Not all fields are present on every quest page. Missing fields are
returned as empty lists / empty strings — callers must handle gracefully.
"""

from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup, Tag


class QuestInfo(TypedDict):
    prerequisites: list[str]   # quest names that must be completed first
    reward_items: list[str]    # item names given as rewards
    start_npc: str             # NPC name at the start point (best-effort)
    kills: list[str]           # NPC names listed as kills required


def parse_quest(html: str) -> QuestInfo:
    """Return quest metadata from a wiki quest page.

    Returns an empty QuestInfo (all lists empty, string empty) if the
    page has no recognisable quest infobox.
    """
    soup = BeautifulSoup(html, "html.parser")

    infobox = _find_infobox(soup)
    if infobox is None:
        return QuestInfo(prerequisites=[], reward_items=[], start_npc="", kills=[])

    rows = _parse_infobox_rows(infobox)

    prerequisites = _extract_links(rows.get("prerequisites", rows.get("completion requirements", "")))
    reward_items = _extract_reward_items(rows.get("rewards", rows.get("reward", "")))
    start_npc = _extract_start_npc(rows.get("start point", rows.get("starting point", "")))
    kills = _extract_links(rows.get("kills required", rows.get("enemies to defeat", "")))

    return QuestInfo(
        prerequisites=prerequisites,
        reward_items=reward_items,
        start_npc=start_npc,
        kills=kills,
    )


def _find_infobox(soup: BeautifulSoup) -> Tag | None:
    """Find the quest infobox table."""
    # Try class-based lookup first
    for cls in ("infobox-quest", "infobox"):
        box = soup.find("table", class_=cls)
        if box:
            return box

    # Fallback: any table that has "Start point" or "Prerequisites" as a cell
    for table in soup.find_all("table"):
        text = table.get_text()
        if "Start point" in text or "Prerequisites" in text:
            return table

    return None


def _parse_infobox_rows(infobox: Tag) -> dict[str, Tag]:
    """Return a dict mapping header text → data cell Tag."""
    rows: dict[str, Tag] = {}
    for tr in infobox.find_all("tr"):
        cells = tr.find_all("td") + tr.find_all("th")
        if len(cells) >= 2:
            header = cells[0].get_text(strip=True).lower().rstrip(":")
            data_cell = cells[1]
            rows[header] = data_cell
    return rows


def _extract_links(cell: Tag | str) -> list[str]:
    """Extract all link texts from a cell, used for quest/NPC name lists."""
    if not cell:
        return []
    if isinstance(cell, str):
        return []

    links = []
    for a in cell.find_all("a"):
        text = a.get_text(strip=True)
        # Skip image links and trivial single-char anchors
        if text and len(text) > 1 and not text.startswith("File:"):
            links.append(text)

    # If no links, try plain text — comma or newline separated
    if not links:
        raw = cell.get_text(separator="\n", strip=True)
        for chunk in re.split(r"[\n,]", raw):
            chunk = chunk.strip()
            if chunk and len(chunk) > 2:
                links.append(chunk)

    return links


def _extract_reward_items(cell: Tag | str) -> list[str]:
    """Extract item names from the Rewards infobox cell.

    The rewards cell typically contains links to item pages mixed with
    text like "2 Quest points" and XP amounts. We want only item links.
    """
    if not cell or isinstance(cell, str):
        return []

    items = []
    for a in cell.find_all("a"):
        text = a.get_text(strip=True)
        href = a.get("href", "")
        # Skip non-item links: quest points, XP, skill icons, etc.
        if not text or len(text) <= 1:
            continue
        if "Quest_points" in href or "Experience" in href:
            continue
        if re.match(r"^\d", text):    # starts with a digit → likely XP/qty
            continue
        if text.endswith("XP") or text.endswith("experience"):
            continue
        items.append(text)

    return items


def _extract_start_npc(cell: Tag | str) -> str:
    """Best-effort extraction of the starting NPC name from the Start point cell."""
    if not cell or isinstance(cell, str):
        return ""

    # The cell often reads "Speak to [NPC name] at [location]"
    # Most reliable: first link in the cell that isn't a location
    links = []
    for a in cell.find_all("a"):
        text = a.get_text(strip=True)
        if text and len(text) > 1:
            links.append(text)

    if links:
        return links[0]

    # Fallback: strip "Speak to" prefix from plain text
    raw = cell.get_text(strip=True)
    raw = re.sub(r"^(?:speak\s+to\s+|talk\s+to\s+)", "", raw, flags=re.IGNORECASE)
    # Take text up to first preposition ("at", "in", "near", "outside")
    raw = re.split(r"\s+(?:at|in|near|outside|by)\s+", raw, maxsplit=1)[0]
    return raw.strip()
