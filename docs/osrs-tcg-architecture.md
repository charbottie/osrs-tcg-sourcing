# OSRS TCG Plugin Architecture

**Repo**: `Azderi/osrs-tcg` · **Plugin Hub name**: OSRS TCG · **Current version**: 0.17.2  
**Language**: Java 11 · **Build**: Gradle · **Package**: `com.osrstcg`

---

## Overview

OSRS TCG is a RuneLite external plugin that overlays a gacha trading card game onto OSRS gameplay. Players earn **credits** through normal gameplay, spend credits to open **booster packs**, and build a **card collection** representing items, NPCs, and bosses from the game.

---

## Package Structure

```
com.osrstcg/
├── OsrsTcgPlugin.java         # Entry point — wires everything together
├── OsrsTcgConfig.java         # All user-facing settings
├── data/                      # Card data loading
│   ├── CardDefinition.java    # Card data model (POJO)
│   ├── CardDatabase.java      # Loads Card.json; indexed by name
│   ├── PackCatalog.java       # Booster pack definitions
│   └── BoosterPackDefinition.java
├── model/                     # Domain model
│   ├── TcgState.java          # Top-level state (economy + collection)
│   ├── CollectionState.java   # Owned cards map
│   ├── EconomyState.java      # Credits, packs opened
│   ├── CardCollectionKey.java # {cardName, foil} — unique card slot
│   └── OwnedCardInstance.java # One owned copy with provenance metadata
├── service/                   # Business logic
│   ├── TcgStateService.java   # Owns/persists the player's state
│   ├── CreditAwardService.java
│   ├── NpcKillCreditTracker.java
│   ├── GameMessageCreditTracker.java
│   ├── PackOpeningService.java
│   ├── PackRevealService.java
│   ├── OwnedCardNamesApiService.java  # Inter-plugin API
│   └── CollectionShareService.java    # osrs-tcg.xyz profile sharing
├── persist/                   # Storage layer
│   ├── TcgStateStore.java
│   ├── TcgStateCodec.java     # RLTCG_v2 encoding (gzip + XOR + base64)
│   └── TcgStateFileBackupStore.java
├── party/                     # RuneLite Party plugin messages
│   └── Tcg*PartyMessage.java
├── overlay/                   # In-game overlays
│   ├── PackRevealOverlay.java
│   └── CreditsInfoboxOverlay.java
└── ui/                        # Swing UI panels
    ├── TcgPanel.java
    └── collectionalbum/
        └── CollectionAlbumManager.java
```

---

## Key Components

### Card Data (`CardDatabase`)
- Loads `Card.json` bundled in the plugin JAR at plugin startup (singleton, loads once)
- Returns `List<CardDefinition>` — name-indexed via lowercase linear scan
- Card names are HTML-entity-decoded and trimmed on load
- No numeric IDs — **name is the sole identifier**

### Player State (`TcgStateService`)
- Owns `TcgState` = `{EconomyState (credits, openedPacks), CollectionState (ownedCards: Map<CardCollectionKey, Integer>)}`
- Persisted in RuneLite `ConfigManager` (RSProfile-scoped):
  - **Group**: `osrstcg` · **Key**: `state`
  - **Encoding**: `RLTCG_v2:` + base64(XOR_salt(gzip(JSON)))
- File backups stored in `.runelite/bronzeman-tcg/` directory (3 rotating files)
- Emits collection change notifications (used by `OwnedCardNamesApiService`)

### Credit Award System (`CreditAwardService`)
Credits are earned through:

| Source | Rate |
|--------|------|
| XP gained (non-combat skills) | 100 credits per 1,000 XP |
| XP gained (combat — via `FakeXpDrop`) | 100 credits per 1,000 XP |
| NPC/boss kill | Equal to NPC combat level in credits |
| Level-up bonus | Exponential curve: 1,250 (level 2) → 25,000 (level 99+) |
| Clue scrolls | Via `GameMessageCreditTracker` |
| Boss-specific sources | CoX CM, Gauntlet, Phantom Muspah, Abyssal Sire, etc. |

Credit cooldown: 3 ticks after login/world hop to suppress bogus XP drops.

### Inter-Plugin API (`OwnedCardNamesApiService`)
Other RuneLite plugins query OSRS TCG for owned card names via `PluginMessage`:

```java
// Constants (copy these — no cross-classloader import):
OwnedCardNamesApiService.NAMESPACE = "osrstcg"
OwnedCardNamesApiService.QUERY     = "query-owned-names"
OwnedCardNamesApiService.REPLY     = "owned-names"
OwnedCardNamesApiService.CHANGED   = "owned-names-changed"
OwnedCardNamesApiService.KEY_OWNED_NAMES = "ownedNames"

// To query:
eventBus.post(new PluginMessage("osrstcg", "query-owned-names"));

// Response arrives as:
// PluginMessage("osrstcg", "owned-names", {ownedNames: List<String>})
// Pushes also arrive on any collection change:
// PluginMessage("osrstcg", "owned-names-changed", {ownedNames: List<String>})
```

Payload: `List<String>` of distinct owned card names (foil and normal folded), sorted case-insensitively. **This is the preferred inter-plugin interface** (event-bus, instant, no compression/decode overhead).

**Legacy fallback**: Bronzeman also reads the raw compressed ConfigManager state directly via `TcgCollectionReader`, used when OSRS TCG predates the API.

### Pack Opening
1. Player spends credits → `PackOpeningService.buyAndOpenPack()`
2. Cards are rolled from `CardDatabase` weighted by rarity (`RarityMath`)
3. Results handed to `PackRevealService` → animated overlay reveal
4. Collection updated in `TcgStateService`; party announcement broadcast

### Trading (Party Plugin)
Cards can be traded between players in a RuneLite Party:
- `CardPartyTradeService` / `CardPartyTransferService` handle the multi-step protocol
- 14 different `TcgTrade*PartyMessage` types
- Requires base RuneLite Party plugin to be enabled

---

## State Persistence Flow

```
Login / Profile switch
       ↓
TcgStateService.load()
       ↓
TcgStateStore → ConfigManager (primary)
       ↓ (on failure)
TcgStateFileBackupStore (up to 3 backups)
       ↓
OwnedCardNamesApiService starts listening + emitting changes
       ↓
CollectionShareService.onLoginOrProfileReady() → osrs-tcg.xyz sync
```

---

## Debug Commands

| Command | Requires Debug Mode | Effect |
|---------|--------------------|----|
| `::tcg-open` | No | Open first booster pack |
| `::tcg-load` | No | Restore from file backup (once per session) |
| `::tcg-save` | No | Save file backup manually |
| `::tcg-reset` | No | Reset collection via UI |
| `::tcg-give <card name>` | Yes | Add one copy of named card |
| `::tcg-give <card name> (foil)` | Yes | Add foil copy |
| `::tcg-set <amount>` | Yes | Set credit balance |
| `::tcg-complete` | Yes | Add 1× every catalog card |
| `::tcg-apex` | Yes | Open forced apex pack |

Chat command: `!tcg` — broadcasts your collection stats to the chat.
