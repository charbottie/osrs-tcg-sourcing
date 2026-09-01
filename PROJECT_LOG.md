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
