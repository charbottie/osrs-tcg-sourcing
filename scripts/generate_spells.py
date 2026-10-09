"""Generate spells.json — every spell's level and rune cost, from the OSRS Wiki
spellbook pages (Standard, Ancient, Lunar, Arceuus).

Central source for anything that needs to know what a spell costs: diary
"cast X" tasks (generate_diaries.py) and the Magic skilling tab.

Output: scripts/output/spells.json
  { "<Spell name>": { book, level, runes: {"Law rune": 1, ...}, members } }
Also: scripts/output/rune_sources.json
  { "<Elemental rune>": ["<combination rune or staff that supplies it>", ...] }
  From the wiki's Elemental staff and Combination rune tables, plus the
  few other unlimited sources in EXTRA_SOURCES. Lets a spell's rune cost be
  met by "the rune, or anything that supplies it".

Usage:
  python3 scripts/generate_spells.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from generate_diaries import _fetch_wikitext

_OUT = Path(__file__).resolve().parent / "output" / "spells.json"
_SOURCES_OUT = _OUT.with_name("rune_sources.json")

ELEMENTS = ("Air rune", "Water rune", "Earth rune", "Fire rune")
# Unlimited rune sources the two wiki tables don't list (wiki item pages).
# Tomes are left out: they only supply runes while charged with pages.
EXTRA_SOURCES = {
    "Kodai wand": ["Water rune"],
    "Twinflame staff": ["Fire rune", "Water rune"],
}

BOOKS = {
    "Standard": "Standard spellbook",
    "Ancient": "Ancient Magicks",
    "Lunar": "Lunar spellbook",
    "Arceuus": "Arceuus spellbook",
}

_ROW_SPLIT = re.compile(r"^\|-.*$", re.M)
# Spell name cell: "{{plinkt|Name}}" (Standard) or "|[[Name]]" after the icon cells (others)
_NAME_RE = re.compile(r"\{\{plinkt?\|([^}|]+)|^\|\s*\[\[(?!File:)([^\]|]+)(?:\|[^\]]*)?\]\]\**\s*$", re.M)
_RUNES_RE = re.compile(r"\{\{RuneReq\|([^}]*)\}\}")
_LEVEL_RE = re.compile(r"^\|\s*(\d+)\s*$", re.M)
_MEMBERS_RE = re.compile(r"\{\{members\|(yes|no)\}\}", re.I)


def parse_book(book: str, wikitext: str) -> dict[str, dict]:
    spells: dict[str, dict] = {}
    for row in _ROW_SPLIT.split(wikitext):
        name, runes = _NAME_RE.search(row), _RUNES_RE.search(row)
        level = _LEVEL_RE.search(row)
        if not (name and runes and level):
            continue
        cost = {}
        for part in runes.group(1).split("|"):
            if "=" in part:
                rune, qty = (x.strip() for x in part.split("=", 1))
                if qty.isdigit():
                    cost[f"{rune} rune"] = int(qty)
        members = _MEMBERS_RE.search(row)
        spells.setdefault((name.group(1) or name.group(2)).strip(), {
            "book": book,
            "level": int(level.group(1)),
            "runes": cost,
            "members": (members.group(1).lower() == "yes") if members else None,
        })
    return spells


_PLINK_RE = re.compile(r"\{\{plink[tp]?\|([^}|]+)")


def rune_sources() -> dict[str, list[str]]:
    """Elemental rune -> the combination runes and staves that also supply it."""
    sources: dict[str, list[str]] = {r: [] for r in ELEMENTS}

    def add(rune: str, item: str) -> None:
        if item != rune and item not in sources[rune]:
            sources[rune].append(item)

    # Combination rune table: "| {{plinkt|Mist rune|...}} | {{plinkp|Air rune}} {{plinkp|Water rune}} ... | {{plinkt|Mist battlestaff}}"
    combo_of: dict[str, list[str]] = {}
    for row in _ROW_SPLIT.split(_fetch_wikitext("Combination rune")):
        names = [n.strip() for n in _PLINK_RE.findall(row)]
        parts = [n for n in names if n in ELEMENTS]
        if names and names[0].endswith(" rune") and len(parts) == 2:
            combo_of[names[0]] = parts
    # Elemental staff price table: first plink is the rune, the rest are staves supplying it
    text = _fetch_wikitext("Elemental staff")
    for row in _ROW_SPLIT.split(text[text.find("==Price=="):]):
        names = [n.strip() for n in _PLINK_RE.findall(row)]
        if len(names) < 2:
            continue
        rune = names[0] if names[0].endswith(" rune") else names[1]
        staves = [n for n in names if n != rune and not n.endswith(" rune")]
        for element in ([rune] if rune in ELEMENTS else combo_of.get(rune, [])):
            if rune not in ELEMENTS:
                add(element, rune)
            for staff in staves:
                add(element, staff)
    for item, runes in EXTRA_SOURCES.items():
        for rune in runes:
            add(rune, item)
    return sources


def main() -> int:
    spells: dict[str, dict] = {}
    for book, page in BOOKS.items():
        found = parse_book(book, _fetch_wikitext(page))
        print(f"  {book:<9} {len(found):>3} spells")
        for k, v in found.items():
            spells.setdefault(k, v)
    _OUT.write_text(json.dumps(spells, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT} ({len(spells)} spells)")
    sources = rune_sources()
    _SOURCES_OUT.write_text(json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_SOURCES_OUT} ({sum(map(len, sources.values()))} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
