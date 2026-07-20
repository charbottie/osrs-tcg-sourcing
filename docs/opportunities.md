# Contribution Opportunities

Based on the current state of both plugins and the ticket conversation between Lottie, Az, and Felmeme.

---

## 1. Card Browser (High Priority — On Roadmap, Owner Spec in Progress)

**What**: A grouped view of available cards in the Bronzeman side panel, so players can discover what they need to unlock. Currently the panel has search/nearby/progress but no browseable catalogue.

**Lottie's original idea**: "click an NPC you have unlocked and it shows what weapons/items you have from that... or vice versa click a weapon and see what NPC drops it."

**Felmeme's status**: Agreed as next feature after PvM content data. "We'll work on it as we go."

**What's needed**:
- Grouping taxonomy is the owner's design call (e.g. all logs under "Logs", skill-specific views)
- Cards can be grouped by: `category[0]` (Monster vs Resource), geography tags, equipment slot, or skill association
- The side panel (`BronzemanTcgPanel.java`) already exists — needs a new tab/view
- Card display can reuse wiki `imageUrl` from Card.json
- Cross-reference: `ResourceNodeCatalog` already has "this node drops this card" relationships — could be used to build reverse lookups

**Technical approach**:
- Build a reverse index at startup: `cardName → Set<ResourceNode>` (where can you get this card)
- Build another: `npcName → Set<Resource cards>` via the combination of TrackedMonsterCatalog + Card.json categories
- Render as a filtered, scrollable panel grouped by category

---

## 2. ID-Based Lookup (Medium Priority — Requires Upstream Co-op)

**What**: Az's Card.json currently has no numeric IDs for cards. Everything is name-based. This means:
- Bronzeman's catalog must be manually regenerated each time Card.json changes
- NPC matching can fail if names drift between the wiki, the card, and the game client
- Item matching is brittle for items with multiple ID variants (e.g. degraded equipment)

**From the ticket**: Az said "my card list doesn't have IDs for NPCs and items or anything for that matter" but is "happy to add anything that's necessary for the gamemode."

**What it would take**:
- Az adds `npcId` (or `npcIds: []`) and `itemId` (or `itemIds: []`) fields to Card.json for relevant cards
- OSRS Wiki already has NPC IDs and item IDs — the generation scripts could fetch them
- Bronzeman would then check `npc.getId()` instead of name matching, eliminating disambiguation suffix problems

**Technical approach**:
- Wiki provides IDs via infoboxes at page URLs (no api.php — use plain page URL + parse HTML)
- `scripts/generate_tracked_monsters.py` extended to also write IDs alongside names
- RuneLite's `NPC.getId()` gives the NPC ID directly at interaction time
- Item IDs available via `ItemManager.getItemComposition(itemId)`

**Risk**: Az is busy with the base TCG vision; this is a low-friction ask if the generation script does the heavy lifting and he just needs to approve adding the field.

---

## 3. Auto-Regenerate Catalogs on Card.json Changes (Medium Priority)

**What**: Currently the snapshot JSONs (`tracked_monster_names.json`, `tracked_item_names.json`) must be manually regenerated via `generate_tracked_monsters.py` whenever Az ships a Card.json update. This is a maintenance burden and creates drift.

**Options**:
- **GitHub Action**: trigger on Card.json change detection (poll `osrs-tcg.xyz/catalog/Card.json`), run the script, open a PR against `Felmeme/bronzeman-tcg`
- **Wiki as source of truth**: instead of depending on Az's Card.json, pull NPC/item lists directly from the OSRS Wiki (rate-limit: 1 req/sec, plain page URLs, cache everything — per wiki staff guidance)
- **Felmeme's generation script already exists**: just needs CI wiring

**Wiki API notes** (from Bronzeman CLAUDE.md):
- Use plain page URLs (not `api.php?action=parse`) — hits edge cache
- Descriptive `User-Agent` naming this project
- Pace at ~1 req/sec
- Cache every fetch in the repo so re-runs hit the wiki zero times
- Plugin makes NO wiki requests at runtime — only dev-time data generation

---

## 4. Click-NPC → Show Cards Overlay (Medium Priority — Needs Design)

**What**: Right-clicking (or hovering) an NPC shows what cards you have that relate to it — drops, the monster card itself, any resource cards from the area.

**Technical feasibility**:
- RuneLite's `MenuOptionClicked` or `MenuOpened` events can detect right-click on NPC
- `NpcOverlay` can draw tooltips/popups near an NPC
- Would need: `npcName → [associated cards]` reverse map (monster card + any loot/drop associations)
- The loot associations don't currently exist in the data — would need wiki integration to get NPC loot tables

**Simpler version**: overlay shows just the monster card status (owned/not owned) on hover — no loot association. Achievable now with current data.

---

## 5. Wiki Integration for Loot Tables (Longer Term)

**From the ticket**: Lottie suggested connecting to OSRS Wiki for richer data. Felmeme said manual searching is the current gap.

**What wiki data could provide**:
- NPC loot tables: `NPC X → drops [Item A, Item B, ...]` 
- Using this, the "click NPC to see what items you've unlocked from it" feature becomes possible
- The OSRS Wiki has a public API and the wiki team is already in touch with both Az and Felmeme

**Constraints**:
- All wiki data fetching must be at dev-time (never at runtime inside the plugin)
- Generate static JSON resources, bundle them in the JAR
- Respect wiki rate limits and caching guidance above

**Data quality note from Felmeme**: "they told me off for scraping the wiki too much" (resolved: "do it this way instead" — plain URLs, cached)

---

## 6. Fix: Encoded Name Defect in Snapshot Generator

**What**: 4 tracked names contain U+FFFD replacement characters from an encoding bug in `generate_tracked_monsters.py`. Examples: rosé wines, "grubs à la mode" (items with non-ASCII characters).

**Fix**: Fix encoding handling in the generator script, regenerate both snapshots. Quick win, self-contained.

---

## Summary Table

| Opportunity | Effort | Dependency | Status |
|-------------|--------|-----------|--------|
| Card browser panel | Medium | None | Next on roadmap |
| Click-NPC → status overlay (simple) | Small | None | Could do now |
| ID-based lookup | Medium | Az adds IDs to Card.json | Needs Az buy-in |
| Auto-regenerate catalogs (CI) | Small | None | Quick win |
| Wiki loot table integration | Large | Wiki scraping pipeline | Longer term |
| Click-NPC → loot cards overlay | Medium | Wiki loot tables first | Dependent |
| Fix encoded name defect | Small | None | Quick win |
