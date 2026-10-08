"""Generate spells.json — every spell's level and rune cost, from the OSRS Wiki
spellbook pages (Standard, Ancient, Lunar, Arceuus).

Central source for anything that needs to know what a spell costs: diary
"cast X" tasks (generate_diaries.py) and the Magic skilling tab.

Output: scripts/output/spells.json
  { "<Spell name>": { book, level, runes: {"Law rune": 1, ...}, members } }

Usage:
  python3 scripts/generate_spells.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from generate_diaries import _fetch_wikitext

_OUT = Path(__file__).resolve().parent / "output" / "spells.json"

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


def main() -> int:
    spells: dict[str, dict] = {}
    for book, page in BOOKS.items():
        found = parse_book(book, _fetch_wikitext(page))
        print(f"  {book:<9} {len(found):>3} spells")
        for k, v in found.items():
            spells.setdefault(k, v)
    _OUT.write_text(json.dumps(spells, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT} ({len(spells)} spells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
