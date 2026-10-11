"""Generate recipes.json — every XP-giving production recipe from the OSRS Wiki, for the Skilling
tab's production skills (Fletching, Smithing, Crafting, Cooking, Herblore, Construction,
Runecraft). Covers outputs with no TCG card too (e.g. Oak shortbow (u), POH furniture).

Source: the wiki's "recipe" Bucket (api.php?action=bucket), cached in cache/wiki_recipes.json
(delete it to refetch). Quest gates the wiki recipe data doesn't carry are taken from the
hand-checked production entries in item_sources.json / ingredient_info.json (same output + skill),
plus the rules in QUEST_RULES below.

Output: scripts/output/recipes.json   (list)
  {output, outputQuantity, skill, level, xp, ingredients: [{item, quantity}], tools: [..],
   facilities, members, levels: {other skill: level}, quests: [..], access?, page}

Usage:
  python3 scripts/generate_recipes.py
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "cache" / "wiki_recipes.json"
_OUT = _HERE / "output" / "recipes.json"

SKILLS = {"Fletching", "Smithing", "Crafting", "Cooking", "Herblore", "Construction", "Runecraft"}
SKILL_NAME = {"Runecraft": "Runecrafting"}
# Quest gates by output pattern (OSRS Wiki): barbarian mixes need Barbarian Training (Barbarian Herblore)
QUEST_RULES = [(re.compile(r" mix\(\d\)$"), "Herblore", ["Barbarian Training"])]
# Gates that come with a facility (OSRS Wiki): totem sites are the Vale Totems minigame in Varlamore
FACILITY_GATES = {"Totem site": {"quests": ["Vale Totems"], "access": "varlamore"}}
# Construction facilities that aren't in a player-owned house
NON_POH = {"Boat schematics": "sailing", "Shipwrights' Workbench": None, "Shipwright's Workbench": None,
           "Old fire pit": None, "Hole (Crab trapping)": None}


def fetch() -> list[dict]:
    if _CACHE.exists():
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    out, off = [], 0
    while True:
        q = f"bucket('recipe').select('page_name','production_json').limit(500).offset({off}).run()"
        url = "https://oldschool.runescape.wiki/api.php?action=bucket&format=json&query=" + urllib.parse.quote(q)
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            b = json.loads(r.read())["bucket"]
        out += b
        off += 500
        if len(b) < 500:
            break
        time.sleep(1)
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


def _plain(s) -> str:
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    s = re.sub(r"\[\[File:[^\]]*\]\]", "", s)
    return re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s).strip()


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def merge_alternatives(recipes: list[dict]) -> list[dict]:
    """Recipes that are the same apart from one interchangeable ingredient (feather colours on
    arrows/bolts/darts, the bow offered at a Vale totem…) become one recipe whose ingredient has
    "alts": [any one of these]. Same output, skill, level, xp, tools, facility and gates only."""
    groups: dict[tuple, list[dict]] = {}
    for m in recipes:
        k = (m["output"], m["skill"], m["level"], m["xp"], tuple(m["tools"]), m["facilities"],
             tuple(m["quests"]), m.get("access"), len(m["ingredients"]))
        groups.setdefault(k, []).append(m)
    out = []
    for ms in groups.values():
        while ms:
            base, rest = ms[0], ms[1:]
            slot, same = None, [base]
            for m in rest:
                diff = [i for i, (a, b) in enumerate(zip(base["ingredients"], m["ingredients"]))
                        if a["item"] != b["item"] or a["quantity"] != b["quantity"]]
                ok = len(diff) == 1 and base["ingredients"][diff[0]]["quantity"] == m["ingredients"][diff[0]]["quantity"]
                if ok and (slot is None or diff[0] == slot):
                    slot = diff[0]
                    same.append(m)
            if len(same) > 1:
                merged = {**base, "ingredients": [dict(i) for i in base["ingredients"]]}
                merged["ingredients"][slot]["alts"] = list(dict.fromkeys(m["ingredients"][slot]["item"] for m in same))
                out.append(merged)
            else:
                out.append(base)
            ms = [m for m in rest if m not in same]
    return out


def main() -> int:
    rows = fetch()
    known = {}
    for f in (_HERE / "output" / "item_sources.json", _HERE / "ingredient_info.json"):
        for name, v in json.loads(f.read_text(encoding="utf-8")).items():
            ps = v.get("production")
            for p in (ps if isinstance(ps, list) else [ps] if ps else []):
                if p.get("quests"):
                    known.setdefault((name, p.get("skill")), set()).update(p["quests"])
    out, seen = [], set()
    for r in rows:
        p = json.loads(r["production_json"])
        o = p.get("output")
        o = o[0] if isinstance(o, list) and o else o
        if not isinstance(o, dict) or not o.get("name"):
            continue  # gathering entries (rocks, trees…) have no output
        name = o["name"]
        skills = p.get("skills") or []
        for s in skills:
            sk = s.get("name", "").capitalize() if s.get("name", "").lower() == "cooking" else s.get("name", "")
            xp = _num(s.get("experience") or 0)
            if sk not in SKILLS or not xp or xp <= 0:
                continue  # formula xp (e.g. "1×Construction level") is covered by skilling_curated
            skill = SKILL_NAME.get(sk, sk)
            if skill == "Cooking" and name.lower().startswith("burnt"):
                continue
            ings = [{"item": m["name"], "quantity": _num(m.get("quantity")) or 1} for m in p.get("materials") or [] if m.get("name")]
            tools = [t.strip() for t in _plain(p.get("tools")).split(",") if t.strip() and t.strip().lower() != "none"]
            fac = _plain(p.get("facilities")) or None
            key = (name, skill, tuple(sorted((i["item"], i["quantity"]) for i in ings)), fac)
            if key in seen:
                continue
            seen.add(key)
            m = {"output": name, "outputQuantity": _num(o.get("quantity")) or 1, "skill": skill,
                 "level": int(_num(s.get("level")) or 1), "xp": xp, "ingredients": ings, "tools": tools,
                 "facilities": fac, "members": bool(p.get("members")),
                 "levels": {SKILL_NAME.get(x["name"], x["name"]): int(_num(x.get("level")) or 1)
                            for x in skills if x is not s and x.get("name") and (_num(x.get("level")) or 0) > 1},
                 "quests": sorted(known.get((name, skill), set())), "page": r["page_name"]}
            for pat, rsk, qs in QUEST_RULES:
                if rsk == skill and pat.search(name):
                    m["quests"] = sorted(set(m["quests"]) | set(qs))
            fg = FACILITY_GATES.get(fac)
            if fg:
                m["quests"] = sorted(set(m["quests"]) | set(fg.get("quests", [])))
                if fg.get("access"):
                    m["access"] = fg["access"]
            if skill == "Construction":
                if fac in NON_POH:
                    if NON_POH[fac]:
                        m["access"] = NON_POH[fac]
                else:
                    m["access"] = "house"  # built in a player-owned house (no facility, or a "… space" hotspot)
            out.append(m)
    out = merge_alternatives(out)
    out.sort(key=lambda m: (m["skill"], m["level"], m["output"]))
    _OUT.write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT}: {len(out)} recipes", dict(Counter(m["skill"] for m in out)))
    print("  with quests:", sum(1 for m in out if m["quests"]), "· POH (house):", sum(1 for m in out if m.get("access") == "house"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
