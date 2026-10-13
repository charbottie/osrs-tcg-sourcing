#!/usr/bin/env python3
"""Scrape clue step data from the OSRS Wiki.

Produces scripts/output/clue_steps.json with sections:
  emote    — emote clues per tier (items + combat NPC for Hard/Elite/Master)
  sherlock — Sherlock tasks per tier (Elite / Master, items required)
  falo     — Falo the Bard steps (lyric → valid items)
  cryptic  — cryptic "talk to NPC" steps per tier
  anagram  — anagram clues per tier (anagram → NPC to talk to)
  cipher   — cipher clues per tier (cipher → NPC to talk to)
  digInfo  — map/coordinate tiers with Spade requirement + combat NPC info
  map        — map clue steps per tier (location, dig vs search, requirements)
  coordinate — coordinate clue steps per tier (coords, Requirements column, fight NPCs)

Plus two reverse indexes:
  itemIndex — item name → [step refs]
  npcIndex  — NPC card name → [step refs]

Every step also carries the planner's shared requirement fields (requirements, quests,
partialQuests, skills, access, diaries, reqNotes, noCard; emote/Sherlock/Falo also `slots`) —
see "Requirement model" below. Hand-curated data (NPC fixes, item groups, location → access /
quest rules, per-row overrides) lives in scripts/clue_curated.json. The run ends with a
validation pass (card names, quests, access keys, groups) and exits 1 on any problem.

Usage:
  python scripts/generate_clue_steps.py
  python scripts/generate_clue_steps.py --force-refresh   # re-fetch cached pages
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bs4 import BeautifulSoup, Tag
import wiki_fetcher
from catalog_names import npc_names

_OUT = Path(__file__).parent / "output" / "clue_steps.json"

_DIG_RE = re.compile(r'\bdig\b', re.IGNORECASE)

EMOTE_TIERS    = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]
SHERLOCK_TIERS = ["Elite", "Master"]
CRYPTIC_TIERS  = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]
ANAGRAM_TIERS  = ["Beginner", "Medium", "Hard", "Elite", "Master"]
CIPHER_TIERS   = ["Medium", "Hard"]   # the wiki's Ciphers page has only Medium and Hard tables

# Emote clue tiers where a Double Agent must be defeated before collecting reward.
# Wiki: every Hard and Master emote step says "Beware of double agents!"; no Elite step does.
DOUBLE_AGENT_TIERS = {"Hard", "Master"}

# Charlie the Tramp asks for one of these items in beginner clue scrolls.
# Source: https://oldschool.runescape.wiki/w/Charlie_the_Tramp/Tasks
CHARLIE_ITEMS = ["Iron ore", "Iron dagger", "Raw herring", "Raw trout", "Trout", "Pike", "Leather body", "Leather chaps"]

# Hand-curated data (NPC fixes, item groups, location → access/quest rules, overrides)
_CURATED_PATH = Path(__file__).parent / "clue_curated.json"
CUR: dict = json.loads(_CURATED_PATH.read_text(encoding="utf-8"))

# Clue NPCs the wiki tables name by place/role → their TCG card (None = a place, no NPC gate)
CLUE_NPC_FIXES: dict[str, str | None] = CUR["npcFixes"]

# Tiers that contain map clues (dig at X) — Spade required.
# Source: https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Maps
MAP_CLUE_TIERS = ["Beginner", "Easy", "Medium", "Hard", "Elite"]

# Tiers that contain coordinate clues — Spade required.
# Hard:   Saradomin wizard (outside Wilderness) or Zamorak wizard (inside Wilderness)
# Elite:  Armadylean guard or Bandosian guard (randomly chosen)
# Master: Three Ancient Wizards (multi-combat) or Brassican Mage (single-combat)
# Source: https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Coordinates
COORDINATE_CLUE_TIERS: dict[str, dict] = {
    "Medium": {},
    "Hard":   {"combatNpc": "Saradomin wizard", "wildernessNpc": "Zamorak wizard"},
    "Elite":  {"combatNpc": "Armadylean guard", "altCombatNpc": "Bandosian guard"},
    "Master": {"combatNpc": "Ancient Wizard",   "altCombatNpc": "Brassican Mage"},
}

# Hot/cold clue tiers and their per-step combat NPC mapping.
# Beginner: no combat NPC spawns.
# Master: Combat Type column says "Single" (→ Brassican Mage) or "Multi" (→ Ancient Wizard).
# Source: https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Hot_Cold
HOT_COLD_TIERS = ["Beginner", "Master"]
HOT_COLD_COMBAT: dict[str, str] = {
    "Single": "Brassican Mage",
    "Multi":  "Ancient Wizard",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cell_text(td: Tag) -> str:
    """Return normalised plain text for a cell, stripping footnote refs."""
    for tag in td.find_all(["sup", "ref"]):
        tag.decompose()
    return " ".join(td.get_text(" ").split())


def _links_in_cell(td: Tag) -> list[str]:
    """Return canonical page names from all wiki links in a <td>.

    Uses the `title` attribute of <a> tags.
    Skips red links, File/Category/Template namespaced links.
    """
    items: list[str] = []
    for a in td.find_all("a", href=True):
        href: str = a["href"]
        if not href.startswith("/w/"):
            continue
        title = a.get("title", "").strip()
        if not title:
            continue
        if title.endswith("(page does not exist)"):
            title = a.get_text().strip()
        if ":" in title:
            continue  # File:, Category:, Template:, etc.
        if title and title not in items:
            items.append(title)
    return items


def _first_link_in_cell(td: Tag) -> str | None:
    links = _links_in_cell(td)
    return links[0] if links else None


def _split_by_tier_headers(soup: BeautifulSoup, tier_names: list[str],
                             header_tags: tuple = ("h2", "h3")
                             ) -> dict[str, list[Tag]]:
    """Walk the page and group <table> elements by the nearest preceding tier header."""
    result: dict[str, list[Tag]] = {t: [] for t in tier_names}
    current: str | None = None

    for el in soup.find_all(True):
        if el.name in header_tags:
            text = el.get_text(" ").strip()
            for tier in tier_names:
                if tier.lower() in text.lower():
                    current = tier
                    break
        elif el.name == "table" and current:
            result[current].append(el)

    return result


# ── Requirement model (Phase 1A) ──────────────────────────────────────────────
# Every step gets the planner's shared requirement fields (only when non-empty):
#   requirements:  [{label, type:'item'|'npc'|'enemy', cards:[any-of], mode?:'all',
#                    optional?, sets?:[[all-of], …] (any one complete set), tool?, group?}]
#   quests / partialQuests: [quests.json keys];  skills: {Skill: level}
#   access: [access_routes.json keys];  diaries: ["Area Tier"]
#   reqNotes: [text]  — conditional / unparsed requirement wording, for display only
#   noCard:   [names] — linked items/NPCs that have no TCG card (never a gate)

_HERE = Path(__file__).parent
_LT, _RT = "⟦", "⟧"                       # ⟦title|text⟧ link markers
_LINK_RE = re.compile(_LT + r"([^|" + _RT + r"]*)\|([^" + _RT + r"]*)" + _RT)

SKILLS = ["Attack", "Strength", "Defence", "Ranged", "Prayer", "Magic", "Runecraft", "Hitpoints",
          "Crafting", "Mining", "Smithing", "Fishing", "Cooking", "Firemaking", "Woodcutting",
          "Agility", "Herblore", "Thieving", "Fletching", "Slayer", "Farming", "Construction",
          "Hunter", "Sailing"]
_SK = "|".join(SKILLS + ["Runecrafting"])
_SKILL_RES = [
    re.compile(rf"\b(?:level\s+)?(\d{{1,2}})\s+(?:levels?\s+)?({_SK})\b", re.I),
    re.compile(rf"\b({_SK})\s+(?:level\s+)?(?:of\s+)?(\d{{1,2}})\b", re.I),
    re.compile(rf"\b({_SK})\s+level\s+of\s+(\d{{1,2}})\b", re.I),
]
_NEG_RE = re.compile(r"not (?:be )?(?:required|needed|necessary)|do(?:es)?n'?t (?:need|count|work)|"
                     r"do(?:es)? not (?:need|count|work)|can'?t be used|cannot be used|recommend|"
                     r"optional|advis|not work|no need|is not a requirement", re.I)
_REQ_RE = re.compile(r"requir|\bneed|\bmust\b|\bbring\b|to (?:enter|reach|access|equip|wear|wield|use|"
                     r"dock|disembark)|access|completion|complete|started|\bstart(?:ing|ed)?\s+(?:of\s+)?\u27e6|"
                     r"partial|progress|only accessible|is a requirement", re.I)
_COND_RE = re.compile(r"\bif\b|\bunless\b|\botherwise\b|have not|haven't|has not|hasn't|without|"
                      r"alternatively|instead|\beither\b|,\s*or\b|also count|also work|can also|"
                      r"\btotal\b|in either|\bmay use|\bcan use|shortcut", re.I)
_OBTAIN_RE = re.compile(r"to obtain|to get (?:the|a|an)\b|to receive|to buy|to purchase|to make|"
                        r"to craft|to create|obtained|to kill|for the key|to fight", re.I)
_PARTIAL_RE = re.compile(r"partial|started|\bstart|progress|partway|parts? of|during|up ?to\b|halfway|"
                         r"begun|begin", re.I)
_TRAVEL_RE = re.compile(r"teleport|fairy ring|fairy code|close to|nearby|quickly|fastest|easily|"
                        r"alternatively|reached by|can be reached|charter|glider|spirit tree|\blyre\b|"
                        r"\bvia\b", re.I)
_LOC_SKIP_RE = re.compile(_TRAVEL_RE.pattern + r"|\bnote\b|beware|warning", re.I)


def _marked(td: Tag) -> str:
    """Cell text with each wiki link kept as ⟦title|text⟧ (footnotes dropped)."""
    td = copy.copy(td)
    for tag in td.find_all(["sup", "ref"]):
        tag.decompose()
    for a in td.find_all("a"):
        title = (a.get("title") or "").strip()
        if title.endswith("(page does not exist)"):
            title = a.get_text().strip()
        text = " ".join(a.get_text(" ").split())
        href = a.get("href", "")
        if not href.startswith("/w/") or ":" in title or not title:
            a.replace_with(text)
            continue
        a.replace_with(f" {_LT}{title}|{text or title}{_RT} ")   # icon-only links (skill icons) → title
    return " ".join(td.get_text(" ").split())


def _plain(s: str) -> str:
    s = _LINK_RE.sub(lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"\s+([.,;:!?)])", r"\1", s)
    return " ".join(s.split())


def _sentences(s: str) -> list[str]:
    """Split marked text into sentences; parentheticals become their own pseudo-sentences."""
    toks: list[str] = []

    def _hold(m):
        toks.append(m.group(0))
        return f"§{len(toks) - 1}§"
    held = _LINK_RE.sub(_hold, s)
    parens: list[str] = []
    while True:
        new = re.sub(r"\(([^()]*)\)", lambda m: (parens.append(m.group(1)), " ")[1], held)
        if new == held:
            break
        held = new
    restore = lambda x: re.sub("§(\\d+)§", lambda m: toks[int(m.group(1))], x)
    out = [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z§\d])|\s*;\s*|\s+Note\s*:\s*", held) if p.strip()]
    return [restore(p).strip() for p in out + parens if p.strip()]


def _sentences_ctx(s: str) -> list[tuple[str, str]]:
    """Like _sentences, but each parenthetical comes with the sentence it sits in, so a
    '(requires 76 Agility)' inside a travel tip or an 'if …' sentence keeps that context."""
    toks: list[str] = []

    def _hold(m):
        toks.append(m.group(0))
        return f"§{len(toks) - 1}§"
    restore = lambda x: re.sub("§(\\d+)§", lambda m: toks[int(m.group(1))], x).strip()
    held = _LINK_RE.sub(_hold, s)
    out: list[tuple[str, str]] = []
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z§\d])|\s*;\s*|\s+Note\s*:\s*", held):
        parens: list[str] = []
        bare = sent
        while True:
            new = re.sub(r"\(([^()]*)\)", lambda m: (parens.append(m.group(1)), " ")[1], bare)
            if new == bare:
                break
            bare = new
        if bare.strip():
            out.append((restore(bare), ""))
        out += [(restore(p), restore(bare)) for p in parens if p.strip()]
    return out


class _Resolver:
    """Card / quest / access lookups shared by every parser."""

    def __init__(self):
        cat = json.loads((_HERE.parent / "research" / "card-catalog-live.json").read_text(encoding="utf-8"))
        self.items = {x["name"].lower(): x["name"] for x in cat["items"]}
        self.npcs = npc_names(cat)   # card names, wiki pages and version names -> NPC card
        self.aliases = {k.lower(): v for k, v in json.loads(
            (_HERE / "output" / "card_aliases.json").read_text(encoding="utf-8")).items()}
        self.quests = set(json.loads((_HERE / "output" / "quests.json").read_text(encoding="utf-8")))
        self.quests_l = {q.lower(): q for q in self.quests}
        self.access = {k for k in json.loads((_HERE / "output" / "access_routes.json").read_text(
            encoding="utf-8")) if not k.startswith("_")}
        self.diary_areas = [a["name"] for a in json.loads(
            (_HERE / "output" / "diaries.json").read_text(encoding="utf-8"))]
        self.no_card = {n.lower() for n in CUR["noCard"]}
        self.unresolved: dict[str, int] = {}

    def item(self, name: str) -> str | None:
        name = CUR.get("itemNameFixes", {}).get((name or "").strip(), name)
        l = (name or "").strip().lower()
        if l in self.items:
            return self.items[l]
        a = self.aliases.get(l)
        if a and a.lower() in self.items:
            return self.items[a.lower()]
        tight = re.sub(r"\s+\((\d)\)$", r"(\1)", l)          # wiki "Ranging potion (2)" → "ranging potion(2)"
        if tight != l:
            return self.item(tight)
        return None

    def npc(self, name: str) -> str | None:
        l = (name or "").strip().lower()
        if l in self.npcs:
            return self.npcs[l]
        a = self.aliases.get(l)
        if a and a.lower() in self.npcs:
            return self.npcs[a.lower()]
        base = re.sub(r"\s*\([^()]*\)$", "", l)       # wiki "Cook (Lumbridge)" → in-game name "Cook"
        return self.npcs.get(base) if base != l else None

    def quest(self, title: str) -> str | None:
        t = CUR["questAliases"].get(title, title)
        for cand in (t, "The " + t, re.sub(r"\s+quest$", "", t, flags=re.I)):
            if cand in self.quests:
                return cand
            if cand.lower() in self.quests_l:
                return self.quests_l[cand.lower()]
        return None

    def card_exists(self, name: str) -> bool:
        l = name.lower()
        return l in self.items or l in self.npcs or l in self.aliases


R: _Resolver | None = None


def _new_reqs() -> dict:
    return {"requirements": [], "quests": [], "partialQuests": [], "skills": {}, "access": [],
            "diaries": [], "reqNotes": [], "noCard": []}


def _merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if k == "skills":
            for sk, lv in v.items():
                dst["skills"][sk] = max(lv, dst["skills"].get(sk, 0))
        elif isinstance(v, list):
            for x in v:
                if x not in dst[k]:
                    dst[k].append(x)
    return dst


def _skills_in(plain: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for rx in _SKILL_RES:
        for m in rx.finditer(plain):
            a, b = m.group(1), m.group(2)
            lvl, sk = (a, b) if a.isdigit() else (b, a)
            sk = sk.capitalize() if sk.lower() != "runecrafting" else "Runecraft"
            if 1 < int(lvl) <= 99:
                out[sk] = max(int(lvl), out.get(sk, 0))
    return out


def _diaries_in(plain: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b(easy|medium|hard|elite)\s+([A-Z][\w'&]*(?:\s+[&\w']+)?)\s+(?:achievement\s+)?diary",
                         plain, re.I):
        area = m.group(2).strip().lower()
        hit = next((a for a in R.diary_areas if a.lower().startswith(area.split()[0])), None)
        if hit:
            out.append(f"{hit} {m.group(1).capitalize()}")
    return out


def _item_token(title: str):
    """Classify a linked title: ('group', req) | ('card', name) | ('nocard', name) | None (not an item)."""
    if title in CUR["linkGroups"]:
        g = CUR["linkGroups"][title]
        req = {"label": g["label"], "type": "item", "cards": []}
        req.update({k: g[k] for k in ("group", "tool") if k in g})
        return ("group", req)
    card = R.item(title)
    if card:
        return ("card", card)
    if title.lower() in R.no_card:
        return ("nocard", title)
    return None


def _items_in_sentence(sent: str, optional: bool) -> tuple[list[dict], list[str]]:
    """Item requirements in one requirement sentence: links joined by 'or' / '/' are any-of."""
    reqs, nocard = [], []
    toks = []
    for m in _LINK_RE.finditer(sent):
        if R.quest(m.group(1)) or R.npc(m.group(1)):
            continue
        t = _item_token(m.group(1)) or ("unknown", m.group(1))
        toks.append((m.start(), m.end(), t))
    clusters: list[list] = []
    for i, tok in enumerate(toks):
        if clusters and re.fullmatch(r"\s*(?:\w+\s+){0,2}(?:,\s*)?(?:or|/)\s*(?:an?|the|any)?\s*",
                                     _plain(sent[toks[i - 1][1]:tok[0]])):
            clusters[-1].append(tok[2])
        else:
            clusters.append([tok[2]])
    for cl in clusters:
        if all(k == "unknown" for k, _ in cl):
            continue                                 # places, skills, other pages
        if any(k == "unknown" for k, _ in cl):       # "X or <item page with no card>" → never a gate
            cl = [("nocard", v) if k == "unknown" else (k, v) for k, v in cl]
        if any(k == "nocard" for k, _ in cl):        # an alternative with no card
            nocard += [v for k, v in cl if k == "nocard"]
            if all(k == "nocard" for k, _ in cl):
                continue                             # nothing carded → never a gate
        grp = next((v for k, v in cl if k == "group"), None)
        if grp:
            req = dict(grp)
        else:
            cards = list(dict.fromkeys(v for k, v in cl if k == "card"))
            req = {"label": " or ".join(v for _, v in cl), "type": "item", "cards": cards}
            alts = [v for k, v in cl if k == "nocard"]
            if alts:
                req["noCardAlternatives"] = alts
        if optional:
            req["optional"] = True
        reqs.append(req)
    return reqs, nocard


def _extract(marked: str, *, reqcol: bool = False, items: bool = True) -> dict:
    """Pull quests / skills / diaries / item needs out of free wiki text.

    reqcol=True: the text is a Requirements column (every sentence is a requirement).
    Conditional sentences ("if …", "or …", "unless …") go to reqNotes instead of hard gates.
    """
    out = _new_reqs()
    if not marked or _plain(marked).lower() in ("none", "none.", "-", ""):
        return out
    for sent, ctx in _sentences_ctx(marked):
        plain = _plain(sent)
        ctx_p = _plain(ctx)
        if not plain or plain.lower() in ("none", "none."):
            continue
        if _NEG_RE.search(plain):
            continue
        travel = not reqcol and bool(_TRAVEL_RE.search(plain))
        if not reqcol and _TRAVEL_RE.search(ctx_p):
            continue                                 # a '(…)' inside a travel tip
        if travel and not re.search(r"requir|\bmust\b|\bneeded\b", plain, re.I):
            continue                                 # travel tips aren't requirements
        is_req = reqcol or bool(_REQ_RE.search(plain))
        if not is_req:
            continue
        n_tok = (sum(1 for m in _LINK_RE.finditer(sent) if R.quest(m.group(1))) + len(_skills_in(plain))
                 + (1 if any(_item_token(m.group(1)) for m in _LINK_RE.finditer(sent)) else 0))
        cond = (travel or bool(_COND_RE.search(plain)) or bool(_COND_RE.search(ctx_p))
                or (n_tok >= 2 and bool(re.search(r"\bor\b", plain))))
        obtain = bool(_OBTAIN_RE.search(plain))
        got = False
        # Quests (requirement columns sometimes name a quest without linking it)
        if reqcol and not any(R.quest(m.group(1)) for m in _LINK_RE.finditer(sent)):
            for q in sorted(R.quests, key=len, reverse=True):
                i = plain.lower().find(q.lower())
                if len(q) >= 6 and i >= 0:
                    if cond:
                        got = True
                    elif not obtain:
                        (out["partialQuests"] if _PARTIAL_RE.search(plain[:i]) else out["quests"]).append(q)
                        got = True
                    break
        last_end = 0
        for m in _LINK_RE.finditer(sent):
            q = R.quest(m.group(1))
            if not q:
                continue
            before = _plain(sent[max(last_end, m.start() - 60):m.start()])
            last_end = m.end()
            if obtain:
                continue
            if cond:
                got = True
                continue
            (out["partialQuests"] if _PARTIAL_RE.search(before) else out["quests"]).append(q)
            got = True
        # Skills / diaries
        if not obtain:
            sk = _skills_in(plain)
            if sk and not (cond and len(sk) >= 1 and re.search(r"\bor\b|\btotal\b|either", plain, re.I)):
                if cond:
                    got = True
                else:
                    _merge(out, {"skills": sk})
                    got = True
            dia = _diaries_in(plain)
            if dia and not cond:
                _merge(out, {"diaries": dia})
                got = True
        # Items
        if items and not obtain:
            reqs, nocard = _items_in_sentence(sent, optional=cond)
            _merge(out, {"requirements": reqs, "noCard": nocard})
            got = got or bool(reqs)
        if cond or (reqcol and not got and not ctx and plain.lower() not in ("spade", "none")):
            out["reqNotes"].append(plain)
    out["quests"] = list(dict.fromkeys(out["quests"]))
    out["partialQuests"] = [q for q in dict.fromkeys(out["partialQuests"]) if q not in out["quests"]]
    return out


def _location_text(marked_or_plain: str) -> str:
    """Location wording with travel tips (teleports, fairy rings, 'close to …') removed."""
    keep = [s for s in _sentences(marked_or_plain) if not _LOC_SKIP_RE.search(_plain(s))]
    return _plain(" ".join(keep))


def _loc_rules(text: str) -> dict:
    out = _new_reqs()
    if not text:
        return out
    for rule in CUR["locationRules"]:
        if re.search(rule["match"], text, re.I):
            _merge(out, {k: rule.get(k, []) for k in ("access", "quests", "partialQuests")})
    return out


_FAIRY_STAFF_REQ = {"label": "Dramen or Lunar staff (fairy ring; not needed with the Lumbridge & Draynor elite diary)",
                    "type": "item", "cards": ["Dramen staff", "Lunar staff"],
                    "routes": [{"label": "Lumbridge & Draynor elite diary", "cards": [],
                                "diaries": ["Lumbridge & Draynor Elite"]}]}


def _finalize(step: dict, acc: dict) -> dict:
    """Write the accumulated requirement fields onto a step (dropping empty ones)."""
    qa, pqa = CUR["questAccess"], CUR["partialQuestAccess"]
    for q in list(acc["quests"]):
        if q in qa:
            acc["quests"].remove(q)
            _merge(acc, {"access": [qa[q]]})
    for q in list(acc["partialQuests"]):
        if q in acc["quests"]:
            acc["partialQuests"].remove(q)
        elif q in pqa:
            acc["partialQuests"].remove(q)
            _merge(acc, {"access": [pqa[q]]})
    if ("Fairytale II - Cure a Queen" in acc["partialQuests"]
            and not any("Dramen staff" in r.get("cards", []) for r in acc["requirements"])):
        acc["requirements"].append(dict(_FAIRY_STAFF_REQ))   # fairy rings need a staff
    if "Sailing" in acc["skills"] and "sailing" not in acc["access"]:
        acc["access"].append("sailing")              # a Sailing level to dock = a boat-only island
    # de-duplicate requirements by (type, cards, group, tool)
    seen, reqs = set(), []
    for r in acc["requirements"]:
        key = (r.get("type"), tuple(r.get("cards", [])), r.get("group"), r.get("tool"),
               json.dumps(r.get("sets")))
        if key not in seen:
            seen.add(key)
            reqs.append(r)
    acc["requirements"] = reqs
    acc["noCard"] = list(dict.fromkeys(acc["noCard"]))
    acc["reqNotes"] = list(dict.fromkeys(acc["reqNotes"]))
    for k in ("requirements", "quests", "partialQuests", "skills", "access", "diaries", "reqNotes", "noCard"):
        if acc[k]:
            step[k] = acc[k]
        else:
            step.pop(k, None)
    return step


def _npc_req(name: str | None, kind: str, label: str | None = None) -> tuple[list[dict], list[str]]:
    if not name:
        return [], []
    card = R.npc(name)
    if not card:
        return [], [name]
    return [{"label": label or card, "type": kind, "cards": [card]}], []


def _slot_to_req(sl: dict) -> dict | None:
    if sl.get("unrestricted"):
        return None
    r = {"label": sl["label"], "type": "item", "cards": list(sl.get("cards", []))}
    if sl.get("mode") == "all":
        r["mode"] = "all"
    for k in ("sets", "tool", "group", "optional"):
        if sl.get(k):
            r[k] = sl[k]
    return r


def _group_slots(title: str) -> list[dict] | None:
    g = CUR["itemGroups"].get(title)
    if not g:
        return None
    if "slots" in g:
        return [_drop_cardless(dict(s)) for s in g["slots"]]
    sl = {"label": g["label"], "mode": g.get("mode", "any")}
    if "sets" in g:
        sl["sets"] = [list(s) for s in g["sets"]]
        sl["cards"] = list(dict.fromkeys(c for s in g["sets"] for c in s))
    else:
        sl["cards"] = list(g["cards"])
    if g.get("note"):
        sl["note"] = g["note"]
    return [_drop_cardless(sl)]


def _drop_cardless(sl: dict) -> dict:
    """Items with no TCG card are unrestricted: an any-slot with one is always met; in an
    all-slot / set they simply aren't a gate."""
    free = [c for c in sl.get("cards", []) if not R.card_exists(c)]
    if not free:
        return sl
    sl = dict(sl)
    if sl.get("sets"):
        sets = [[c for c in st if R.card_exists(c)] for st in sl["sets"]]
        if any(not st for st in sets):
            sl.update(unrestricted=True, sets=None)
        else:
            sl["sets"] = sets
        sl["cards"] = [c for c in sl["cards"] if R.card_exists(c)]
    elif sl.get("mode") == "all":
        sl["cards"] = [c for c in sl["cards"] if R.card_exists(c)]
        if not sl["cards"]:
            sl["unrestricted"] = True
    else:
        sl["cards"] = [c for c in sl["cards"] if R.card_exists(c)]
        if sl["cards"]:
            sl["noCardAlternatives"] = free          # informational; the slot stays gated
        else:
            sl["unrestricted"] = True
    sl["note"] = "; ".join(filter(None, [sl.get("note"), ", ".join(free) + " has no card"]))
    if sl.get("sets") is None:
        sl.pop("sets", None)
    return sl


def _norm_slot(sl: dict) -> dict:
    """Curated slot → canonical shape (cards from sets; group_ref expands an itemGroups entry)."""
    if sl.get("group_ref"):
        base = _group_slots(sl["group_ref"])[0]
        base["label"] = sl.get("label", base["label"])
        return base
    sl = dict(sl)
    sl.setdefault("mode", "any")
    if sl.get("sets"):
        sl["cards"] = list(dict.fromkeys(c for s in sl["sets"] for c in s))
    sl.setdefault("cards", [])
    return _drop_cardless(sl)


def _head(name: str) -> str:
    n = re.sub(r"\s*\(.*?\)", "", name.lower()).strip()
    if " of " in n:
        n = n.split(" of ")[0]
    return n.split()[-1] if n.split() else n


_ALT_RE = re.compile(r"can be used|will work|also works?|works with|in place of|acceptable|usable|"
                     r"\bwork\b|will also", re.I)


def _equip_slots(marked: str) -> tuple[list[dict], list[str], list[str]]:
    """Parse an 'Equip a X, Y and any Z.' sentence into slots. Returns (slots, notes, noCard)."""
    slots, notes, nocard = [], [], []
    m = re.search(r"\b(?:Equip|Wear)\b(.*)", marked)
    if not m:
        if re.search(r"nothing equipped|no items equipped", marked, re.I):
            notes.append("Nothing equipped")
        return slots, notes, nocard
    body = m.group(1)
    toks: list[str] = []

    def _hold(mm):
        toks.append(mm.group(1))
        return f"§{len(toks) - 1}§"
    held = _LINK_RE.sub(_hold, body)
    held = re.split(r"\.\s|\.$", held.strip())[0]
    held = re.sub(r"^\s*only\s+", "", held.strip(), flags=re.I)
    for seg in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s+along with\s+", held):
        seg = seg.strip(" .")
        if not seg:
            continue
        ids = [int(x) for x in re.findall("§(\\d+)§", seg)]
        text = re.sub("§\\d+§", "#", seg)
        if not ids:
            phrase = re.sub(r"^(?:a pair of|pair of|an?|the|some)\s+", "", seg.strip(), flags=re.I)
            if re.match(r"(?:no|nothing)\b|wear nothing", phrase, re.I):
                notes.append(seg[0].upper() + seg[1:])
                continue
            if notes and re.match(r"(?:no|nothing|wear nothing)\b", notes[-1], re.I) and len(phrase.split()) <= 2:
                notes[-1] += " and " + phrase           # "nothing on your chest and legs"
                continue
            card = R.item(phrase)
            if card:
                slots.append({"label": _version_label(phrase, card), "cards": [card], "mode": "any"})
            else:
                notes.append(f"Unmatched item wording: {seg}")
            continue
        alts: list[dict] = []
        for i in ids:
            title = toks[i]
            gs = _group_slots(title)
            if gs:
                alts.extend(gs)
                continue
            card = R.item(title)
            if card:
                alts.append({"label": _version_label(title, card), "cards": [card], "mode": "any"})
            else:
                nocard.append(title)
                alts.append({"label": title, "cards": [], "mode": "any", "unrestricted": True,
                             "note": f"{title} has no card"})
        if len(alts) > 1 and re.search(r"\bor\b", text, re.I):
            sl = {"label": " or ".join(a["label"] for a in alts), "mode": "any",
                  "cards": list(dict.fromkeys(c for a in alts for c in a["cards"]))}
            free = [a["label"] for a in alts if a.get("unrestricted")]
            if free and sl["cards"]:
                sl["noCardAlternatives"] = free
            elif free:
                sl["unrestricted"] = True
            slots.append(sl)
        else:
            slots.extend(alts)
    return slots, notes, nocard


def _version_label(title: str, card: str) -> str:
    """Label a worn item by the version the step names when it isn't the card itself: an emote
    step wanting an "Emerald amulet" shows that, not its card's name (Amulet of defence)."""
    t = CUR.get("itemNameFixes", {}).get(title.strip(), title).strip()
    if t.lower() == card.lower() or t.lower() not in R.aliases:
        return card
    return t[:1].upper() + t[1:]


def _add_alternatives(slots: list[dict], names: list[str]) -> list[str]:
    """Attach extra accepted item cards to the slot with the same head noun. Returns leftovers."""
    left = []
    for n in names:
        card = R.item(n)
        if not card or any(card in s["cards"] for s in slots):
            continue
        hits = [s for s in slots if s.get("mode") == "any" and not s.get("sets")
                and any(_head(c) == _head(card) for c in s["cards"])]
        if len(hits) == 1:
            hits[0]["cards"].append(card)
        else:
            left.append(card)
    return left


# ── Emote clues ───────────────────────────────────────────────────────────────

def _parse_emote_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Treasure_Trails/Guide/Emote_clues/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        if "clue" not in headers or "item" not in " ".join(headers):
            continue

        col_clue  = next((i for i, h in enumerate(headers) if h == "clue"), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), 1)
        col_notes = next((i for i, h in enumerate(headers) if "note" in h), -1)

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_clue, col_items):
                continue

            clue_marked  = _marked(cells[col_clue])
            notes_marked = _marked(cells[col_notes]) if 0 <= col_notes < len(cells) else ""
            clue_text = _cell_text(cells[col_clue])
            items     = _links_in_cell(cells[col_items])

            if not clue_text:
                continue

            step: dict = {"tier": tier, "clueText": clue_text, "items": items}
            if tier in DOUBLE_AGENT_TIERS:
                step["combatNpc"] = "Double agent"
            _emote_requirements(step, clue_marked, notes_marked)
            steps.append(step)

    print(f"  Emote {tier}: {len(steps)} steps")
    return steps


def _emote_requirements(step: dict, clue_marked: str, notes_marked: str) -> None:
    """slots (OR/AND item needs), emote unlock, location gates and Notes-column requirements."""
    acc = _new_reqs()
    override = next((v for k, v in CUR["emoteOverrides"].items() if step["clueText"].startswith(k)), None)
    if override and "slots" in override:
        slots, notes, nocard = [_norm_slot(s) for s in override["slots"]], [], []
    else:
        slots, notes, nocard = _equip_slots(clue_marked)
    # Notes: "X can be used / will work / also works" → extra accepted cards on the matching slot
    for sent in _sentences(notes_marked):
        p = _plain(sent)
        if _ALT_RE.search(p) and not _NEG_RE.search(p):
            _add_alternatives(slots, [m.group(1) for m in _LINK_RE.finditer(sent)])
    # Items-column icons not named in the Equip sentence (e.g. the bullroarer you swing)
    covered = {c for s in slots for c in s["cards"]}
    for name in step["items"]:
        card = R.item(name)
        if card and card not in covered and not _group_slots(name):
            left = _add_alternatives(slots, [name])
            if left:
                slots.append({"label": card, "cards": [card], "mode": "any"})
            covered.add(card)
        elif not card and name.lower() in R.no_card:
            nocard.append(name)
    step["slots"] = slots
    if notes:
        acc["reqNotes"] += notes
    acc["noCard"] += nocard
    acc["requirements"] += [r for r in (_slot_to_req(s) for s in slots) if r]
    if step.get("combatNpc"):
        r, nc = _npc_req(step["combatNpc"], "enemy")
        acc["requirements"] += r
        acc["noCard"] += nc
    # Emote unlock (Goblin Salute, Stronghold of Security emotes, Crab dance…)
    for name, u in CUR["emoteUnlocks"].items():
        if re.search(u["match"], step["clueText"], re.I):
            step["emote"] = name
            _merge(acc, {k: u.get(k, []) for k in ("quests", "partialQuests", "access")})
            if u.get("note"):
                acc["reqNotes"].append(u["note"])
    # Where: the clue's first sentence (before "Beware…"/"Equip…") → location rules
    where = re.split(r"\s(?:Beware|Equip|Wear|Have nothing|Have no)\b", step["clueText"])[0]
    _merge(acc, _loc_rules(where))
    # Notes column: quest / skill / item needs (equipping and access); skip "to obtain" ones.
    # Items the slots already cover (with their alternatives) aren't repeated as hard needs.
    ex = _extract(notes_marked)
    in_slots = {c for s in slots for c in s["cards"]}
    ex["requirements"] = [r for r in ex["requirements"]
                          if not (r.get("cards") and set(r["cards"]) <= in_slots)]
    _merge(acc, ex)
    _apply_override(acc, override)
    _finalize(step, acc)


def _apply_override(acc: dict, ov: dict | None) -> None:
    """Curated override: listed keys replace what the parser found ('requirements' are added)."""
    for k, v in (ov or {}).items():
        if k in ("quests", "partialQuests", "access", "reqNotes", "diaries", "noCard"):
            acc[k] = list(v)
        elif k == "skills":
            acc[k] = dict(v)
        elif k == "requirements":
            acc[k] += [dict(r) for r in v]
        elif k == "requirementsOnly":                # keep just these parsed requirements (by label)
            acc["requirements"] = [r for r in acc["requirements"] if r.get("label") in v]


def scrape_emote_clues(force_refresh: bool) -> dict[str, list[dict]]:
    return {tier: _parse_emote_tier(tier, force_refresh) for tier in EMOTE_TIERS}


# ── Sherlock ─────────────────────────────────────────────────────────────────

def _sherlock_item_slots(marked: str) -> tuple[list[dict], list[str], list[str]]:
    """Items-required cell → slots. ',' / 'and' = all, '/' / 'or' = any; '(… also work)' adds
    alternatives to the item before it. Returns (slots, notes, noCard)."""
    slots, notes, nocard = [], [], []
    toks: list[str] = []

    def _hold(m):
        toks.append(m.group(1))
        return f"\u00a7{len(toks) - 1}\u00a7"
    held = _LINK_RE.sub(_hold, marked)
    held = re.split(r"\bNote\s*:|\.\s+(?=[A-Z])", held)[0]

    def _paren(m):
        inner = m.group(1)
        ids = [int(x) for x in re.findall("\u00a7(\\d+)\u00a7", inner)]
        if re.search(r"also work|can be used|substitute|work as well", inner, re.I) and ids:
            return " \u00a4" + "+".join(map(str, ids)) + "\u00a4 "
        if re.search(r"not needed|if\b|unless", inner, re.I):
            notes.append(_plain(re.sub("\u00a7(\\d+)\u00a7", lambda mm: toks[int(mm.group(1))], inner)))
        return " "
    held = re.sub(r"\(([^()]*)\)", _paren, held)
    for seg in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", held):
        seg = seg.strip(" .")
        if not seg:
            continue
        seg = re.split("(?<=\u00a7)\\s+(?=[A-Z])", seg)[0]     # "X Catching a Y does not count" → X
        extra = [int(x) for grp in re.findall("\u00a4([\\d+]+)\u00a4", seg) for x in grp.split("+")]
        seg_main = re.sub("\u00a4[\\d+]+\u00a4", " ", seg)
        ids = [int(x) for x in re.findall("\u00a7(\\d+)\u00a7", seg_main)]
        if not ids:
            txt = _plain(seg_main)
            if txt and txt.lower() not in ("none", "-"):
                notes.append(txt[0].upper() + txt[1:])
            continue
        alts = []
        for i in ids + extra:
            title = toks[i]
            gs = _group_slots(title)
            if gs:
                alts.extend(gs)
                continue
            t = _item_token(title)
            if not t:
                continue
            kind, v = t
            if kind == "group":
                alts.append({"label": v["label"], "mode": "any", "cards": [],
                             **{k: v[k] for k in ("group", "tool") if k in v}})
            elif kind == "card":
                alts.append({"label": v, "cards": [v], "mode": "any"})
            else:
                nocard.append(v)
                alts.append({"label": v, "cards": [], "mode": "any", "unrestricted": True})
        if not alts:
            continue
        if len(alts) == 1:
            slots.append(alts[0])
            continue
        if any(a.get("sets") or a.get("mode") == "all" or a.get("group") or a.get("tool") for a in alts):
            slots.extend(alts)
            continue
        sl = {"label": " / ".join(dict.fromkeys(a["label"] for a in alts)), "mode": "any",
              "cards": list(dict.fromkeys(c for a in alts for c in a["cards"]))}
        free = [a["label"] for a in alts if a.get("unrestricted")]
        if free and sl["cards"]:
            sl["noCardAlternatives"] = free
        elif free:
            sl["unrestricted"] = True
        slots.append(sl)
    return slots, notes, nocard


def _parse_sherlock_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Sherlock/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    tasks: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        joined  = " ".join(headers)
        if "task" not in joined and "skill" not in joined:
            continue

        col_task  = next((i for i, h in enumerate(headers) if "task" in h), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), -1)
        col_skill = next((i for i, h in enumerate(headers) if "skill" in h), -1)
        col_other = next((i for i, h in enumerate(headers) if "other" in h), -1)
        if col_items < 0:
            continue

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_task, col_items):
                continue

            task_marked  = _marked(cells[col_task])
            items_marked = _marked(cells[col_items])
            skill_marked = _marked(cells[col_skill]) if 0 <= col_skill < len(cells) else ""
            other_marked = _marked(cells[col_other]) if 0 <= col_other < len(cells) else ""
            task_text = _cell_text(cells[col_task])
            items_td  = cells[col_items]
            items     = _links_in_cell(items_td)
            if not items:
                raw = _cell_text(items_td)
                if raw and raw.lower() not in ("none", "-", ""):
                    for part in re.split(r"\s*/\s*", raw):
                        part = part.strip()
                        if part and part.lower() != "none":
                            items.append(part)

            if not task_text:
                continue

            task = {"tier": tier, "task": task_text, "items": items, "npc": "Sherlock"}
            _sherlock_requirements(task, task_marked, items_marked, skill_marked, other_marked)
            tasks.append(task)

    print(f"  Sherlock {tier}: {len(tasks)} tasks")
    return tasks


def _sherlock_requirements(task: dict, task_marked: str, items_marked: str,
                           skill_marked: str, other_marked: str) -> None:
    acc = _new_reqs()
    keep = set(CUR["keepItems"]) | set(CUR["linkGroups"]) | set(CUR["itemGroups"])
    dropped = [n for n in task["items"] if not R.item(n) and n.lower() not in R.no_card and n not in keep]
    # Old `items` field: keep real items only (drops "Spiritual mage", "Superior garden", "Abyss", "None (…)")
    task["items"] = [n for n in task["items"] if n not in dropped]
    if dropped:
        task["droppedItems"] = dropped
    norm = lambda t: re.sub(r"\s+([.,!?])", r"\1", t).strip()
    ov = next((v for k, v in CUR["sherlockOverrides"].items() if norm(k) == norm(task["task"])), None)
    if ov is not None and "slots" in ov:
        sl = ov["slots"]
        slots = [_norm_slot(s) for s in (_group_slots(sl) if isinstance(sl, str) else sl)]
        notes, nocard = list(ov.get("reqNotes", [])), []
    else:
        slots, notes, nocard = _sherlock_item_slots(items_marked)
        if ov:
            notes += ov.get("reqNotes", [])
    task["slots"] = slots
    acc["reqNotes"] += notes
    acc["noCard"] += nocard
    acc["requirements"] += _npc_req("Sherlock", "npc")[0]
    acc["requirements"] += [r for r in (_slot_to_req(s) for s in slots) if r]
    for n in (ov or {}).get("optionalCards", []):
        acc["requirements"].append({"label": n, "type": "item", "cards": [R.item(n) or n], "optional": True})
    # Task wording: kill/slay → enemy card; pickpocket → NPC card (gathering/hunting needs none)
    verb = _plain(task_marked).split(" ")[0].lower()
    npc_names = list((ov or {}).get("npcCards", []))
    if not npc_names and verb in ("kill", "slay", "pickpocket"):
        npc_names = [m.group(1) for m in _LINK_RE.finditer(task_marked) if R.npc(m.group(1))][:1]
        if not npc_names:
            first = next(iter(_LINK_RE.finditer(task_marked)), None)
            if first:
                acc["noCard"].append(first.group(1))
    for n in npc_names:
        r, nc = _npc_req(n, "npc" if verb == "pickpocket" else "enemy")
        acc["requirements"] += r
        acc["noCard"] += nc
    # Skill(s) requirements / Other requirements columns
    task["skillsText"] = _plain(skill_marked)
    task["otherRequirements"] = _plain(other_marked)
    _merge(acc, {"skills": _skills_in(_plain(skill_marked))})
    _merge(acc, _extract(other_marked, reqcol=True, items=False))
    _merge(acc, _loc_rules(_plain(task_marked)))
    if ov and "reqNotes" in ov:
        acc["reqNotes"] = list(ov["reqNotes"])
    _finalize(task, acc)


def scrape_sherlock(force_refresh: bool) -> dict[str, list[dict]]:
    return {tier: _parse_sherlock_tier(tier, force_refresh) for tier in SHERLOCK_TIERS}


# ── Falo the Bard ─────────────────────────────────────────────────────────────

def scrape_falo(force_refresh: bool) -> list[dict]:
    html = wiki_fetcher.fetch("Falo_the_Bard", force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch Falo_the_Bard")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        if "lyric" not in " ".join(headers) and "item" not in " ".join(headers):
            continue

        current_lyric: str  = ""
        lyric_items: list[str] = []
        remaining_rows: int = 0

        def _flush():
            nonlocal current_lyric, lyric_items
            if current_lyric and lyric_items:
                steps.append({"lyric": current_lyric, "items": list(lyric_items),
                               "npc": "Falo the Bard"})
            current_lyric = ""
            lyric_items   = []

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            if remaining_rows > 0:
                remaining_rows -= 1
                for item in _links_in_cell(cells[0]):
                    if item not in lyric_items:
                        lyric_items.append(item)
            else:
                _flush()
                if len(cells) < 2:
                    continue
                rowspan        = int(cells[0].get("rowspan", 1))
                remaining_rows = rowspan - 1
                current_lyric  = _cell_text(cells[0])
                lyric_items    = list(_links_in_cell(cells[1]))

        _flush()
        break

    print(f"  Falo: {len(steps)} steps")
    return steps


# ── Cryptic clues — all step types ───────────────────────────────────────────

_TALK_RE = re.compile(r'\b(talk|speak)\b', re.IGNORECASE)
_KILL_RE2 = re.compile(r'\bkill\b', re.IGNORECASE)  # detect kill-the-NPC steps in notes

# Monster card names for filtering kill targets (loaded once at module level)
_MONSTER_CARD_NAMES: set[str] = set()


def _load_monster_card_names() -> None:
    global _MONSTER_CARD_NAMES
    p = Path(__file__).parent / "output" / "monster_drops.json"
    if p.exists() and not _MONSTER_CARD_NAMES:
        import json as _json
        _MONSTER_CARD_NAMES = {k.lower() for k in _json.loads(p.read_text()).keys()}


def _parse_cryptic_table(table: Tag, tier: str) -> list[dict]:
    """Extract ALL rows from one cryptic clue wikitable.

    Each step gets a "type" field:
      "kill"   — kill an NPC to obtain a key or casket (killNpcs field populated)
      "talk"   — talk/speak to an NPC (npc field populated)
      "dig"    — dig at a location (needs Spade)
      "search" — search/inspect an object (no card required)
    """
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    col_clue  = next((i for i, h in enumerate(headers) if "clue" in h), 0)
    col_notes = next((i for i, h in enumerate(headers)
                      if any(k in h for k in ("solution", "note", "task", "answer"))), 1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        idx_clue  = min(col_clue,  len(cells) - 1)
        idx_notes = min(col_notes, len(cells) - 1)

        clue_text  = _cell_text(cells[idx_clue])
        notes_text = _cell_text(cells[idx_notes]) if idx_notes < len(cells) else ""

        if not clue_text:
            continue

        combined = clue_text + " " + notes_text

        step: dict = {
            "tier":     tier,
            "clueText": clue_text,
            "location": notes_text,
            "_clue":    _marked(cells[idx_clue]),
            "_notes":   _marked(cells[idx_notes]) if idx_clue != idx_notes else "",
        }

        if _DIG_RE.search(clue_text):
            step["type"] = "dig"
        elif _KILL_RE2.search(notes_text):
            step["type"] = "kill"
            # Extract wiki-linked names that are monster cards as kill options.
            # Many steps allow alternatives ("or"), so store all card-linked targets.
            all_links = _links_in_cell(cells[idx_notes])
            kill_npcs = [n for n in all_links if n.lower() in _MONSTER_CARD_NAMES]
            if kill_npcs:
                step["killNpcs"] = kill_npcs
        elif _TALK_RE.search(combined):
            step["type"] = "talk"
            npc = _first_link_in_cell(cells[idx_notes])
            if not npc and idx_clue != idx_notes:
                npc = _first_link_in_cell(cells[idx_clue])
            if npc:
                step["npc"] = npc
        else:
            step["type"] = "search"

        steps.append(step)

    return steps


def scrape_cryptic_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape all cryptic clue steps from the wiki (all types)."""
    _load_monster_card_names()
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Cryptic_clues",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch cryptic clues page")
        return {t: [] for t in CRYPTIC_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, CRYPTIC_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in CRYPTIC_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_cryptic_table(table, tier))
        # Deduplicate by clue text (a clue can appear once per tier)
        seen: set[str] = set()
        deduped: list[dict] = []
        for s in steps:
            if s["clueText"] not in seen:
                seen.add(s["clueText"])
                deduped.append(s)
        result[tier] = deduped
        talk  = sum(1 for s in deduped if s["type"] == "talk")
        dig   = sum(1 for s in deduped if s["type"] == "dig")
        kill  = sum(1 for s in deduped if s["type"] == "kill")
        srch  = sum(1 for s in deduped if s["type"] == "search")
        print(f"  Cryptic {tier}: {len(deduped)} steps (talk={talk} dig={dig} kill={kill} search={srch})")

    return result


# ── Anagram clues ─────────────────────────────────────────────────────────────

def _parse_anagram_table(table: Tag, tier: str) -> list[dict]:
    """Extract rows from one anagram clue wikitable.

    Expected columns: Anagram | Solution (NPC) | Location | Challenge Answer
    """
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    col_anagram  = next((i for i, h in enumerate(headers) if "anagram" in h), 0)
    col_solution = next((i for i, h in enumerate(headers)
                         if any(k in h for k in ("solution", "npc", "answer to anagram"))), 1)
    col_location = next((i for i, h in enumerate(headers) if "location" in h), 2)
    col_challenge = next((i for i, h in enumerate(headers)
                          if "challenge" in h or "puzzle" in h), -1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        anagram  = _cell_text(cells[min(col_anagram,  len(cells)-1)])
        npc_cell = cells[min(col_solution, len(cells)-1)]
        npc      = _first_link_in_cell(npc_cell) or _cell_text(npc_cell).strip()
        loc_cell = cells[min(col_location, len(cells)-1)] if len(cells) > 2 else None
        loc_marked = _marked(loc_cell) if loc_cell is not None else ""
        location = _cell_text(loc_cell) if loc_cell is not None else ""
        challenge = None
        if col_challenge >= 0 and col_challenge < len(cells):
            raw = _cell_text(cells[col_challenge]).strip()
            if raw and raw.lower() not in ("-", "", "none", "puzzle box", "light box"):
                challenge = raw

        if anagram and npc:
            steps.append({
                "tier":      tier,
                "anagram":   anagram,
                "npc":       npc,
                "location":  location,
                "challenge": challenge,
                "_loc":      loc_marked,
            })

    return steps


def scrape_anagram_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape all anagram clue steps from the wiki."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Anagrams",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch anagram clues page")
        return {t: [] for t in ANAGRAM_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, ANAGRAM_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in ANAGRAM_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_anagram_table(table, tier))
        result[tier] = steps
        print(f"  Anagram {tier}: {len(steps)} clues")

    return result


# ── Cipher clues ──────────────────────────────────────────────────────────────

def _parse_cipher_table(table: Tag, tier: str) -> list[dict]:
    """Extract rows from one cipher clue wikitable.

    Columns: Cipher | Solution (NPC or location) | Shift distance | Location | Challenge answer
    Rows where Solution is a plain location string (no wikilink) are dig/search steps — skip.
    """
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    col_cipher    = next((i for i, h in enumerate(headers) if "cipher" in h), 0)
    col_solution  = next((i for i, h in enumerate(headers)
                          if "solution" in h or "npc" in h), 1)
    col_challenge = next((i for i, h in enumerate(headers)
                          if "challenge" in h), -1)
    col_location  = next((i for i, h in enumerate(headers) if "location" in h), -1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        loc_marked = _marked(cells[col_location]) if 0 <= col_location < len(cells) else ""
        cipher_text  = _cell_text(cells[min(col_cipher,   len(cells)-1)])
        solution_cell = cells[min(col_solution, len(cells)-1)]
        npc = _first_link_in_cell(solution_cell)
        if not npc:
            continue   # plain-text location (no NPC card) — skip

        challenge = None
        if col_challenge >= 0 and col_challenge < len(cells):
            raw = _cell_text(cells[col_challenge]).strip()
            if raw and raw.lower() not in ("-", "", "none"):
                challenge = raw

        if cipher_text and npc:
            steps.append({
                "tier":      tier,
                "cipher":    cipher_text,
                "npc":       npc,
                "challenge": challenge,
                "location":  _plain(loc_marked),
                "_loc":      loc_marked,
            })

    return steps


def scrape_cipher_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape cipher clue steps that resolve to an NPC."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Ciphers",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch cipher clues page")
        return {t: [] for t in CIPHER_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, CIPHER_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in CIPHER_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_cipher_table(table, tier))
        result[tier] = steps
        print(f"  Cipher {tier}: {len(steps)} clues")

    return result


# ── Hot/cold clues ────────────────────────────────────────────────────────────

def _parse_hotcold_page(tier: str, force_refresh: bool) -> list[dict]:
    """Scrape one hot/cold tier subpage.

    Beginner columns: Location | Image | Map  (no combat NPC)
    Master columns:   Location | Image | Map | Combat Type  (Single→Brassican Mage, Multi→Ancient Wizard)
    """
    page = f"Treasure_Trails/Guide/Hot_Cold/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]
        if "location" not in " ".join(headers):
            continue

        col_location = next((i for i, h in enumerate(headers) if "location" in h), 0)
        col_combat   = next((i for i, h in enumerate(headers) if "combat" in h), -1)
        hdr = table.find_previous(["h2", "h3", "h4"])
        region = hdr.get_text(" ", strip=True) if hdr and hdr.name == "h4" else None

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue

            loc_marked = _marked(cells[min(col_location, len(cells) - 1)])
            location = _cell_text(cells[min(col_location, len(cells) - 1)])
            if not location:
                continue

            step: dict = {"tier": tier, "location": location, "_loc": loc_marked}
            if region:
                step["region"] = region

            if col_combat >= 0 and col_combat < len(cells):
                combat_text = _cell_text(cells[col_combat]).strip()
                npc = HOT_COLD_COMBAT.get(combat_text)
                if npc:
                    step["combatNpc"] = npc
                elif not npc and "border" in location.lower():
                    # Single/multi-combat border — wiki recommends single (Brassican Mage)
                    step["combatNpc"] = "Brassican Mage"

            steps.append(step)

    print(f"  Hot/cold {tier}: {len(steps)} steps")
    return steps


def scrape_hotcold_clues(force_refresh: bool) -> dict[str, list[dict]]:
    return {tier: _parse_hotcold_page(tier, force_refresh) for tier in HOT_COLD_TIERS}


# ── Map clues (per step) ──────────────────────────────────────────────────────

_SEARCH_RE = re.compile(r"\bsearch|\bcrate|\bchest\b|drawers|\bboxes\b|\bbarrel|wardrobe|cupboard|"
                        r"\bopen the\b|\bbookcase|\bbush\b|haystack|\bsack", re.I)
_SPADE_REQ = {"label": "Spade", "type": "item", "cards": ["Spade"]}


def scrape_map_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Treasure_Trails/Guide/Maps → per tier [{tier, location, dig, requirements, …}]."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Maps", force_refresh=force_refresh)
    out: dict[str, list[dict]] = {t: [] for t in MAP_CLUE_TIERS}
    if not html:
        print("  [WARN] Could not fetch map clues page")
        return out
    soup = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, MAP_CLUE_TIERS)
    for tier in MAP_CLUE_TIERS:
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]
            col_loc = next((i for i, h in enumerate(headers) if "location" in h), 1)
            col_page = next((i for i, h in enumerate(headers) if h == "page"), -1)
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if not cells:
                    continue
                loc_marked = _marked(cells[min(col_loc, len(cells) - 1)])
                step = {"tier": tier, "location": _plain(loc_marked)}
                if 0 <= col_page < len(cells):
                    step["page"] = _plain(_marked(cells[col_page]))
                step["dig"] = not (_SEARCH_RE.search(step["location"]) and not _DIG_RE.search(step["location"]))
                acc = _new_reqs()
                if step["dig"]:
                    acc["requirements"].append(dict(_SPADE_REQ))
                _merge(acc, _extract(loc_marked))
                _merge(acc, _loc_rules(_location_text(loc_marked)))
                out[tier].append(_finalize(step, acc))
        print(f"  Map {tier}: {len(out[tier])} steps")
    return out


# ── Coordinate clues (per step) ───────────────────────────────────────────────

def scrape_coordinate_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Treasure_Trails/Guide/Coordinates → per tier [{coords, coordsText, location, fight, …}].

    One wikitable per coordinate: row 1 = Coordinates | Shorthand | Requirements | Fight;
    a later 'Location notes' header row is followed by the notes cell.
    """
    tiers = list(COORDINATE_CLUE_TIERS)
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Coordinates", force_refresh=force_refresh)
    out: dict[str, list[dict]] = {t: [] for t in tiers}
    if not html:
        print("  [WARN] Could not fetch coordinate clues page")
        return out
    soup = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, tiers)
    for tier in tiers:
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []) or not table.find("td"):
                continue
            trs = table.find_all("tr")
            head = [th.get_text(" ", strip=True).lower() for th in trs[0].find_all("th")]
            data = next((tr.find_all("td") for tr in trs[1:] if tr.find_all("td")), [])
            col = lambda name: next((i for i, h in enumerate(head) if name in h), -1)
            cell = lambda i: data[i] if 0 <= i < len(data) else None
            c_coord, c_short, c_req, c_fight = col("coordinates"), col("shorthand"), col("requirement"), col("fight")
            notes_marked = ""
            for i, tr in enumerate(trs):
                if any("location notes" in th.get_text(" ").lower() for th in tr.find_all("th")):
                    nxt = next((t for t in trs[i + 1:] if t.find("td")), None)
                    notes_marked = _marked(nxt.find("td")) if nxt else ""
            short = _plain(_marked(cell(c_short))) if cell(c_short) else ""
            req_marked = _marked(cell(c_req)) if cell(c_req) else ""
            fight_marked = _marked(cell(c_fight)) if cell(c_fight) else ""
            step = {"tier": tier, "coords": short,
                    "coordsText": _plain(_marked(cell(c_coord))) if cell(c_coord) else "",
                    "location": _plain(notes_marked),
                    "requirementsText": _plain(req_marked)}
            fight = [m.group(1) for m in _LINK_RE.finditer(fight_marked)]
            acc = _new_reqs()
            acc["requirements"].append(dict(_SPADE_REQ))
            if fight:
                step["fight"] = fight
                cards = [R.npc(n) for n in fight]
                acc["noCard"] += [n for n, c in zip(fight, cards) if not c]
                cards = [c for c in cards if c]
                if len(cards) == 1:
                    acc["requirements"].append({"label": cards[0], "type": "enemy", "cards": cards})
                elif cards:
                    acc["requirements"].append({
                        "label": " or ".join(cards) + " (random spawn: both cards guarantee the step)",
                        "type": "enemy", "cards": cards, "mode": "all"})
                if "Zamorak wizard" in fight:
                    _merge(acc, {"access": ["wilderness"]})
            _merge(acc, _extract(req_marked, reqcol=True))
            if not (acc["quests"] or acc["partialQuests"]):
                # The Requirements column is the wiki's quest list for the spot; the notes only
                # add region gates it leaves out (Kourend, desert, Wilderness …)
                _merge(acc, {"access": _loc_rules(_location_text(notes_marked))["access"]})
            ov = CUR["coordinateOverrides"].get(short)
            if ov:
                for k in ("quests", "partialQuests", "requirements", "skills", "access"):
                    if k in ov:
                        if k == "requirements":   # replace parsed item needs; keep Spade + fight
                            acc[k] = [r for r in acc[k] if r.get("type") != "item" or r.get("label") == "Spade"] + ov[k]
                        else:
                            acc[k] = ov[k] if not isinstance(ov[k], list) else list(ov[k])
                if "reqNotes" in ov:
                    acc["reqNotes"] = list(ov["reqNotes"])
            out[tier].append(_finalize(step, acc))
        print(f"  Coordinate {tier}: {len(out[tier])} steps")
    return out


# ── Requirements for the talk / riddle step types ─────────────────────────────

def _cryptic_requirements(step: dict) -> None:
    acc = _new_reqs()
    clue_m, notes_m = step.pop("_clue", ""), step.pop("_notes", "")
    t = step.get("type")
    if t == "talk":
        r, nc = _npc_req(step.get("npc"), "npc")
        acc["requirements"] += r
        acc["noCard"] += nc
    elif t == "kill" and step.get("killNpcs"):
        cards = list(dict.fromkeys(c for c in (R.npc(n) for n in step["killNpcs"]) if c))
        if cards:
            acc["requirements"].append({"label": " or ".join(cards), "type": "enemy", "cards": cards})
    if t == "dig" or (t != "talk" and re.match(r"\s*(?:dig|directly under)\b", _plain(notes_m), re.I)):
        step["dig"] = True                           # 'type' stays as before; many search-typed steps are digs
        acc["requirements"].append(dict(_SPADE_REQ))
    if step.get("charlieItems"):
        cards = [c for c in (R.item(n) for n in step["charlieItems"]) if c]
        acc["requirements"].append({"label": "The item Charlie asks for (one of these, at random)",
                                    "type": "item", "cards": cards, "random": True})
    ov = next((v for k, v in CUR["crypticOverrides"].items() if step["clueText"].startswith(k)), {})
    _merge(acc, _extract(notes_m))
    if t != "kill":                                  # kill steps list every spawn; no single place
        _merge(acc, _loc_rules(_plain(clue_m) + " " + _location_text(notes_m)))
    _apply_override(acc, ov)
    _finalize(step, acc)


def _talk_requirements(step: dict) -> None:
    """Anagram / cipher: the NPC's card plus the location's gates."""
    acc = _new_reqs()
    loc_m = step.pop("_loc", "")
    r, nc = _npc_req(step.get("npc"), "npc")
    acc["requirements"] += r
    acc["noCard"] += nc
    _merge(acc, _extract(loc_m, items=True))
    _merge(acc, _loc_rules(_location_text(loc_m)))
    _apply_override(acc, CUR["talkOverrides"].get(step.get("npc")))
    _finalize(step, acc)


def _hotcold_requirements(step: dict) -> None:
    acc = _new_reqs()
    loc_m = step.pop("_loc", "")
    acc["requirements"].append(dict(_SPADE_REQ))
    if step.get("combatNpc"):
        r, nc = _npc_req(step["combatNpc"], "enemy")
        acc["requirements"] += r
        acc["noCard"] += nc
    region = step.get("region")
    key = CUR["hotcoldRegions"].get(region) if region else None
    if key and not any(e["region"] == region and re.search(e["match"], step["location"], re.I)
                       for e in CUR["hotcoldRegionExceptions"]):
        acc["access"].append(key)
    _merge(acc, _extract(loc_m))
    _merge(acc, _loc_rules(_location_text(loc_m)))
    _finalize(step, acc)


def _falo_requirements(step: dict) -> None:
    acc = _new_reqs()
    cards, nocard = [], []
    for n in step["items"]:
        c = R.item(n)
        (cards if c else nocard).append(c or n)
    cards = list(dict.fromkeys(cards))
    if nocard and not cards:
        step["slots"] = [{"label": nocard[0], "cards": [], "mode": "any", "unrestricted": True,
                          "note": f"{nocard[0]} has no card"}]
    else:
        step["slots"] = [{"label": " / ".join(cards), "cards": cards, "mode": "any"}]
        if nocard:
            step["slots"][0]["noCardAlternatives"] = nocard
    acc["noCard"] += nocard
    acc["requirements"] += _npc_req("Falo the Bard", "npc")[0]
    acc["requirements"] += [r for r in (_slot_to_req(s) for s in step["slots"]) if r]
    _finalize(step, acc)


# ── Validation ────────────────────────────────────────────────────────────────

_GROUPS = {"light_source", "slash_weapon", "dragonfire"}
_TOOLS = {"Pickaxe", "Axe", "Harpoon"}


def validate(output: dict) -> list[str]:
    problems: list[str] = []

    def _chk_req(where: str, r: dict):
        for c in r.get("cards", []) + [c for s in r.get("sets") or [] for c in s]:
            if not R.card_exists(c):
                problems.append(f"{where}: card {c!r} not in catalog/aliases")
        if r.get("group") and r["group"] not in _GROUPS:
            problems.append(f"{where}: unknown group {r['group']!r}")
        if r.get("tool") and r["tool"] not in _TOOLS:
            problems.append(f"{where}: unknown tool {r['tool']!r}")
        for rt in r.get("routes") or []:
            for d in rt.get("diaries", []):
                area, _, tier = d.rpartition(" ")
                if area not in R.diary_areas or tier not in ("Easy", "Medium", "Hard", "Elite"):
                    problems.append(f"{where}: route diary {d!r}")
        acc_keys = r.get("access") or []
        for a in ([acc_keys] if isinstance(acc_keys, str) else acc_keys):
            if a not in R.access:
                problems.append(f"{where}: unknown access {a!r}")

    def _chk_step(where: str, st: dict):
        for r in st.get("requirements", []):
            _chk_req(where, r)
        for sl in st.get("slots", []):
            _chk_req(where + " slot", sl)
        for q in st.get("quests", []) + st.get("partialQuests", []):
            if q not in R.quests:
                problems.append(f"{where}: quest {q!r} not in quests.json")
        for a in st.get("access", []):
            if a not in R.access:
                problems.append(f"{where}: access {a!r} not in access_routes.json")
        for sk in st.get("skills", {}):
            if sk not in SKILLS:
                problems.append(f"{where}: skill {sk!r}")
        for d in st.get("diaries", []):
            area, _, tier = d.rpartition(" ")
            if area not in R.diary_areas or tier not in ("Easy", "Medium", "Hard", "Elite"):
                problems.append(f"{where}: diary {d!r}")
        for n in st.get("noCard", []):
            if R.card_exists(n):
                problems.append(f"{where}: noCard {n!r} actually has a card")

    for kind in ("emote", "sherlock", "cryptic", "anagram", "cipher", "hotcold", "map", "coordinate"):
        for tier, steps in output[kind].items():
            for i, st in enumerate(steps):
                _chk_step(f"{kind}/{tier}#{i}", st)
    for i, st in enumerate(output["falo"]):
        _chk_step(f"falo#{i}", st)
    # curated lists
    for title, g in CUR["itemGroups"].items():
        for sl in _group_slots(title):
            _chk_req(f"itemGroups[{title}]", sl)
    for name, ov in CUR["sherlockOverrides"].items():
        sl = ov.get("slots", [])
        for s in (_group_slots(sl) if isinstance(sl, str) else [_norm_slot(x) for x in sl]):
            _chk_req(f"sherlockOverrides[{name[:30]}]", s)
    for n in CUR["noCard"]:
        if R.card_exists(n):
            problems.append(f"noCard: {n!r} has a card")
    for old, new in CUR["npcFixes"].items():
        if new and not R.npc(new):
            problems.append(f"npcFixes: {new!r} is not an NPC card")
    for rule in CUR["locationRules"]:
        for a in rule.get("access", []):
            if a not in R.access:
                problems.append(f"locationRules[{rule['match'][:20]}]: access {a!r}")
        for q in rule.get("quests", []) + rule.get("partialQuests", []):
            if q not in R.quests:
                problems.append(f"locationRules[{rule['match'][:20]}]: quest {q!r}")
    for q, a in list(CUR["questAccess"].items()) + list(CUR["partialQuestAccess"].items()):
        if q not in R.quests or a not in R.access:
            problems.append(f"questAccess: {q!r} → {a!r}")
    return problems


def _summary(output: dict) -> None:
    from collections import Counter
    print("\nRequirement summary (steps with: requirements / quests+partial / skills / access / slots):")
    for kind in ("emote", "sherlock", "cryptic", "anagram", "cipher", "hotcold", "map", "coordinate"):
        for tier, steps in output[kind].items():
            n = len(steps)
            c = lambda k: sum(1 for s in steps if s.get(k))
            q = sum(1 for s in steps if s.get("quests") or s.get("partialQuests"))
            print(f"  {kind:10s} {tier:8s} {n:4d} steps | req {c('requirements'):3d} | quest {q:3d} | "
                  f"skill {c('skills'):3d} | access {c('access'):3d} | slots {c('slots'):3d} | notes {c('reqNotes'):3d}")
    steps = output["falo"]
    print(f"  falo       Master   {len(steps):4d} steps | slots {sum(1 for s in steps if s.get('slots'))}")
    acc = Counter(a for kind in ("emote", "sherlock", "cryptic", "anagram", "cipher", "hotcold", "map", "coordinate")
                  for steps in output[kind].values() for s in steps for a in s.get("access", []))
    print("  access keys used:", dict(acc))


# ── Reverse indexes ───────────────────────────────────────────────────────────

def _build_indexes(
    emote:    dict[str, list[dict]],
    sherlock: dict[str, list[dict]],
    falo:     list[dict],
    cryptic:  dict[str, list[dict]],
    anagram:  dict[str, list[dict]],
    cipher:   dict[str, list[dict]],
    hotcold:  dict[str, list[dict]],
) -> tuple[dict, dict]:
    """Return (itemIndex, npcIndex) for fast O(1) browser lookup."""
    item_index: dict[str, list[dict]] = {}
    npc_index:  dict[str, list[dict]] = {}

    def _add_item(item: str, ref: dict):
        k = item.strip()
        if k:
            item_index.setdefault(k, []).append(ref)

    def _add_npc(npc: str, ref: dict):
        k = npc.strip()
        if k:
            npc_index.setdefault(k, []).append(ref)

    # Emote — items + Double Agent
    for tier, steps in emote.items():
        for step in steps:
            ref = {"type": "emote", "tier": tier,
                   "clueText": step["clueText"], "items": step["items"]}
            for item in step["items"]:
                _add_item(item, ref)
            if step.get("combatNpc"):
                _add_npc(step["combatNpc"],
                         {"type": "emote_combat", "tier": tier,
                          "clueText": step["clueText"]})

    # Sherlock — items + NPC
    for tier, tasks in sherlock.items():
        for task in tasks:
            ref = {"type": "sherlock", "tier": tier,
                   "task": task["task"], "items": task["items"]}
            for item in task["items"]:
                _add_item(item, ref)
            _add_npc("Sherlock", {"type": "sherlock", "tier": tier,
                                  "task": task["task"]})

    # Falo — items + NPC
    for step in falo:
        ref = {"type": "falo", "lyric": step["lyric"], "items": step["items"]}
        for item in step["items"]:
            _add_item(item, ref)
        _add_npc("Falo the Bard", {"type": "falo", "lyric": step["lyric"],
                                    "items": step["items"]})

    # Cryptic — NPC; Charlie the Tramp steps also index his possible items
    for tier, steps in cryptic.items():
        for step in steps:
            if not step.get("npc"):
                continue
            ref = {"type": "cryptic", "tier": tier, "clueText": step["clueText"]}
            if step["npc"] == "Charlie the Tramp" and step.get("charlieItems"):
                ref["charlieItems"] = step["charlieItems"]
            _add_npc(step["npc"], ref)
            # Charlie's item requests go into the item index too
            if step["npc"] == "Charlie the Tramp":
                for item in CHARLIE_ITEMS:
                    _add_item(item, {"type": "charlie", "tier": "Beginner",
                                     "clueText": step["clueText"],
                                     "charlieItems": CHARLIE_ITEMS})

    # Anagram — NPC only
    for tier, steps in anagram.items():
        for step in steps:
            if step.get("npc"):
                _add_npc(step["npc"], {"type": "anagram", "tier": tier,
                                        "anagram": step["anagram"],
                                        "challenge": step.get("challenge")})

    # Cipher — NPC only
    for tier, steps in cipher.items():
        for step in steps:
            if step.get("npc"):
                _add_npc(step["npc"], {"type": "cipher", "tier": tier,
                                        "cipher": step["cipher"],
                                        "challenge": step.get("challenge")})

    # Map clues — Spade required for each tier
    for tier in MAP_CLUE_TIERS:
        _add_item("Spade", {"type": "map", "tier": tier})

    # Coordinate clues — Spade + optional combat NPCs per tier
    for tier, info in COORDINATE_CLUE_TIERS.items():
        _add_item("Spade", {"type": "coordinate", "tier": tier})
        if info.get("combatNpc"):
            _add_npc(info["combatNpc"],
                     {"type": "coordinate_combat", "tier": tier,
                      "wilderness": False, "alt": False})
        if info.get("wildernessNpc"):
            _add_npc(info["wildernessNpc"],
                     {"type": "coordinate_combat", "tier": tier,
                      "wilderness": True, "alt": False})
        if info.get("altCombatNpc"):
            _add_npc(info["altCombatNpc"],
                     {"type": "coordinate_combat", "tier": tier,
                      "wilderness": False, "alt": True})

    # Hot/cold — Spade required for all tiers; Master steps also spawn a combat NPC
    for tier, steps in hotcold.items():
        _add_item("Spade", {"type": "hotcold", "tier": tier})
        for step in steps:
            if step.get("combatNpc"):
                _add_npc(step["combatNpc"],
                         {"type": "hotcold_combat", "tier": tier,
                          "location": step["location"]})

    return item_index, npc_index


# ── Total step counts (for achievability display) ─────────────────────────────

def scrape_step_counts(
    emote:    dict[str, list[dict]],
    sherlock: dict[str, list[dict]],
    falo:     list[dict],
    cryptic:  dict[str, list[dict]],
    anagram:  dict[str, list[dict]],
    cipher:   dict[str, list[dict]],
    hotcold:  dict[str, list[dict]],
    force_refresh: bool,
) -> dict[str, dict[str, int]]:
    """Return total step counts per type per tier.

    All clue types are now fully scraped, so counts are derived directly
    from the structured data.  Only map, coordinate, scan, and hot/cold
    still need wiki fetches (they have no per-step structured data).
    """
    counts: dict[str, dict[str, int]] = {}

    # ── Fully scraped — derive counts directly ────────────────────────────────
    counts["emote"]    = {t: len(v) for t, v in emote.items()}
    counts["sherlock"] = {t: len(v) for t, v in sherlock.items()}
    counts["falo"]     = {"Master": len(falo)}
    counts["anagram"]  = {t: len(v) for t, v in anagram.items()}
    counts["cipher"]   = {t: len(v) for t, v in cipher.items()}

    # Cryptic — total and dig counts derived from the fully-structured data
    counts["cryptic"]    = {t: len(v) for t, v in cryptic.items()}
    counts["crypticDig"] = {
        t: sum(1 for s in v if s.get("type") == "dig")
        for t, v in cryptic.items()
    }

    # ── Map clues ─────────────────────────────────────────────────────────────
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Maps",
                               force_refresh=force_refresh)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        by_tier = _split_by_tier_headers(soup, MAP_CLUE_TIERS)
        map_counts: dict[str, int] = {}
        for tier in MAP_CLUE_TIERS:
            total = 0
            for table in by_tier[tier]:
                if "wikitable" not in table.get("class", []):
                    continue
                for tr in table.find_all("tr"):
                    if tr.find_all("td"):
                        total += 1
            # Gallery items (li.gallerybox) for tiers that use image galleries
            # collected under the same tier header
            map_counts[tier] = total if total else map_counts.get(tier, 0)
        counts["map"] = map_counts
        print("  Map totals:", map_counts)

    # ── Coordinate clues ──────────────────────────────────────────────────────
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Coordinates",
                               force_refresh=force_refresh)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        coord_tier_names = list(COORDINATE_CLUE_TIERS.keys())
        by_tier = _split_by_tier_headers(soup, coord_tier_names)
        coord_counts: dict[str, int] = {}
        for tier in coord_tier_names:
            # one wikitable per coordinate (each is a small multi-row table), so count tables
            coord_counts[tier] = sum(1 for table in by_tier[tier]
                                     if "wikitable" in table.get("class", []) and table.find("td"))
        counts["coordinate"] = coord_counts
        print("  Coordinate totals:", coord_counts)

    # (Scan clues are an RS3 mechanic — OSRS has none; removed 2026-10-11.)

    # ── Hot/cold clues — derived from fully-structured data ──────────────────
    counts["hotcold"] = {t: len(v) for t, v in hotcold.items()}
    print("  Hot/cold totals:", counts["hotcold"])

    return counts


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force-refresh", action="store_true",
                   help="Re-fetch pages even if cached")
    args = p.parse_args()
    force = args.force_refresh
    global R
    R = _Resolver()

    print("Scraping emote clue steps…")
    emote = scrape_emote_clues(force)

    print("Scraping Sherlock tasks…")
    sherlock = scrape_sherlock(force)

    print("Scraping Falo the Bard…")
    falo = scrape_falo(force)

    print("Scraping cryptic clue talk-to steps…")
    cryptic = scrape_cryptic_clues(force)

    print("Scraping anagram clues…")
    anagram = scrape_anagram_clues(force)

    print("Scraping cipher clues…")
    cipher = scrape_cipher_clues(force)

    print("Scraping hot/cold clue steps…")
    hotcold = scrape_hotcold_clues(force)

    print("Scraping map clue steps…")
    map_steps = scrape_map_clues(force)

    print("Scraping coordinate clue steps…")
    coord_steps = scrape_coordinate_clues(force)

    # Inject Charlie the Tramp's item requests into his cryptic clue steps
    for step in cryptic.get("Beginner", []):
        if step.get("npc") == "Charlie the Tramp":
            step["charlieItems"] = CHARLIE_ITEMS

    print("Scraping total step counts…")
    step_counts = scrape_step_counts(emote, sherlock, falo, cryptic, anagram, cipher, hotcold, force)

    print("Building indexes…")
    item_index, npc_index = _build_indexes(emote, sherlock, falo, cryptic, anagram, cipher, hotcold)

    # Cryptic dig steps — Spade required; one index entry per tier
    for tier, count in step_counts.get("crypticDig", {}).items():
        if count:
            item_index.setdefault("Spade", []).append(
                {"type": "cryptic_dig", "tier": tier, "count": count}
            )

    # Structured dig-clue info for the browser (tiers + Spade + combat NPCs)
    dig_info = {
        "map": {tier: {} for tier in MAP_CLUE_TIERS},
        "coordinate": {
            tier: info for tier, info in COORDINATE_CLUE_TIERS.items()
        },
    }

    # Clue NPCs the wiki tables name by place/role, mapped to their TCG card (checked on the
    # wiki 2026-10-11). None = not an NPC (a place), so the step has no NPC card gate.
    for steps_by_tier in (cryptic, anagram, cipher):
        for steps in steps_by_tier.values():
            for st in steps:
                if isinstance(st, dict) and st.get("npc") in CLUE_NPC_FIXES:
                    st["npc"] = CLUE_NPC_FIXES[st["npc"]]
                    if st["npc"] is None:
                        st.pop("npc")
    for old, new in CLUE_NPC_FIXES.items():
        refs = npc_index.pop(old, [])
        if new and refs:
            npc_index.setdefault(new, []).extend(refs)

    # Shared requirement model for the talk / riddle step types (after the NPC fixes)
    for steps in cryptic.values():
        for st in steps:
            _cryptic_requirements(st)
    for steps_by_tier in (anagram, cipher):
        for steps in steps_by_tier.values():
            for st in steps:
                _talk_requirements(st)
    for steps in hotcold.values():
        for st in steps:
            _hotcold_requirements(st)
    for st in falo:
        _falo_requirements(st)

    output = {
        "emote":      emote,
        "sherlock":   sherlock,
        "falo":       falo,
        "cryptic":    cryptic,
        "anagram":    anagram,
        "cipher":     cipher,
        "hotcold":    hotcold,
        "digInfo":    dig_info,
        "stepCounts": step_counts,
        "itemIndex":  item_index,
        "npcIndex":   npc_index,
        "map":        map_steps,
        "coordinate": coord_steps,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

    total_emote    = sum(len(v) for v in emote.values())
    total_sherlock = sum(len(v) for v in sherlock.values())
    total_cryptic  = sum(len(v) for v in cryptic.values())
    total_anagram  = sum(len(v) for v in anagram.values())
    total_cipher   = sum(len(v) for v in cipher.values())
    print(f"\nWrote {_OUT}")
    print(f"  Emote steps:         {total_emote}")
    print(f"  Sherlock tasks:      {total_sherlock}")
    print(f"  Falo steps:          {len(falo)}")
    print(f"  Cryptic steps:       {total_cryptic}")
    print(f"  Anagram clues:       {total_anagram}")
    print(f"  Cipher clues:        {total_cipher}")
    print(f"  Item index entries:  {len(item_index)}")
    print(f"  NPC index entries:   {len(npc_index)}")
    print(f"  Map steps:           {sum(len(v) for v in map_steps.values())}")
    print(f"  Coordinate steps:    {sum(len(v) for v in coord_steps.values())}")
    _summary(output)
    problems = validate(output)
    print(f"\nValidation: {len(problems)} problem(s)")
    for x in problems:
        print("  ! " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
