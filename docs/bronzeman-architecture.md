# Bronzeman TCG Plugin Architecture

**Repo**: `Felmeme/bronzeman-tcg` · **Plugin Hub**: Live · **Package**: `com.bronzemantcg`  
**Developer**: Felmeme [TCG] · **Language**: Java 11 · **Build**: Gradle 8.10 (Temurin JDK 11)

---

## Overview

Bronzeman TCG turns OSRS TCG card ownership into gameplay restrictions. Players can only attack NPCs, use items, gather resources, and access content for which they've collected the relevant card. This is a read-only consumer of OSRS TCG data — it never writes to OSRS TCG's state.

---

## Class Structure

```
com.bronzemantcg/
├── BronzemanTcgPlugin.java      # Main plugin — enforcement engine
├── BronzemanTcgConfig.java      # All settings (17 sections, ~30 config items)
├── BronzemanTcgPanel.java       # Side panel (search / nearby / progress)
├── BronzemanTcgOverlay.java     # World overlays for locked NPCs
├── TcgStatsOverlay.java         # Optional credits/cards overlay

│ ─ Card ownership reading ─
├── TcgCollectionReader.java     # Reads OSRS TCG's persisted state (cached 5s)
├── TcgStateDecoder.java         # Decodes RLTCG_v2 format
├── TcgStateDto.java             # Minimal mirror of osrs-tcg JSON shape

│ ─ Catalog system ─
├── CardNameCatalog.java         # Abstract: entityName → [cardVariantNames]
├── CardNames.java               # Dose-stripping util ("Attack potion(3)" → "Attack potion")
├── TrackedMonsterCatalog.java   # /tracked_monster_names.json (1,198 NPCs)
├── TrackedItemCatalog.java      # /tracked_item_names.json (5,149 items)
├── ConsumablesCatalog.java      # Potions/food by name
├── ResourceNodeCatalog.java     # /resource_nodes.json (400+ gathering nodes)
├── RecipeCatalog.java           # /recipe_nodes.json (378 crafting recipes)
├── ContentCatalog.java          # /content_cards.json (PvM content, 7 entries)
├── QuestCatalog.java            # Quest-required card lookups
├── QuestNpcIndex.java           # Quest NPCs that bypass NPC lock

│ ─ Visual overlays ─
├── LockedItemIconOverlay.java   # Bank-filler badge on locked items
├── LockedNpcOverlay.java        # Grey tint/outline on locked NPCs (if any)

│ ─ Skill restriction modes (enums) ─
├── NpcVisibilityMode.java       # OFF / PREVENT_COMBAT / PREVENT_INTERACTION / HIDE_NPCS
├── LockState.java               # LOCKED / UNLOCKED
├── BankingMode.java             # OFF / DEPOSIT_ONLY / FULL_BANKING
├── ThievingMode.java            # COINS_POUCH / COINS_POUCH_NPC / ALL
├── StallThievingMode.java       # OFF / ANY_OF / ALL_ITEMS
├── FishingRestrictionMode.java  # OFF / ANY_OF / REQUIRE_ALL
├── FiremakingMode.java          # JUST_LOGS / LOGS_TINDERBOX
├── SmeltingMode.java            # ORE / BARS / BOTH
├── SmithingMode.java            # BARS / ITEMS / BOTH
├── RunecraftingMode.java        # TALISMAN / TALISMAN_RUNES
├── FarmingRakeMode.java         # RAKE / BOTH (+ weeds)
├── FarmingPlantMode.java        # TOOLS / TOOLS_SEEDS / ALL
├── HunterBirdsMode.java         # NET_ONLY / ALL
├── ImplingMode.java             # NET / BOTH
├── SalamanderMode.java          # ROPE_NET / ALL
├── PitfallMode.java             # TOOLS / ALL
└── SailingUpgradeMode.java      # PARTS / PARTS_MATERIALS / EVERYTHING
```

---

## How It Reads OSRS TCG Data

### Method 1: PluginMessage API (preferred, when OSRS TCG ≥ API version)
```java
// Send a query:
eventBus.post(new PluginMessage("osrstcg", "query-owned-names"));
// Receive reply: PluginMessage("osrstcg", "owned-names", {ownedNames: List<String>})
// Also receives pushes on any collection change: "owned-names-changed"
```
Instant, no compression/decode overhead. Built and tested in-game; awaiting upstream merge.

### Method 2: Config decode fallback (always available)
`TcgCollectionReader` reads directly from RuneLite `ConfigManager`:
- Group: `osrstcg` · Key: `state`
- Decodes via `TcgStateDecoder`: strip `RLTCG_v2:` prefix → base64 decode → XOR salt → gunzip → JSON parse
- Cached for **5 seconds** to avoid repeated decompression
- Cache invalidated on `RuneScapeProfileChanged`
- On decode failure: **enforcement stands down entirely** with repeating chat warning (fail-open since 2026-07-18 — prevents locking out users on upstream format changes)

`TcgStateDto` mirrors only the fields needed:
```java
class TcgStateDto {
    List<OwnedCardInstanceDto> cardInstances; // {cardName, foil}
    long credits;
}
```

### Owned Name Resolution
`TcgCollectionReader` returns `Set<String>` of owned card names in **lowercase**. Foil and normal copies are folded — owning either counts as unlocked.

---

## Enforcement Architecture

### What's Checked
All enforcement goes through `MenuOptionClicked` events (before the action executes):

| Event type | What's checked |
|-----------|---------------|
| `NPC_FIRST..FIFTH_OPTION` where option = "Attack" | NPC card owned? |
| `WIDGET_TARGET_ON_NPC` (spell/item on NPC) | NPC card owned? |
| `GROUND_ITEM_FIRST..FIFTH_OPTION` where option = "Take" | Item card owned? |
| `WIDGET_TARGET_ON_GROUND_ITEM` (telegrab) | Item card owned? |
| `GAME_OBJECT_FIRST..FIFTH_OPTION` | Resource node check |
| `NPC_FIRST..FIFTH_OPTION` (gathering NPCs) | Resource node check |
| `WIDGET_DEFAULT`/interface clicks | Recipe/skill check |

Secondary enforcement layers:
- **Menu entry hiding**: locked options removed before menu renders (visual layer)
- **Click consumption**: `event.consume()` blocks the action as final guard
- **Entity visibility**: NPCs can be hidden entirely in config

### NPC Lock Check Flow
```
MenuOptionClicked(Attack on NPC)
  → getTransformedComposition().getName() → Text.removeTags()
  → TrackedMonsterCatalog.isTracked(npcName)?
      → No: always allow (untracked NPCs are never restricted)
      → Yes: TrackedMonsterCatalog.getCardVariantsLowerCase(npcName)
          → owned.containsAny(variants)?
              → Yes: allow
              → No: consume event + chat feedback
```

### Quest NPC Bypass
`QuestNpcIndex` tracks NPCs associated with quests the player has started or finished. These NPCs are **always shown and talkable** (even on strictest settings) — prevents quest-bricking. Attack still requires the card.

### Resource Node Check
`ResourceNodeCatalog` contains 400+ hand-curated nodes in `resource_nodes.json`, each with:
```json
{
  "kind": "tree|rock|fishing-spot|thieving-stalls|...",
  "name": "Oak tree",
  "option": "Chop down",
  "cards": ["Oak logs"]
}
```
Checks: does the player own the card(s) required for this (name, option) pair?

### Recipe Check
`RecipeCatalog` contains 378 recipes in `recipe_nodes.json` covering:
- Firemaking (logs + tinderbox), Smelting, Smithing, Cooking, Crafting, Enchanting, Fletching, Herblore, Runecrafting
- Make-X flows: mouse-only (spacebar and materials-for-one bypass — owner-accepted)

---

## Catalog System

### `CardNameCatalog` (abstract base)
- Loads `{entityToCards: {lowerEntityName → [lowerCardNames]}}` from a classpath resource
- `isTracked(entityName)` → boolean
- `getCardVariantsLowerCase(entityName)` → `Set<String>` of card names that unlock this entity
- Potion dose stripping via `CardNames.stripDoseSuffix()`

### Static Snapshots
Snapshots are **bundled** (not fetched at runtime). Must be regenerated with:
```bash
python scripts/generate_tracked_monsters.py <path-to-Card.json>
```
This splits Monster/Resource categories, strips bracket disambiguators, excludes `(unused)` cards.

---

## Configuration Surface (BronzemanTcgConfig)

Sections and key settings:

| Section | Key settings |
|---------|-------------|
| **General** | NPC Locks (Off/Prevent Combat/Prevent Interaction/Hide), Ground Items, Item Usage, Food Settings, Banking, Grand Exchange, Coin Settings, Item exempt list, Chat feedback, Allow LMS, Conflict warning |
| **Visuals** | Locked Item Indicator (Off/Fade/Fade+Icon), Tint locked NPCs, Outline colour/width/feather, TCG stats overlay |
| **Cooking** | Restrict cooking, Require burnt food |
| **Crafting** | Restrict crafting, Restrict enchanting, Require crushed gem |
| **Farming** | Raking mode, Planting mode, Compost bins |
| **Firemaking** | Mode (Just logs / Logs+Tinderbox), Include event logs |
| **Fletching** | Restrict fletching |
| **Herblore** | Restrict herblore |
| **Hunter** | Birds mode, Implings mode, Chinchompas, Salamanders mode, Pitfalls mode, Extreme rumour masters |
| **Mining** | Restrict mining |
| **Runecrafting** | Mode (Talisman / Talisman+Runes) |
| **Sailing** | Boat upgrades mode, Restrict salvaging |
| **Slayer** | Require masters, Require monsters, Include superiors |
| **Smithing** | Smelting mode, Smithing mode |
| **Thieving** | Pickpocketing mode, Stall mode, H.A.M. Insanity, Master Farmer insanity |
| **Woodcutting** | Restrict woodcutting |
| **Fishing** | Fishing mode (Off/Any of/Require ALL) |

---

## Key Operational Notes

### Version / Release Flow
- Version in `runelite-plugin.properties` → `version=0.MINOR.PATCH`
- Every release: bump version + add CHANGELOG.md entry → push → PR to `runelite/plugin-hub` with new commit hash
- **Never rename a config keyName** — renaming wipes player settings
- **Never set a non-empty default on user-editable list fields** — RuneLite re-injects the default when stored value is cleared

### Build
```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-11.0.31.11-hotspot"
./gradlew build --no-daemon
./gradlew run   # dev client
```

### Testing
No automated in-game tests possible. Manual test plan:
1. Attack unowned tracked NPC → blocked + chat
2. `::tcg-give <name>`, wait ≤5s → attack succeeds
3. Attack untracked NPC → never blocked
4. Toggle config off → restriction lifts
5. LMS match → all restrictions lift

---

## Deferred / Known Gaps
- **Sailing**: implemented but untested in-game (owner lacks quick access)
- **Firemaking**: permanent log objects with "Light" option bypass the gate (fix: add object node)
- **Card browser panel**: on roadmap — grouped view by skill/type
- **Grey model recolor**: roadmap (dropdown alongside outline/tint)
- **Time Tracking interop**: per-patch harvest/compost restrictions
- **Encoded name defect**: 4 tracked names have U+FFFD replacement chars from snapshot generator encoding bug
