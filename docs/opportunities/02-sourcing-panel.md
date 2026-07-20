# Plan: Card Sourcing Panel

## What We're Building

A sourcing/info panel integrated into the OSRS TCG collection album. Click any card → see where it comes from and what it connects to. Pure information — no restrictions, no blocking.

**Monster card clicked:**
- Notable drops (filtered to only items that have TCG cards), each highlighted ✓/✗ based on whether you own that card
- Quest access requirements (e.g. "Requires: Monkey Madness II → Monkey Madness I → Tree Gnome Village")
- Slayer level requirement if applicable

**Item/Resource card clicked:**
- Which monsters drop it (only monsters that have TCG cards), with rarity labels, each highlighted ✓/✗
- Quest connections — if obtained via quest reward or unlocked by a quest

---

## Where It Lives

### Decision: PR to `Azderi/osrs-tcg`

The card viewer (`CollectionAlbumWindow`) is a JFrame in OSRS TCG. Another plugin cannot inject UI into it — there's no inter-Swing hook available across classloaders. So the sourcing panel must either:

**A) Live inside OSRS TCG** — PR to Azderi/osrs-tcg, adds a sourcing view to the album window  
**B) Be a standalone plugin** — has its own RuneLite nav panel with search, reads ownership via PluginMessage API

**Recommendation: A (PR to OSRS TCG)**
- Az said he's "happy to add anything that's necessary" — he's already open
- The natural UX is click-in-album → see info, not click-album → go to different panel
- The sourcing data (drop tables, quest chains) is also useful to OSRS TCG itself (e.g. for future pack theming)
- Az is actively adding features — this is a good moment to propose it

**De-risking**: Build the data pipeline and panel component first. Once it's solid, submit the PR. The PR scope for Az is small (wire up the panel); the heavy lift is the data.

---

## UI Design

### Integration Point in the Album Window

The album window has:
```
[NORTH: controls, search, filter, paging]
[CENTER: CardLayout — browse grid ↔ variants panel]
[SOUTH: party/trade buttons]
```

**Proposed change**: split CENTER into a **master-detail layout**:
```
[NORTH: controls]
[CENTER-LEFT: card grid (existing, narrowed)] | [CENTER-RIGHT: sources panel (new, ~280px)]
[SOUTH: trade buttons]
```

The right panel is hidden when no card is selected, expands when a card is clicked. This is a JSplitPane or a simple side-by-side BoxLayout. Non-destructive to existing layout.

**Alternative (simpler, less invasive)**: add a third CardLayout view "sources" that shows when a card is clicked (same as how variants panel slides in). User clicks card → sources slide in → "Back" button returns to grid.

**Recommendation: master-detail split** — avoids losing context of the full grid while reading sources. The right panel starts collapsed (0px) and expands to ~280px on first card click.

### Sources Panel Wireframe

```
┌──────────────────────────────────┐
│ [Card image, ~80×120px]          │
│  Name (bold)                     │
│  Category tag · Rarity tier      │
│  Examine text (italic, small)    │
├──────────────────────────────────┤
│ DROPS / SOURCES                  │
│ (scrollable list)                │
│  ✓ Abyssal demon (lv 124) Rare   │  ← green ✓ = you own that card
│  ✓ Grotesque Guardians    Rare   │
│  ✗ Kraken (lv 291)        Rare   │  ← grey ✗ = not yet collected
│                                  │
├──────────────────────────────────┤
│ QUEST CONNECTIONS                │
│  Unlocked by: Monkey Madness II  │
│  → requires: Monkey Madness I    │
│  → requires: Tree Gnome Village  │
└──────────────────────────────────┘
```

For Monster cards (same panel, different content):
```
┌──────────────────────────────────┐
│ [Monster image]                  │
│  Abyssal Sire (lv 350)          │
│  Monster · Legendary             │
│  "A higher order of abyssal..."  │
├──────────────────────────────────┤
│ ACCESS                           │
│  Slayer: 85                      │
│  Quest: None                     │
├──────────────────────────────────┤
│ NOTABLE DROPS (cards only)       │
│  ✓ Abyssal whip         Common   │
│  ✗ Abyssal dagger       Uncommon │
│  ✗ Abyssal orphan       Rare     │
│  ✓ Abyssal head         Rare     │
└──────────────────────────────────┘
```

Owned cards get a green tint / ✓ mark. Unowned get grey / ✗. 
No card in catalog → not shown (only relevant items appear).

---

## Data Architecture

### Three bundled JSON files (generated at dev-time, bundled in JAR)

#### 1. `monster_drops.json`
```json
{
  "Abyssal Sire": {
    "drops": [
      {"card": "Abyssal whip", "rarity": "Common"},
      {"card": "Abyssal dagger", "rarity": "Uncommon"},
      {"card": "Abyssal orphan", "rarity": "Very Rare"}
    ],
    "slayerLevel": 85,
    "quests": []
  }
}
```
Only includes drops for items that have a TCG card. Cross-referenced against Card.json.

#### 2. `item_sources.json` (reverse index)
```json
{
  "Abyssal whip": {
    "monsters": [
      {"card": "Abyssal demon", "rarity": "Rare"},
      {"card": "Grotesque Guardians", "rarity": "Rare"}
    ],
    "quests": []
  },
  "Zenyte shard": {
    "monsters": [
      {"card": "Demonic gorilla", "rarity": "Uncommon"}
    ],
    "quests": ["Monkey Madness II"]
  }
}
```

#### 3. `quest_chains.json`
```json
{
  "Monkey Madness II": {
    "prerequisites": ["Monkey Madness I", "Tree Gnome Village"],
    "rewardCards": ["Zenyte shard"],
    "monsterCards": ["Demonic gorilla"]
  }
}
```

### Data Generation Pipeline

Script (`scripts/generate_sources.py`) using OSRS Wiki:
1. Fetch Card.json → build set of all card names (monster + item)
2. For each monster card: fetch its wiki page, parse loot table infobox, filter to items in Card.json, record rarity bucket (Common/Uncommon/Rare/Very Rare/Extremely Rare)
3. Build reverse index: item → list of monster sources
4. Fetch quest pages: parse prerequisites and item rewards
5. Write three JSON files

**Wiki rules** (per Bronzeman CLAUDE.md guidance):
- Plain page URLs only (e.g. `https://oldschool.runescape.wiki/w/Abyssal_Sire`)
- Never `api.php?action=parse`
- Pace: ~1 req/sec
- Descriptive `User-Agent: osrs-tcg-sources/dev (github.com/Azderi/osrs-tcg)`
- Cache all raw fetches in `scripts/cache/` so re-runs are free
- No wiki requests at plugin runtime — data is static in JAR

**Rarity bucketing**: OSRS Wiki uses exact fractions. Map to labels:
- 1/1 – 1/10 → Common
- 1/11 – 1/100 → Uncommon  
- 1/101 – 1/500 → Rare
- 1/501 – 1/5000 → Very Rare
- 1/5001+ → Extremely Rare

---

## New Classes Required

### In OSRS TCG plugin

| Class | Purpose |
|-------|---------|
| `CardSourceCatalog.java` | Loads monster_drops.json + item_sources.json + quest_chains.json; provides lookup API |
| `CardSourcePanel.java` | The Swing panel — shows card image, drops, sources, quest chain |
| `SourceEntry.java` | Simple POJO: `{String cardName, String rarity, boolean owned}` |

### Changes to existing classes

| Class | Change |
|-------|--------|
| `CollectionAlbumGridPanel.java` | Fire "card selected" callback for ANY click (currently only fires for owned multi-copy; single clicks on unowned cards are silent) |
| `CollectionAlbumWindow.java` | Add split-pane layout with `CardSourcePanel` on right; wire up `onSlotSelectionChanged` to update source panel; inject `CardSourceCatalog` |
| `OsrsTcgPlugin.java` | Inject `CardSourceCatalog` and pass to `CollectionAlbumManager` |

---

## Click Behavior Changes

### Current behavior
- Click unowned card → selects it, but nothing happens (south bar stays disabled)
- Click owned single-copy → selects for trading
- Click owned multi-copy → opens variants panel

### New behavior
- Click ANY card (owned or not) → show sourcing panel on the right
- Owned card still selects for trading as before
- Multi-copy still opens variants panel as before (sourcing visible alongside)

The right-panel (source info) is always updated on click, regardless of ownership.

---

## Phased Delivery

### Phase 1: Data pipeline + panel component (independent)
- Write `generate_sources.py` — fetch, parse, generate the 3 JSONs
- Build `CardSourceCatalog.java` and `CardSourcePanel.java` as standalone Swing components
- Test with a small harness (no RuneLite needed)
- Generate + validate data for ~100 representative cards

### Phase 2: Album integration (PR to OSRS TCG)
- Submit PR to `Azderi/osrs-tcg` with:
  - 3 JSON data files in resources
  - `CardSourceCatalog.java`, `CardSourcePanel.java`, `SourceEntry.java`
  - Modified `CollectionAlbumWindow.java`, `CollectionAlbumGridPanel.java`
  - One config toggle: "Show card sources panel" (default ON)
- Discuss with Az: layout preference, whether to use split pane or third CardLayout view

### Phase 3: Full coverage
- Run data pipeline against complete Card.json (all 1,227 monsters, all relevant items)
- Verify coverage / fill gaps (some monsters may not have wiki loot tables)
- Quest chain data for all quest-gated items

---

## Questions to Resolve Before Starting

1. **Layout**: split-pane (grid stays visible) vs third CardLayout view (sources replace grid). User preference?
2. **Rarity display**: show exact fraction (1/512) or label only (Rare)? Or both?
3. **Quest chain depth**: show full prerequisite chain (all the way to root quests) or just immediate prereqs?
4. **Scope of "notable drops"**: all TCG card drops, or only ones worth highlighting (e.g. exclude common drops like Bones)?
5. **Untracked monsters**: if a monster has no TCG card, should its drops still appear in item sources? (probably no — you can't "unlock" that source)
6. **PR vs standalone**: confirm PR to OSRS TCG is the right approach, or build as separate plugin first

---

## Effort Estimate

| Task | Effort |
|------|--------|
| Data pipeline script | 1-2 sessions |
| `CardSourcePanel.java` (Swing UI) | 1 session |
| `CardSourceCatalog.java` (data loading) | < 1 session |
| Album window integration | 1 session |
| Data validation + edge cases | 1 session |
| PR + review cycle with Az | async |

Total: ~4-5 sessions of focused work before PR-ready state.
