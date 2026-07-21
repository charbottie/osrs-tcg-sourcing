"""Parse OSRS Wiki quest pages from HTML.

Quest pages use a <table class="questdetails"> structure with rows:
  <th class="questdetails-header">Row label</th>
  <td class="questdetails-info">...</td>

Key rows parsed:
  Start point    — NPC you speak to to start the quest
  Requirements   — Quest prerequisites (sub-list) + skill requirements (scp spans)
  Items required — Items the player must bring
  Enemies to defeat — NPCs that must be killed

Skill requirements are encoded as:
  <span class="scp" data-skill="SkillName" data-level="N">

Quest prerequisites are in a nested list under "Completion of the following quests".
"""

from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup, NavigableString, Tag


# ── OSRS skill names (used to filter scp spans) ───────────────────────────────
_OSRS_SKILLS: frozenset[str] = frozenset({
    "Attack", "Strength", "Defence", "Ranged", "Prayer", "Magic", "Hitpoints",
    "Runecrafting", "Construction", "Agility", "Herblore", "Thieving", "Crafting",
    "Fletching", "Slayer", "Hunter", "Mining", "Smithing", "Fishing", "Cooking",
    "Firemaking", "Woodcutting", "Farming", "Sailing",
})


class SkillReq(TypedDict):
    skill: str
    level: int
    boostable: bool


class QuestInfo(TypedDict):
    prerequisites: list[str]           # quest names required first
    reward_items: list[str]            # item names given as quest rewards
    start_npc: str                     # best-effort starting NPC name
    kills: list[str]                   # NPC names to kill
    skill_requirements: list[SkillReq] # skill levels needed
    items_required: list[str]          # items the player must bring


def parse_quest(html: str) -> QuestInfo:
    """Return quest metadata from a wiki quest page.

    Parses the <table class="questdetails"> structure. Returns an empty
    QuestInfo if no recognisable quest details table is found.
    """
    soup = BeautifulSoup(html, "html.parser")

    qd = soup.find("table", class_="questdetails")
    if qd is None:
        return QuestInfo(
            prerequisites=[], reward_items=[], start_npc="", kills=[],
            skill_requirements=[], items_required=[],
        )

    rows = _parse_questdetails(qd)

    return QuestInfo(
        prerequisites=_extract_prerequisites(rows.get("requirements")),
        reward_items=[],   # rewards are JavaScript-rendered; not reliably parseable
        start_npc=_extract_start_npc(rows.get("start point")),
        kills=_extract_kills(rows.get("enemies to defeat")),
        skill_requirements=_extract_skill_requirements(rows.get("requirements")),
        items_required=_extract_items_required(rows.get("items required")),
    )


# ── Infobox helpers (kept for backwards compatibility / quest points) ──────────

def _find_infobox(soup: BeautifulSoup) -> Tag | None:
    """Find the quest infobox-quest table (for metadata like quest points)."""
    for cls in ("infobox-quest", "infobox"):
        box = soup.find("table", class_=cls)
        if box:
            return box
    return None


def _parse_infobox_rows(infobox: Tag) -> dict[str, Tag]:
    """Return a dict mapping header text → data cell Tag (from infobox-quest)."""
    rows: dict[str, Tag] = {}
    for tr in infobox.find_all("tr"):
        cells = tr.find_all("td") + tr.find_all("th")
        if len(cells) >= 2:
            header = cells[0].get_text(strip=True).lower().rstrip(":")
            rows[header] = cells[1]
    return rows


# ── questdetails parsing ───────────────────────────────────────────────────────

def _parse_questdetails(qd: Tag) -> dict[str, Tag]:
    """Return {lowercase_header: data_cell} from a questdetails table."""
    rows: dict[str, Tag] = {}
    for tr in qd.find_all("tr"):
        th = tr.find("th", class_="questdetails-header")
        td = tr.find("td", class_="questdetails-info")
        if th and td:
            header = th.get_text(strip=True).lower()
            rows[header] = td
    return rows


def _extract_prerequisites(cell: Tag | None) -> list[str]:
    """Extract quest prerequisite names from the Requirements cell.

    Two patterns on the wiki:
    1. "<li>Completion of the following quests: <ul><li><a>Quest A</a></li>...</ul>"
       → take first link from each child <li> of the nested <ul>
    2. "<li>Completion of <a>Quest A</a></li>"
       → take the first link from the <li> directly

    Both "Completion of" and "Completed" prefixes are handled.
    """
    if cell is None:
        return []

    prereqs: list[str] = []
    seen: set[str] = set()

    for li in cell.find_all("li"):
        text = li.get_text(strip=True).lower()

        if text.startswith(("completion of", "completed")):
            nested_ul = li.find("ul")
            if nested_ul:
                # Pattern 1: nested list of multiple prereqs
                for child_li in nested_ul.find_all("li", recursive=False):
                    link = child_li.find("a")
                    if link:
                        name = link.get_text(strip=True)
                        if name and len(name) > 1 and name not in seen:
                            seen.add(name)
                            prereqs.append(name)
            else:
                # Pattern 2: single prereq — first link in this <li>
                link = li.find("a")
                if link:
                    name = link.get_text(strip=True)
                    if name and len(name) > 1 and name not in seen:
                        seen.add(name)
                        prereqs.append(name)

    return prereqs


def _extract_skill_requirements(cell: Tag | None) -> list[SkillReq]:
    """Extract skill requirements from scp spans in the Requirements cell."""
    if cell is None:
        return []

    results: list[SkillReq] = []
    seen: set[str] = set()

    for span in cell.find_all("span", class_="scp"):
        skill = span.get("data-skill", "").strip()
        level_str = span.get("data-level", "").strip()

        if skill not in _OSRS_SKILLS:
            continue
        if skill in seen:
            continue
        seen.add(skill)

        try:
            level = int(level_str)
        except (ValueError, TypeError):
            continue

        # Check if this span or its parent <li> says "(not boostable)"
        parent_text = ""
        parent = span.parent
        if parent:
            parent_text = parent.get_text(strip=True).lower()
        boostable = "not boostable" not in parent_text

        results.append(SkillReq(skill=skill, level=level, boostable=boostable))

    return results


def _extract_items_required(cell: Tag | None) -> list[str]:
    """Extract required item names from the 'Items required' cell.

    Takes the first <a> link from each top-level <li> in the checklist,
    which is the item itself (nested content describes how to obtain it).
    Returns empty list if the cell text is 'None'.
    """
    if cell is None:
        return []
    if cell.get_text(strip=True).lower() in ("none", "none."):
        return []

    items: list[str] = []

    # The items are usually inside a div.checklist > ul
    checklist = cell.find("div", class_="checklist")
    ul = checklist.find("ul") if checklist else cell.find("ul")
    if not ul:
        return []

    for li in ul.find_all("li", recursive=False):
        link = li.find("a")
        if link:
            name = link.get_text(strip=True)
            # Skip skill page links, map links, file links
            href = link.get("href", "")
            if any(x in href for x in ("File:", "Show_on_map", "action=", "Leagues")):
                continue
            # Skip if the linked name is an OSRS skill name (e.g. "Magic" skill page)
            if name in _OSRS_SKILLS:
                continue
            if name and len(name) > 1 and not name.startswith("File:"):
                items.append(name)

    return items


def _extract_kills(cell: Tag | None) -> list[str]:
    """Extract NPC names from the 'Enemies to defeat' cell."""
    if cell is None:
        return []
    if cell.get_text(strip=True).lower() in ("none", "none.", ""):
        return []

    kills: list[str] = []
    seen: set[str] = set()
    for a in cell.find_all("a"):
        href = a.get("href", "")
        if "File:" in href or "action=" in href:
            continue
        name = a.get_text(strip=True)
        if name and len(name) > 1 and name not in seen:
            seen.add(name)
            kills.append(name)

    return kills


def _extract_start_npc(cell: Tag | None) -> str:
    """Extract the starting NPC name from the 'Start point' cell."""
    if cell is None:
        return ""

    for a in cell.find_all("a"):
        href = a.get("href", "")
        name = a.get_text(strip=True)
        # Skip map links, edit links, file links
        if any(x in href for x in ("File:", "action=", "Show_on_map", "Leagues", "map")):
            continue
        if "show on map" in name.lower() or "map icon" in name.lower():
            continue
        if name and len(name) > 1:
            return name

    # Fallback: plain text, strip "Talk to" prefix
    raw = cell.get_text(strip=True)
    raw = re.sub(r"^(?:speak\s+to\s+|talk\s+to\s+)", "", raw, flags=re.IGNORECASE)
    raw = re.split(r"\s+(?:at|in|near|outside|by)\s+", raw, maxsplit=1)[0]
    return raw.strip()
