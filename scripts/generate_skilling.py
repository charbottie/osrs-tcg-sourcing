"""Generate skilling.json — training methods for the skills that aren't covered by item
gathering/production data: Agility courses, Thieving (pickpockets, stalls, other), Hunter,
Prayer (bones / ashes), Firemaking (logs, pyres, Wintertodt) and Ranged (weapon + the ammo
it can fire).

Source: scripts/skilling_curated.json — built from the OSRS Wiki (each method keeps a short
wiki quote and its page), in the shared requirement model:
  {skill, name, level, xp, type, requirements: [{label, type, cards, mode?, optional?, tool?, note?}],
   quests, levels, access, note, wiki, page}
This script validates card names (catalog or card_aliases.json versions), quest names
(quests.json), access keys (access_routes.json) and writes the output.

Output: scripts/output/skilling.json   (list of methods)

Usage:
  python3 scripts/generate_skilling.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CURATED = _HERE / "skilling_curated.json"
_OUT = _HERE / "output" / "skilling.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    methods = json.loads(_CURATED.read_text(encoding="utf-8"))
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    names = {x["name"].lower() for k in ("items", "npcs") for x in cat[k]}
    aliases = json.loads((_HERE / "output" / "card_aliases.json").read_text(encoding="utf-8"))
    quests = set(json.loads((_HERE / "output" / "quests.json").read_text(encoding="utf-8")))
    access = set(json.loads((_HERE / "output" / "access_routes.json").read_text(encoding="utf-8")))
    diary_areas = {a["name"] for a in json.loads((_HERE / "output" / "diaries.json").read_text(encoding="utf-8"))}
    problems = []
    for m in methods:
        for r in m.get("requirements", []):
            for c in r.get("cards", []):
                for n in (c if isinstance(c, list) else [c]):
                    if n.lower() not in names and n.lower() not in aliases:
                        problems.append(f"{m['skill']} / {m['name']}: card {n!r}")
        for q in m.get("quests", []) + m.get("partialQuests", []):
            if q not in quests:
                problems.append(f"{m['skill']} / {m['name']}: quest {q!r}")
        for dk in m.get("diaries", []):
            area, _, tier = dk.rpartition(" ")
            if area not in diary_areas or tier not in ("Easy", "Medium", "Hard", "Elite"):
                problems.append(f"{m['skill']} / {m['name']}: diary {dk!r}")
        if m.get("access") and m["access"] not in access:
            problems.append(f"{m['skill']} / {m['name']}: access {m['access']!r}")
    _OUT.write_text(json.dumps(methods, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT}: {len(methods)} methods", dict(Counter(m["skill"] for m in methods)))
    for x in problems:
        print("  ! " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
