# Project Log

---

## 2026-07-19 — Session 1: Initial Setup & Research

**Goal**: Orient Lottie in the OSRS TCG ecosystem and establish a usable vault structure.

### What was done

**Research**:
- Read all 3 Discord exports (Announcements, FAQ, private ticket with Az/Felmeme/Lottie)
- Found GitHub repos via API search:
  - `Azderi/osrs-tcg` — Az's core TCG plugin (Java, Gradle, 13 stars)
  - `Felmeme/bronzeman-tcg` — Felmeme's Bronzeman plugin (Java, Gradle, Plugin Hub live)
  - `Sqwiglyy/groupman-tcg` — separate competing implementation, not the one we're working with
- Fetched `OsrsTcgPlugin.java`, `CardDatabase.java`, `CardDefinition.java`, `CardNameCatalog.java`, `TcgCollectionReader.java` via WebFetch before cloning
- Discovered `plugins/bronzeman-tcg/CLAUDE.md` — Felmeme's own detailed handoff doc from prior AI sessions

**Setup**:
- Created folder structure: `discord/`, `plugins/`, `docs/`, `research/`
- Moved Discord exports into `discord/` with clean names
- Cloned both repos into `plugins/`
- Fetched and saved `research/card-catalog.json` (6,376 cards, 2.8MB)

**Documentation written**:
- `docs/data-structures.md` — Card.json schema (Monster + Resource fields), state encoding, catalog snapshot format
- `docs/osrs-tcg-architecture.md` — Package structure, credit system, inter-plugin API, state persistence, debug commands
- `docs/bronzeman-architecture.md` — Class structure, OSRS TCG data reading (2 methods), enforcement flow, catalog system, all config sections, operational notes
- `docs/opportunities.md` — 7 contribution ideas ranked by effort/dependency

### Key findings

1. **Cards have no numeric IDs** — name is the sole key. This is the root of the name-matching complexity in Bronzeman.

2. **Two inter-plugin communication paths**: 
   - PluginMessage API (instant, event-driven) — built in both plugins, awaiting upstream release
   - Config decode fallback (TcgCollectionReader, 5s cache) — always available

3. **Bronzeman is further along than expected** — full skill suite implemented (cooking, smithing, crafting, herblore, fletching, hunting, farming, thieving, runecrafting, sailing, mining, woodcutting, fishing). Already on Plugin Hub with real users.

4. **Felmeme's CLAUDE.md is the ground truth** for Bronzeman's current state. Read it before making any changes to that plugin.

5. **Next agreed feature in Bronzeman**: card browser panel (grouped card view by skill/type). Design is Felmeme/owner's call.

6. **Wiki integration**: both devs have been in touch with wiki team. Scraping rules — plain page URLs, 1 req/sec, cache everything, never api.php at runtime.

### Context used this session
~45% (estimated)

---

## 2026-08-31 — Session 3: v1.0 State Format + Preview Tool Optimisations

**Goal**: Support RLTCG_v3 (v1.0 state format), add account discovery dropdown, and fix canGetItem() categorisation gaps.

### What was done

**decode_collection.py — RLTCG_v3 support**:
- v1.0 of osrs-tcg removed the XOR obfuscation step from state encoding
- Added `RLTCG_v3` decode path: `Base64 → gzip.decompress → JSON` (no XOR)
- Both `RLTCG_v2` (pre-v1.0) and `RLTCG_v3` (v1.0+) now supported via `KNOWN_PREFIXES`
- `find_best_backup()` and `find_state_blobs_from_profiles()` scan for either prefix

**server.py — `/api/accounts/list` endpoint**:
- Added `_api_accounts_list()` handler: runs decode_collection.py as subprocess, reads resulting `all_collections.json`, returns sorted account list with name/cardCount/credits/updatedAt

**preview.html — Account discovery dropdown**:
- Replaced RSN text `<input>` with `<select>` dropdown
- `populateAccountDropdown(accounts)` populates from accounts list with `name (N,NNN)` labels
- `onAccountChange(rsn)` switches collection + hiscores levels + quest completions together when dropdown changes
- Startup: populates dropdown from static `all_collections.json` (already loaded), auto-selects top account
- `refreshAll()` re-fetches `/api/accounts/list` after collection refresh to update card counts in dropdown

**preview.html — canGetItem() fixes**:
- **Shop currency fix**: 285 items had `shopBought=true` but only special-currency shops (NMZ points, Marks of Grace, Tokkul etc.). Old code assumed Coins. Fixed: check actual `shop.currency` field; free with Coins only if a coins-shop exists; special currencies treated as owned if the player has the currency card.
- **Tanning map**: Added `TANNING_MAP` for 7 leather items. Hides → leathers via tanner NPC requires only Coins + hide card (no skill). Previously these were always locked unless the player had the leather card.
- **Karambwanji alias**: `resolveToolParts()` now replaces `bait` with `Karambwanji` for Karambwan vessel tools (Karambwanji is a specific fish bait).
- **Silver sickle (b) alias**: `TOOL_PART_ALIASES` maps `silver sickle (b)` → `Silver sickle` (the card name).
- **Clue scroll rewards**: 405 items only obtainable from clue scrolls were permanently locked. Added: if `src.clueTiers.length > 0`, item is obtainable (any player can do clue scrolls).
- **Production tool cards**: `canGetItem()`'s production branch now checks tool cards (Hammer → 209 smithing items, Knife → 54 fletching, Chisel → 48 crafting, Needle → 52 crafting). Uses `getImplicitTools()` which merges wiki-scraped tools with hard-coded skill defaults.
- **Skilling tab non-card tool lock fix**: Tool strings that contain no TCG-card parts no longer show a lock; they show the tool name as a plain note.

**quest_cards.json — Client of Kourend feather fix**:
- bronzeman-tcg v0.3.0 changed quest_cards.json schema: `cardGroups`/`groupLabels` → `sections`/`requirements`/`cards`; file also moved from `src/main/resources/` to `src/main/resources/quest/`
- The stash from the previous session was invalid due to these breaking changes; dropped it and re-applied the fix directly in the new schema format
- Client of Kourend now correctly lists all 7 feather types as an ANY requirement

### Impact summary
- v3 decode: unlocks all accounts that installed osrs-tcg v1.0+
- Account dropdown: no more manual RSN typing; switching account also refreshes levels and quests
- canGetItem fixes: ~1,000+ items more accurately categorised (unlocked vs locked)

### Context used this session
~85% (two sessions, ran out of context partway through)

---

## 2026-09-01 — Session 4: Quest Cards v1.0 Rework + Pipeline Migration

**Goal**: Rework all quest card requirements to use v1.0 card names; update the generate pipeline to use the v1.0 catalog.

### What was done

**bronzeman-tcg quest_cards.json — v1.0 rework**:
- Saved v1.0 live catalog from `~/.runelite/OSRS-TCG/catalog/cards.live.json` → `research/card-catalog-v1.json` (5200 cards: 3809 items + 1391 NPCs)
- Kept beta catalog as `research/card-catalog.json` for reference
- Validated all 221 quests in quest_cards.json against v1.0 catalog
- Applied 55 distinct renames (142 refs) and 27 distinct removals (33 refs):
  - Cat variants → `Pet cat`; Infernal tools → Dragon base; Machete variants → `Machete`
  - Armoured zombie variants → `Armoured zombie`; Wardens → `The Wardens`
  - Potion names → herb names (e.g., Attack potion → Guam leaf)
  - Removed: Tattered pages, Uncharged cell, Cadava berries, colored feathers/logs, Burnt meat, etc.
- Added Ghostspeak amulet to The Restless Ghost
- Added 10 Recipe for Disaster sub-quests, Vale Totems, Learning the Ropes
- Fixed Romeo & Juliet (empty section after Cadava berries removal)
- Fixed Into the Tombs (duplicate Wardens entries merged)
- Synced `scripts/output/bm_quest_cards.json` ← plugin quest_cards.json (203 → 221 quests)

**Generate pipeline — v1.0 migration**:
- `generate_sources.py`: `load_cards()` now normalises v1.0 `{items, npcs}` format to flat list
  - Carries `equipmentSlot`, `itemIds`, `wikiPage` fields from v1.0 structure
  - Added `card_wiki_page()` helper: prefers explicit `wiki.page` field over inferred slug
  - Updated all 3 wiki fetch call sites to use `card_wiki_page(card)`
- `generate_equipment.py`: updated CARD_JSON path + added `_load_equip_cards()` normaliser
- `generate_food.py`: updated CARD_JSON path + added inline v1.0 normalisation
- `server.py`: updated `--card-json` arg to pass `card-catalog-v1.json`
- Ran full pipeline regeneration using 6815 cached wiki HTML pages:
  - `monster_drops.json`: 1391 entries, 15,250 drop rows, 779 monsters with TCG drops
  - `item_sources.json`: 3809 entries (1191 production, 1109 shops, 243 spawns, 709 clue rewards)

### Context used this session
~35%

---

## 2026-09-30 — Session 5: Tag Reordering, Quest NPCs, UI Polish

**Goal**: Improve card category ordering, tag quest NPCs, add UI quality-of-life fixes.

### What was done

**`scripts/reorder_categories.py`** (new script):
- Applies tag priority rules in a single pass over `card_categories.json`
- Rules: ores → Smithing first, remove Magic; logs → Firemaking > Fletching > Construction > Woodcutting > Sailing, remove Prayer/Smithing/Magic/Crafting; seeds → Farming first; herbs (Farming+Herblore) → Herblore first; potions → Herblore first; bones/ashes → Prayer first; planks/nails → Construction first; bars → Gold/Silver → Crafting, Lead/Cupronickel → Sailing, others → Smithing; raw food → Cooking first; pickaxes → Mining > Tool, Melee/Weapon last; WC axes → remove Smithing, Woodcutting > Tool, Melee/Weapon last; bows/crossbows → remove Construction, Ranged > Fletching, Weapon last; specific overrides for Fishing bait, Rope, Clay, Tinderbox, Soda ash, Bucket of sand
- Clay needed Crafting tag injected (source data was missing it)
- 698 items reordered out of 5,198

**`card_categories.json`** — Quest NPC tagging:
- 336 cards given `Quest` as primary tag
- Includes: quest givers (Bob, Wizard Mizgog), type=npc quest interactions, quest-specific bosses with no meaningful drops (Elvarg, Agrith Naar, Barrelchest Anchor, etc.)
- Generic mobs used in quests (Skeleton in The Restless Ghost) intentionally excluded

**`bm_quest_cards.json`** — Dwarf Cannon fix:
- Added Ammo mould as an item requirement (handed to player mid-quest then confiscated)

**`preview.html`** — Multiple UI improvements:
- **Wishlist quest click-through**: quest names in the wishlist panel are now clickable links to the quest detail page
- **Self-referential production fix**: items whose only production recipe lists themselves as an ingredient (e.g. Black dagger → poisoning recipe stored incorrectly) no longer show a broken production panel or "crafting null 0" stat block
- **`canGet` self-reference fix**: null-skill assembly recipes (Godsword, planks) still count as obtainable after the self-reference guard was corrected
- **Pack Acquisition click-through**: pack names in a card's "Pack Acquisition" section now navigate to the pack detail page
- **Toast notifications**: amber/red warning toast appears at bottom-centre when collection refresh returns 0 cards, a 401 auth error, or a logged decode error

### Context used this session
~65%

---

## 2026-09-30 — Session 6: Navigation Safety Rewrite + Tidy-up

**Goal**: Complete comprehensive navigation safety rewrite; tidy up general functionality.

### What was done

**Navigation safety rewrite — `scripts/preview.html`**:
- Eliminated ALL remaining unsafe `onclick` patterns that embedded card/quest names as JS string literals (apostrophe-injection risk — e.g. "Farmer's hat" would break onclick)
- Removed `safeNav` lambda entirely; replaced with data-attribute pattern throughout
- Converted: skill detail training rows (gathering/production/combat/hunter/ranged-setup), slayer master row, required-for quest list, quest list items, quest detail toggle-done button, prerequisite links, NPC/enemy/item card links (both BM schema and wiki fallback sections), clue scroll reward rows, Runecrafting Abyss link, equipment tab row onclick and view-card button
- Equipment tab: removed `escapedName` variable; row onclick uses `this.dataset.nav`; `setEquipped` uses `decodeURIComponent(this.dataset.item)`
- Pack acquisition table link converted to `_navToPack(this)` + `data-pack` attribute

**HTML encoding tidy-up**:
- Applied `escHtml()` to all 20 bare `data-nav="${var}"` patterns across renderItem, renderMonster, renderCanGet, skill detail, and shop sections
- Fixes attribute corruption for the 4 cards with `&` in names: `Mushroom & onion`, `Partyhat & specs`, `Pirate hat & patch`, `Top hat & monocle`

**Error visibility**:
- Added red toast on `refreshCollection()` network failure (was only changing button text to "✗ Error")

### Summary of nav safety state after this session
All navigation onclick handlers in the file use the `data-*` attribute + `_navToCard/Quest/Pack(this)` or `this.dataset.*` pattern. Zero unsafe string-literal name embedding remains.

### Commits
- `09355cd` — Navigation safety rewrite (58+/42-)
- `2e6f550` — escHtml tidy-up + pack link (21+/21-)
- `e57f392` — Refresh error toast (1+)

### Context used this session
~40%

---

## Future Work

### Browser session fallback for cloud collection

**Problem**: When the RuneLite plugin's cloud JWT expires (e.g. during OSRS downtime), `decode_collection.py` gets a 401 from `api.osrs-tcg.net/api/v1/me/cards` and falls back to the local `tcg.save`, which may be stale or missing. However, the user's browser may still have a valid session at `osrs-tcg.net` because the browser's refresh token is bound to a separate random device key (not the RS profile key).

**How to implement**:

1. **User exports browser tokens once** — paste this into DevTools console at `osrs-tcg.net`:
   ```javascript
   JSON.stringify({
     deviceKey: localStorage.getItem('osrs-tcg.deviceKey'),
     refreshToken: localStorage.getItem('osrs-tcg.refreshToken'),
     accountId: localStorage.getItem('osrs-tcg.accountId'),
     displayName: localStorage.getItem('osrs-tcg.displayName')
   })
   ```
   Save the output to `~/.runelite/OSRS-TCG/browser-session.json`.

2. **`decode_collection.py` — `_fetch_cloud_cards()` fallback**:
   - After a 401 on the plugin JWT, check for `browser-session.json` alongside `cloud-session.json`
   - Read `deviceKey` and `refreshToken` from it
   - POST to `https://api.osrs-tcg.net/api/v1/auth/refresh` with `{refreshToken, profileKeyHash: SHA256(deviceKey)}`
   - On success, extract the new `accessToken` and retry `GET /api/v1/me/cards`
   - Optionally write the new `accessToken` back to `browser-session.json` for efficiency

3. **Token refresh endpoint** (confirmed from JS bundle analysis):
   - `POST https://api.osrs-tcg.net/api/v1/auth/refresh`
   - Body: `{"refreshToken": "...", "profileKeyHash": "<64-char SHA-256 hex>"}`
   - `profileKeyHash` = `SHA-256(deviceKey)` where `deviceKey` is the 64-char hex string from localStorage
   - Returns new `accessToken` on success

4. **`server.py`** — surface the fallback status in the API response so the toast can distinguish "used browser session fallback" from a real failure.

**Why the plugin token expires but the browser one doesn't**: The plugin's refresh token is bound to the RS profile key (derived from RuneLite's `ConfigManager.getRSProfileKey()`). When the game is unreachable or the profile rotates, the plugin can't refresh. The browser token uses a stable random key stored in localStorage, so it survives game downtime.
