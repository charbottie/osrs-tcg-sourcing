"""Shared access to scripts/location_requirements.json (entry requirements of places).

Used by generate_monster_locations.py, generate_slayer.py, generate_skilling.py and
generate_clue_steps.py; the planner (preview.html) reads the same file and evaluates it with
_locGate() / _locReqOk(), using the same merge rules as merge_gate() below.

  load()            -> {name: entry} (no "_" keys)
  lookup(name)      -> the entry for a location name (case-insensitive) or None
  gate_for(name)    -> the full gate for a place: its own fields plus its parent chain's
  merge_gate(a, b)  -> a gate meeting both (idempotent: merging the same gate twice changes nothing)
  validate(...)     -> list of problems (unknown quests / cards / diaries / access keys / parents)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
PATH = _HERE / "location_requirements.json"
# Fields that make up a gate (everything else is metadata: note / wiki / page / boostable / clueMatch)
GATE_KEYS = ("quests", "partialQuests", "diaries", "cards", "cardGroup", "skills", "skillsSum",
             "questPoints", "access", "anyOf", "allOf")
CARD_GROUPS = {"light_source", "tool:Axe", "tool:Pickaxe"}
_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
        _cache = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _cache


def reviewed_no_gate() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8")).get("_reviewedNoGate", {})


def _index() -> dict:
    return {k.lower(): k for k in load()}


def lookup(name: str) -> dict | None:
    k = _index().get((name or "").lower())
    return load()[k] if k else None


def own_gate(entry: dict) -> dict:
    return {k: entry[k] for k in GATE_KEYS if entry.get(k) not in (None, [], {}, "")}


def gate_for(name: str, _seen: set | None = None) -> dict:
    """The gate of a place, including every parent it sits inside."""
    e = lookup(name)
    if not e:
        return {}
    seen = _seen or set()
    if name.lower() in seen:
        return {}
    seen.add(name.lower())
    g = own_gate(e)
    if e.get("parent"):
        g = merge_gate(gate_for(e["parent"], seen), g)
    return g


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def merge_gate(a: dict | None, b: dict | None) -> dict:
    """A gate that needs both a and b. Lists of quests/diaries union; skills take the higher level;
    'cards' (any one) and 'anyOf' can't be unioned without weakening them, so a second, different
    list moves into allOf. Merging a gate into itself returns it unchanged."""
    out = json.loads(json.dumps(a or {}))
    for k, v in (b or {}).items():
        if v in (None, [], {}, ""):
            continue
        if k not in out:
            out[k] = json.loads(json.dumps(v))
        elif k in ("quests", "partialQuests", "diaries"):
            out[k] = list(dict.fromkeys(out[k] + v))
        elif k in ("skills", "skillsSum"):
            out[k] = {**out[k], **{s: max(l, out[k].get(s, 0)) for s, l in v.items()}}
        elif k == "questPoints":
            out[k] = max(out[k], v)
        elif k == "allOf":
            out[k] = out[k] + [x for x in v if not any(_same(x, y) for y in out[k])]
        elif _same(out[k], v):
            continue
        else:   # cards / cardGroup / anyOf / access that differ: both must hold
            extra = {k: v}
            out.setdefault("allOf", [])
            if not any(_same(extra, y) for y in out["allOf"]):
                out["allOf"].append(extra)
    if "partialQuests" in out and "quests" in out:   # a completed quest also covers "started"
        out["partialQuests"] = [q for q in out["partialQuests"] if q not in out["quests"]]
        if not out["partialQuests"]:
            del out["partialQuests"]
    return out


def validate(quests: set[str], card_ok, diary_areas: set[str], access: set[str]) -> list[str]:
    """card_ok(name) -> bool. Returns problems as strings."""
    probs = []
    names = load()

    def check(where: str, g: dict):
        for q in g.get("quests", []) + g.get("partialQuests", []):
            if q not in quests:
                probs.append(f"{where}: quest {q!r}")
        for c in g.get("cards", []):
            if not card_ok(c):
                probs.append(f"{where}: card {c!r}")
        if g.get("cardGroup") and g["cardGroup"] not in CARD_GROUPS:
            probs.append(f"{where}: cardGroup {g['cardGroup']!r}")
        for d in g.get("diaries", []):
            area, _, tier = d.rpartition(" ")
            if area not in diary_areas or tier not in ("Easy", "Medium", "Hard", "Elite"):
                probs.append(f"{where}: diary {d!r}")
        if g.get("access") and g["access"] not in access:
            probs.append(f"{where}: access {g['access']!r}")
        for s in list(g.get("skills", {})) + [x for k in g.get("skillsSum", {}) for x in k.split("+")]:
            if s not in SKILLS:
                probs.append(f"{where}: skill {s!r}")
        for sub in g.get("anyOf", []) + g.get("allOf", []):
            check(where + " (sub-gate)", sub)

    for name, e in names.items():
        unknown = set(e) - set(GATE_KEYS) - {"parent", "boostable", "clueMatch", "note", "wiki", "page"}
        if unknown:
            probs.append(f"{name}: unknown keys {sorted(unknown)}")
        if e.get("parent") and not lookup(e["parent"]) and e["parent"] not in reviewed_no_gate():
            probs.append(f"{name}: parent {e['parent']!r} is not a location here")
        if not own_gate(e) and not e.get("parent"):
            probs.append(f"{name}: no gate fields")
        if e.get("clueMatch"):
            try:
                re.compile(e["clueMatch"])
            except re.error as ex:
                probs.append(f"{name}: clueMatch {ex}")
        check(name, own_gate(e))
    return probs


SKILLS = {"Attack", "Strength", "Defence", "Ranged", "Prayer", "Magic", "Runecrafting", "Construction",
          "Hitpoints", "Agility", "Herblore", "Thieving", "Crafting", "Fletching", "Slayer", "Hunter",
          "Mining", "Smithing", "Fishing", "Cooking", "Firemaking", "Woodcutting", "Farming", "Sailing"}


def validate_with_outputs() -> list[str]:
    """validate() against the committed outputs and the live catalog."""
    out = _HERE / "output"
    quests = set(json.loads((out / "quests.json").read_text(encoding="utf-8")))
    diary_areas = {a["name"] for a in json.loads((out / "diaries.json").read_text(encoding="utf-8"))}
    access = set(json.loads((out / "access_routes.json").read_text(encoding="utf-8")))
    cat = json.loads((_HERE.parent / "research" / "card-catalog-live.json").read_text(encoding="utf-8"))
    names = {x["name"].lower() for k in ("items", "npcs") for x in cat[k]}
    aliases = json.loads((out / "card_aliases.json").read_text(encoding="utf-8"))
    return validate(quests, lambda c: c.lower() in names or c.lower() in aliases, diary_areas, access)


if __name__ == "__main__":
    ps = validate_with_outputs()
    print(f"{len(load())} locations, {len(ps)} problems")
    for p in ps:
        print("  ! " + p)
    raise SystemExit(1 if ps else 0)
