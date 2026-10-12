"""Generate recipes.json — every XP-giving production recipe from the OSRS Wiki, for the Skilling
tab's production skills (Fletching, Smithing, Crafting, Cooking, Herblore, Construction,
Runecraft). Covers outputs with no TCG card too (e.g. Oak shortbow (u), POH furniture).

Source: the wiki's "recipe" Bucket (api.php?action=bucket), cached in cache/wiki_recipes.json
(delete it to refetch). Quest gates the wiki recipe data doesn't carry are taken from the
hand-checked production entries in item_sources.json / ingredient_info.json (same output + skill),
plus the rules in QUEST_RULES below.

Output: scripts/output/recipes.json   (list)
  {output, outputQuantity, skill, level, xp, ingredients: [{item, quantity}], tools: [..],
   facilities, members, levels: {other skill: level}, quests: [..], access?, page,
   internal?: "<minigame / quest>",   # only made inside that minigame/quest: not normal training
   noXp?: true}                       # a 0-xp step (Pie shell, Uncooked egg…), kept only so the
                                      # planner can tell that an ingredient can be made

"internal" (see tag_internal): a facility named "X (minigame)" (Singing Bowl (The Gauntlet)…), a
minigame/quest-only facility (FACILITY_INTERNAL), a quest item (wiki infobox "quest = …", no TCG
card) made from something with no source outside that quest (M'speak amulet ← Enchanted bar), and
anything made from an item that only internal recipes make (Corrupted body (perfected) ← (attuned)).
Item quest data: the wiki's infobox_item Bucket, cached in cache/wiki_item_quests.json.

Usage:
  python3 scripts/generate_recipes.py
"""

from __future__ import annotations

import json
import wiki_api
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
FACILITY_GATES = {"Totem site": {"quests": ["Vale Totems"], "access": "varlamore"},
                  # Temple of Marimbo Dungeon on Ape Atoll (zenyte; the M'speak step is a quest item)
                  "Wall of flame": {"quests": ["Monkey Madness I"], "access": "ape_atoll"}}
# Facilities named "X (Y)": Y is a quest (gate), a place (nothing), or a minigame — those recipes only
# happen inside it. Real repeatable minigames also carry their entry gates (OSRS Wiki).
MINIGAME_GATES = {
    "The Gauntlet": {"quests": ["Song of the Elves"], "access": "prifddinas"},
    "The Corrupted Gauntlet": {"quests": ["Song of the Elves"], "access": "prifddinas"},
    "Zalcano": {"quests": ["Song of the Elves"], "access": "prifddinas"},
    "Trouble Brewing": {"quests": ["Cabin Fever"], "access": "mos_le_harmless"},
    "Mastering Mixology": {"access": "varlamore", "levels": {"Herblore": 60}},
    "Tempoross Cove": {"levels": {"Fishing": 35}},
}
PLACES = {"Chasm of Fire"}
# Outputs named "X (Y)" / "X (…, Y)" where Y is a minigame: furniture built only during it
OUTPUT_MINIGAMES = {"Mahogany Homes"}
# One-time builds (no repeat xp): Fossil Island Museum Camp and other camp builds
ONE_OFF_PAGE = re.compile(r"Museum [Cc]amp|\(Fossil Island\)|Wyrmscraig|^Ring of Stones$|^Half-built Loom$")   # "Anvil (Chasm of Fire)": just where the anvil is
# Facilities that only exist inside a minigame or a quest step (OSRS Wiki facility pages)
FACILITY_INTERNAL = {
    "Leela": "Prince Ali Rescue",                 # she makes the bronze key from the key print
    "Refiner": "Mastering Mixology", "Mixing vessel": "Mastering Mixology",
    "Fermentation Vat": "Desert Treasure II - The Fallen Empire",
    "Catalytic runic altar": "Guardians of the Rift", "Elemental runic altar": "Guardians of the Rift",
}
# Items that only exist inside a minigame (no recipe makes them; mined / handed out in there)
ITEM_INTERNAL = {"Guardian essence": "Guardians of the Rift", "Uncharged cell": "Guardians of the Rift",
                 "Raw paddlefish": "The Gauntlet",
                 # Chambers of Xeric: raid herbs, gourd vials and secondaries exist only in the raid
                 **{n: "Chambers of Xeric" for n in ("Grimy golpar", "Grimy buchu leaf", "Grimy noxifer",
                    "Water-filled gourd vial", "Stinkhorn mushroom", "Endarkened juice", "Cicely")}}
# Chambers of Xeric fish and bats: "Raw pysk fish (0)" … "Raw psykk bat (6)"
ITEM_INTERNAL_RE = [(re.compile(r"^Raw \w+ (fish|bat) \(\d\)$"), "Chambers of Xeric")]


def _item_internal(n: str) -> str | None:
    return ITEM_INTERNAL.get(n) or next((v for pat, v in ITEM_INTERNAL_RE if pat.search(n)), None)
MINIGAMES = set(MINIGAME_GATES) | {"Mastering Mixology", "Guardians of the Rift", "Chambers of Xeric"}
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
        b = wiki_api.get_json(url)["bucket"]
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


_QCACHE = _HERE / "cache" / "wiki_item_quests.json"


def fetch_item_quests() -> dict[str, str]:
    """Item → the quest(s) its wiki infobox names (infobox_item Bucket, quest != "No")."""
    if not _QCACHE.exists():
        out, off = [], 0
        while True:
            q = (f"bucket('infobox_item').select('page_name','item_name','quest').where('quest','!=','No')"
                 f".limit(500).offset({off}).run()")
            b = wiki_api.get_json("https://oldschool.runescape.wiki/api.php?action=bucket&format=json&query="
                                  + urllib.parse.quote(q))["bucket"]
            out += b
            off += 500
            if len(b) < 500:
                break
        _QCACHE.write_text(json.dumps(out), encoding="utf-8")
    res = {}
    for r in json.loads(_QCACHE.read_text(encoding="utf-8")):
        qs = re.findall(r"\[\[([^\]|#]+)", r.get("quest") or "")
        for n in {r.get("item_name"), r.get("page_name")}:
            if n and qs:
                res.setdefault(n, qs[0].strip())
    return res


def tag_internal(recipes: list[dict], is_card, has_data, item_quest: dict[str, str], quests: set[str]) -> Counter:
    """Set "internal" (and a minigame's gates) on recipes that only happen inside a minigame/quest."""
    why = Counter()
    for m in recipes:
        fac = m.get("facilities") or ""
        par = re.search(r"\(([^)]+)\)$", fac)
        onm = [re.search(r"\(([^)]+)\)$", x) for x in (m["output"], m["page"])]
        onm = [x.group(1).split(", ")[-1] for x in onm if x]
        if any(x in quests or x in OUTPUT_MINIGAMES for x in onm):
            m["internal"] = next(x for x in onm if x in quests or x in OUTPUT_MINIGAMES)   # Table (Daddy's Home)…
            why["output named after a quest/minigame"] += 1
        elif par and par.group(1) in MINIGAME_GATES:
            m["internal"] = par.group(1)
            why["facility (minigame)"] += 1
        elif fac in FACILITY_INTERNAL:
            m["internal"] = FACILITY_INTERNAL[fac]
            why["facility (minigame/quest-only)"] += 1
        elif any(_item_internal(i["item"]) for i in m["ingredients"]):
            m["internal"] = next(_item_internal(i["item"]) for i in m["ingredients"] if _item_internal(i["item"]))
            why["minigame-only ingredient"] += 1
        g = MINIGAME_GATES.get(m.get("internal"))
        if g:
            m["quests"] = sorted(set(m["quests"]) | set(g.get("quests", [])))
            if g.get("access"):
                m["access"] = g["access"]
            if g.get("levels"):
                m["levels"] = {**g["levels"], **m["levels"]}
    # Quest items made from something with no source outside the quest, and anything made from an
    # item only internal recipes make — to a fixpoint
    def ok_item(n, sourced):
        return is_card(n) or has_data(n) or n in sourced
    while True:
        sourced = {m["output"] for m in recipes if not m.get("internal")}
        # outputs whose only "source" is a recipe chain that bottoms out in nothing: iterate
        good = set()
        while True:
            add = {m["output"] for m in recipes if not m.get("internal") and m["output"] not in good
                   and all(any(ok_item(a, good) for a in (i.get("alts") or [i["item"]])) for i in m["ingredients"])}
            if not add:
                break
            good |= add
        changed = False
        for m in recipes:
            if m.get("internal"):
                continue
            bad = [i["item"] for i in m["ingredients"] if not any(ok_item(a, good) for a in (i.get("alts") or [i["item"]]))]
            if not bad:
                continue
            made_internal = [r["internal"] for r in recipes if r.get("internal") and r["output"] in bad]
            q = item_quest.get(m["output"]) or item_quest.get(m["page"])
            # a card made from a quest-only item stays (the planner shows it as "no known source"):
            # the card is usually repeatable after the quest (Nettle tea, Lunar helm…)
            if made_internal and is_card(m["output"]) and not set(made_internal) & MINIGAMES:
                continue
            if made_internal and not any(r["output"] in bad and not r.get("internal") for r in recipes):
                m["internal"] = made_internal[0]
                why["made from a minigame/quest-only item"] += 1
                changed = True
            elif q and not is_card(m["output"]):
                m["internal"] = q
                why["quest item from a quest-only material"] += 1
                changed = True
        if not changed:
            return why


def _row(p: dict, r: dict, s: dict | None, skill: str | None, xp: float, known) -> dict:
    o = p.get("output")
    o = o[0] if isinstance(o, list) and o else o
    name = o["name"]
    skills = p.get("skills") or []
    ings = [{"item": m["name"], "quantity": _num(m.get("quantity")) or 1} for m in p.get("materials") or [] if m.get("name")]
    tools = [t.strip() for t in _plain(p.get("tools")).split(",") if t.strip() and t.strip().lower() != "none"]
    fac = _plain(p.get("facilities")) or None
    return {"output": name, "outputQuantity": _num(o.get("quantity")) or 1, "skill": skill,
            "level": int(_num(s.get("level")) or 1) if s else 1, "xp": xp, "ingredients": ings, "tools": tools,
            "facilities": fac, "members": bool(p.get("members")),
            "levels": {SKILL_NAME.get(x["name"], x["name"]): int(_num(x.get("level")) or 1)
                       for x in skills if x is not s and x.get("name")
                       and ((_num(x.get("level")) or 0) > 1 or x["name"] == "Sailing")},   # any Sailing: a boat part
            "quests": sorted(known.get((name, skill), set())), "page": r["page_name"],
            **({"oneOff": "first time only"} if re.search(r"first time", str(o.get("subtxt") or ""), re.I) else {})}


def main() -> int:
    rows = fetch()
    known = {}
    data_names = set()
    for f in (_HERE / "output" / "item_sources.json", _HERE / "ingredient_info.json"):
        for name, v in json.loads(f.read_text(encoding="utf-8")).items():
            data_names.add(name)
            ps = v.get("production")
            for p in (ps if isinstance(ps, list) else [ps] if ps else []):
                if p.get("quests"):
                    known.setdefault((name, p.get("skill")), set()).update(p["quests"])
    cards = {n.lower() for n in json.loads((_HERE / "output" / "item_sources.json").read_text(encoding="utf-8"))}
    aliases = json.loads((_HERE / "output" / "card_aliases.json").read_text(encoding="utf-8"))
    is_card = lambda n: n.lower() in cards or (aliases.get(n.lower()) or "").lower() in cards
    has_data = lambda n: n in data_names
    out, seen, zero = [], set(), []
    for r in rows:
        p = json.loads(r["production_json"])
        o = p.get("output")
        o = o[0] if isinstance(o, list) and o else o
        if not isinstance(o, dict) or not o.get("name"):
            continue  # gathering entries (rocks, trees…) have no output
        name = o["name"]
        skills = p.get("skills") or []
        any_xp = False
        for s in skills:
            sk = s.get("name", "").capitalize() if s.get("name", "").lower() == "cooking" else s.get("name", "")
            xp = _num(s.get("experience") or 0)
            if xp and xp > 0:
                any_xp = True
            if sk not in SKILLS or not xp or xp <= 0:
                continue  # formula xp (e.g. "1×Construction level") is covered by skilling_curated
            skill = SKILL_NAME.get(sk, sk)
            if skill == "Cooking" and name.lower().startswith("burnt"):
                continue
            m = _row(p, r, s, skill, xp, known)
            key = (name, skill, tuple(sorted((i["item"], i["quantity"]) for i in m["ingredients"])), m["facilities"])
            if key in seen:
                continue
            seen.add(key)
            for pat, rsk, qs in QUEST_RULES:
                if rsk == skill and pat.search(name):
                    m["quests"] = sorted(set(m["quests"]) | set(qs))
            fg = FACILITY_GATES.get(m["facilities"])
            if fg:
                m["quests"] = sorted(set(m["quests"]) | set(fg.get("quests", [])))
                if fg.get("access"):
                    m["access"] = fg["access"]
            if skill == "Construction" and m["levels"].get("Sailing"):
                m["access"] = "sailing"           # a boat facility / upgrade (hull, keel, cargo hold…)
                m["oneOff"] = "boat upgrade"
            elif ONE_OFF_PAGE.search(m["page"]) or ONE_OFF_PAGE.search(m["output"]):
                m["oneOff"] = "one-time camp build"
                if skill == "Construction":
                    m.pop("access", None)
            elif skill == "Construction":
                fac = m["facilities"]
                if fac in NON_POH:
                    if NON_POH[fac]:
                        m["access"] = NON_POH[fac]
                else:
                    m["access"] = "house"  # built in a player-owned house (no facility, or a "… space" hotspot)
            out.append(m)
        if not any_xp and not any(_num(s.get("experience") or 0) for s in skills) and not str(
                next((s.get("experience") for s in skills if s.get("experience")), "")).strip("0"):
            # a 0-xp step: its skill is the first one listed (level gate), if any
            s = skills[0] if skills else None
            sk = SKILL_NAME.get((s or {}).get("name", ""), (s or {}).get("name")) if s else None
            if sk and sk.lower() == "cooking":
                sk = "Cooking"
            zero.append({**_row(p, r, s, sk, 0, known), "noXp": True})
    # Keep only the 0-xp steps that make a non-card ingredient of some recipe (recursively)
    need = {i["item"] for m in out for i in m["ingredients"] for i_ in [i] for _ in [0]}
    need |= {a for m in out for i in m["ingredients"] for a in i.get("alts") or []}
    need = {n for n in need if not is_card(n) and not has_data(n)}
    keep, zseen = [], set()
    while need:
        nxt = set()
        for z in zero:
            k = (z["output"], tuple((i["item"], i["quantity"]) for i in z["ingredients"]), z["facilities"])
            if z["output"] in need and k not in zseen:
                zseen.add(k)
                keep.append(z)
                nxt |= {i["item"] for i in z["ingredients"] if not is_card(i["item"]) and not has_data(i["item"])}
        need = nxt - {z["output"] for z in keep}
    out = merge_alternatives(out)
    quests = set(json.loads((_HERE / "output" / "quests.json").read_text(encoding="utf-8")))
    why = tag_internal(out + keep, is_card, has_data, fetch_item_quests(), quests)
    out.sort(key=lambda m: (m["skill"], m["level"], m["output"]))
    keep.sort(key=lambda m: (m["skill"] or "", m["level"], m["output"]))
    _OUT.write_text(json.dumps(out + keep, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT}: {len(out)} recipes", dict(Counter(m["skill"] for m in out)), f"+ {len(keep)} 0-xp steps")
    print("  with quests:", sum(1 for m in out if m["quests"]), "· POH (house):", sum(1 for m in out if m.get("access") == "house"))
    print("  one-off:", dict(Counter(m["oneOff"] for m in out if m.get("oneOff"))))
    print("  internal:", sum(1 for m in out if m.get("internal")), dict(why))
    for k, n in Counter(m["internal"] for m in out if m.get("internal")).most_common():
        print(f"    {n:4} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
