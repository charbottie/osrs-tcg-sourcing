# 01 — Card Browser Panel (Bronzeman)

**Status**: Next agreed feature on Bronzeman roadmap. Owner spec in progress.  
**Repo**: `Felmeme/bronzeman-tcg`  
**Effort**: Medium (~2 sessions)  
**Dependencies**: None — self-contained in Bronzeman  

---

## Problem

The Bronzeman side panel (`BronzemanTcgPanel.java`) currently has search / nearby / progress views. There's no way to browse what cards exist, grouped by how you'd get them (skill, region, boss). Players navigating "what do I need to unlock next?" have no in-plugin discovery path.

---

## What We're Building

A browseable catalogue of all TCG cards, grouped by skill or content type, filterable, with ownership indicators. Players can see at a glance which cards in a category they've collected.

Example groupings:
- **Woodcutting**: all log cards (Normal logs, Oak logs, Willow logs, …)
- **Mining**: all ore/bar cards
- **Slayer**: cards by slayer master (Turael's creatures, Konar's creatures, …)
- **Bosses**: by region or tier (Wilderness bosses, God Wars, …)
- **Quests**: cards that require quest completion
- **Fishing**: all raw fish cards

Each card shown as a compact row: `[icon] Name | Category | ✓/✗`

---

## Data Available

### From Card.json (already in JAR)
- `name` — card name
- `category[]` — first tag = type (Monster/Resource), subsequent tags = geography/type (Morytania, Weapon, etc.)
- `equipmentSlot` — for equipment cards
- `questItem` — boolean flag

### From Bronzeman's existing catalogs
- `TrackedMonsterCatalog` — all monster cards by NPC name
- `TrackedItemCatalog` — all item cards
- `ResourceNodeCatalog` — which skill produces which item (already maps logs→woodcutting, ores→mining, fish→fishing, etc.)
- `QuestCatalog` — which items are quest-gated

The skill grouping taxonomy can be largely inferred from `ResourceNodeCatalog` — it already maps items to skills. This is the key reuse opportunity.

---

## Taxonomy Design

Rather than hand-curating every group, derive taxonomy from existing data:

```
Card.json category[0] = "Monster" → group under "NPCs & Bosses"
  sub-group by geography tag (Wilderness, Kourend, …)

Card.json category[0] = "Resource" → group by skill:
  ResourceNodeCatalog "kind" = "tree"         → Woodcutting
  ResourceNodeCatalog "kind" = "rock"         → Mining
  ResourceNodeCatalog "kind" = "fishing-spot" → Fishing
  category[] contains "Consumable"            → Herblore / Farming
  equipmentSlot is set                        → Equipment (sub by slot)
  questItem = true                            → Quests
  everything else                             → General / Other
```

**Owner decision required**: the grouping taxonomy is explicitly the owner's design call (per Bronzeman CLAUDE.md). Present options, don't implement a taxonomy without approval.

---

## New Classes

### `CardBrowserPanel.java`
Replaces or extends `BronzemanTcgPanel.java`. New tab: "Browse".

Layout:
```
[Browse] [Nearby] [Progress]          ← tab bar
─────────────────────────────────────
Group: [Woodcutting ▼]               ← dropdown or collapsible list
─────────────────────────────────────
Search: [_______________]
─────────────────────────────────────
□ Oak logs          Resource  ✓
□ Willow logs       Resource  ✗
□ Teak logs         Resource  ✗
□ Mahogany logs     Resource  ✗
…
─────────────────────────────────────
Owned: 12 / 24 in this group
```

Cards clickable → shows name + examine text in a tooltip or mini detail pane at bottom.

### `CardTaxonomy.java`
Builds the group → card mapping at plugin startup by cross-referencing:
- `ResourceNodeCatalog.getEntityToCards()` keyed by `kind`
- `TrackedMonsterCatalog.getEntityToCards()` for NPCs
- Card.json category tags as fallback

Returns `Map<String, List<String>>` — group name → list of card names in that group.

### `CardGroupEntry.java`
Simple POJO: `{String cardName, boolean owned, String rarity}` — one row in the browser.

---

## Integration Points

- `BronzemanTcgPlugin.java` — inject `CardTaxonomy` and pass to panel
- `TcgCollectionReader.java` — already provides owned set; subscribe to changes to keep browser live
- `BronzemanTcgPanel.java` — add "Browse" tab (use `JTabbedPane` or custom tab bar)

No new config items needed (browser is always available, no restrictions involved).

---

## UI Constraints (RuneLite panel)

Bronzeman's side panel is a standard RuneLite `PluginPanel` (200px wide, variable height, scrollable). Key constraints:
- No floating windows — everything in the fixed-width panel
- Use `RuneLite`'s `ColorScheme` and `FontManager` for styling consistency
- Keep rows compact: icon (16×16 from imageCacheService or a sprite), name, ✓/✗ mark

---

## Phased Delivery

**Phase 1 — Flat list with search** (1 session)
- Render all cards as a scrollable list, sorted A-Z
- Filter by owned/not owned
- No grouping yet
- Gets the browser into the panel quickly for feedback

**Phase 2 — Grouped taxonomy** (1 session, after owner approves taxonomy)
- Group dropdown / collapsible sections
- Per-group progress count ("12 / 24")
- Owner review + iterate

---

## Open Questions

1. Should the browser show ALL 6,376 cards or just the ones Bronzeman tracks (1,227 monsters + 5,149 items)?
2. Taxonomy grouping: dropdown (one group at a time) or collapsible accordion (all groups visible)?
3. What happens when you click a card in the browser? Tooltip only? Mini detail at bottom? Or nothing (browse-only)?
4. Should untracked cards (those with no Bronzeman restriction) appear? With a visual distinction?

---

## Reuse Opportunities

- `ResourceNodeCatalog.getEntityToCards()` — already maps entity name → card names by kind; invert to get skill → cards
- `TcgCollectionReader` — ownership check, live updates via 5-second cache
- `SharedCardRenderer` (from OSRS TCG) — card image rendering, but not accessible cross-plugin; use a simple icon from imageCacheService instead
- Wiki image URLs from Card.json — can render small thumbnails (same pattern as OSRS TCG's `WikiImageCacheService`)
