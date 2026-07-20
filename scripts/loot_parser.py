"""Parse OSRS Wiki monster loot tables from HTML.

The wiki renders drop tables as one or more <table class="... item-drops ...">
tables per monster page (one table per drop category: always, weapons, food,
etc.). Each table has one or more data rows.

Actual column layout (verified against live pages 2026-07):
  cells[0]  inventory-image   — item sprite, ignored
  cells[1]  item-col          — item name (inside <a> tag)
  cells[2]  (none)            — quantity string
  cells[3]  table-bg-*        — rarity: either label text ("Always") or
                                fraction text ("4/128", "1/26.9")
  cells[4]  ge-column         — GE price, ignored
  cells[5]  alch-column       — high alch, ignored

The rarity cell class encodes the colour tier:
  table-bg-blue   → Always
  table-bg-green  → Common
  table-bg-yellow → Uncommon
  table-bg-orange → Rare
  table-bg-red    → Very Rare / Extremely Rare

We use the cell text as the fraction directly when it matches N/D format,
and fall back to the bg-colour class if not.
"""

from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup, Tag

import rarity_mapper

_FRACTION_RE = re.compile(r"^\d+(?:\.\d+)?/[\d,.]+$")

# Maps table-bg-* colour to a fallback label when the cell text isn't a fraction
_BG_TO_LABEL: dict[str, str] = {
    "table-bg-blue":   "Always",
    "table-bg-green":  "Common",
    "table-bg-yellow": "Uncommon",
    "table-bg-orange": "Rare",
    "table-bg-red":    "Very Rare",
}


_RDT_KEYWORDS = {"rare and gem drop table", "rare drop table", "gem drop table"}

class DropRow(TypedDict):
    item: str          # item name as it appears on the wiki
    quantity: str      # e.g. "1", "1–5", "100 (noted)"
    fraction: str      # e.g. "1/512", "4/128", or "" if not found
    wiki_label: str    # colour-derived label, e.g. "Rare"
    rarity: str        # our normalised label from rarity_mapper
    section: str       # wiki section heading the table belongs to
    is_rdt: bool       # True if this drop is from the shared Rare Drop Table


def _fraction_rate(frac: str) -> float:
    """Parse 'N/D' → float probability, for duplicate-dedup comparison."""
    if not frac:
        return 0.0
    m = re.match(r"^([\d.]+)/([\d,]+)$", frac)
    if not m:
        return 0.0
    return float(m.group(1)) / float(m.group(2).replace(",", ""))


def parse_drops(html: str) -> list[DropRow]:
    """Return all drop rows from a wiki monster page.

    Drops are not filtered — caller filters to TCG cards only.
    Returns an empty list if no drops tables are found.

    Deduplicates by item name within the same fromRdt bucket, keeping the
    entry with the highest drop probability. This handles monsters like
    Scurrius that have multiple independent drop tables on the same page.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[DropRow] = []

    # Walk the page in document order, tracking the current section heading
    current_section = ""
    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h2", "h3", "h4"):
            current_section = el.get_text(strip=True)
        elif el.name == "table" and "item-drops" in el.get("class", []):
            is_rdt = current_section.lower() in _RDT_KEYWORDS
            for tr in el.find_all("tr"):
                row = _parse_row(tr, current_section, is_rdt)
                if row:
                    rows.append(row)

    # Deduplicate: keep the highest-probability entry per (item, is_rdt) pair
    best: dict[tuple, DropRow] = {}
    for row in rows:
        key = (row["item"], row["is_rdt"])
        if key not in best or _fraction_rate(row["fraction"]) > _fraction_rate(best[key]["fraction"]):
            best[key] = row

    return list(best.values())


def _parse_row(tr: Tag, section: str, is_rdt: bool) -> DropRow | None:
    cells = tr.find_all("td")
    # Skip header rows and malformed rows (need at least 4 cells)
    if len(cells) < 4:
        return None

    item_name = _extract_item_name(cells[1])  # item-col cell
    if not item_name:
        return None

    quantity = cells[2].get_text(strip=True)
    fraction, wiki_label = _extract_rarity(cells[3])

    return DropRow(
        item=item_name,
        quantity=quantity,
        fraction=fraction,
        wiki_label=wiki_label,
        rarity=rarity_mapper.best(fraction or None, wiki_label or None),
        section=section,
        is_rdt=is_rdt,
    )


def _extract_item_name(cell: Tag) -> str:
    link = cell.find("a")
    if link:
        return link.get_text(strip=True)
    return cell.get_text(strip=True)


def _extract_rarity(cell: Tag) -> tuple[str, str]:
    """Return (fraction_str, label_str) from the rarity cell (cells[3])."""
    text = cell.get_text(strip=True)
    classes = cell.get("class", [])

    # Derive colour-based label from table-bg-* class
    wiki_label = ""
    for cls in classes:
        if cls in _BG_TO_LABEL:
            wiki_label = _BG_TO_LABEL[cls]
            break

    # Strategy 1: data-drop-fraction attribute on any child span (most reliable)
    for span in cell.find_all("span"):
        frac = span.get("data-drop-fraction", "")
        if frac and _FRACTION_RE.match(frac.strip()):
            return frac.strip(), wiki_label

    # Strategy 2: cell text directly (strips citation refs like "[3]" first)
    clean_text = re.sub(r"\[\d+\]", "", text).strip()

    if clean_text.lower() in ("always",):
        return "1/1", "Always"

    if _FRACTION_RE.match(clean_text):
        return clean_text, wiki_label

    # Strategy 3: title attribute on the cell itself ("0.195%" → not a fraction, skip)
    # title= holds percentage, data-sort-value holds denominator as int — not useful

    return "", wiki_label


def parse_monster_info(html: str) -> dict:
    """Extract metadata from a monster's wiki infobox.

    Returns a dict with keys:
      slayerLevel  — int or None
      combatLevel  — int or None
    """
    soup = BeautifulSoup(html, "html.parser")
    infobox = soup.find("table", class_="infobox-monster") or soup.find("table", class_="infobox")
    result = {"slayerLevel": None, "combatLevel": None}
    if not infobox:
        return result

    for tr in infobox.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        value = cells[1].get_text(strip=True).replace(",", "")
        m = re.search(r"\d+", value)
        if not m:
            continue
        if "slayer level" in label:
            result["slayerLevel"] = int(m.group())
        elif label in ("combat level", "combat"):
            result["combatLevel"] = int(m.group())

    return result
