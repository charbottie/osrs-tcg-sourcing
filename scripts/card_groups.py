"""Canonical card groups for bm_quest_cards.json.

A group is a named set of interchangeable cards that satisfy a requirement
(e.g. any axe, any pickaxe).  Groups are stored in the top-level "groups"
key of bm_quest_cards.json and referenced by name in requirements:

    {"label": "Any axe", "group": "axe", "type": "item"}

rather than listing all 11 axe variants inline.

Rules for adding a group:
  - The same set of cards appears as an any-of requirement in 2+ quests.
  - The set has a natural game-mechanic name ("any log", "any pickaxe", etc.).
  - Cards are ordered weakest → strongest so the renderer shows them in a
    logical tier order.

One-off or context-specific sets (e.g. "Rune axe or higher", "any spear")
are kept as explicit cards[] on the requirement rather than as groups.
"""

# Each list is ordered weakest → strongest (or alphabetical if no clear tier).
CARD_GROUPS: dict[str, list[str]] = {
    # ── Woodcutting ──────────────────────────────────────────────────────────
    "axe": [
        "Bronze axe", "Iron axe", "Steel axe", "Black axe", "Mithril axe",
        "Adamant axe", "Gilded axe", "Rune axe", "Dragon axe",
        "3rd age axe", "Crystal axe",
    ],

    # ── Mining ───────────────────────────────────────────────────────────────
    "pickaxe": [
        "Bronze pickaxe", "Iron pickaxe", "Steel pickaxe", "Black pickaxe",
        "Mithril pickaxe", "Adamant pickaxe", "Gilded pickaxe", "Rune pickaxe",
        "Dragon pickaxe", "3rd age pickaxe", "Crystal pickaxe",
    ],

    # ── Logs (firemaking / construction / misc) ──────────────────────────────
    # Full set — any log including Redwood.
    "log": [
        "Logs", "Oak logs", "Willow logs", "Teak logs", "Maple logs",
        "Mahogany logs", "Yew logs", "Magic logs", "Redwood logs",
    ],

    # ── Ranged — bows (non-crossbow) ─────────────────────────────────────────
    "bow": [
        "Shortbow", "Oak shortbow", "Oak longbow", "Willow shortbow",
        "Willow longbow", "Maple shortbow", "Maple longbow", "Yew shortbow",
        "Yew longbow", "Magic shortbow", "Magic longbow", "Longbow",
    ],

    # ── Ranged — crossbows ────────────────────────────────────────────────────
    "crossbow": [
        "Crossbow", "Bronze crossbow", "Blurite crossbow", "Iron crossbow",
        "Steel crossbow", "Mithril crossbow", "Adamant crossbow",
        "Rune crossbow", "Dragon crossbow",
    ],

    # ── Dungeoneering / lighting ──────────────────────────────────────────────
    "light-source": [
        "Candle", "Torch", "Oil lamp", "Oil lantern", "Candle lantern",
        "Mining helmet", "Bullseye lantern", "Bruma torch", "Abyssal lantern",
    ],

    # ── Construction ─────────────────────────────────────────────────────────
    "nails": [
        "Bronze nails", "Iron nails", "Steel nails", "Black nails",
        "Mithril nails", "Adamantite nails", "Rune nails",
    ],

    # ── Rune crafting ─────────────────────────────────────────────────────────
    "essence": ["Rune essence", "Pure essence"],

    # ── Miscellaneous ─────────────────────────────────────────────────────────
    "cake":       ["Cake", "Chocolate cake"],
    "fishing-rod":["Fishing rod", "Fly fishing rod"],
    "needle":     ["Needle", "Costume needle"],
}
