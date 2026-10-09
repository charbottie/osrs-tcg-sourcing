"""Generate bosses.json — every boss encounter in the planner, with requirements in
the same model as quests (see preview.html `_expandReq`).

Sources:
  - The OSRS Wiki "Boss" page tables (world / Wilderness / instanced / slayer /
    minigame / skilling bosses and raids): location, quest + skill requirements,
    collection log. These are re-read on every run.
  - scripts/boss_curated.json — what the wiki tables don't say: which encounter a
    wiki boss row belongs to (Barrows = six brothers, raids = their rooms), the
    monsters you must kill, kill-count monsters, entry items, tools, access area,
    optional items, notes, list category. Edit this file, not the output.

Output: scripts/output/bosses.json
  [ { name, category, sub?, area?, note?, location, members?, wikiBosses:[…],
      quests:[…], levels:{Skill: n}, requirements:[ {label, type, cards, mode?,
      optional?, routes?, access?, spells?, tool?, group?, note?} ], lootFrom?, relatedCards? } ]
Also prints a validation report (and writes scripts/cache/boss_validation.json):
wiki boss rows not covered by any encounter, quests/skills the wiki lists that the
curated entry lacks (reported, not merged — the wiki table mixes in alternatives),
and card names that don't resolve.

Usage:
  python3 scripts/generate_bosses.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from generate_diaries import _fetch_wikitext

_HERE = Path(__file__).resolve().parent
_CURATED = _HERE / "boss_curated.json"
_OUT = _HERE / "output" / "bosses.json"
_REPORT = _HERE / "cache" / "boss_validation.json"

# Curated `area` → access_routes.json key. Areas with no gate (Kandarin, the open world) map to None.
AREA_ACCESS = {
    "Morytania": "morytania", "Kourend": "kourend", "Varlamore": "varlamore", "Fossil Island": "fossil_island",
    "Ape Atoll": "ape_atoll", "Prifddinas": "prifddinas", "Tirannwn": "tirannwn", "Mos Le Harmless": "mos_le_harmless",
    "Waterbirth Island": "waterbirth", "Desert": "desert", "Sophanem": "sophanem", "Wilderness": "wilderness",
    "Zanaris": "zanaris", "Abyss": "abyss", "Kandarin": None,
}
DT2_QUEST = "Desert Treasure II - The Fallen Empire"

# Wiki sections that aren't planner boss encounters (quest bosses live on the Questing tab)
SKIP_SECTIONS = {"Quest bosses", "Quests with multiple bosses", "Event bosses", "Nightmare Zone", "See also", "List of bosses"}

_SCP_RE = re.compile(r"\{\{SCP\|([A-Za-z]+)\|(\d+)")
_QUEST_RE = re.compile(r"\{\{SCP\|Quest\}\}\s*(?:\[\[([^\]|]+)(?:\|[^\]]*)?\]\])?")
_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_PLINK_RE = re.compile(r"\{\{[Pp]link\|([^}|]+)")


def _clean(text: str) -> str:
    text = re.sub(r"\{\{efn[^}]*\}\}", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^/]*/>", "", text, flags=re.S)
    return text


def parse_boss_tables(wikitext: str) -> list[dict]:
    """One dict per boss row: name, section, location, solo, quests, levels, other, log."""
    rows: list[dict] = []
    section = None
    for part in re.split(r"\n(=+[^=\n]+=+)[ \t]*(?=\n)", wikitext):
        head = re.fullmatch(r"(=+)([^=]+)\1", part.strip())
        if head:
            section = head.group(2).strip()
            continue
        if section in SKIP_SECTIONS or section is None:
            continue
        for table in re.findall(r"\{\|.*?\n\|\}", part, flags=re.S):
            header = re.search(r"\n!(.*?)\n\|-", table, flags=re.S)
            cols: list[str] = []
            for h in re.split(r"\n!|!!", header.group(1)) if header else []:
                span = re.search(r"colspan\s*=\s*\"?(\d+)", h)
                label = h.split("|")[-1].strip()
                cols += [label] * (int(span.group(1)) if span else 1)
            for row in table.split("\n|-")[1:]:
                cells = [c.strip() for c in re.split(r"\n\|(?![}-])", row)[1:]]
                if not cells or not cells[0].startswith("[["):
                    continue
                cell = {cols[i] if i < len(cols) else str(i): _clean(c) for i, c in enumerate(cells)}
                req = cell.get("Requirements", "")
                # A row can hold several bosses ("[[Calvar'ion]] &<br/>[[Vet'ion]]")
                for name in [n.strip() for n in _LINK_RE.findall(cells[0]) if not n.startswith("File:")]:
                  rows.append({
                    "name": name,
                      "section": section,
                      "location": [l for l in _LINK_RE.findall(cell.get("Location", "")) if not l.startswith("File:")],
                      "solo": cell.get("Solo only", "").strip() or None,
                      "quests": [q for q in _QUEST_RE.findall(req) if q],
                      "levels": {s: int(n) for s, n in _SCP_RE.findall(req) if s not in ("Combat", "Quest")},
                      "otherReq": re.sub(r"\s+", " ", re.sub(r"\{\{SCP\|[^}]*\}\}|<br\s*/?>", " ", req)).strip(),
                      "log": [p.strip() for p in _PLINK_RE.findall(cell.get("Collection log", ""))],
                  })
    return rows


def load_card_names(card_json: str) -> tuple[set[str], dict[str, str]]:
    cat = json.loads(Path(card_json).read_text(encoding="utf-8"))
    names = {x["name"].lower() for k in ("items", "npcs") for x in cat[k]}
    aliases_path = _HERE / "output" / "card_aliases.json"
    aliases = json.loads(aliases_path.read_text(encoding="utf-8")) if aliases_path.exists() else {}
    return names, aliases


def build(card_json: str) -> tuple[list[dict], dict]:
    curated = json.loads(_CURATED.read_text(encoding="utf-8"))
    wiki_rows = parse_boss_tables(_fetch_wikitext("Boss"))
    by_name = {r["name"].lower(): r for r in wiki_rows}
    names, aliases = load_card_names(card_json)
    is_card = lambda n: n.lower() in names or n.lower() in aliases

    report = {"uncoveredWikiBosses": [], "wikiOnly": [], "unknownCards": [], "unknownWikiRefs": []}
    covered: set[str] = set()
    out = []
    for enc in curated["encounters"]:
        wb = enc.get("wikiBosses") or [enc["name"]]
        rows = []
        for n in wb:
            r = by_name.get(n.lower())
            if r:
                rows.append(r)
                covered.add(n.lower())
            elif enc.get("wikiBosses"):
                report["unknownWikiRefs"].append(f'{enc["name"]}: {n}')
        e = dict(enc)
        e["wikiBosses"] = [r["name"] for r in rows]
        e["location"] = sorted({l for r in rows for l in r["location"]})
        # Quests + skill levels stay as curated (the wiki table mixes in alternatives, e.g.
        # "Agility 85 or a rune thrownaxe"); differences are reported for review instead.
        quests = list(enc.get("quests", []))
        levels = dict(enc.get("levels", {}))
        for r in rows:
            for q in r["quests"]:
                if q not in quests:
                    report["wikiOnly"].append(f'{enc["name"]}: quest {q}')
            for s, n in r["levels"].items():
                if levels.get(s, 0) < n:
                    report["wikiOnly"].append(f'{enc["name"]}: {s} {levels.get(s, "-")} (wiki {n})')
        # Area → a shared access requirement at the top; "DT2" is a quest gate
        area = enc.get("area")
        if area == "DT2":
            if DT2_QUEST not in quests:
                quests.append(DT2_QUEST)
        elif area:
            if area not in AREA_ACCESS:
                report["unknownWikiRefs"].append(f'{enc["name"]}: unknown area {area}')
            elif AREA_ACCESS[area]:
                e["requirements"] = [{"label": f"Reach {area}", "access": AREA_ACCESS[area], "type": "item"}] + list(enc.get("requirements", []))
        e["quests"], e["levels"] = quests, levels
        e["wikiRequirementText"] = [f'{r["name"]}: {r["otherReq"]}' for r in rows if r["otherReq"]]
        for req in e.get("requirements", []) + e.get("lootRequirements", []):
            for c in req.get("cards", []):
                for n in (c if isinstance(c, list) else [c]):
                    if not is_card(n):
                        report["unknownCards"].append(f'{enc["name"]}: {n}')
        out.append(e)
    report["uncoveredWikiBosses"] = [f'{r["name"]} ({r["section"]})' for r in wiki_rows if r["name"].lower() not in covered]
    return out, report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    data, report = build(args.card_json)
    _OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT} ({len(data)} encounters)")
    for k, v in report.items():
        print(f"  {k}: {len(v)}")
        for x in v[:60]:
            print("    -", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
