# Data Structures

## Card.json Schema

The card catalog is hosted at `https://osrs-tcg.xyz/catalog/Card.json` and bundled inside the OSRS TCG plugin JAR at `/Card.json`. Current snapshot: **6,376 cards**.

### Card Categories
Cards partition into two main types by their first category tag:

| Category | Count | Description |
|----------|-------|-------------|
| `Monster` | 1,227 | NPCs / attackable entities |
| `Resource` | 5,149 | All other items (equipment, consumables, etc.) |

Resource cards carry additional sub-category tags (geography + type):
- Types: `Armour`, `Weapon`, `Consumable`, `Clue`, `General`
- Geography: `Morytania`, `Kourend`, `Asgarnia`, `Kandarin`, `Varlamore`, `Desert`, `Misthalin`, `Wilderness`, `Fremennik`, `Tirannwn`, `Karamja`, `Barrows`

### Item Card Fields (Resource)
```json
{
  "name": "Abyssal whip",
  "category": ["Resource", "Weapon", "Morytania"],
  "imageUrl": "https://oldschool.runescape.wiki/images/thumb/...",
  "questItem": false,
  "tradeable": true,
  "equipable": true,
  "stackable": false,
  "noteable": true,
  "options": ["Wield", "Drop"],
  "examine": "A weapon from the Abyss.",
  "value": 120001,
  "equipmentSlot": "weapon"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | **Primary key** — no numeric ID exists |
| `category` | string[] | First tag = primary type; rest = sub-types/geography |
| `imageUrl` | string | OSRS Wiki image URL |
| `questItem` | boolean | |
| `tradeable` | boolean | |
| `equipable` | boolean | |
| `stackable` | boolean | |
| `noteable` | boolean | |
| `options` | string[] | In-game right-click options |
| `examine` | string | |
| `value` | integer | High Alchemy GP value |
| `equipmentSlot` | string? | `"weapon"`, `"neck"`, `"head"`, etc. Only present if equipable |

### Monster Card Fields
Monster cards have different/additional fields:
```json
{
  "name": "Abyssal Sire",
  "level": 350,
  "category": ["Monster"],
  "imageUrl": "https://oldschool.runescape.wiki/images/thumb/...",
  "examine": "A higher order of abyssal demon.",
  "attackStyle": "Melee",
  "maxHit": "66 (Melee), 96 (with explosion)"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | **Primary key** — may have wiki disambiguation suffix (see below) |
| `level` | integer | Combat level — used for rarity/score calculation |
| `category` | string[] | Always `["Monster"]` |
| `imageUrl` | string | |
| `examine` | string | |
| `attackStyle` | string | e.g. `"Melee"`, `"Ranged"`, `"Magic"` |
| `maxHit` | string | Free-text, e.g. `"66 (Melee), 96 (with explosion)"` |
| `overrideScore` | long? | Overrides level-derived rarity contribution when present |

### Name Disambiguation
67 monster card names carry wiki-style bracket suffixes that the in-game NPC name never contains:
- `"Monkey (monster)"` → in-game NPC: `"Monkey"`
- `"Soldier (Yanille)"`, `"Soldier (Falador)"`, ..., `"Soldier (Camelot)"` (11 variants) → all unlock in-game `"Soldier"`

The Bronzeman plugin's `TrackedMonsterCatalog` handles this via a `{entityName → [cardNames]}` map. Owning **any** variant card unlocks the NPC.

2 `(unused)` monster cards are excluded from Bronzeman enforcement as they have no in-game attackable equivalent.

---

## OSRS TCG State Format

Player state is stored in RuneLite's `ConfigManager` under:
- **Group**: `osrstcg`
- **Key**: `state`
- **Value**: `RLTCG_v2:` + base64(XOR_salt(gzip(JSON)))

The `TcgStateDecoder` in Bronzeman mirrors this transform exactly (salt copied from `TcgStateStorageEncoding.java` in OSRS TCG).

### State JSON Shape (schemaVersion 3)
```json
{
  "cardInstances": [
    { "cardName": "Abyssal whip", "foil": false },
    { "cardName": "Zulrah", "foil": true }
  ],
  "credits": 12500
}
```

Note: schema evolved — earlier versions had `collectionState.instances[]` at a nested path. Current schema (v3) has `cardInstances[]` at top level.

---

## Bronzeman Catalog Snapshot Format

The Bronzeman plugin bundles two static JSON snapshots:

### `/tracked_monster_names.json`
```json
{
  "entityToCards": {
    "goblin": ["goblin (monster)"],
    "monkey": ["monkey (monster)"],
    "soldier": ["soldier (yanille)", "soldier (falador)", "..."]
  }
}
```
- Keys: in-game entity name (lowercase)
- Values: array of matching card names (lowercase)
- 1,198 entity entries ← 1,225 Monster cards (2 `(unused)` excluded)

### `/tracked_item_names.json`  
- Same format as monster catalog
- 5,149 entries ← 5,149 Resource cards (1:1 mapping, no disambiguation needed)

Both are regenerated via `scripts/generate_tracked_monsters.py` when Card.json updates.

### Consumables Catalog
`ConsumablesCatalog` handles potion dose stripping: `"Attack potion(3)"` → `"attack potion"`. All four dose variants map to one card.

---

## CardCollectionKey (OSRS TCG internal)

The `CardCollectionKey` identifies a unique owned card slot: `{cardName, foil}`. The collection is stored as `Map<CardCollectionKey, Integer>` (card → count of copies owned).

For Bronzeman purposes, foil and normal are folded together — owning either counts as unlocked.
