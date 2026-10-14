"""Generate skilling.json — training methods for the skills that aren't covered by item
gathering/production data: Agility courses, Thieving (pickpockets, stalls, other), Hunter,
Prayer (bones / ashes), Firemaking (logs, pyres, Wintertodt) and Ranged (weapon + the ammo
it can fire).

Source: scripts/skilling_curated.json — built from the OSRS Wiki (each method keeps a short
wiki quote and its page), in the shared requirement model:
  {skill, name, level, xp, type, requirements: [{label, type, cards, mode?, optional?, tool?, note?}],
   quests, levels, access, location?, note, wiki, page, outputs?}
  location = a place in location_requirements.json whose entry gate the planner also applies
  (e.g. "Farming Guild (advanced tier)" → 85 Farming).
Gathering methods (type "gathering") also list the cards they yield:
  outputs: ["Woad leaf", {"card": "Raw shark", "level": 70}, {"card": "Oak roots", "levels": {"Woodcutting": 15}, "tool": "Axe"}]
  (a string = at the method's level; an object adds its own level in the method's skill, other skill
  levels or a TOOL_TIERS tool). [] = yields no card (canoes, Tithe Farm, anima plants…). Farming
  outputs are the wiki's {{Farming info}} |crop=; the rest the method page's drop table or name.
  The card page lists each method under "Gathering" and canGetItem counts it as a source.
This script validates card names (catalog or card_aliases.json versions), quest names
(quests.json), access keys (access_routes.json) and writes the output.

Output: scripts/output/skilling.json   (list of methods)

Usage:
  python3 scripts/generate_skilling.py --card-json research/card-catalog-live.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import location_reqs

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
            for c in r.get("cards", []) + [c for rt in r.get("routes", []) for c in rt.get("cards", [])]:
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
        if m.get("type") == "gathering":
            if not isinstance(m.get("outputs"), list):
                problems.append(f"{m['skill']} / {m['name']}: gathering method without outputs")
            for o in m.get("outputs") or []:
                n = o if isinstance(o, str) else o.get("card", "")
                if n.lower() not in names and n.lower() not in aliases:
                    problems.append(f"{m['skill']} / {m['name']}: output {n!r} is not a card")
                if isinstance(o, dict) and set(o) - {"card", "level", "levels", "tool"}:
                    problems.append(f"{m['skill']} / {m['name']}: output {n!r} has unknown keys")
        if m.get("access") and m["access"] not in access:
            problems.append(f"{m['skill']} / {m['name']}: access {m['access']!r}")
        # "location": a place in location_requirements.json; the planner applies its gate
        # (guild levels, Sailing level to dock, worn items…) on top of the method's own fields
        if m.get("location") and not location_reqs.lookup(m["location"]):
            problems.append(f"{m['skill']} / {m['name']}: location {m['location']!r} not in location_requirements.json")
    _OUT.write_text(json.dumps(methods, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT}: {len(methods)} methods", dict(Counter(m["skill"] for m in methods)))
    gat = [m for m in methods if m.get("type") == "gathering"]
    print(f"  gathering: {len(gat)} methods, {sum(1 for m in gat if m.get('outputs'))} with card outputs")
    for x in problems:
        print("  ! " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
