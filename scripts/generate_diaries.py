"""Generate diaries.json — Achievement Diary tasks and requirements from the OSRS Wiki.

Each wiki diary page has one task table per tier: task text in the first cell,
requirements (skills, quests, items) as bullet lines in the second. This script
parses those tables and derives each task's TCG card needs from central data:

  - items in the Requirements column (things you use → need the card under
    Bronzeman rules) — matched to cards via the catalog's tcg.variants
  - for "make / cook / craft / smith … X" tasks, X's production ingredients from
    output/item_sources.json (the same data item pages use)
  - monsters linked in the task text when you kill / slay / defeat / pickpocket them
  - talk-only NPCs need no card, so they aren't listed

Hand-curated data (reward NPCs, tier rewards, per-task card overrides) lives in
the constants below, so the generated file is the single source the page reads.

Output: scripts/output/diaries.json — same shape the page uses for DIARY_DATA:
  [{ name, rewardNpc, easy|medium|hard|elite: {
       skills, quests, items, monsters,            # derived: union/max over tasks
       rewards: {item, lamp, benefits[]},
       tasks: [{ n, task, skills, boostable?, skillsAny?, combat?, quests,
                 partialQuests?, items, monsters, notes? }] } }]

Usage:
  python3 scripts/generate_diaries.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from generate_sources import _card_for_drop, load_variant_aliases, set_variant_aliases

_DIR = Path(__file__).resolve().parent
_OUT_DIR = _DIR / "output"
TIERS = ["easy", "medium", "hard", "elite"]

# Our area name -> wiki page
AREAS: dict[str, str] = {
    "Ardougne": "Ardougne Diary",
    "Desert": "Desert Diary",
    "Falador": "Falador Diary",
    "Fremennik": "Fremennik Diary",
    "Kandarin": "Kandarin Diary",
    "Karamja": "Karamja Diary",
    "Kourend & Kebos": "Kourend & Kebos Diary",
    "Lumbridge & Draynor": "Lumbridge & Draynor Diary",
    "Morytania": "Morytania Diary",
    "Varrock": "Varrock Diary",
    "Western Provinces": "Western Provinces Diary",
    "Wilderness": "Wilderness Diary",
}

# ── Curated layer ─────────────────────────────────────────────────────────────
# Who hands out each area's diary rewards (wiki; not machine-readable on the pages).
REWARD_NPCS: dict[str, str] = {
    "Ardougne": "Two-pints",
    "Desert": "Jarr",
    "Falador": "Sir Rebral",
    "Fremennik": "Thorodin",
    "Kandarin": "The 'Wedge'",
    "Karamja": "Pirate Jackie the Fruit",
    "Kourend & Kebos": "Elise",
    "Lumbridge & Draynor": "Hatius Cosaintus",
    "Morytania": "Le-sabrè",
    "Varrock": "Toby",
    "Western Provinces": "Elder gnome child",
    "Wilderness": "Lesser Fanatic",
}

# Barrows equipment sets (the brother who drops each, and its four pieces). Level needs stay
# simplified on the task (Defence 70 + any of Attack/Strength/Magic/Ranged 70).
BARROWS_SETS = [
    {"name": "Ahrim's", "monster": "Ahrim the Blighted",
     "items": ["Ahrim's hood", "Ahrim's robetop", "Ahrim's robeskirt", "Ahrim's staff"]},
    {"name": "Dharok's", "monster": "Dharok the Wretched",
     "items": ["Dharok's helm", "Dharok's platebody", "Dharok's platelegs", "Dharok's greataxe"]},
    {"name": "Guthan's", "monster": "Guthan the Infested",
     "items": ["Guthan's helm", "Guthan's platebody", "Guthan's chainskirt", "Guthan's warspear"]},
    {"name": "Karil's", "monster": "Karil the Tainted",
     "items": ["Karil's coif", "Karil's leathertop", "Karil's leatherskirt", "Karil's crossbow"]},
    {"name": "Torag's", "monster": "Torag the Corrupted",
     "items": ["Torag's helm", "Torag's platebody", "Torag's platelegs", "Torag's hammers"]},
    {"name": "Verac's", "monster": "Verac the Defiled",
     "items": ["Verac's helm", "Verac's brassard", "Verac's plateskirt", "Verac's flail"]},
]

# Per-task card needs the rules can't infer from the wiki text (keyed area, tier, task n).
#   items / monsters: extra cards needed · spells: spell names whose runes are needed
#   remove: generated cards that aren't actually needed · note: shown with the task
CARD_OVERRIDES: dict[tuple[str, str, int], dict] = {
    # ── Ardougne
    ("Ardougne", "hard", 11):  {"remove": ["Dragon sq shield ornament kit"]},
    ("Ardougne", "elite", 4):  {"items": ["Knife", "Hammer"], "note": "From scratch: fletch the stock and smith the limbs."},
    # ── Desert
    ("Desert", "easy", 8):     {"partialQuests": ["Icthlarin's Little Helper"]},
    ("Desert", "easy", 9):     {"npcs": ["Guardian mummy"]},
    ("Desert", "medium", 8):   {'items': ['Vial of water', 'Pestle and mortar'], 'note': 'Unfinished potion made from scratch. Unfinished potion made from scratch; grind the goat horn.'},
    ("Desert", "hard", 4):     {"items": ["Rope"], "note": "Rope to enter the Kalphite Lair."},
    ("Desert", "elite", 1):    {"items": ["Pastry dough", "Pie dish", "Raw bear meat"], "monsters": ["Chompy bird"],
                                "note": "Wild pie chain: pie shell, bear meat, chompy (from chompy birds) and rabbit."},
    ("Desert", "elite", 4):    {"items": ["Kq head"], "monsters": ["Kalphite Queen"],
                                "note": "The KQ head comes from killing the Kalphite Queen."},
    # ── Falador
    ("Falador", "easy", 8):    {"npcs": ["Monk of Entrana"]},
    ("Falador", "easy", 11):   {"remove": ["Crossbow string"]},
    ("Falador", "medium", 2):  {"spells": ["Telekinetic Grab"]},
    ("Falador", "medium", 4):  {"items": ["Scarecrow"]},
    ("Falador", "medium", 9):  {"items": ["Initiate sallet", "Initiate hauberk", "Initiate cuisse"]},
    ("Falador", "hard", 9):    {"items": ["Proselyte sallet", "Proselyte hauberk", "Proselyte cuisse"]},
    ("Falador", "elite", 6):   {'items': ['Vial of water', 'Pestle and mortar'], 'note': 'Unfinished potion made from scratch. Unfinished potion made from scratch; crush the bird nest.'},
    # ── Fremennik
    ("Fremennik", "easy", 4):  {"items": ["Silver ore"], "note": "From scratch: smelt the silver bar."},
    ("Fremennik", "hard", 3):  {"items": ["Vial of water"], "note": "Unfinished potion made from scratch."},
    ("Fremennik", "elite", 1): {"monsters": ["Dagannoth Rex", "Dagannoth Prime", "Dagannoth Supreme"]},
    ("Fremennik", "elite", 3): {"remove": ["Cosmic rune", "Water rune", "Earth rune", "Amulet of glory"]},
    ("Fremennik", "elite", 5): {"notBoostable": ["Agility", "Strength", "Ranged"]},
    # ── Karamja
    ("Karamja", "medium", 1):  {"npcs": ["Cap'n Izzy No-Beard"]},
    ("Karamja", "medium", 6):  {"remove": ["Thatch spar light"]},
    ("Karamja", "medium", 8):  {'itemsAny': [['Trading sticks', 'Machete']], 'anyOf': [], 'note': "Or Agility 79 with Legends' Quest to use the shortcut."},
    ("Karamja", "medium", 9):  {'itemsAny': [['Trading sticks', 'Machete']], 'anyOf': [], 'note': "Or Agility 79 with Legends' Quest to use the shortcut."},
    ("Karamja", "medium", 11): {"items": ["Trading sticks"], "itemsAny": [["Opal", "Jade", "Red topaz"]]},
    ("Karamja", "hard", 3):    {'items': ['Raw oomlie'], 'note': 'The oomlie wrap is cooked from raw oomlie in a palm leaf.', 'skills': {'Cooking': 50}, 'notBoostable': ['Cooking']},
    ("Karamja", "elite", 2):   {"itemsAny": [["Fire cape", "Infernal cape"]], "monsters": ["TzTok-Jad"],
                                "note": "A Fire cape comes from defeating TzTok-Jad (Infernal cape: TzKal-Zuk)."},
    # ── Kandarin
    ("Kandarin", "medium", 11): {"monsters": ["Penance Fighter", "Penance Healer", "Penance Ranger", "Penance Runner"]},
    ("Kandarin", "hard", 1):   {"items": ["Pearl barbarian rod"], "remove": ["Feather"],
                                "itemsAny": [["Fishing bait", "Feather", "Fish offcuts", "Roe", "Caviar"]],
                                "note": "Any barbarian rod (the TCG card is Pearl barbarian rod) and any of the listed baits."},
    ("Kandarin", "hard", 3):   {"items": ["Yew logs"], "note": "From scratch: cut and fletch the yew logs."},
    ("Kandarin", "hard", 9): {'monsters': ['Penance Fighter', 'Penance Healer', 'Penance Ranger', 'Penance Runner', 'Penance Queen'], 'note': 'Bought from Commander Connad for 95,000 coins plus honour points, which come from playing Barbarian Assault.', 'npcsNoCard': ['Commander Connad']},
    ("Kandarin", "elite", 1):  {"monsters": ["Penance Fighter", "Penance Healer", "Penance Ranger", "Penance Runner", "Penance Queen"]},
    ("Kandarin", "elite", 4):  {"items": ["Caviar"]},
    # ── Kourend & Kebos
    ("Kourend & Kebos", "easy", 11): {"items": ["Vial of water"], "note": "Unfinished potion made from scratch."},
    ("Kourend & Kebos", "medium", 7): {"itemsAny": [["Bronze nails", "Iron nails", "Steel nails", "Black nails",
                                                    "Mithril nails", "Adamantite nails", "Rune nails"]]},
    ("Kourend & Kebos", "medium", 8): {'items': ['Intelligence'], 'monstersAny': [['Gangster', 'Gang boss']]},
    ("Kourend & Kebos", "elite", 1): {"items": ["Dark essence block"], "remove": ["Pure essence"]},
    ("Kourend & Kebos", "elite", 5): {"monsters": ["Hydra", "Alchemical Hydra"],
                                      "itemsAny": [["Boots of stone", "Boots of brimstone", "Granite boots"]],
                                      "note": "Either Hydra or Alchemical Hydra counts."},
    ("Kourend & Kebos", "elite", 6): {'items': ['Soul rune', 'Blood rune', 'Law rune']},
    ("Kourend & Kebos", "elite", 7): {"monsters": ["Great Olm"]},
    # ── Lumbridge & Draynor
    ("Lumbridge & Draynor", "easy", 10): {"items": ["Pot of flour", "Bucket of water"]},
    ("Lumbridge & Draynor", "medium", 11): {"remove": ["Eclectic impling", "Essence impling"],
                                            "note": "Implings are caught (Hunter), not fought."},
    ("Lumbridge & Draynor", "medium", 12): {"items": ["Earth rune"], "remove": ["Fire rune"],
                                            "note": "Earth runes and an earth talisman are used on the fire altar."},
    ("Lumbridge & Draynor", "hard", 5): {"npcs": ["Juna"]},
    # ── Morytania
    ("Morytania", "easy", 2):  {"items": ["Thin snail"], "itemsAny": [["Ecto-token", "Coins"]], "anyOf": []},
    ("Morytania", "easy", 5):  {"remove": ["Cowhide"], "itemsAny": [["Cowhide", "Snake hide", "Green dragonhide",
                                "Blue dragonhide", "Red dragonhide", "Black dragonhide"]], "note": "Any hide Sbott can tan."},
    ("Morytania", "easy", 9):  {'items': ['Bucket of slime'], 'remove': ['Curved bone', 'Long bone'], 'note': 'Any bones to grind into bonemeal.'},
    ("Morytania", "hard", 4):  {"items": ["Mahogany logs"]},
    ("Morytania", "hard", 8):  {"quests": ["King's Ransom"]},
    ("Morytania", "elite", 1): {"remove": ["Dragon harpoon"]},
    ("Morytania", "elite", 2): {'items': ['Tinderbox', 'Sacred oil'], 'itemsAny': [['Magic logs', 'Redwood logs']]},
    ("Morytania", "elite", 6): {"skills": {"Defence": 70},
                                "skillsAny": [[{"Attack": 70}, {"Strength": 70}, {"Magic": 70}, {"Ranged": 70}]],
                                "setsAny": "barrows",
                                "note": "Wear any one complete Barrows set (helm, body, legs and weapon). The brothers' pieces come from the chest; each set has its own level needs on top of Defence 70."},
    ("Varrock", "easy", 1):    {"npcs": ["Thessalia"]},
    ("Varrock", "easy", 7):    {"remove": ["Logs", "Plank"]},
    ("Varrock", "medium", 1):  {"remove": ["Tarromin"], "note": "The Apothecary makes it from your ingredients."},
    ("Varrock", "medium", 3):  {"npcs": ["Gertrude"]},
    ("Varrock", "elite", 3):   {"items": ["Pastry dough", "Pie dish", "Strawberry", "Watermelon"]},
    # ── Western Provinces
    ("Western Provinces", "easy", 6):  {'monsters': ['Chompy bird', 'Jubbly bird'], 'monstersAny': [['Chompy bird', 'Jubbly bird']], 'remove': ['Chompy bird', 'Jubbly bird'], 'npcs': ['Rantz']},
    ("Western Provinces", "easy", 10): {'items': ['Oak logs', 'Knife']},
    ("Western Provinces", "hard", 1):  {'monsters': ['Elf Warrior', 'Elf Archer'], 'note': 'Either an elf warrior or archer.', 'monstersAny': [['Elf Warrior', 'Elf Archer']]},
    ("Western Provinces", "hard", 12): {"items": ["Banana"]},
    ("Western Provinces", "elite", 1): {'items': ['Magic logs', 'Knife']},
    # ── Wilderness
    ("Wilderness", "medium", 2): {'monsters': ['Ent'], 'note': 'The Ent has to be killed before its trunk can be chopped.', 'remove': ['Elder Chaos druid']},
    ("Wilderness", "hard", 1): {"items": ["Blood rune", "Fire rune", "Air rune"],
                                "itemsAny": [["Saradomin staff", "Guthix staff", "Zamorak staff"]]},
    ("Wilderness", "elite", 3): {"items": ["Raw dark crab"]},
    ("Wilderness", "elite", 4): {"items": ["Runite ore"], "monsters": ["Runite Golem"]},
    ("Ardougne", "medium", 9): {"lightSource": True},
    ("Ardougne", "hard", 7): {"items": ["Palm tree seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Desert", "easy", 10): {"items": ["Waterskin"]},
    ("Desert", "medium", 10): {"lightSource": True},
    ("Desert", "hard", 8): {"items": ["Keris partisan"], "lightSource": True},
    ("Desert", "elite", 5): {"npcs": ["Guardian mummy"]},
    ("Falador", "hard", 3): {"lightSource": True},
    ("Falador", "hard", 10): {"skillsAny": [[{"Attack": 99}, {"Strength": 99}]], "note": "Or a combined Attack + Strength of 130."},
    ("Falador", "elite", 1): {"remove": ["Abyssal lantern"], "note": "The Abyssal lantern is only for the alternative route."},
    ("Falador", "elite", 3): {"items": ["Magic seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Fremennik", "easy", 2): {"npcs": ["Yrsa"]},
    ("Fremennik", "medium", 6): {"skills": {"Hunter": 35}, "note": "Hunter 45 bare-handed, or 35 with a butterfly net and jar."},
    ("Fremennik", "hard", 7): {"tools": [], "note": "Rake, harpoon, lobster pot, pickaxe or axe — any one, for working the kingdom."},
    ("Kandarin", "hard", 6): {"note": "Any bow except the excluded ones (twisted, cursed, dark, crystal, ogre, rain, starter, signed oak)."},
    ("Kandarin", "elite", 6): {"items": ["Magic logs"]},
    ("Karamja", "medium", 3): {"remove": ["Lesser demon"], "note": "Only pass the lesser demons; no kill needed."},
    ("Karamja", "medium", 13): {"itemsAny": [["Apple tree seed", "Banana tree seed", "Orange tree seed", "Curry tree seed", "Pineapple seed", "Papaya tree seed", "Palm tree seed", "Dragonfruit tree seed"]], "items": ["Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Karamja", "medium", 14): {"items": ["Knife"], "itemsAny": [["Teasing stick", "Hunter\u0027s spear"]]},
    ("Karamja", "medium", 19): {"quests": ["Jungle Potion"], "anyOf": []},
    ("Karamja", "hard", 2): {"monsters": ["Tz-Kih", "Tz-Kek"]},
    ("Karamja", "hard", 9): {"skills": {"Slayer": 50}},
    ("Karamja", "hard", 10): {"monstersAny": [["Bronze dragon", "Iron dragon", "Steel dragon"]]},
    ("Karamja", "elite", 3): {"items": ["Palm tree seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Karamja", "elite", 5): {"items": ["Calquat tree seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Kourend & Kebos", "hard", 6): {"lightSource": True},
    ("Kourend & Kebos", "hard", 7): {"items": ["Xeric\u0027s talisman", "Lizardman fang"], "remove": []},
    ("Kourend & Kebos", "elite", 3): {"items": ["Dark totem base", "Dark totem middle", "Dark totem top"]},
    ("Kourend & Kebos", "elite", 8): {"items": ["Celastrus seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Lumbridge & Draynor", "easy", 2): {"lightSource": True},
    ("Lumbridge & Draynor", "medium", 3): {"items": ["Steel arrow"], "itemsAny": [["Ava\u0027s attractor", "Coins"]]},
    ("Lumbridge & Draynor", "hard", 7): {"quests": ["Recipe for Disaster"]},
    ("Lumbridge & Draynor", "hard", 8): {"note": "Gloves are needed to pick belladonna."},
    ("Lumbridge & Draynor", "elite", 2): {"lightSource": True},
    ("Morytania", "hard", 1): {"items": ["Blood rune"]},
    ("Morytania", "hard", 2): {"remove": ["Infernal Mage", "Nechryael"]},
    ("Morytania", "hard", 6): {"lightSource": True},
    ("Varrock", "hard", 5): {"items": ["Skull sceptre"]},
    ("Varrock", "hard", 8): {"items": ["Yew seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Western Provinces", "hard", 5): {"items": ["Monkey greegree"]},
    ("Western Provinces", "hard", 8): {"items": ["Palm tree seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Western Provinces", "elite", 3): {"items": ["Magic seed", "Plant pot", "Gardening trowel", "Watering can"], "note": "Saplings are grown from the seed in a plant pot (gardening trowel, watering can)."},
    ("Western Provinces", "elite", 5): {"itemsAny": [["Void melee helm", "Void ranger helm", "Void mage helm"]]},
    ("Wilderness", "hard", 10): {"items": ["Fishing rod", "Harralander", "Vial of water"], "note": "An oily fishing rod is made from a fishing rod with harralander tar."},
    ("Wilderness", "elite", 1): {"monstersAny": [["Callisto", "Artio"], ["Venenatis", "Spindel"], ["Vet\u0027ion", "Calvar\u0027ion"]]},
    ("Wilderness", "elite", 5): {"remove": ["Rogue"]},
    ("Western Provinces", "medium", 8): {"monstersAny": [["Chompy bird", "Jubbly bird"]], "remove": ["Chompy bird", "Jubbly bird"], "npcs": ["Rantz"]},
    ("Western Provinces", "hard", 9): {"monstersAny": [["Chompy bird", "Jubbly bird"]], "remove": ["Chompy bird", "Jubbly bird"], "npcs": ["Rantz"]},
    ("Western Provinces", "elite", 6): {"monstersAny": [["Chompy bird", "Jubbly bird"]], "remove": ["Chompy bird", "Jubbly bird"], "npcs": ["Rantz"]},
    ("Kandarin", "easy", 8): {"items": ["Empty fishbowl"]},
    ("Lumbridge & Draynor", "easy", 7): {"items": ["Oak logs"]},
    ("Kourend & Kebos", "easy", 6): {"remove": ["Veos"], "note": "Veos or Cabin Boy Herbert (no card) can take you."},
    ("Desert", "easy", 8): {"npcs": ["Guardian mummy"], "itemsAny": [["Ivory comb", "Pottery scarab", "Pottery statuette", "Stone scarab", "Stone seal", "Stone statuette", "Gold seal", "Golden scarab", "Golden statuette"]], "note": "Any Pyramid Plunder artefact."},
}

_SKILL_RE = re.compile(r"\{\{SCP\|([A-Za-z]+)\|(\d+)[^}]*\}\}")
_QUEST_LINE_RE = re.compile(r"\{\{SCP\|Quest\}\}\s*(.*)")
_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_NOT_BOOSTABLE_RE = re.compile(r"\{\{boostable\|no?\}\}|neither \[\[boost", re.I)
_KILL_RE = re.compile(r"\b(kill|slay|defeat|pickpocket|steal from)\b", re.I)
_MAKE_RE = re.compile(r"\b(make|craft|smith|cook|fletch|brew|mix|create|bake|build|cast|"
                      r"string|cut|smelt|tan|spin|weave|construct|fire)\b", re.I)
_TASK_START_RE = re.compile(r"^\|\s*(\d+)\.\s*(.*)")
# Bronzeman: using / equipping / consuming an item needs its card
_USE_RE = re.compile(r"\b(burn|equip|equipped|wear|wearing|wield|eat|drink|fill|offer|cremate|use|"
                     r"operate|recharge|upgrade|plant|feed)\b", re.I)   # not "charge": charging makes the item
# "Any pickaxe" etc. -> the page's TOOL_TIERS keys (any owned tier satisfies it)
_TOOL_RE = re.compile(r"(?i)\bany \[*\s*(pickaxe|axe|harpoon)\b")


def _split_parens(line: str) -> tuple[str, list[str]]:
    """Top-level (...) groups in a requirement line, ignoring parens inside [[links]]/{{templates}}.
    Returns (line without the groups, [group contents])."""
    out, groups, depth, buf, inner = [], [], 0, "", 0
    i = 0
    while i < len(line):
        two = line[i:i + 2]
        if two in ("[[", "{{"):
            inner += 1; buf += two; i += 2; continue
        if two in ("]]", "}}") and inner:
            inner -= 1; buf += two; i += 2; continue
        c = line[i]
        if not inner and c == "(":
            if depth == 0:
                out.append(buf); buf = ""
            else:
                buf += c
            depth += 1
        elif not inner and c == ")" and depth:
            depth -= 1
            if depth == 0:
                groups.append(buf); buf = ""
            else:
                buf += c
        else:
            buf += c
        i += 1
    out.append(buf)
    return "".join(out), groups


def _top_level_split(line: str) -> list[str]:
    """Split a requirement line into required segments. Top-level " and " always separates;
    ", " separates too, unless the and-segment contains a top-level "or" — then its commas
    are list separators of alternatives ("Knife, Wilderness sword 1 or 2, or a slashing weapon")."""
    out = []
    for seg in _split_top(line, (" and ",)):
        if re.search(r"\bor\b", _outside_brackets(seg)):
            out.append(seg)
        else:
            out += _split_top(seg, (", ",))
    return [p for p in out if p.strip()]


def _outside_brackets(s: str) -> str:
    return re.sub(r"\[\[[^\]]*\]\]|\{\{[^}]*\}\}|\([^)]*\)", "", s)


def _split_top(line: str, seps: tuple[str, ...]) -> list[str]:
    parts, buf, depth, i = [], "", 0, 0
    while i < len(line):
        two = line[i:i + 2]
        if two in ("[[", "{{"):
            depth += 1; buf += two; i += 2; continue
        if two in ("]]", "}}") and depth:
            depth -= 1; buf += two; i += 2; continue
        c = line[i]
        if c in "(":
            depth += 1
        elif c == ")" and depth:
            depth -= 1
        sep = next((x for x in seps if line.startswith(x, i)), None) if depth == 0 else None
        if sep:
            parts.append(buf); buf = ""
            i += len(sep)
            continue
        buf += c
        i += 1
    parts.append(buf)
    return [p for p in parts if p.strip()]


def _strip_markup(s: str) -> str:
    s = re.sub(r"<!--.*?(-->|$)", "", s, flags=re.S)          # wiki editor comments
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{SCP\|Quest\}\}\s*", "", s)
    s = _SKILL_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}", s)   # {{SCP|Hunter|69}} -> "Hunter 69"
    s = re.sub(r"\{\{(?:Coins|NoCoins)\|(-?[\d,]+)\}\}", lambda m: f"{int(m.group(1).replace(',', '')):,}", s)
    prev = None
    while prev != s:                       # nested templates: strip innermost first, repeat
        prev, s = s, re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = _LINK_RE.sub(lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"'{2,}", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _tier_sections(wikitext: str) -> dict[str, str]:
    """==Easy== … sections holding the task tables."""
    out = {}
    for tier in TIERS:
        m = re.search(rf"^==\s*{tier}\s*==\s*$", wikitext, re.I | re.M)
        if not m:
            continue
        nxt = re.search(r"^==[^=].*==\s*$", wikitext[m.end():], re.M)
        out[tier] = wikitext[m.end(): m.end() + nxt.start() if nxt else len(wikitext)]
    return out


def _rows(section: str) -> list[tuple[int, str, str]]:
    """(n, task cell, requirements cell) for each task row."""
    rows = []
    for chunk in re.split(r"^\|-.*$", section, flags=re.M):
        lines = chunk.strip("\n").split("\n")
        start = next((i for i, l in enumerate(lines) if _TASK_START_RE.match(l)), None)
        if start is None:
            continue
        # requirements cell = the next line that starts with "|" after the task cell
        req_i = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("|")), None)
        n = int(_TASK_START_RE.match(lines[start]).group(1))
        task = "\n".join([_TASK_START_RE.match(lines[start]).group(2)] + lines[start + 1: req_i or len(lines)])
        req_lines = []
        for l in (lines[req_i:] if req_i is not None else []):
            if l.startswith("|}") or l.startswith("="):   # end of table / next section
                break
            req_lines.append(l)
        rows.append((n, task, "\n".join(req_lines).lstrip("|")))
    return rows


# Lottie plays an ironman (no Grand Exchange): drop GE value/resale clauses from reward
# text, and drop bullets that are only about the GE.
_GE_CLAUSE_RE = re.compile(r",?\s*(?:resellable on the Grand Exchange|for a profit of|worth (?:a total|an average|a total average|a total of)?\s*(?:average )?of)\b[^.]*?(?:on the Grand Exchange|\(after tax\))?(?:\s*\(after tax\))?(?=\.|$)", re.I)


def _ironman_text(txt: str) -> str | None:
    if re.search(r"(?i)grand exchange", txt):
        cut = _GE_CLAUSE_RE.sub("", txt).strip()
        return None if re.search(r"(?i)grand exchange", cut) else cut
    return txt


# Reward lines whose card links point at the wrong thing (area, tier, card to drop)
REWARD_CARD_REMOVE: set[tuple[str, str, str]] = {
    ("Wilderness", "easy", "Lever"),      # the Wilderness lever, not the Dorgesh-Kaan "Lever" item
}


def _reward_cards(raw_line: str, ctx: "Ctx | None") -> tuple[list[str], list[str], list[str]]:
    """Cards linked in a reward's main line (sub-bullets aren't requirements):
    (items, monsters you'd kill — have a combat level, talk-only NPCs)."""
    if ctx is None:
        return [], [], []
    items, monsters, npcs = [], [], []
    for title, _ in _LINK_RE.findall(raw_line):
        c = ctx.item_card(title)
        if c:
            if c not in items:
                items.append(c)
            continue
        n = ctx.npc_card(title)
        if n:
            dest = monsters if n.lower() in ctx.combat_npcs else npcs
            if n not in dest:
                dest.append(n)
    return items, monsters, npcs


def _rewards(section: str, ctx: "Ctx | None" = None) -> list[dict]:
    """The tier's ===Rewards=== bullets: [{text, sub:[...]}] (wiki wording, markup stripped)."""
    m = re.search(r"^===\s*Rewards\s*===\s*$", section, re.M)
    if not m:
        return []
    out: list[dict] = []
    for line in section[m.end():].split("\n"):
        if line.startswith("=") or line.startswith("{|"):
            break
        if line.startswith("**") and out:
            txt = _ironman_text(_strip_markup(line.lstrip("*")))
            if txt:
                out[-1]["sub"].append(txt)
        elif line.startswith("*"):
            txt = _ironman_text(_strip_markup(line.lstrip("*")))
            if txt:
                items, monsters, npcs = _reward_cards(line, ctx)
                if "coin" not in txt.lower():
                    items = [c for c in items if c != "Coins"]   # came from a stripped GE value clause
                entry = {"text": txt, "sub": [], "_mentioned": [t for t, _ in _LINK_RE.findall(line)]}
                for key, val in (("items", items), ("monsters", monsters), ("npcs", npcs)):
                    if val:
                        entry[key] = val
                out.append(entry)
            else:
                out.append({"text": "", "sub": [], "_drop": True})   # keep its sub-bullets out too
    return [r for r in out if not r.get("_drop")]


class Ctx:
    def __init__(self, card_json: str):
        cat = json.loads(Path(card_json).read_text(encoding="utf-8"))
        self.items = {i["name"].lower(): i["name"] for i in cat["items"]}
        self.item_pages = {i["name"].lower(): (i.get("wiki") or {}).get("page", "") for i in cat["items"]}
        # herb cards whose variants include a "Grimy …" item ("any grimy herb")
        self.grimy_herb_cards = {i["name"] for i in cat["items"]
                                 if any(v.get("name", "").lower().startswith("grimy ")
                                        for v in i.get("tcg", {}).get("variants", []))}
        self.npcs = {n["name"].lower(): n["name"] for n in cat["npcs"]}
        set_variant_aliases(load_variant_aliases(card_json))
        self.quests = {q.lower(): q for q in json.loads((_OUT_DIR / "quests.json").read_text(encoding="utf-8"))}
        self.sources = json.loads((_OUT_DIR / "item_sources.json").read_text(encoding="utf-8"))
        spells_path = _OUT_DIR / "spells.json"   # from generate_spells.py
        self.spells = {k.lower(): v for k, v in json.loads(spells_path.read_text(encoding="utf-8")).items()} \
            if spells_path.exists() else {}
        self.unknown_quests: set[str] = set()
        md = json.loads((_OUT_DIR / "monster_drops.json").read_text(encoding="utf-8"))
        self.combat_npcs = {k.lower() for k, v in md.items() if v.get("combatLevel")}

    def item_card(self, title: str) -> str | None:
        title = title.replace("_", " ").strip()         # wiki links can use underscores
        if title.lower().startswith("burnt "):
            return None                                 # burnt food is a different item
        c = _card_for_drop(title, self.items)
        if not c:
            t = title
            forms = [re.sub(r"ves$", "f", t), re.sub(r"ies$", "y", t), re.sub(r"es$", "", t),   # plural → singular
                     re.sub(r"s$", "", t), t + "s", t + "es",                                    # either way
                     re.sub(r"^(\w+?)s( of .*)$", r"\1\2", t)]                                 # "Marks of grace"
            for form in forms:
                if form != t:
                    c = _card_for_drop(form, self.items)
                    if c:
                        break
        card = self.items.get(c.lower()) if c else None
        # A link titled exactly like a card but pointing at a different wiki page is a
        # different thing: "[[Jewellery]]" is the category page, the card is "Jewellery (item)".
        # Only trust this when the card's page carries the "(item)" disambiguator — the
        # catalog's other wiki pages are unreliable (Coins → "Coins (Shilo Village)").
        if card and title.strip().lower() == card.lower():
            page = (self.item_pages.get(card.lower()) or "").lower()
            if page.endswith("(item)"):
                return None
        return card

    def npc_card(self, title: str) -> str | None:
        return self.npcs.get(title.lower()) or self.npcs.get(re.sub(r"\s*\([^)]*\)$", "", title).lower())

    def is_quest(self, title: str) -> bool:
        return (title.lower() in self.quests
                or re.sub(r"\s*\(quest\)$", "", title, flags=re.I).lower() in self.quests)

    def quest(self, title: str) -> str:
        q = self.quests.get(title.lower()) or self.quests.get(re.sub(r"\s*\(quest\)$", "", title, flags=re.I).lower())
        if not q:
            self.unknown_quests.add(title)
        return q or title


def _only_made(src: dict | None) -> bool:
    """True if an item's only source is production (it must be made to be obtained)."""
    if not src or not src.get("production"):
        return False
    return not any(v for k, v in src.items() if k != "production")


# Lottie's account is an Ironman: the wiki's ironman-only requirements ARE the requirements,
# so they're folded into the normal ones rather than shown separately.
IRONMAN_ACCOUNT = True

# Lines / clauses that describe help or alternatives, not requirements
_NOT_REQUIRED_RE = re.compile(
    r"(?i)\b(recommended|optional|optionally|not required|isn't required|is not required|helpful|useful|"
    r"does not (count|work)|doesn't (count|work)|won't (count|work)|cannot be used|can't be used|"
    r"alternatively|not needed|if you (don't|do not) have)\b")
# The task's own output: "Craft X", "Cook X", "Chop X", "Catch X"…
_PRODUCE_RE = re.compile(r"(?i)\b(make|craft|smith|cook|fletch|brew|mix|create|bake|build|cast|string|cut|"
                         r"smelt|tan|spin|weave|construct|fire|chop|mine|fish|catch|pick|collect|harvest|"
                         r"grow|obtain|get|receive|claim|loot)\b")
_KILL_RE2 = re.compile(r"(?i)\b(kill|kills|killed|killing|slay|slaying|defeat|defeating|pickpocket|"
                       r"steal from|hunt|attack)\b")
_TALK_RE = re.compile(r"(?i)\b(talk|speak|trade|ask|buy|sell|claim|have|get|pay|bring|give|show|charter|"
                      r"teleport|travel|exchange|tan|make you)\b")
_PLACE_AFTER_RE = re.compile(r"^(?:'s\b|\s+(?:pen|anvil|cave|caves|dungeon|house|shop|stall|guild|lair|altar|"
                             r"patch|course|island|mine|camp|hut|pyramid|tower|temple|village|grotto|hideout))", re.I)
_QUEST_WORDS_RE = re.compile(r"(?i)^\s*(\{\{SCP\|Quest\}\}\s*)?(completion|partial completion|started|start|quest start)\b")
_ANY_CATEGORY_RE = re.compile(r"(?i)\bany \[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_OTHER_TASK_RE = re.compile(r"(?i)\b(another|other|separate|different) (easy |medium |hard |elite )?task\b|"
                            r"\bfor (a|an|the) (easy|medium|hard|elite) task\b|#(easy|medium|hard|elite)\b")


def _skills_in(seg: str) -> list[tuple[str, int, bool]]:
    """(skill, level, boostable) for each {{SCP|Skill|N}} in seg; a {{Boostable|n}} applies to the
    skill right before it only."""
    out = []
    for m in _SKILL_RE.finditer(seg):
        tail = seg[m.end():m.end() + 40]
        nb = re.match(r"\s*\{\{boostable\|no?\}\}", tail, re.I) is not None
        out.append((m.group(1), int(m.group(2)), not nb))
    if re.search(r"(?i)neither (\[\[boost|boostable)", seg):   # "(neither boostable)" covers all
        out = [(sk, lv, False) for sk, lv, _ in out]
    return out


def _category_cards(ctx: "Ctx", title: str) -> list[str]:
    """'any [[crossbow]]' → every item card whose name ends with that category word."""
    word = re.sub(r"\s*\([^)]*\)$", "", title).strip().lower().rstrip("s")
    if len(word) < 4 or word in ("pickaxe", "axe", "harpoon"):
        return []
    if word == "grimy herb":
        return sorted({v for v in ctx.grimy_herb_cards})
    return sorted(c for k, c in ctx.items.items() if k.endswith(word) and not k.startswith("burnt "))


def parse_task(n: int, task_cell: str, req_cell: str, ctx: Ctx) -> dict:
    lines = task_cell.split("\n")
    first = lines[0]
    # note lines under the task text, except ones about *other* tasks
    _NOT_COUNT = re.compile(r"(?i)\b(do not|don't|doesn't|does not|won't|not) (count|work)\b")
    task_notes = [l for l in lines[1:] if l.strip() and not _OTHER_TASK_RE.search(l) and not _NOT_COUNT.search(l)]
    task_text = _strip_markup(first)

    skills: dict[str, int] = {}
    boostable: dict[str, bool] = {}
    quests, partial, items, notes, tools = [], [], [], [], []
    any_of: list[list[dict]] = []           # mixed alternatives: [{card}|{skill,level}|{quest}]
    ironman_skills: dict[str, int] = {}
    ironman_quests: list[str] = []
    combat = None
    kept_req_lines: list[str] = []          # requirement lines that are real requirements
    group_labels: dict[tuple, str] = {}     # category groups → "Any crossbow"
    light_source = False                    # "any light source" → page's LIGHT_SOURCE_ITEMS
    paren_npc_text: list[str] = []          # bracketed asides that may name an NPC you talk to

    derived: set[str] = set()   # items inferred from production/spells, not stated by the wiki

    def add_item(c: str | None, inferred: bool = False) -> None:
        if c and c not in items:
            items.append(c)
            if inferred:
                derived.add(c)
        elif c and not inferred:
            derived.discard(c)

    def add_skill(sk: str, lv: int, bst: bool) -> None:
        nonlocal combat
        if sk == "Combat":
            combat = max(combat or 0, lv)
            return
        if lv > skills.get(sk, 0):
            skills[sk] = lv
            boostable[sk] = bst
        elif lv == skills.get(sk, 0):
            boostable[sk] = boostable.get(sk, True) and bst

    def options_in(seg: str) -> list[dict]:
        opts = [{"skill": sk, "level": lv} for sk, lv, _ in _skills_in(seg) if sk != "Combat"]
        for t, _ in _LINK_RE.findall(seg):
            if ctx.is_quest(t):
                opts.append({"quest": ctx.quest(t)})
                continue
            c = ctx.item_card(t)
            if c and {"card": c} not in opts:
                opts.append({"card": c})
        for t in _ANY_CATEGORY_RE.findall(seg):
            for c in _category_cards(ctx, t):
                if {"card": c} not in opts:
                    opts.append({"card": c})
        return opts

    for raw in req_cell.split("\n"):
        line = raw.strip().lstrip("*").strip()
        if not line or line.startswith("{{NA"):
            continue
        # footnotes ({{efn}} / <ref>): only ironman ones matter
        for ref in re.findall(r"<ref[^>/]*>(.*?)</ref>|\{\{efn\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", line, flags=re.S):
            txt = ref[0] or ref[1]
            if re.search(r"(?i)ironm", txt):
                for sk, lv, _ in _skills_in(txt):
                    ironman_skills[sk] = max(ironman_skills.get(sk, 0), lv)
                notes.append("Ironman: " + _strip_markup(txt))
        line = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|\{\{efn\|(?:[^{}]|\{\{[^{}]*\}\})*\}\}", "", line, flags=re.S).strip()
        if _NOT_REQUIRED_RE.search(line):
            # drop only the clauses that are recommendations / optional, keep the rest
            keep = [seg for seg in _split_top(line, (", ", "; ")) if not _NOT_REQUIRED_RE.search(seg)]   # "A and B recommended" stays one clause
            notes.append(_strip_markup(line))
            if not keep:
                continue
            line = ", ".join(keep)
        line_not_boostable = re.search(r"(?i)\(\s*neither\b[^)]*boost", line) is not None
        line, groups = _split_parens(line)
        # NPCs mentioned in brackets still count ("(speak to [[Tinsay]] after the quest)")
        paren_npc_text.extend(g for g in groups if not re.search(r"(?i)ironman|\bor\b", g) and not _NOT_REQUIRED_RE.search(g)
                              and not re.search(r"(?i)\b(do not|don't|doesn't|does not|won't|not) (count|work)", g))
        if line_not_boostable:
            line = re.sub(r"(\{\{SCP\|[A-Za-z]+\|\d+[^}]*\}\})", r"\1{{Boostable|n}}", line)
        for g in groups:
            if re.search(r"(?i)ironman", g):
                if re.search(r"(?i)\bunless\b", g):
                    notes.append(_strip_markup(g))
                    continue
                for sk, lv, _ in _skills_in(g):
                    ironman_skills[sk] = max(ironman_skills.get(sk, 0), lv)
                ironman_quests += [ctx.quest(t) for t, _ in _LINK_RE.findall(g) if ctx.is_quest(t)]
                notes.append("Ironman: " + _strip_markup(g))
            elif re.match(r"(?i)\s*access to\b", line) and re.search(r"\bor\b|/", g) \
                    and len([o for o in options_in(g) if "card" in o]) > 1:
                # "Access to the Water Altar (water talisman/tiara, elemental talisman/tiara, or the Abyss)"
                any_of.append([o for o in options_in(g) if "card" in o])
                notes.append(_strip_markup(line + " (" + g + ")"))
            elif _SKILL_RE.search(g) or _QUEST_WORDS_RE.search(g) or _NOT_REQUIRED_RE.search(g) \
                    or re.search(r"\bor\b", g):
                notes.append(_strip_markup(g))       # conditional / alternative: "requires Crafting 55"
        line = line.strip()
        if not line:
            continue
        kept_req_lines.append(line)

        if re.search(r"(?i)\b(any|a) \[*\s*light source", line):
            light_source = True
        for tool in _TOOL_RE.findall(line):
            if tool.capitalize() not in tools:
                tools.append(tool.capitalize())
        least = re.search(r"(?i)at least (?:an? )?\[\[([^\]|]*?(pickaxe|axe|harpoon))\]\]", line)
        if least:
            if least.group(2).capitalize() not in tools:
                tools.append(least.group(2).capitalize())
            notes.append(f"At least a {least.group(1).lower()}")
            line = line.replace(least.group(0), "")
        if re.match(r"(?i)access to \[\[barbarian (firemaking|smithing|fishing|herblore)", line):
            if ctx.is_quest("Barbarian Training") and "Barbarian Training" not in partial:
                partial.append(ctx.quest("Barbarian Training"))
            notes.append(_strip_markup(line))
            continue

        # quests — by wording, with or without {{SCP|Quest}}
        if _QUEST_WORDS_RE.search(line) and any(ctx.is_quest(t) for t, _ in _LINK_RE.findall(line)):
            rest = re.sub(r"^\{\{SCP\|Quest\}\}\s*", "", line)
            linked, prev_end = [], 0
            for m in _LINK_RE.finditer(rest):
                if ctx.is_quest(m.group(1)):
                    before = rest[prev_end:m.start()]
                    is_partial = bool(re.search(r"(?i)\b(started|partial|start)", before)) or \
                        (not linked and re.match(r"(?i)\s*(started|partial|start|quest start)", rest) is not None)
                    if linked and not re.search(r"(?i)\b(completion|started|partial|start)", before):
                        is_partial = linked[-1][1]
                    linked.append((m.group(1), is_partial))
                prev_end = m.end()
            if any("/" in t for t, _ in linked):                 # subquest named → drop the parent
                linked = [(t, p) for t, p in linked if "/" in t or not any(x.startswith(t + "/") for x, _ in linked)]
            if re.search(r"\bor\b", _outside_brackets(rest)) and len(linked) > 1:
                any_of.append([{"quest": ctx.quest(t)} for t, _ in linked])
            else:
                for t, is_partial in linked:
                    (partial if is_partial else quests).append(ctx.quest(t))
            continue

        # everything else: split into required segments; a segment with a top-level "or"
        # is one group of alternatives (skills / items / quests, possibly mixed)
        line_had_req = False
        for seg in _top_level_split(line):
            if re.search(r"\bor\b|/", _outside_brackets(seg)):
                opts = options_in(seg)
                if len(opts) > 1:
                    any_of.append(opts)
                    line_had_req = True
                    continue
                if len(opts) == 1:      # "X or something we can't represent" → X isn't strictly needed
                    notes.append(_strip_markup(seg))
                    continue
            for sk, lv, bst in _skills_in(seg):
                add_skill(sk, lv, bst)
                line_had_req = True
            for t in _ANY_CATEGORY_RE.findall(seg):
                group = _category_cards(ctx, t)
                if group:
                    any_of.append([{"card": c} for c in group])
                    group_labels[tuple(group)] = "Any " + re.sub(r"\s*\([^)]*\)$", "", t).lower()
                    line_had_req = True
            if re.match(r"(?i)\s*(access|ability)\b", _strip_markup(seg)):
                continue
            for t, _ in _LINK_RE.findall(seg):
                if ctx.is_quest(t) or ctx.npc_card(t):
                    continue
                c = ctx.item_card(t)
                if c:
                    add_item(c)
                    line_had_req = True
        if not line_had_req:
            txt = _strip_markup(line)
            if txt and not re.fullmatch(r"(?i)any (pickaxe|axe|harpoon)", txt):
                notes.append(txt)

    # ── links in the task line itself ─────────────────────────────────────────
    first_links = list(_LINK_RE.finditer(first))
    products = set()
    if _PRODUCE_RE.search(task_text):
        for m in first_links:
            c = ctx.item_card(m.group(1))
            # "Cook a karambwan" links the raw fish: that's the input, not the product
            if c and not c.lower().startswith(("raw ", "uncooked ", "unfired ", "unstrung ")):
                products.add(c)
    # items the task uses / equips / consumes ("use of" is a noun phrase, not the verb)
    if re.search(r"(?i)\b(burn|equip|equipped|wear|wearing|wield|eat|drink|fill|offer|cremate|"
                 r"use(?! of)|operate|recharge|upgrade|plant|feed)\b", task_text):
        for m in first_links:
            c = ctx.item_card(m.group(1))
            if c and not m.group(1).lower().startswith("burnt "):
                add_item(c)

    # production: the product's ingredients from central item_sources (recursing into
    # ingredients that can only be made)
    ingredient_cards: set[str] = set()     # cards reached through an ingredient name

    def add_ingredients(name: str, depth: int) -> None:
        prod = (ctx.sources.get(name, {}) or {}).get("production") or {}
        for tool in prod.get("tools") or []:                 # e.g. Pestle and mortar, Hammer
            add_item(ctx.item_card(tool if isinstance(tool, str) else tool.get("item", "")), inferred=True)
        for ing in prod.get("ingredients") or []:
            raw = ing.get("item", "")
            c = ctx.item_card(raw)
            add_item(c, inferred=True)
            # "Runite crossbow (u)" is a version of the Rune crossbow card: using it needs that card
            if c and raw.lower() != c.lower():
                ingredient_cards.add(c)
            if depth < 3 and _only_made(ctx.sources.get(raw) or ctx.sources.get(c or "")):
                add_ingredients(raw if raw in ctx.sources else c, depth + 1)

    if _MAKE_RE.search(task_text):
        for m in first_links:
            title = m.group(1)
            product = ctx.item_card(title)
            if product:
                add_ingredients(product, 0)
                variant = next((k for k in ctx.sources if k.lower() == title.lower()), None)
                if variant and variant != product:
                    add_ingredients(variant, 1)

    # spells in the task line / real requirement lines: runes from central spells.json
    for t, _ in _LINK_RE.findall(first + "\n" + "\n".join(kept_req_lines)):
        spell = ctx.spells.get(t.lower())
        if spell:
            for rune in spell["runes"]:
                add_item(ctx.item_card(rune), inferred=True)

    # The Barrows: you dig into the brothers' mounds, so anything there needs a spade
    if any("barrows" in t.lower() and "gloves" not in t.lower()
           for t, _ in _LINK_RE.findall(first + "\n" + "\n".join(kept_req_lines))):
        add_item(ctx.item_card("Spade"))
        notes.append("A spade is needed to dig into the brothers' mounds.")

    # ── NPCs (any interaction with an NPC that has a card needs the card) ─────
    monsters, npcs = [], []
    kill_task = bool(_KILL_RE2.search(task_text))
    talk_task = bool(_TALK_RE.search(task_text))
    catch_task = bool(re.search(r"(?i)\b(catch|trap|net|snare|box trap)\b", task_text)) and not kill_task
    npc_sources = ([(first, True)] + [(l, False) for l in task_notes] + [(l, False) for l in kept_req_lines]
                   + [(g, False) for g in paren_npc_text])
    for text, is_task_line in npc_sources:
        for m in _LINK_RE.finditer(text):
            title = m.group(1)
            if ctx.is_quest(title) or _PLACE_AFTER_RE.match(text[m.end():]):
                continue
            c = ctx.npc_card(title)
            if not c or c in monsters or c in npcs:
                continue
            if catch_task and c.lower() in ctx.combat_npcs:
                continue                      # Hunter catches aren't fights (and gathering needs no card)
            if not kill_task and ctx.item_card(title):
                continue                      # "Manta ray" the fish, not the Sailing creature
            if re.match(r"\s*(?:area|room|floor|lair|dungeon|cave)\b", text[m.end():], re.I):
                continue                      # "the Infernal Mage area" is a place
            fights = c.lower() in ctx.combat_npcs
            if fights and (kill_task or not talk_task):
                monsters.append(c)
            else:
                npcs.append(c)       # e.g. Rantz in a chompy-kill task: you talk to him

    # outputs aren't requirements (unless the task also equips/uses them)
    used_outputs = set()
    if re.search(r"(?i)\b(equip|wear|wield|eat|drink)\b", task_text):
        used_outputs = products
    items = [c for c in items if c not in products or c in used_outputs or c in ingredient_cards]

    notes = [re.sub(r"^(?:and|or)\s+", "", x).strip().capitalize() if re.match(r"(?:and|or)\s", x) else x
             for x in notes if x.strip(" ,.")]

    # split mixed alternatives into the simple shapes where possible
    skills_any = [[{o["skill"]: o["level"]} for o in g] for g in any_of if all("skill" in o for o in g)]
    items_any = [[o["card"] for o in g] for g in any_of if all("card" in o for o in g)]
    mixed = [g for g in any_of if not all("skill" in o for o in g) and not all("card" in o for o in g)]
    # an explicit wiki "any of" group beats an item we only inferred (e.g. production says
    # Rune essence, the wiki says pure / daeyalt / rune essence); an item the wiki itself
    # requires makes the group redundant
    kept_groups = []
    for g in items_any:
        overlap = [c for c in g if c in items]
        if overlap and all(c in derived for c in overlap):
            items = [c for c in items if c not in overlap]
            kept_groups.append(g)
        elif not overlap:
            kept_groups.append(g)
    items_any = kept_groups

    mentioned = []
    for text in [first] + task_notes + kept_req_lines + paren_npc_text:
        for t, _ in _LINK_RE.findall(text):
            t = t.strip()
            if t and t not in mentioned and not t.lower().startswith(("file:", "category:")):
                mentioned.append(t)

    out = {"n": n, "task": task_text, "skills": skills, "quests": quests, "items": items,
           "monsters": monsters, "npcs": npcs, "_mentioned": mentioned}
    if any(v is False for v in boostable.values()):
        out["notBoostable"] = sorted(s for s, v in boostable.items() if v is False)
    if skills_any:
        out["skillsAny"] = skills_any
    if items_any:
        out["itemsAny"] = items_any
        labels = {str(i): group_labels[tuple(g)] for i, g in enumerate(items_any) if tuple(g) in group_labels}
        if labels:
            out["itemsAnyLabels"] = labels
    if mixed:
        out["anyOf"] = mixed
    if combat:
        out["combat"] = combat
    if partial:
        out["partialQuests"] = partial
    if tools:
        out["tools"] = tools
    if light_source:
        out["lightSource"] = True
    if IRONMAN_ACCOUNT:
        for sk, lv in ironman_skills.items():
            if lv > out["skills"].get(sk, 0):
                out["skills"][sk] = lv
                # the ironman level carries its own boostability; drop the normal level's "nb"
                if sk in out.get("notBoostable", []):
                    out["notBoostable"].remove(sk)
                    if not out["notBoostable"]:
                        del out["notBoostable"]
        for q in ironman_quests:
            if q not in out["quests"]:
                out["quests"].append(q)
    else:
        if ironman_skills:
            out["ironmanSkills"] = ironman_skills
        if ironman_quests:
            out["ironmanQuests"] = ironman_quests
    if notes:
        out["notes"] = notes
    return out


def _apply_override(area: str, tier: str, task: dict, ctx: Ctx) -> None:
    ov = CARD_OVERRIDES.get((area, tier, task["n"]))
    if not ov:
        return
    for c in ov.get("items", []):
        if ctx.item_card(c) and ctx.item_card(c) not in task["items"]:
            task["items"].append(ctx.item_card(c))
    for spell in ov.get("spells", []):
        for rune in ctx.spells.get(spell.lower(), {}).get("runes", {}):
            c = ctx.item_card(rune)
            if c and c not in task["items"]:
                task["items"].append(c)
    for m in ov.get("monsters", []):
        c = ctx.npc_card(m)
        if c and c not in task["monsters"]:
            task["monsters"].append(c)
    for npc in ov.get("npcs", []):
        c = ctx.npc_card(npc)
        if c and c not in task["npcs"]:
            task["npcs"].append(c)
    rm = {x.lower() for x in ov.get("remove", [])}
    for key in ("items", "monsters", "npcs"):
        task[key] = [c for c in task[key] if c.lower() not in rm]
    for g in ov.get("itemsAny", []):                       # add an "any one of" item group
        cards = [ctx.item_card(c) or c for c in g]
        task["items"] = [c for c in task["items"] if c not in cards]
        task.setdefault("itemsAny", [])
        if cards not in task["itemsAny"]:
            task["itemsAny"].append(cards)
    for g in ov.get("monstersAny", []):                    # "kill a chompy or a jubbly"
        cards = [ctx.npc_card(c) or c for c in g]
        task["monsters"] = [c for c in task["monsters"] if c not in cards]
        task["npcs"] = [c for c in task["npcs"] if c not in cards]
        task.setdefault("monstersAny", [])
        if cards not in task["monstersAny"]:
            task["monstersAny"].append(cards)
    if "skills" in ov:                                     # replace the skill requirements
        task["skills"] = dict(ov["skills"])
    if "skillsAny" in ov:
        task["skillsAny"] = ov["skillsAny"]
    if "anyOf" in ov:
        task["anyOf"] = ov["anyOf"]
    for key in ("quests", "partialQuests", "notBoostable"):
        for q in ov.get(key, []):
            if q not in task.setdefault(key, []):
                task[key].append(q)
    if ov.get("lightSource"):
        task["lightSource"] = True
    if ov.get("setsAny") == "barrows":                     # wear any one complete Barrows set
        task["setsAny"] = {"label": "Any Barrows set", "sets": BARROWS_SETS}
    for key in ("itemsAny", "monstersAny", "anyOf", "skillsAny", "notBoostable", "partialQuests"):
        if key in task and not task[key]:
            del task[key]
    if ov.get("note"):
        task.setdefault("notes", []).append(ov["note"])


def _tier_summary(tasks: list[dict]) -> dict:
    """Tier-level fields derived from its tasks, so they can never drift."""
    skills: dict[str, int] = {}
    quests, items, monsters, npcs = [], [], [], []
    for t in tasks:
        for s, lv in t["skills"].items():
            skills[s] = max(skills.get(s, 0), lv)
        for q in t["quests"] + t.get("partialQuests", []):
            if q not in quests:
                quests.append(q)
        items += [c for c in t["items"] if c not in items]
        monsters += [c for c in t["monsters"] if c not in monsters]
        npcs += [c for c in t["npcs"] if c not in npcs]
    return {"skills": skills, "quests": quests, "items": items, "monsters": monsters, "npcs": npcs}


_TYPES_CACHE = _DIR / "cache" / "wiki_page_types.json"


def _page_types(titles: list[str]) -> dict[str, str]:
    """Wiki infobox type per page title ("Item", "NPC", "Monster", "Location"…, or "" if none).
    Batched 50 titles per API request; cached in scripts/cache/wiki_page_types.json."""
    import time, urllib.parse, urllib.request
    cache = json.loads(_TYPES_CACHE.read_text(encoding="utf-8")) if _TYPES_CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&prop=revisions&rvprop=content"
               "&rvslots=main&format=json&redirects=1&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read()).get("query", {})
        alias = {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}
        types = {}
        for page in q.get("pages", {}).values():
            content = (page.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            m = re.search(r"\{\{\s*Infobox ([A-Za-z ]+?)\s*[|\n}]", content)
            types[page["title"]] = m.group(1).strip() if m else ""
        for t in batch:
            target = alias.get(alias.get(t, t), alias.get(t, t))
            cache[t] = types.get(target, "")
        time.sleep(1)
    _TYPES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _TYPES_CACHE.write_text(json.dumps(cache, indent=0, ensure_ascii=False), encoding="utf-8")
    return cache


def _tag_uncarded(result: list[dict], ctx: Ctx) -> None:
    """For every task, list the items and NPCs it mentions that have NO TCG card — so the page
    can show they were considered (no card = no restriction), not missed."""
    def carded(t: str) -> bool:
        return bool(ctx.item_card(t) or ctx.npc_card(t))
    entries = [x for a in result for tier in TIERS
               for x in a.get(tier, {}).get("tasks", []) + a.get(tier, {}).get("rewards", [])]
    titles = [t for x in entries for t in x.get("_mentioned", []) if not carded(t) and not ctx.is_quest(t)]
    types = _page_types(titles)
    for a in result:
        for tier in TIERS:
            for task in a.get(tier, {}).get("tasks", []) + a.get(tier, {}).get("rewards", []):
                items_nc, npcs_nc = [], []
                for t in task.pop("_mentioned", []):
                    if carded(t) or ctx.is_quest(t):
                        continue
                    kind = types.get(t, "")
                    name = re.sub(r"\s*\([^)]*\)$", "", t.replace("_", " ")).strip()
                    name = name[:1].upper() + name[1:]
                    if re.search(r"(?i)\bpoints?\b|^noted$|^bank note$|^collection log$", name):
                        continue                  # game mechanics, not items
                    if kind in ("Item", "Bonuses", "Construction", "Pet", "Currency") and name not in items_nc:
                        items_nc.append(name)
                    elif kind in ("NPC", "Monster") and name not in npcs_nc:
                        npcs_nc.append(name)
                if items_nc:
                    task["itemsNoCard"] = items_nc
                if npcs_nc:
                    task["npcsNoCard"] = npcs_nc
        for tier in TIERS:                                  # unlinked ones named by an override
            for task in a.get(tier, {}).get("tasks", []):
                ov = CARD_OVERRIDES.get((a["name"], tier, task["n"]), {})
                for key in ("npcsNoCard", "itemsNoCard"):
                    for x in ov.get(key, []):
                        if x not in task.setdefault(key, []):
                            task[key].append(x)


def build(ctx: Ctx) -> list[dict]:
    result = []
    for area, page in AREAS.items():
        text = _fetch_wikitext(page)
        tm = re.search(r"\|\s*taskmasters?\s*=\s*\[\[([^\]|]+)", text)   # infobox
        entry = {"name": area, "rewardNpc": tm.group(1).strip() if tm else REWARD_NPCS.get(area)}
        for tier, section in _tier_sections(text).items():
            tasks = [parse_task(n, t, r, ctx) for n, t, r in _rows(section)]
            for t in tasks:
                _apply_override(area, tier, t, ctx)
            rewards = _rewards(section, ctx)
            for r in rewards:
                r["items"] = [c for c in r.get("items", []) if (area, tier, c) not in REWARD_CARD_REMOVE]
                if not r["items"]:
                    del r["items"]
            entry[tier] = {**_tier_summary(tasks), "rewards": rewards, "tasks": tasks}
        result.append(entry)
        for (oa, ot, on) in CARD_OVERRIDES:                # an override on a missing task is a typo
            if oa == area and on > len(entry.get(ot, {}).get("tasks", [])):
                raise SystemExit(f"CARD_OVERRIDES targets {oa} {ot} task {on}, which doesn't exist")
        print(f"  {area:<22} " + " / ".join(str(len(entry.get(t, {}).get('tasks', []))) for t in TIERS))
    _tag_uncarded(result, ctx)
    return result


_WIKITEXT_CACHE = _DIR / "cache" / "wikitext"


def _fetch_wikitext(page: str, refresh: bool = False) -> str:
    """Raw wikitext for a page, cached in scripts/cache/wikitext/ (gitignored)."""
    import time, urllib.parse, urllib.request
    cache = _WIKITEXT_CACHE / (page.replace(" ", "_").replace("/", "%2F") + ".txt")
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    time.sleep(1)  # be polite to the wiki
    url = ("https://oldschool.runescape.wiki/api.php?action=parse&prop=wikitext&format=json&page="
           + urllib.parse.quote(page.replace(" ", "_")))
    req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = json.loads(r.read())["parse"]["wikitext"]["*"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    p.add_argument("--out-dir", default=str(_OUT_DIR))
    args = p.parse_args()
    ctx = Ctx(args.card_json)
    data = build(ctx)
    out = Path(args.out_dir) / "diaries.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    if ctx.unknown_quests:
        print(f"  Quests not in quests.json: {sorted(ctx.unknown_quests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
