"""Generate slayer.json — Slayer masters, their task lists and every monster that counts
for each task, from the OSRS Wiki.

Sources (re-read each run, cached in scripts/cache/wikitext/):
  - Each master's page or its "<Master>/Slayer assignments" subpage: the task table
    (amount, extended amount, unlock requirement, alternatives, weight; Konar's locations).
  - "Slayer task/<Task>" pages: the Infobox Slayer requirements and the Monster Variants
    table (every monster that counts, with its locations).
  - scripts/slayer_curated.json: what the wiki doesn't state as data — master replacements
    (Aya after While Guthix Sleeps…), required Slayer equipment per task, and which
    locations need area access (access_routes.json keys).

Output: scripts/output/slayer.json
  { masters: [{name, cards, replaces?, requirements: {combat, slayer, quests}, notes, wilderness?,
               tasks: [{task, weight, amount, extended, unlock: {slayer, combat, quests, ability}, alternatives, locations?}]}],
    tasks: {<task>: {page, slayer, combat, otherReq, monsters: [{name, card, locations, locationAccess: {loc: access key | null}}], equipment}},
    unlocks: [ability names that unlock tasks] }
Also writes scripts/cache/slayer_validation.json: monsters with no card, task pages not found.

Usage:
  python3 scripts/generate_slayer.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from generate_diaries import _fetch_wikitext

_HERE = Path(__file__).resolve().parent
_CURATED = _HERE / "slayer_curated.json"
_OUT = _HERE / "output" / "slayer.json"
_REPORT = _HERE / "cache" / "slayer_validation.json"

_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]([a-z]*)")
_SCP_RE = re.compile(r"\{\{SCP\|([A-Za-z]+)\|(\d+)")
_WEIGHT_RE = re.compile(r"\{\{\+=\|weight\|(\d+)|^\s*(\d+)\s*$")


def _clean(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", "", text)  # self-closing refs first, or the paired pattern swallows rows
    text = re.sub(r"<ref[^>]*>.*?</ref>|\{\{Cite[^}]*\}\}|\{\{CiteTwitter[^}]*\}\}|\{\{efn[^}]*\}\}|\{\{note\|[^}]*\}\}", "", text, flags=re.S)
    return text


def _cells(row: str) -> list[str]:
    out = []
    for c in re.split(r"\n\|(?![}-])|\|\|", row)[1:]:
        c = re.sub(r"^\s*(?:data-sort-value=\"[^\"]*\"|style=\"[^\"]*\"|class=\"[^\"]*\")\s*\|", "", c.strip())
        out.append(c.strip())
    return out


def _tables_with(text: str, col: str) -> list[tuple[list[str], list[list[str]]]]:
    found = []
    for table in re.findall(r"\{\|.*?\n\|\}", _clean(text), flags=re.S):
        header = re.search(r"\n!(.*?)\n\|-", table, flags=re.S)
        if not header:
            continue
        cols = []
        for h in re.split(r"\n!|!!", header.group(1)):
            span = re.search(r"colspan\s*=\s*\"?(\d+)", h)
            label = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]|\[\[([^\]]*)\]\]", lambda m: m.group(1) or m.group(2), h.split("|")[-1]).strip()
            cols += [label] * (int(span.group(1)) if span else 1)
        if not any(col.lower() in c.lower() for c in cols):
            continue
        rows = [_cells(r) for r in table.split("\n|-")[1:]]
        found.append((cols, [r for r in rows if r]))
    return found


def _col(cols: list[str], row: list[str], *names: str) -> str:
    for n in names:
        for i, c in enumerate(cols):
            if n.lower() in c.lower() and i < len(row):
                return row[i]
    return ""


def _task_name(cell: str) -> tuple[str, str]:
    """'[[Aberrant spectre]]s' → ('Aberrant spectres', 'Aberrant spectre')."""
    m = _LINK_RE.search(cell)
    if not m:
        return re.sub(r"[\[\]']", "", cell).strip(), ""
    target, disp, suffix = m.group(1).strip(), (m.group(2) or m.group(1)).strip(), m.group(3)
    return disp + suffix, target


def _parse_unlock(cell: str, quests: set[str]) -> dict:
    out = {}
    for skill, lvl in _SCP_RE.findall(cell):
        if skill in ("Slayer", "Combat"):
            out[skill.lower()] = int(lvl)
    qs = [l for l, *_ in _LINK_RE.findall(cell) if l in quests]
    if qs:
        out["quests"] = qs
    ab = re.findall(r"''([^']+)''", cell)
    if ab:
        out["ability"] = ab[0].strip()
    return out


def parse_master(name: str, quests: set[str]) -> list[dict]:
    text = ""
    for page in (f"{name}/Slayer assignments", name):
        try:
            text = _fetch_wikitext(page)
        except Exception:
            continue
        if _tables_with(text, "Weight"):
            break
    tasks = []
    for cols, rows in _tables_with(text, "Weight"):
        for r in rows:
            task, target = _task_name(r[0])
            wm = _WEIGHT_RE.search(_col(cols, r, "Weight"))
            if not task or not wm:
                continue
            alts = [l for l, *_ in _LINK_RE.findall(_col(cols, r, "Alternative"))]
            locs = [l for l, *_ in _LINK_RE.findall(_col(cols, r, "location"))]
            t = {"task": task, "target": target, "weight": int(wm.group(1) or wm.group(2)),
                 "amount": re.sub(r"\s+", " ", re.sub(r"\{\{[^}]*\}\}", "", _col(cols, r, "Amount"))).strip(),
                 "extended": re.sub(r"\s+", " ", _col(cols, r, "Extended")).strip(),
                 "unlock": _parse_unlock(_col(cols, r, "Unlock", "Requirement"), quests),
                 "alternatives": alts}
            if locs:
                t["locations"] = locs
            tasks.append(t)
    return tasks


def _fetch_follow(page: str) -> tuple[str, str]:
    """Wikitext of a page, following up to 2 #REDIRECTs; returns (final page, text)."""
    for _ in range(3):
        text = _fetch_wikitext(page)
        m = re.match(r"\s*#REDIRECT\s*\[\[([^\]#|]+)", text, flags=re.I)
        if not m:
            return page, text
        page = m.group(1).strip()
    return page, text


def parse_task_page(task: str, target: str) -> dict | None:
    target = target.replace("Slayer task/", "")
    cands = [task, task[:1].upper() + task[1:].lower(), f"{target}s", target, re.sub(r"s$", "", task)]
    for cand in dict.fromkeys(cands):
        try:
            page, text = _fetch_follow(f"Slayer task/{cand}")
        except Exception:
            continue
        if "Infobox Slayer" not in text and "Monster Variants" not in text:
            continue
        info = re.search(r"\{\{Infobox Slayer(.*?)\n\}\}", text, flags=re.S)
        params = {}
        if info:
            for line in info.group(1).split("\n|")[1:]:
                if "=" in line:
                    k, v = line.split("=", 1)
                    params[k.strip()] = v.strip()
        lv = lambda v: int(m.group(1)) if (m := re.search(r"(\d+)", v or "")) else None
        monsters = []
        sec = text[text.find("==Monster Variants=="):] if "==Monster Variants==" in text else text
        for cols, rows in _tables_with(sec, "Monster")[:1]:
            for r in rows:
                m = _LINK_RE.search(r[0])
                if not m or m.group(1).startswith("Slayer task/"):
                    continue
                locs = [l for l, *_ in _LINK_RE.findall(_col(cols, r, "Location"))]
                monsters.append({"name": m.group(1).strip(), "locations": locs})
        return {"page": page, "slayer": lv(params.get("skillreq")), "combat": lv(params.get("combatreq")),
                "otherReq": [l for l, *_ in _LINK_RE.findall(params.get("otherreq", ""))], "monsters": monsters}
    return None


# Wiki location region (Infobox Location "leagueRegion") → access_routes.json key.
# Regions with no entry need nothing to reach. Specific places override this in
# slayer_curated.json "locationAccess" (e.g. Fossil Island, Prifddinas, Ape Atoll).
REGION_ACCESS = {"Morytania": "morytania", "Kourend": "kourend", "Varlamore": "varlamore",
                 "Desert": "desert", "Tirannwn": "tirannwn"}
_REGION_CACHE = _HERE / "cache" / "location_regions.json"


def location_regions(titles: list[str]) -> dict[str, str]:
    """location page → leagueRegion (first one), batched 50 per request, cached."""
    import time, urllib.parse, urllib.request
    cache = json.loads(_REGION_CACHE.read_text(encoding="utf-8")) if _REGION_CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=revisions"
               "&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read())["query"]
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            m = re.search(r"\|\s*leagueRegion\s*=(.*?)(?:\n\||\n\}\})", text, flags=re.S)
            found = re.findall(r"(Misthalin|Asgarnia|Kandarin|Karamja|Fremennik|Kourend|Varlamore|Morytania|Desert|Tirannwn|Wilderness)",
                               m.group(1) if m else "", flags=re.I)
            region = "&".join(dict.fromkeys(f.capitalize() for f in found))
            srcs = [pg["title"]] + back.get(pg["title"], [])
            for t in list(srcs):
                srcs += back.get(t, [])
            for t in srcs:
                cache[t] = region
        for t in batch:
            cache.setdefault(t, "")
        _REGION_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        time.sleep(1)
    return cache


_SLAYLVL_CACHE = _HERE / "cache" / "monster_slayer_levels.json"


def monster_slayer_levels(titles: list[str]) -> dict[str, int]:
    """monster page → Slayer level needed to attack it (Infobox Monster |slaylvl), batched + cached."""
    import time, urllib.parse, urllib.request
    cache = json.loads(_SLAYLVL_CACHE.read_text(encoding="utf-8")) if _SLAYLVL_CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=revisions"
               "&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read())["query"]
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            lv = [int(x) for x in re.findall(r"\|\s*slaylvl\d*\s*=\s*(\d+)", text)]
            srcs = [pg["title"]] + back.get(pg["title"], [])
            for t in list(srcs):
                srcs += back.get(t, [])
            for t in srcs:
                cache[t] = min(lv) if lv else 0   # lowest version's level (e.g. the base monster)
        for t in batch:
            cache.setdefault(t, 0)
        _SLAYLVL_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        time.sleep(1)
    return cache


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cur = json.loads(_CURATED.read_text(encoding="utf-8"))
    quests = set(json.loads((_HERE / "output" / "quests.json").read_text(encoding="utf-8")))
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    names = {x["name"].lower(): x["name"] for k in ("items", "npcs") for x in cat[k]}
    aliases = json.loads((_HERE / "output" / "card_aliases.json").read_text(encoding="utf-8"))
    card_of = lambda n: names.get(n.lower()) or aliases.get(n.lower())
    loc_override = cur.get("locationAccess", {})
    report = {"taskPagesMissing": [], "monstersNoCard": [], "unmappedLocations": {}}

    # Boss tasks ("Boss", "Bosses", "Wilderness bosses"): the boss is chosen when assigned,
    # so the task is "any boss on the list" — kept as its own entry, monsters = alternatives
    BOSS_TASKS = {"boss", "bosses", "wilderness bosses"}
    masters, task_names = [], {}   # task_names: lowercase → (canonical name, target)
    for m in cur["masters"]:
        tasks = parse_master(m["page"], quests)
        print(f"  {m['name']:<10} {len(tasks)} tasks")
        masters.append({**{k: v for k, v in m.items() if k != "page"}, "tasks": tasks})
        for t in tasks:
            # one key per task regardless of case or plural ("Bloodveld" / "Bloodvelds")
            key = "boss" if t["task"].lower() in BOSS_TASKS else re.sub(r"s$", "", t["task"].lower())
            canon = "Boss" if key == "boss" else t["task"][:1].upper() + t["task"][1:].lower()
            task_names.setdefault(key, (canon, t["target"]))
            t["task"] = task_names[key][0]
    tasks_out = {}
    pending = []
    for key, (task, target) in sorted(task_names.items()):
        if key == "boss":
            # "Boss Slayer" page: every assignable boss with its Slayer level + other requirements.
            # The planner judges each one by that boss's own status on the Bosses tab.
            bosses = []
            for cols, rows in _tables_with(_fetch_wikitext("Boss Slayer"), "Slayer level")[:1]:
                for r in rows:
                    m = re.search(r"\{\{ilinkt\|([^|}]+)", r[0]) or _LINK_RE.search(r[0])
                    if not m:
                        continue
                    # the Boss column spans 2 header cells but is 1 cell per row: read by position
                    lvl = re.search(r"\{\{SCP\|Slayer\|(\d+)", r[2] if len(r) > 2 else "")
                    other = r[3] if len(r) > 3 else ""
                    bosses.append({"name": m.group(1).strip(), "slayer": int(lvl.group(1)) if lvl else None,
                                   "quests": [l for l, *_ in _LINK_RE.findall(other) if l in quests],
                                   "locations": [], "locationAccess": {}})
            for b in bosses:
                b["card"] = card_of(b["name"]) or card_of(re.sub(r" brothers$", "", b["name"]))
            tasks_out[task] = {"page": "Boss Slayer", "boss": True, "monsters": bosses, "equipment": []}
            continue
        tp = parse_task_page(task, target)
        if tp and not tp["monsters"]:  # a task page with no Monster Variants table
            tp["monsters"] = [{"name": re.sub(r"s$", "", target.replace("Slayer task/", "")) or task, "locations": []}]
        if not tp:  # no "Slayer task/" page: the main monster plus the masters' listed alternatives
            report["taskPagesMissing"].append(task)
            alts = sorted({a for m in masters for t in m["tasks"] if t["task"] == task for a in t["alternatives"]})
            base = target.replace("Slayer task/", "")
            tp = {"page": None, "monsters": [{"name": n, "locations": []} for n in dict.fromkeys([base] + alts) if n]}
        pending.append((task, tp))
    regions = location_regions([l for _, tp in pending for mon in tp["monsters"] for l in mon["locations"]]
                               + [l for m in masters for t in m["tasks"] for l in t.get("locations", [])])
    def access_of(loc):
        if loc in loc_override:
            return loc_override[loc]
        # a place in several regions is reachable through whichever needs nothing
        rs = [r for r in regions.get(loc, "").split("&") if r]
        keys = [REGION_ACCESS.get(r) for r in rs]
        return None if not rs or None in keys else keys[0]
    for m in masters:  # Konar's per-task locations
        for t in m["tasks"]:
            if t.get("locations"):
                t["locationAccess"] = {l: access_of(l) for l in t["locations"]}
    for task, tp in pending:
        for mon in tp["monsters"]:
            mon["card"] = card_of(mon["name"]) or card_of(re.sub(r"\s*\(.*?\)\s*$", "", mon["name"]))
            if not mon["card"]:
                report["monstersNoCard"].append(f"{task}: {mon['name']}")
            # per location: its access key (None = nothing needed); the monster is reachable if any location is
            mon["locationAccess"] = {l: access_of(l) for l in mon["locations"]}
            for l in mon["locations"]:
                if not regions.get(l) and l not in loc_override:  # no region on the wiki page
                    report["unmappedLocations"][l] = report["unmappedLocations"].get(l, 0) + 1
        tp["equipment"] = cur.get("equipment", {}).get(task, [])
        tasks_out[task] = tp
    # ── Curated overrides from the wiki verification pass (pending ones wait for review) ──
    norm = lambda t: re.sub(r"s$", "", t.lower())
    by_key = {norm(t): t for t in tasks_out}
    for key, o in cur.get("taskOverrides", {}).items():
        task = by_key.get(key)
        if not task or o.get("pending"):
            continue
        tp = tasks_out[task]
        mons = tp["monsters"]
        drop = set(o.get("monstersRemove", []))   # exact names: "Kalphite worker" (a stray duplicate) ≠ "Kalphite Worker"
        if tp.get("page") is None and o.get("monstersAdd"):
            mons[:] = []                      # no task page: the verified list replaces the fallback
        mons[:] = [m for m in mons if m["name"] not in drop]
        for add in o.get("monstersAdd", []):
            ex = next((m for m in mons if m["name"].lower() == add["name"].lower()), None)
            if ex:
                ex["locations"] = list(dict.fromkeys(ex["locations"] + add.get("locations", [])))
                if add.get("card"):
                    ex["card"] = add["card"]
            else:
                mons.append({"name": add["name"], "card": add.get("card") or card_of(add["name"]), "locations": add.get("locations", [])})
        for name, locs in o.get("locationsAdd", {}).items():
            for m in mons:
                if m["name"].lower() == name.lower():
                    m["locations"] = list(dict.fromkeys(m["locations"] + locs))
        for name, card in o.get("cardFixes", {}).items():
            for m in mons:
                if m["name"].lower() == name.lower():
                    m["card"] = card
        for name, lvl in o.get("monsterSlayer", {}).items():
            for m in mons:
                if m["name"].lower() == name.lower():
                    m["slayer"] = lvl
        # equipment: task-wide, or per monster (appliesTo / monsterEquipment)
        tp["equipment"] = [e for e in o.get("equipment", []) if not e.get("appliesTo")]
        for e in o.get("equipment", []):
            for name in e.get("appliesTo", []):
                for m in mons:
                    if m["name"].lower() == name.lower():
                        m.setdefault("equipment", []).append({k: v for k, v in e.items() if k != "appliesTo"})
        for name, eqs in o.get("monsterEquipment", {}).items():
            for m in mons:
                if m["name"].lower() == name.lower():
                    m.setdefault("equipment", []).extend(eqs)
        # location gates: quests / cards (any one) / skills / access needed at that location
        for g in o.get("locationGates", []):
            gate = {k: g[k] for k in ("quests", "cards", "skills", "access", "note") if g.get(k)}
            for m in mons:
                if g.get("monster") and g["monster"].lower() != m["name"].lower():
                    continue
                if g["location"] not in m["locations"]:
                    continue
                m.setdefault("locationGates", {})[g["location"]] = gate
            for mstr in masters:  # Konar's task-level locations
                for t in mstr["tasks"]:
                    if t["task"] == task and g["location"] in t.get("locations", []):
                        t.setdefault("locationGates", {})[g["location"]] = gate
        if o.get("konarLocations"):
            for mstr in masters:
                for t in mstr["tasks"]:
                    if t["task"] == task and t.get("locations") is not None:
                        t["locations"] = o["konarLocations"]
        if o.get("notes"):
            tp["notes"] = o["notes"]
        for m in mons:  # recompute access for added locations
            m["card"] = m.get("card") or card_of(m["name"]) or card_of(re.sub(r"\s*\(.*?\)\s*$", "", m["name"]))
            m["locationAccess"] = {l: (m.get("locationAccess", {}).get(l) if l in m.get("locationAccess", {}) else None) for l in m["locations"]}
    for tp in tasks_out.values():   # one entry per monster: merge repeated rows (one per location table)
        seen = {}
        for m in tp["monsters"]:
            k = m["name"].lower()
            if k in seen:
                seen[k]["locations"] = list(dict.fromkeys(seen[k]["locations"] + m["locations"]))
                seen[k].setdefault("locationGates", {}).update(m.get("locationGates", {}))
                for e in m.get("equipment", []):
                    seen[k].setdefault("equipment", []).append(e)
                seen[k]["card"] = seen[k].get("card") or m.get("card")
            else:
                seen[k] = m
        tp["monsters"] = list(seen.values())
    # locations added by overrides need their region looked up too
    extra = [l for tp in tasks_out.values() for m in tp["monsters"] for l in m["locations"] if l not in regions]
    if extra:
        regions.update(location_regions(extra))
    for tp in tasks_out.values():
        if tp.get("boss"):
            continue
        for m in tp["monsters"]:
            m["locationAccess"] = {l: access_of(l) for l in m["locations"]}
            m["wilderness"] = [l for l in m["locations"] if "Wilderness" in regions.get(l, "")]
    for mstr in masters:
        for t in mstr["tasks"]:
            if t.get("locations"):
                t["locationAccess"] = {l: access_of(l) for l in t["locations"]}
            if mstr.get("wilderness"):
                t["wildernessOnly"] = True   # Krystilia: only Wilderness locations count
    lvls = monster_slayer_levels([m["name"] for tp in tasks_out.values() if not tp.get("boss") for m in tp["monsters"]])
    for tp in tasks_out.values():
        if tp.get("boss"):
            continue
        for m in tp["monsters"]:
            lv = max(lvls.get(m["name"], 0), m.get("slayer") or 0)
            if lv > 1:
                m["slayer"] = lv
    report["monstersNoCard"] = [f"{n}: {m['name']}" for n, tp in tasks_out.items() for m in tp["monsters"] if not m.get("card")]
    report["pendingReview"] = sorted(o["task"] for o in cur.get("taskOverrides", {}).values() if o.get("pending"))

    unlocks = sorted({t["unlock"]["ability"] for m in masters for t in m["tasks"] if t["unlock"].get("ability")})
    out = {"masters": masters, "tasks": tasks_out, "unlocks": unlocks, "unlockInfo": cur.get("unlockInfo", {})}
    _OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    report["unmappedLocations"] = dict(sorted(report["unmappedLocations"].items(), key=lambda kv: -kv[1]))
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT}: {len(masters)} masters, {len(tasks_out)} tasks, {len(unlocks)} unlocks")
    for k, v in report.items():
        print(f"  {k}: {len(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
