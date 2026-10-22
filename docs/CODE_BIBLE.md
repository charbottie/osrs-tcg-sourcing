# Bronzeman Planner: Code Bible

A complete map of the code in this repo, so it can be looked after without help. Written 22 Oct 2026.

**How to read this.** The first part is plain English: what the planner is, how to start it, and the words used in the rest of the document. After that comes the detailed reference, which is more technical: every file, every server endpoint, every function in the page and in the Python scripts. Each entry starts with a plain sentence saying what it's for.

**Line numbers** are given as "approx. line" (or "approx. L123"). They were right when this was written, but they move whenever code is added above them. To find something, search the file for its name (in most editors: Cmd+F).

**Not covered:** `plugins/` (copies of other people's RuneLite plugins, kept only for reference) and `scripts/cache/` (downloaded wiki pages and images; not in git and safe to delete, they are fetched again when needed).

---

## Part 1. The planner in plain words

### What this is

The Bronzeman Planner is a web page that runs on your own computer. It reads which OSRS TCG cards an account owns (from RuneLite's save files) and shows what that account can do under Bronzeman TCG rules: which quests are ready, which training methods are open, which monsters, bosses, diaries and clue steps are possible, and which missing cards would unlock the most.

It has three parts:

1. **The page** (`scripts/preview.html`). Everything you see and click. It is a single file with no build step.
2. **The local server** (`scripts/server.py`). A small program that hands the page its files and does the jobs a web page can't do by itself: reading your RuneLite collection, looking up hiscores, and fetching card pictures.
3. **The data** (`scripts/output/*.json` and a few `.json` files in `scripts/`). Game facts (drops, quests, recipes, diaries...) prepared in advance from the OSRS Wiki by the update scripts (`scripts/generate_*.py`). You only need to re-run those when the game or the card list changes.

### How to start the planner

1. Open **Terminal**: press **Cmd+Space**, type `Terminal`, press **Enter**.
2. Paste this line and press **Enter**:

   ```
   cd ~/git/osrs_tcg && python3 scripts/server.py
   ```

3. You should see `OSRS TCG preview server → http://localhost:8765/preview.html`. **Leave this Terminal window open** while you use the planner. Closing it stops the planner.
4. Open your web browser and go to **http://localhost:8765/preview.html**
5. Pick your account in the dropdown at the top and click **↻ Refresh** to load your latest cards.

**To stop it:** click the Terminal window and press **Ctrl+C**.

**If it says "Address already in use":** the planner is already running (perhaps in another Terminal window). Just open http://localhost:8765/preview.html in the browser. If you really want to restart it, find the other window and press Ctrl+C there first.

**If the page is blank or shows old data:** reload the browser page (Cmd+R). The server tells the browser not to keep old copies, so a reload always picks up the newest files.

**Without the server:** the page does not work. Opened straight from Finder, the browser refuses to let it load its data files, and it only shows "⚠ Needs a local server" with the start command. Always start server.py first.

### Glossary

| Word | Meaning here |
|---|---|
| **Terminal** | The Mac app where you type commands (Cmd+Space → "Terminal"). Every "How to run" line in this document is typed there, from the `~/git/osrs_tcg` folder. |
| **Server** | `scripts/server.py`. A small program on your own computer that the browser talks to at `http://localhost:8765`. Nothing is put on the internet. |
| **Generator / update script** | A `scripts/generate_*.py` file. It reads the OSRS Wiki (and the card list) and writes a data file. Run one only when the game or the card catalog changed. |
| **JSON data file** | A `.json` file: plain text holding structured data (lists and "name: value" pairs). The page loads these. `scripts/output/*.json` are mostly written by generators; the `*_curated.json` / `*_overrides.json` files in `scripts/` are edited by hand. |
| **Hand-curated** | Written or corrected by a person (or a Claude agent) rather than by a script. Generators read these files; they never overwrite them. |
| **Hand fixes** | Corrections made directly in a committed output file. Re-running the generator would undo them, so always write to a scratch folder and compare first (see Part 7). |
| **Cache** | Saved copies of things already downloaded (`scripts/cache/`), so re-running a script doesn't download the wiki again. Safe to delete; it just makes the next run slower. |
| **Wiki** | The OSRS Wiki (oldschool.runescape.wiki), the source of almost all game facts here. It has strict rules about scripted access (Part 7). |
| **Catalog** | The full list of TCG cards, copied from the OSRS TCG plugin into `research/card-catalog-live.json` (5,172 cards: 1,400 NPC + 3,772 item). Every generator and the server read it. |
| **Card** | A TCG card. Bronzeman rules say you can only use an item, or interact with an NPC, if you own its card. |
| **Version / variant** | An in-game item covered by a card (e.g. "Prayer potion(3)" counts as the "Prayer potion" card). Listed in the catalog's `tcg.variants`. |
| **Access route** | A named way into an area (e.g. `morytania`, `desert`), in `output/access_routes.json`. Met when you own every card of any one route. |
| **Gate / location requirement** | What you need to enter a place (a level, quest, item), in `scripts/location_requirements.json`. |
| **Tab** | One of the 11 views across the top of the page: Cards, Wishlist, Equipment, Skilling, Questing, Diaries, Bosses, Slayer, Clues, Packs, Rules. |
| **Endpoint** | An address on the server that does a job, like `/api/hiscores?player=NAME`. |
| **Headless check** | `scripts/dev/cdp_check.mjs`: opens the page in an invisible Chrome, runs a test and saves a screenshot. |

---

## Part 2. Overview: how the pieces fit

### Architecture

```
            OSRS Wiki  (plain page URLs ?action=raw, action=query / action=bucket;  NEVER action=parse)
                │          via scripts/wiki_api.py and scripts/wiki_fetcher.py, cached in scripts/cache/
                ▼
  research/card-catalog-live.json ──► GENERATORS  scripts/generate_*.py
  (the TCG card list)                   │   + libraries: loot_parser, quest_parser, item_scraper,
                                        │     rarity_mapper, catalog_names, location_reqs
  HAND-CURATED JSON in scripts/ ───────►│   (boss_curated, skilling_curated, slayer_curated,
  (edited by a person / agent)          │    clue_curated, item_sources_overrides,
                                        │    monster_locations_overrides, location_requirements,
                                        │    gathering_sources)
                                        ▼
                       scripts/output/*.json   (+ generated JSON kept in scripts/: clue_*.json,
                       (committed; some carry   ingredient_info.json)
                        hand fixes)
                                        │
  RuneLite on disk ──► decode_collection.py ──► output/my_collection.json, all_collections.json
  (~/.runelite/...)    decode_completed_quests.py ──► output/completed_quests.json
                                        │
                                        ▼
                       scripts/server.py  (http://localhost:8765)
                         • serves scripts/ as static files (no-cache)
                         • /api/*  collection refresh, accounts, hiscores, quests, packs, generate
                         • /images/**  card art from osrs-tcg.net   (disk cache scripts/cache/tcg_img/)
                         • /wikiimg/** wiki images → original file → RuneLite sprite (scripts/cache/wiki_img/)
                                        │
                                        ▼
                       scripts/preview.html   loadData() fetches every JSON in parallel,
                         expands requirements, runs _validateDataNames(), loads the collection,
                         then each tab's render function draws the view.
                         Browser localStorage keeps per-viewer state (wishlist, ticks, equipment).
```

### Data flow in one paragraph

Generators read the card catalog, the wiki (through the cache) and the hand-curated JSON, and write JSON into `scripts/output/` (a few into `scripts/` itself). Those files are committed to git. When you open the page, `loadData()` in preview.html fetches all of them at once, then asks the server for your collection (`/api/accounts/list`, `/api/collection/refresh`), your levels (`/api/hiscores`) and quests (`/api/quests/completed`). Every tab then works things out in the browser: `isOwned()` says whether you own a card, `canGetItem()` whether you can obtain an item, `_reqMet()` whether a requirement row is met, `_accessMet()` whether you can reach an area, and `_locGate()` what a place needs.

### Regeneration order

Only needed when the game or the card catalog changed. Every command is run from `~/git/osrs_tcg`. **Write to a scratch folder and diff before replacing committed outputs** (Part 7): pass `--out-dir` where the script supports it, otherwise copy the committed file aside first and compare with `git diff` afterwards.

| Step | Command | Writes |
|---|---|---|
| 1 | `python3 scripts/generate_card_aliases.py --card-json research/card-catalog-live.json` | output/card_aliases.json |
| 2 | `python3 scripts/generate_sources.py --card-json research/card-catalog-live.json --out-dir <scratch>` (~25 min) | monster_drops, item_sources, card_categories, card_details (+ quest_chains) |
| 3 | `python3 scripts/reorder_categories.py` (on the adopted card_categories.json) | output/card_categories.json |
| 4 | `python3 scripts/generate_quests.py` | output/quests.json |
| 5 | `python3 scripts/generate_spells.py` | output/spells.json, output/rune_sources.json |
| 6 | `python3 scripts/generate_diaries.py --card-json research/card-catalog-live.json --out-dir <scratch>` (uses spells + item_sources) | output/diaries.json |
| 7 | `python3 scripts/generate_card_versions.py --card-json research/card-catalog-live.json` | output/card_versions.json |
| 8 | `python3 scripts/generate_bosses.py --card-json research/card-catalog-live.json` | output/bosses.json |
| 9 | `python3 scripts/generate_boss_loot.py --card-json research/card-catalog-live.json --out-dir <scratch>` (after 2 and 8) | boss_loot.json, collection_log.json |
| 10 | `python3 scripts/generate_monster_locations.py --card-json research/card-catalog-live.json` | output/monster_locations.json |
| 11 | `python3 scripts/generate_slayer.py --card-json research/card-catalog-live.json` (reads monster_locations for "(nearby)" renames) | output/slayer.json |
| 12 | `python3 scripts/generate_ingredient_info.py` | scripts/ingredient_info.json |
| 13 | `python3 scripts/generate_shop_owners.py --card-json research/card-catalog-live.json` | output/shop_owners.json |
| 14 | `python3 scripts/generate_recipes.py` | output/recipes.json |
| 15 | `python3 scripts/generate_skilling.py --card-json research/card-catalog-live.json` | output/skilling.json |
| 16 | `python3 scripts/generate_clue_sources.py [--refresh]` (after card_versions) | scripts/clue_scroll_sources.json, clue_sources.json, clue_reward_rarities.json |
| 17 | `python3 scripts/generate_clue_steps.py [--force-refresh]` | output/clue_steps.json |
| 18 | `python3 scripts/generate_equipment.py`, `python3 scripts/generate_food.py` | equipment_data.json, food_data.json |
| 19 | `python3 scripts/generate_icons.py` (always last) | output/method_icons.json |
| check | `python3 scripts/location_reqs.py`; `python3 scripts/scan_location_requirements.py` | (reports only) |

Why this order: diaries need spells and item_sources; boss loot needs monster_drops and bosses; monster locations need slayer_curated and location_requirements, and slayer then reads monster_locations; shop owners need monster_locations; recipes need item_sources, ingredient_info and quests; skilling needs diaries and access routes; clue steps need diaries, quests, aliases and monster_drops; icons need recipes, skilling and spells. CLAUDE.md gives the short form: recipes → skilling_curated → skilling → shop owners → icons last.

After regenerating, start the server, open the page and check the browser console (Cmd+Option+J in Chrome) has no `[data check]` warnings, or use the headless check (`scripts/dev/cdp_check.mjs`).

---

## Part 3. Every file under scripts/

Each entry: what it's for in plain words, then inputs, outputs, how to run, and what depends on it. Python files list their functions in Part 6; preview.html is broken down in Part 5; server.py in Part 4.

### 3.1 The page, the server, tools and assets

#### scripts/preview.html
- **What it's for (plain English):** the planner itself, the web page you use. One file holding the layout (HTML), the look (CSS) and all the logic (JavaScript, from approx. line 913).
- **Inputs:** every JSON file listed in 3.2 and 3.3 (fetched by `loadData()`), the server's `/api/*` endpoints, `/images/**` and `/wikiimg/**` pictures, local icons in `assets/icons/`, and browser localStorage.
- **Outputs:** nothing on disk. It keeps per-viewer state in browser localStorage: `tcg_wishlist` (wishlist v2), per-account quest completions / manual ticks / started quests (keys from `_cqFileKey`, `_cqManualKey`, `_cqStartedKey`), `completed_quests`, `tcg_slayer_unlocks`, diary task ticks (`_diaryTickKey`), `dps_settings`, `equip_*` (equipped items per style and slot, sort, active style).
- **How to run:** start server.py, then open http://localhost:8765/preview.html (Part 1).
- **Depended on by:** nothing; it is the end of the pipeline. `scripts/dev/cdp_check.mjs` tests it.

#### scripts/server.py
- **What it's for (plain English):** the small local program that serves the page and does the jobs the page can't (read RuneLite saves, hiscores, pictures). Full details in Part 4.
- **Inputs:** files in `scripts/`; `~/.runelite/OSRS-TCG/profiles|backups`, `~/.runelite/profiles2/*.properties`, `~/.runelite/screenshots/<player>/Quests/`; network: osrs-tcg.net (packs, card art, cloud revision), OSRS hiscores, the wiki (images), static.runelite.net (sprites).
- **Outputs:** runs `decode_collection.py` (→ `output/my_collection.json`, `output/all_collections.json`); `output/generate.log`; image caches `scripts/cache/wiki_img/`, `scripts/cache/tcg_img/`; `scripts/cache/runelite_item_names.json`.
- **How to run:** `python3 scripts/server.py [--port 8765]` (`--port` default 8765). Stop with Ctrl+C.
- **Depended on by:** preview.html (all `/api`, `/images`, `/wikiimg` calls); `cdp_check.mjs` needs it running.

#### scripts/requirements.txt
- **What it's for (plain English):** the two extra Python packages the scripts need.
- **Contents:** `requests>=2.28`, `beautifulsoup4>=4.11`. Install with `pip3 install -r scripts/requirements.txt`. Used by `wiki_fetcher.py` (requests) and the HTML parsers (BeautifulSoup).

#### scripts/dev/cdp_check.mjs
- **What it's for (plain English):** an automatic "open the page and look" test. It opens the planner in an invisible Chrome, runs a bit of JavaScript you give it, prints the console messages, and saves a screenshot.
- **Inputs:** a URL, an output PNG path, a JS snippet (may `await`; its return value is printed as `[result]`), optional wait in ms (default 2500). Needs Google Chrome at `/Applications/Google Chrome.app` and Node 22+ (no npm packages).
- **How to run:** `node scripts/dev/cdp_check.mjs http://localhost:8765/preview.html out.png '<js returning a value>' [waitMs]` (the server must be running).
- **Depended on by:** nothing; a developer tool. Use it to confirm there are no `[data check]` warnings or console errors after a change.

#### scripts/assets/icons/ (31 PNG files, as a group)
- **What it's for (plain English):** small pictures that must always show, stored locally so they never depend on the wiki.
- **Contents:** 24 skill icons (`<Skill>_icon.png`, Agility ... Woodcutting incl. Sailing and Runecraft), `Quest_point_icon.png`, and 6 clue scroll icons `Clue_scroll_(beginner|easy|medium|hard|elite|master).png`. Sourced from RuneLite's skill icons and static.runelite.net item icons (21 Oct 2026, after the wiki's bot check started blocking images).
- **Depended on by:** preview.html: `skillIcon()` (skill icons), `questIcon()` (quest point icon), the clue scroll views and clue list.

#### scripts/output/.gitkeep
- **What it's for (plain English):** an empty placeholder so git keeps the `output/` folder. No content.

#### scripts/cache/ (not documented in detail)
- Downloaded wiki HTML (`wiki_html/`), wikitext (`wikitext/`), Bucket/API caches (`*.json`), image caches (`wiki_img/`, `tcg_img/`), validation reports (`boss_validation.json`, `slayer_validation.json`). Gitignored, ~800 MB. Deleting a file makes the next run refetch it (politely, ~1 request per second).

### 3.2 Hand-curated JSON in scripts/ (edited by a person or agent)

These are the files to edit when data is wrong. Generators read them and never overwrite them, except the four generated files flagged below.

#### scripts/boss_curated.json
- **What it's for (plain English):** the boss facts the wiki tables don't give: which encounter each wiki boss row belongs to, monsters you must kill, entry items, tools, area access, notes, list category.
- **Edited by:** hand / agents. Format: `{_comment, encounters: [...]}` in the shared requirement model (cards = any one, `mode:'all'`, optional, routes, access, spells, tool, group).
- **Read by:** `generate_bosses.py` (→ output/bosses.json). preview.html mentions it in comments only; the page reads bosses.json.

#### scripts/skilling_curated.json
- **What it's for (plain English):** the list of training methods for Agility, Thieving, Hunter, Prayer, Firemaking, Ranged and gathering skills, each with a short wiki quote and page.
- **Edited by:** hand / agents (720 methods). Each: `{skill, name, level, xp, type, requirements, quests, levels, access, location?, note, wiki, page, outputs?}`.
- **Read by:** `generate_skilling.py` (validates → output/skilling.json), `scan_location_requirements.py` (location names).

#### scripts/slayer_curated.json
- **What it's for (plain English):** Slayer facts the wiki doesn't give as data: master pages, cards and replacements, required equipment per task, which locations need area access.
- **Edited by:** hand / agents. Keys: `masters`, `equipment`, `locationAccess` (place → access key, `'sailing'`, `'excluded'`, or null = open), `taskOverrides`, `unlockInfo`, `_comment`.
- **Read by:** `generate_slayer.py`, `generate_monster_locations.py`, `generate_shop_owners.py` (locationAccess), `scan_location_requirements.py`.

#### scripts/clue_curated.json
- **What it's for (plain English):** corrections for the clue-step parser: NPC name fixes, things known to have no card, item name fixes, quest aliases, location rules, per-step overrides.
- **Edited by:** hand / agents (19 keys incl. `npcFixes`, `noCard`, `itemNameFixes`, `keepItems`, `questAliases`, `locationRules`, `emoteOverrides`, `sherlockOverrides`...).
- **Read by:** `generate_clue_steps.py` only.

#### scripts/item_sources_overrides.json
- **What it's for (plain English):** hand-checked fixes to "how to get this item" (gathering levels, shops, spawns, gaps) layered on top of generate_sources.py output.
- **Edited by:** hand / agents (~529 items). Per item, a field given here replaces the generated field; `null` removes it. `_comment*` keys explain each batch of fixes.
- **Read by:** `generate_sources.py` pass 6. **Never edit item_sources.json directly; put the fix here.** preview.html only mentions it in a comment.

#### scripts/monster_locations_overrides.json
- **What it's for (plain English):** fixes to where monsters are found, for cases the wiki infobox data can't express.
- **Edited by:** hand. Per NPC card: `drop` / `add` locations with reason and wiki quote; `_locationAccess` per-place access fixes; `_packRegionNotes`; `_doc`.
- **Read by:** `generate_monster_locations.py`, `generate_shop_owners.py`.

#### scripts/location_requirements.json
- **What it's for (plain English):** the one central list of what you need to enter a place (guild levels, quests, worn items, diaries), e.g. the Farming Guild's 45/65/85 Farming tiers.
- **Edited by:** hand / agents (~111 places). `_doc` explains the gate model; `_reviewedNoGate` lists places checked and found open. Validate with `python3 scripts/location_reqs.py`.
- **Read by:** preview.html directly (`_setLocReqs` → `_locGate` / `_locReqOk`), `location_reqs.py` (used by generate_monster_locations, generate_slayer, generate_skilling, generate_clue_steps), `scan_location_requirements.py`.

#### scripts/gathering_sources.json
- **What it's for (plain English):** hand-written gathering methods (mine, chop, fish...) for ~150 item cards, with levels.
- **Edited by:** hand, checked against wiki skill pages.
- **Read by:** `generate_sources.py` pass 2 (`load_gathering`) → item_sources.json.

#### scripts/ingredient_info.json (generated)
- **What it's for (plain English):** production / shop / spawn info for recipe ingredients that have no card.
- **Written by:** `generate_ingredient_info.py` (overwritten wholesale). **Read by:** preview.html (`ingredientInfo`, ingredient pages), `generate_recipes.py`, `generate_shop_owners.py`.

#### scripts/clue_scroll_sources.json, scripts/clue_sources.json, scripts/clue_reward_rarities.json (generated)
- **What they're for (plain English):** where to get a clue scroll of each tier; which tiers' reward caskets give each card; how rare each reward is per tier.
- **Written by:** `generate_clue_sources.py` (in scripts/, not output/; re-running overwrites them, so diff first).
- **Read by:** preview.html (`clueScrollSources`, `clueRewardsByTier`, `clueRewardRarities`); `clue_sources.json` also by `generate_sources.py` pass 5 (item_sources `clueTiers`).

### 3.3 Data files in scripts/output/

"Hand fixes: yes" means the committed file has corrections a fresh run would lose: **run the generator into a scratch folder, diff, and patch only the intended changes.** Every file here is fetched by preview.html's `loadData()`.

| File | Plain-English contents | Written by | Hand fixes? | Read by in the page (variable) | Also read by |
|---|---|---|---|---|---|
| `access_routes.json` | Named ways into areas (Morytania, Desert, Kourend...) and shared requirement routes, with wiki quotes | **Hand-curated** (no generator) | n/a: edit directly | `accessRoutes` → `_accessMet`, `_routeMet` | generate_bosses, generate_skilling, generate_slayer, generate_monster_locations, generate_clue_steps, location_reqs (key validation) |
| `bm_quest_cards.json` | Card requirements per quest under Bronzeman rules (sections, routes, groups, optional rows, `consideredNoCard`) | **Hand-curated** (started from the plugin's quest_cards.json; checked against the wiki) | n/a: edit directly | `bmQuestCards` → Questing tab, `_questReqRow`, `_expandReq` | card_groups.py documents its `groups` |
| `monster_drops.json` | Each monster card's drops (card, rarity, fraction, rare-drop-table flag), Slayer and combat level | generate_sources.py (pass 1) | yes (Deadman fixes, patched tables) | `monsterDrops` → card pages, Slayer, Bosses, `canGetItem` | generate_boss_loot, generate_diaries, generate_clue_steps |
| `item_sources.json` | How to get every item card: monsters, shops, spawns, gathering, production, quests, clue tiers | generate_sources.py (passes 2-6) | yes, but fixes belong in `item_sources_overrides.json` | `itemSources` → `canGetItem`, `_itemGetNeeds`, item pages | generate_recipes, generate_ingredient_info, generate_shop_owners, generate_diaries |
| `card_categories.json` | Category tags per card (Smithing, Weapon, F2P...) | generate_sources.py, then reorder_categories.py | yes (~1,288 entries differ from a fresh run) | `cardCategories` → filters, tags | reorder_categories.py |
| `card_details.json` | Examine text, image URL/path, tier, regions per card | generate_sources.py | yes (image fixes) | `cardDetails` → `_cardImg`, card pages | generate_card_versions |
| `card_aliases.json` | Item version name → card name | generate_card_aliases.py | no | `cardAliases` → `_cardInfo` | many generators (name validation) |
| `card_versions.json` | Each card's item versions and how each is made | generate_card_versions.py | no | `cardVersions` → card page "Versions" | generate_clue_sources |
| `quests.json` | Every quest: prerequisites, skill reqs, kills, start NPC, QP, members | generate_quests.py | possibly (overwritten wholesale; diff first) | `questsData` → Questing tab | most generators (quest-name validation) |
| `diaries.json` | Achievement Diary tasks, requirements, NPCs and rewards | generate_diaries.py | **no: never hand-edit**; fix the parser or `CARD_OVERRIDES` / `REWARD_NPCS` | `DIARY_DATA` → Diaries tab, `_buildDiaryByCard` | generate_skilling, generate_clue_steps, location_reqs |
| `spells.json` | Every spell's book, level, rune cost | generate_spells.py | no | `spellsData` → spell requirements, Magic methods | generate_diaries, generate_icons |
| `rune_sources.json` | Elemental rune → staves / combination runes that supply it | generate_spells.py | no | `runeSources` | (none) |
| `bosses.json` | Every boss encounter with requirements | generate_bosses.py (+ boss_curated.json) | no: edit boss_curated.json | `BOSS_DATA` → Bosses tab | generate_boss_loot |
| `boss_loot.json` | Chest / reward-pool loot for raids, Barrows, etc. | generate_boss_loot.py | yes | `bossLoot` → boss loot tables | (none) |
| `collection_log.json` | Each boss's collection-log cards (marks uniques ◆) | generate_boss_loot.py | yes | `collectionLog` | (none) |
| `slayer.json` | Slayer masters, task lists, monsters per task, locations | generate_slayer.py (+ slayer_curated.json) | no: edit slayer_curated.json | `SLAYER` → Slayer tab | scan_location_requirements |
| `monster_locations.json` | Where each NPC card is found + access per place, `_gates` | generate_monster_locations.py (+ overrides) | no: edit the overrides file | `monsterLocations` → "Found at", reachability | generate_slayer, generate_shop_owners, scan_location_requirements |
| `shop_owners.json` | Shop → owner NPC card(s) and location | generate_shop_owners.py | no | `SHOP_OWNERS` → `_shopStatus`, `canGetItem` | scan_location_requirements |
| `recipes.json` | Every XP-giving production recipe | generate_recipes.py | no | `RECIPES` → Skilling tab | generate_icons |
| `skilling.json` | Curated training methods, validated | generate_skilling.py (from skilling_curated.json) | no: edit skilling_curated.json | `SKILLING` → Skilling tab, gathering sources | generate_icons |
| `method_icons.json` | Icon URL for each recipe / method / spell row | generate_icons.py | no | `METHOD_ICONS` | (none) |
| `clue_steps.json` | Every clue step and what it needs | generate_clue_steps.py (+ clue_curated.json) | no: edit clue_curated.json | `clueSteps` → Clues tab, item/NPC clue usage | (none) |
| `equipment_data.json` | Gear stats by slot | generate_equipment.py | no | `equipBySlot` → Equipment tab, DPS | (none) |
| `food_data.json` | HP healed per food card | generate_food.py | no | `foodData` | (none) |
| `my_collection.json` | **Your** owned cards (personal, gitignored) | decode_collection.py (via server) | n/a | `loadCollection()` → `owned` | server.py |
| `all_collections.json` | Every local account's cards, credits, timestamps (gitignored) | decode_collection.py | n/a | `allCollections` → account dropdown, `switchCollection` | server.py `/api/accounts/list` |
| `completed_quests.json` | Quests finished, from screenshots (gitignored) | decode_completed_quests.py | n/a | startup + `syncQuestsFromScreenshots` fallback | (none) |
| `generate.log` | Log of a server-triggered generate run (gitignored) | server.py `/api/generate/run` | n/a | not read by the page | server.py `/api/generate/log` |

Not present: `quest_chains.json` (README mentions it; generate_sources.py writes it only without `--skip-quests`, and nothing reads it).

### 3.4 Python scripts in scripts/

Plain-English purpose, inputs, outputs and how to run each script. Its functions are listed in Part 6.

#### scripts/card_groups.py
- **What it's for (plain English):** a reference list of "any one of these" card groups (any axe, any pickaxe, any log...) used in quest requirements.
- **Inputs / outputs:** none. DOCUMENTATION ONLY (says so at the top of the file): data only, no CLI, not imported. Defines `CARD_GROUPS` (dict of group name → card names, weakest to strongest).
- **Depended on by:** nothing imports it today; it documents the `groups` key of `output/bm_quest_cards.json`. (`location_reqs.py` has its own unrelated `CARD_GROUPS`.)

#### scripts/catalog_names.py
- **What it's for (plain English):** helps the generators find an NPC's card when wiki text names the NPC slightly differently from the card.
- **Inputs:** a loaded catalog dict passed in. **Outputs:** none (library).
- **Depended on by:** imported by `generate_shop_owners.py`, `generate_slayer.py`, `generate_clue_steps.py`, `generate_clue_sources.py`, `generate_diaries.py`.

#### scripts/decode_collection.py
- **What it's for (plain English):** reads your card collection out of RuneLite's save files (or the OSRS TCG cloud) so the planner knows which cards you own.
- **Inputs:** `~/.runelite/OSRS-TCG/profiles/*/tcg.save` (v1.0+), `~/.runelite/OSRS-TCG/backups/*/*` (pre-v1.0), `~/.runelite/profiles2/*.properties` (RLTCG_v2/v3 blobs), `cloud-session.json` + api.osrs-tcg.net for cloud accounts (cached `scripts/cache/cloud_cards_<hash>.json`, 30 s), `research/card-catalog-live.json` (to normalise `npc:<id>` names).
- **Outputs:** `--out` (default `scripts/output/my_collection.json`) and `scripts/output/all_collections.json` (every account). Both gitignored (personal data).
- **How to run:** `python3 scripts/decode_collection.py [--out PATH] [--player RSN]` (`--out` default `scripts/output/my_collection.json`; `--player` case-insensitive display name; without it `--out` comes from the single source with the most cards: the newest save file or the largest profiles2 profile. Profiles are never merged). Normally run for you by server.py.
- **Depended on by:** server.py (`/api/collection/refresh`, `/api/accounts/list`); preview.html loads `all_collections.json` at startup.

#### scripts/decode_completed_quests.py
- **What it's for (plain English):** works out which quests you've finished from RuneLite's automatic quest-completion screenshots.
- **Inputs:** filenames in `~/.runelite/screenshots/<player>/Quests/` (`Quest(<name>) YYYY-MM-DD_HH-MM-SS.png`). **Outputs:** `scripts/output/completed_quests.json` (gitignored).
- **How to run:** `python3 scripts/decode_completed_quests.py --player YOUR_RSN` (`--player` required in practice).
- **Depended on by:** preview.html (loads `output/completed_quests.json` at startup and as the fallback for Quest sync; the server endpoint `/api/quests/completed` does the same scan live).

#### scripts/generate_boss_loot.py
- **What it's for (plain English):** builds the loot list for bosses whose rewards come from a chest or reward pool (raids, Barrows, Moons, Gauntlet...), plus each boss's collection-log items.
- **Inputs:** `--card-json` catalog; `monster_drops.json` and `bosses.json` from `--in-dir` (default `scripts/output/`); wiki chest pages and the Collection log page via `wiki_fetcher` (cache `scripts/cache/wiki_html/`).
- **Outputs:** `boss_loot.json` and `collection_log.json` in `--out-dir` (default `scripts/output/`).
- **How to run:** `python3 scripts/generate_boss_loot.py --card-json research/card-catalog-live.json [--out-dir DIR] [--in-dir DIR]` (`--in-dir` = where monster_drops.json / bosses.json are read, default `scripts/output/`; run after generate_sources.py and generate_bosses.py).
- **Depended on by:** preview.html Bosses tab (loot tables; collection-log items marked ◆ as Uniques).
- **Caution:** committed outputs carry hand fixes; write to a scratch `--out-dir` and diff. Rarity rules: wiki tiers, raid uniques "Unique" with share of the roll, footnoted items "Conditional".

#### scripts/generate_bosses.py
- **What it's for (plain English):** builds the list of every boss encounter (with its quest, skill and card requirements) shown on the Bosses tab.
- **Inputs:** `--card-json` catalog; the wiki "Boss" page wikitext (via `generate_diaries._fetch_wikitext`); `scripts/boss_curated.json`; `output/card_aliases.json`; `output/access_routes.json` keys.
- **Outputs:** `scripts/output/bosses.json`; validation report `scripts/cache/boss_validation.json` (printed too).
- **How to run:** `python3 scripts/generate_bosses.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html Bosses tab (`BOSS_DATA` is built from bosses.json); `generate_boss_loot.py` (boss names).
- **Caution:** edit `boss_curated.json`, not the output.

#### scripts/generate_card_aliases.py
- **What it's for (plain English):** makes a lookup so item versions ("Prayer potion(3)", "Grimy ranarr weed") count as the right card on the page.
- **Inputs:** `--card-json` catalog (`items[].tcg.variants`). **Outputs:** `scripts/output/card_aliases.json`.
- **How to run:** `python3 scripts/generate_card_aliases.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html (`cardAliases`, used by `_cardInfo`), and generate_recipes / generate_bosses / generate_skilling / generate_slayer / generate_clue_steps / generate_clue_sources / location_reqs (name validation).

#### scripts/generate_card_versions.py
- **What it's for (plain English):** lists every item version a card covers (e.g. Infernal harpoon under Dragon harpoon) and how each version is made.
- **Inputs:** `--card-json`; wiki pages read in batches of 50 via action=query (cache `scripts/cache/version_pages.json`), image URLs via the wiki API (cached).
- **Outputs:** `scripts/output/card_versions.json`.
- **How to run:** `python3 scripts/generate_card_versions.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html (card page "Versions" list, `cardVersions`), `generate_clue_sources.py`.

#### scripts/generate_clue_sources.py
- **What it's for (plain English):** Works out where you can get each tier of clue scroll (monsters, pickpocketing, implings, chests, skilling, caskets, Watson) and which item cards each tier's reward casket can give, with drop rates.
- **Inputs:** Wiki `action=bucket` "dropsline" data via `wiki_api.get_json` (cached in `scripts/cache/clue_sources_bucket.json`); raw wikitext of Clue geode / Clue nest / Clue bottle via `generate_diaries._fetch_wikitext` (cached in `scripts/cache/wikitext/`); rendered "Reward casket (tier)" pages via `wiki_fetcher.fetch` (Mimic table); `research/card-catalog-live.json`; `output/card_aliases.json`; `output/card_versions.json`; `generate_sources` variant aliases.
- **Outputs:** three files in `scripts/` (not `output/`): `clue_scroll_sources.json` ({tier: [sources]}), `clue_sources.json` ({reward card: [tiers]}), `clue_reward_rarities.json` ({tier: {name: rate}}); plus the bucket cache.
- **How to run:** `python3 scripts/generate_clue_sources.py [--refresh]` — `--refresh` (flag, default off) re-fetches wiki data instead of using the cache.
- **Depended on by:** `generate_sources.py` Pass 5 (`clue_sources.json` → `item_sources[*].clueTiers`); `preview.html` data loading (all three files: Clues tab "where to get the clue", clue reward tiers and rarities on item pages).
- **Hand fixes / caution:** Output paths and shapes were kept from the original hand-made files, so re-running overwrites them; diff before committing. Source-name fixes go in `SOURCE_CARDS`. Never `api.php?action=parse`.

#### scripts/generate_clue_steps.py
- **What it's for (plain English):** Builds the list of every Treasure Trail (clue scroll) step — emotes, Sherlock, Falo, cryptics, anagrams, ciphers, hot/cold, maps, coordinates — and works out which cards, quests, skills and area access each step needs, so the Clues tab can say which steps you can do.
- **Inputs:** OSRS Wiki guide pages fetched as HTML through `wiki_fetcher.fetch` (cached in `scripts/cache/wiki_html/`); `research/card-catalog-live.json`; `scripts/clue_curated.json` (hand-curated: `npcFixes`, `noCard`, `itemNameFixes`, `keepItems`, `questAliases`, `questAccess`, `partialQuestAccess`, `itemGroups`, `linkGroups`, `locationRules`, `hotcoldRegions`, `hotcoldRegionExceptions`, `emoteUnlocks`, `emoteOverrides`, `sherlockOverrides`, `coordinateOverrides`, `crypticOverrides`, `talkOverrides`); `output/card_aliases.json`, `output/quests.json`, `output/access_routes.json`, `output/diaries.json`, `output/monster_drops.json`; `scripts/location_requirements.json` (for `tag_locations`).
- **Outputs:** `scripts/output/clue_steps.json` with keys `emote`, `sherlock`, `falo`, `cryptic`, `anagram`, `cipher`, `hotcold`, `digInfo`, `stepCounts`, `itemIndex`, `npcIndex`, `map`, `coordinate`. Exits 1 if the validation pass finds problems.
- **How to run:** `python3 scripts/generate_clue_steps.py [--force-refresh]` — `--force-refresh` (flag, default off) re-fetches wiki pages even when cached. Run after `generate_diaries.py`, `generate_quests.py` and the access-route / alias outputs exist.
- **Depended on by:** `preview.html` (loads `output/clue_steps.json` into `clueSteps` at startup; used by the Clues tab, clue-step usage sections on item and NPC detail pages, and `_validateDataNames`).
- **Hand fixes / caution:** Don't hand-edit `clue_steps.json`; put fixes in `scripts/clue_curated.json` (overrides, NPC fixes, location rules) and re-run. Fix wording problems in the parser. Fetches go through `wiki_fetcher` (plain page URLs, cached, never `api.php?action=parse`).

#### scripts/generate_diaries.py
- **What it's for (plain English):** Reads every Achievement Diary page on the wiki and turns each task into a checklist of the levels, quests, item cards, monster cards and NPC cards you need, plus each tier's rewards, so the Diaries tab can show what you can complete.
- **Inputs:** `--card-json` catalog (normally `research/card-catalog-live.json`); raw wikitext of the 12 diary pages via `wiki_api.raw` (cached in `scripts/cache/wikitext/`, 404s remembered as `.missing`); `output/quests.json`, `output/item_sources.json` (production ingredients), `output/spells.json` (rune costs, optional), `output/monster_drops.json` (combat NPCs); wiki page types via batched API (cached `scripts/cache/wiki_page_types.json`).
- **Outputs:** `<out-dir>/diaries.json` (default `scripts/output/diaries.json`): `[{name, rewardNpc, easy|medium|hard|elite: {skills, quests, items, monsters, npcs, rewards, tasks:[…]}}]`, plus `npcsNoCard` / `itemsNoCard` "considered" tags.
- **How to run:** `python3 scripts/generate_diaries.py --card-json research/card-catalog-live.json [--out-dir scripts/output]` — `--card-json` required; `--out-dir` defaults to `scripts/output`. Run after `generate_spells.py` and `generate_sources.py`.
- **Depended on by:** `preview.html` (fetches `output/diaries.json` into `DIARY_DATA` for the Diaries tab, diary cross-links on card pages, progress bars); `generate_clue_steps.py` (diary area names); `generate_skilling.py` (diary area names); `location_reqs.py` (validates diary keys). Its `_fetch_wikitext` helper is imported by `generate_bosses.py`, `generate_clue_sources.py`, `generate_slayer.py`, `generate_spells.py`; `_page_types` by `generate_monster_locations.py`.
- **Hand fixes / caution:** Never hand-edit diary tasks in `preview.html` or `diaries.json`. Fix the parser, or add to `CARD_OVERRIDES` / `REWARD_NPCS` / `REWARD_CARD_REMOVE` here and re-run. `build` stops with an error if a `CARD_OVERRIDES` key names a task that doesn't exist. `IRONMAN_ACCOUNT = True` folds the wiki's ironman requirements into the normal ones and strips Grand Exchange wording.

#### scripts/generate_equipment.py
- **What it's for (plain English):** builds gear stats (attack/defence bonuses, level requirements, combat style) for every equipment card, for the Equipment tab and DPS calculator.
- **Inputs:** `research/card-catalog-live.json` (fixed path `CARD_JSON`); OSRSBox / osrsreboxed `items-complete.json` downloaded from GitHub. **Outputs:** `scripts/output/equipment_data.json` (grouped by slot).
- **How to run:** `python3 scripts/generate_equipment.py` (no flags).
- **Depended on by:** preview.html Equipment tab + DPS calculator (`equipBySlot`).

#### scripts/generate_food.py
- **What it's for (plain English):** records how much health each food card heals.
- **Inputs:** wiki `Food/All_food` raw wikitext (`wiki_api.raw`, not cached); `research/card-catalog-live.json` (fixed path). **Outputs:** `scripts/output/food_data.json`.
- **How to run:** `python3 scripts/generate_food.py` (no flags).
- **Depended on by:** preview.html Equipment tab (`foodData`).

#### scripts/generate_icons.py
- **What it's for (plain English):** finds a small picture for every Skilling-tab row that has no card art (recipe outputs, wiki methods, spells).
- **Inputs:** `scripts/cache/wiki_recipes.json` (from generate_recipes), `output/skilling.json`, `output/spells.json`; page images via wiki API `prop=pageimages` (cache `scripts/cache/page_images.json`).
- **Outputs:** `scripts/output/method_icons.json`.
- **How to run:** `python3 scripts/generate_icons.py` (no flags). Run it LAST, after recipes / skilling / spells.
- **Depended on by:** preview.html Skilling tab (`methodIcons`).

#### scripts/generate_ingredient_info.py
- **What it's for (plain English):** gives the page production/shop/spawn info for recipe ingredients that are not cards themselves (unfinished potions, (u) bows...), so the whole unlock chain can be shown.
- **Inputs:** `output/item_sources.json` (production ingredients that aren't card keys); each ingredient's wiki page via `wiki_fetcher` (cached), parsed by `item_scraper`.
- **Outputs:** `scripts/ingredient_info.json` (note: in scripts/, not output/). Overwritten wholesale on each run.
- **How to run:** `python3 scripts/generate_ingredient_info.py` (no flags).
- **Depended on by:** preview.html (`ingredientInfo`, ingredient pages), `generate_recipes.py`, `generate_shop_owners.py`.

#### scripts/generate_monster_locations.py
- **What it's for (plain English):** works out where each monster/NPC card can be found and what area access each spot needs (the card page's "Found at" box).
- **Inputs:** `--card-json`; wiki buckets `infobox_monster`/`infobox_npc` (cache `scripts/cache/npc_id_pages.json`); page wikitext 50 per request (cache `scripts/cache/npc_page_versions.json`); `wiki_page_types` cache; `slayer_curated.json` locationAccess; `monster_locations_overrides.json`; `location_requirements.json`; `REGION_ACCESS` from generate_slayer.py.
- **Outputs:** `scripts/output/monster_locations.json`.
- **How to run:** `python3 scripts/generate_monster_locations.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html (`monsterLocations`, NPC reachability), `generate_slayer.py`, `generate_shop_owners.py` (reads `_gates`; imports `_links`, `base_place`), `scan_location_requirements.py`. It imports `_page_types` from generate_diaries.
- **Caution:** fixes go in `monster_locations_overrides.json` (prefer fixing the generator).

#### scripts/generate_quests.py
- **What it's for (plain English):** builds the basic list of all quests with their skill requirements, prerequisites, kills and start NPC.
- **Inputs:** wiki `List_of_quests` + every quest page via `wiki_fetcher` (cached HTML), parsed by `quest_parser`.
- **Outputs:** `<out-dir>/quests.json` (default `scripts/output/quests.json`; overwritten wholesale; hand fixes in the committed file would be lost, so diff first). `members` comes from each quest page's infobox (so mini-quests are no longer all marked free-to-play; the committed file still has the 19 mini-quests as `members: false` until the next run).
- **How to run:** `python3 scripts/generate_quests.py [--out-dir DIR] [--limit N]` (`--out-dir` default `scripts/output/`; `--limit` = only the first N quests, for testing, and exits with a message unless `--out-dir` is somewhere other than `scripts/output/`).
- **Depended on by:** preview.html Questing tab (`questsData`), and generate_recipes / generate_skilling / generate_diaries / generate_slayer / generate_clue_steps / location_reqs / decode_completed_quests (quest-name validation).

#### scripts/generate_recipes.py
- **What it's for (plain English):** builds every XP-giving production recipe (Fletching, Smithing, Crafting, Cooking, Herblore, Construction, Runecraft) for the Skilling tab, including outputs that have no card.
- **Inputs:** wiki `recipe` Bucket via action=bucket (cache `scripts/cache/wiki_recipes.json`, delete to refetch); `infobox_item` Bucket for item quests (cache `scripts/cache/wiki_item_quests.json`); `output/item_sources.json`, `ingredient_info.json`, `output/card_aliases.json`, `output/quests.json`.
- **Outputs:** `scripts/output/recipes.json`.
- **How to run:** `python3 scripts/generate_recipes.py` (no flags).
- **Depended on by:** preview.html Skilling tab (`recipes`), `generate_icons.py`.

#### scripts/generate_shop_owners.py
- **What it's for (plain English):** maps every shop to the shopkeeper NPC whose card you need to buy there, and where the shop is.
- **Inputs:** `--card-json`; wiki `infobox_shop` Bucket via `wiki_api.get_json` (cache `scripts/cache/wiki_shop_owners.json`); `output/item_sources.json`, `ingredient_info.json`, `output/monster_locations.json` (`_gates`), `slayer_curated.json`, `monster_locations_overrides.json`.
- **Outputs:** `scripts/output/shop_owners.json`.
- **How to run:** `python3 scripts/generate_shop_owners.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html (`shopOwners`, used by `canGetItem` shop checks), `scan_location_requirements.py`.

#### scripts/generate_skilling.py
- **What it's for (plain English):** checks and publishes the hand-written list of training methods for skills that aren't plain production (Agility, Thieving, Hunter, Prayer, Firemaking, Ranged, gathering...).
- **Inputs:** `--card-json`; `scripts/skilling_curated.json`; `output/card_aliases.json`, `output/quests.json`, `output/access_routes.json`, `output/diaries.json`, `location_requirements.json` (validation).
- **Outputs:** `scripts/output/skilling.json`.
- **How to run:** `python3 scripts/generate_skilling.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html Skilling tab (`skillingMethods`), `generate_icons.py`.

#### scripts/generate_slayer.py
- **What it's for (plain English):** builds the Slayer data: masters, their task lists and every monster that counts for each task, with location access.
- **Inputs:** `--card-json`; wiki master pages / "Slayer assignments" subpages and "Slayer task/<Task>" pages (cache `scripts/cache/wikitext/`); location regions and monster Slayer levels via batched API (cached); `slayer_curated.json`; `output/quests.json`, `output/card_aliases.json`, `output/monster_locations.json`, `location_requirements.json`.
- **Outputs:** `scripts/output/slayer.json`; report `scripts/cache/slayer_validation.json`.
- **How to run:** `python3 scripts/generate_slayer.py --card-json research/card-catalog-live.json`.
- **Depended on by:** preview.html Slayer tab (`slayerData`), `scan_location_requirements.py`; `REGION_ACCESS` and `location_regions` are imported by generate_monster_locations / generate_shop_owners; it imports `_fetch_wikitext` from generate_diaries.

#### scripts/generate_sources.py
- **What it's for (plain English):** the main data builder: drop tables for every monster card and "how to get it" for every item card.
- **Inputs:** `--card-json`; wiki monster/quest/item pages via `wiki_fetcher` (HTML cache `scripts/cache/wiki_html/`); `gathering_sources.json`; `clue_sources.json`; `item_sources_overrides.json`.
- **Outputs (in `--out-dir`):** `monster_drops.json`, `item_sources.json`, `quest_chains.json` (only without `--skip-quests`; not committed), `card_categories.json`, `card_details.json`.
- **How to run:** `python3 scripts/generate_sources.py --card-json research/card-catalog-live.json [--limit N] [--monster NAME] [--skip-quests] [--skip-items] [--out-dir DIR]` (`--out-dir` default `scripts/output/`). A full run takes ~25 min. server.py's `/api/generate/run` runs it with `--skip-quests`.
- **CLI rules:** `--limit N` limits only the monsters in pass 1 (not the item or quest passes). `--limit` and `--monster` are partial runs: they exit with a message unless `--out-dir` is somewhere other than `scripts/output/`. A full run into `scripts/output/` first copies the five existing outputs (`_OUTPUT_FILES`) to `scripts/cache/output_backup/generate_sources-<timestamp>/` (`_backup_outputs`), so you can diff against them before keeping the run. Pass 3 (quests) finds no quest items with the live catalog (it has no quest-item field), so `quest_chains.json` stays `{}`.
- **Depended on by:** its helpers (`_card_for_drop`, `load_cards`, `load_variant_aliases`...) are imported by generate_boss_loot, generate_diaries, generate_clue_sources. Its outputs feed almost everything: preview.html (monster drops, item sources, categories, details); generate_boss_loot, generate_diaries, generate_clue_steps (monster_drops); generate_recipes, generate_ingredient_info, generate_shop_owners, generate_diaries (item_sources); reorder_categories; generate_card_versions.
- **Caution:** committed item_sources / card_categories / card_details carry hand fixes. Always run into a scratch `--out-dir`, diff, and patch. Hand fixes go in `item_sources_overrides.json` (pass 6). Deadman/NMZ/PvM Arena/Construction pages are skipped (`_NON_MAIN_GAME_RE`).

#### scripts/generate_spells.py
- **What it's for (plain English):** records every spell's level and rune cost, and which staves/combination runes count as each elemental rune.
- **Inputs:** wiki spellbook pages (Standard, Ancient, Lunar, Arceuus), Elemental staff and Combination rune tables (raw wikitext via `generate_diaries._fetch_wikitext`, cached). **Outputs:** `scripts/output/spells.json` and `scripts/output/rune_sources.json`.
- **How to run:** `python3 scripts/generate_spells.py` (no flags).
- **Depended on by:** preview.html (`spellsData`, `runeSources`: spell requirements and the Magic skilling list), `generate_diaries.py`, `generate_icons.py`.

#### scripts/item_scraper.py
- **What it's for (plain English):** reads a wiki item page and pulls out how the item is made, where it spawns, which shops sell it and what drops it.
- **Inputs:** page HTML passed in (from `wiki_fetcher`). **Outputs:** none (library, no CLI).
- **Depended on by:** `generate_sources.py` (pass 4), `generate_ingredient_info.py`.

#### scripts/location_reqs.py
- **What it's for (plain English):** shared helper for "what do you need to enter this place" (guild levels, quests, items), and a checker for `location_requirements.json`.
- **Inputs:** `scripts/location_requirements.json`; for validation also `output/quests.json`, `output/diaries.json`, `output/access_routes.json`, `output/card_aliases.json`, `research/card-catalog-live.json`.
- **Outputs:** none (prints problems).
- **How to run:** `python3 scripts/location_reqs.py` (no flags) validates the file; exits 1 on problems.
- **Depended on by:** imported by generate_monster_locations, generate_slayer, generate_skilling, generate_clue_steps. preview.html applies the same merge rules in `_locGate()` / `_locReqOk()`.

#### scripts/loot_parser.py
- **What it's for (plain English):** reads the drop tables on a wiki monster page.
- **Inputs:** page HTML. **Outputs:** none (library). **Depended on by:** `generate_sources.py` (pass 1).

#### scripts/quest_parser.py
- **What it's for (plain English):** reads a wiki quest page's details table (start NPC, requirements, items, enemies).
- **Inputs:** page HTML. **Outputs:** none (library). **Depended on by:** `generate_quests.py`, `generate_sources.py` (pass 3).

#### scripts/rarity_mapper.py
- **What it's for (plain English):** turns a drop rate like "1/512" into the wiki's rarity words (Common, Uncommon, Rare, Very Rare).
- **Inputs / outputs:** none (library). Tiers: Always; Common ≤1/25; Uncommon <1/100; Rare <1/1,000; Very Rare beyond.
- **Depended on by:** `loot_parser.py`, `generate_boss_loot.py`. A wiki "Extremely rare" label maps to Very Rare (the top tier).

#### scripts/reorder_categories.py
- **What it's for (plain English):** puts each card's category tags in a sensible order (e.g. logs show Firemaking first, bones show Prayer first).
- **Inputs / outputs:** reads and rewrites `scripts/output/card_categories.json` in place.
- **How to run:** `python3 scripts/reorder_categories.py [--dry-run]` (`--dry-run` prints changes without writing).
- **Depended on by:** preview.html (category tags and filters).

#### scripts/scan_location_requirements.py
- **What it's for (plain English):** maintenance helper that finds places the planner mentions whose entry requirements aren't recorded yet.
- **Inputs:** `output/monster_locations.json`, `output/slayer.json`, `output/shop_owners.json`, `skilling_curated.json`, `location_requirements.json`; wiki Infobox Location via batched action=query (cache `scripts/cache/location_infobox_reqs.json`).
- **Outputs:** none (prints a report).
- **How to run:** `python3 scripts/scan_location_requirements.py [--all]` (`--all` lists every place with a requirement field, not just uncovered ones).
- **Depended on by:** nothing (manual tool).

#### scripts/wiki_api.py
- **What it's for (plain English):** the polite way for generators to read the OSRS Wiki (rate-limited, never the forbidden `action=parse`).
- **Inputs / outputs:** network only; callers cache. **Depended on by:** imported by generate_card_versions, generate_clue_sources, generate_diaries, generate_food, generate_icons, generate_monster_locations, generate_recipes, generate_shop_owners, generate_slayer, scan_location_requirements (generate_bosses / generate_spells reach it through `generate_diaries._fetch_wikitext`).

#### scripts/wiki_fetcher.py
- **What it's for (plain English):** downloads rendered wiki pages once and keeps them on disk so re-runs don't hit the wiki.
- **Inputs:** plain wiki page URLs. **Outputs:** `scripts/cache/wiki_html/<page>.html` (delete a file to refetch).
- **Depended on by:** imported by generate_sources, generate_quests, generate_boss_loot, generate_ingredient_info, generate_clue_steps, generate_clue_sources.

#### scripts/server.py
See 3.1 above and Part 4.

---

## Part 4. server.py in detail

In plain words: server.py is a tiny web server on your own machine (port 8765). It hands the browser the planner's files, and offers a few "endpoints" the page calls to read your RuneLite collection, your hiscores, finished quests, the pack list, and pictures. It is a `ThreadingHTTPServer`, so a slow picture download never freezes the page.

### Endpoints

API routes (`/api/...`) accept both GET and POST. All JSON replies are UTF-8 with `Access-Control-Allow-Origin: *`.

| Path | Method | Params | What it does / returns | Used by the page? |
|---|---|---|---|---|
| `/<file>` (anything else) | GET, HEAD | — | Static file from `scripts/` (e.g. `/preview.html`, `/output/quests.json`, `/assets/icons/...`). `/` itself has no index page, so it shows Python's plain directory listing of `scripts/`. Sent with `Cache-Control: no-cache` so edits show on reload. | yes (all data) |
| `/images/<path>` | GET, HEAD | path must match `[\w ./%()'&,!+-]+\.(png\|gif\|jpg\|jpeg\|webp)`, no `..` | Card art / pack images proxied from `https://osrs-tcg.net/images/<path>`, cached forever in `scripts/cache/tcg_img/<path>`. 400 on a bad path, 502 if it can't be fetched. | yes (`_cardImg`) |
| `/wikiimg/<path>` | GET, HEAD | same path rule | Wiki image proxy: tries `oldschool.runescape.wiki/images/<path>`, then the original file if `<path>` is a `thumb/.../NNpx-` thumbnail, then RuneLite's item sprite with the same name. Good images cached in `scripts/cache/wiki_img/<sha1 of path>`. | yes (`_wikiImg`) |
| `/api/collection/refresh` | GET/POST | `?player=<RSN>` optional | Runs `decode_collection.py --out output/my_collection.json [--player RSN]` and returns that JSON plus `refreshedAt`, `log`, `player`. 500 + `{error}` on failure. | yes (`refreshCollection`) |
| `/api/collection/status` | GET/POST | — | `{exists, cardCount, updatedAt}` of my_collection.json, no decode. | no |
| `/api/collection/source-mtime` | GET/POST | — | `{sourceMtime, sourceTime}`: newest change time of any RuneLite TCG save (tcg.save, backups, profiles2). Cheap "has anything changed?" check. | yes (`refreshAll`) |
| `/api/collection/revision` | GET/POST | `?player=<RSN>` required | For cloud accounts: `{isCloud, player, revision, stateHash}` from `api.osrs-tcg.net/api/v1/me/cards?limit=1` using the stored token. Cached 45 s per player; on HTTP 429 backs off (Retry-After, min 30 s) and keeps answering with the last good value. `{isCloud:false}` for local accounts; 400 without player. | only by the disabled live sync |
| `/api/accounts/list` | GET/POST | — | Re-runs `decode_collection.py`, then returns `{accounts: [{name, cardCount, credits, updatedAt}], updatedAt}` from all_collections.json, newest first. | yes (`refreshAll`) |
| `/api/generate/run` | GET/POST | — | Starts `generate_sources.py --card-json research/card-catalog-live.json --skip-quests` on a background thread, logging to `output/generate.log`. `{started:true}` or `{started:false, reason:"already running"}`. **Writes straight into scripts/output/**, so prefer running generators by hand into a scratch folder. | no |
| `/api/generate/status` | GET/POST | — | `{running:true, elapsedSecs, logLines}` / `{running:false, result:"ok" or "error", tookSecs}` / `{running:false, result:null}`. | no |
| `/api/generate/log` | GET/POST | — | `{log: <text of generate.log>}`. | no |
| `/api/hiscores` | GET/POST | `?player=<RSN>` required | `{player, levels: {Skill: level}}` from the OSRS hiscores lite CSV (unranked skills left out). 400 without player, 502 on network error. | yes (`lookupLevels`) |
| `/api/quests/completed` | GET/POST | `?player=<RSN>` optional | `{player, completedQuests, screenshotCount, dirsScanned}` from `~/.runelite/screenshots/<player>/Quests/` filenames (all players if none given). | yes (`syncQuestsFromScreenshots`) |
| `/api/packs` | GET/POST | — | The TCG pack catalog from `https://api.osrs-tcg.net/api/v1/packs`, cached in memory 24 h. 502 on error. | yes (`loadData`) |
| any other `/api/...` | — | — | 404. POST to a non-API path: 405. | |

### Caching headers

- Static files: `Cache-Control: no-cache` (added in `end_headers` unless the handler set its own), so the browser revalidates every load.
- Images (`_send_image`): `Cache-Control: max-age=604800` (7 days) on success; on failure a 502 with `Cache-Control: no-store`, so a failure never sticks in the browser.
- Disk caches: good images are kept forever; failures are never cached, so the next request tries again. A per-file lock (`_IMG_LOCKS`) makes sure one image is downloaded only once even if many requests arrive together. HTTP 403/404/502 from a source skips straight to the next source (the wiki's bot check won't clear on retry); other errors retry up to 3 times.
- The page adds `?v=<timestamp>` to its JSON fetches as an extra cache-buster.

### Image proxies, in plain words

- **Card art** (`/images/...`): each card's picture comes from osrs-tcg.net, the TCG's own site, using the `imagePath` in `card_details.json`. Saved to disk the first time.
- **Wiki pictures** (`/wikiimg/...`): since 21 Oct 2026 the wiki's "Weird Gloop" bot check answers uncached requests from this machine with a browser challenge (502/403), which an `<img>` can't pass. The proxy tries the wiki (cached copies still work), then the full-size original, then RuneLite's sprite for an item of the same name (`static.runelite.net/cache/item/icon/<id>.png`, ids from `names.json`, cached in `scripts/cache/runelite_item_names.json`). If all fail, the page itself tries the wiki directly once and then hides the icon (no broken-image boxes).

### Every function, class and method

Module level:
- `_fetch_image_cached(cache, urls, tries)` — approx. L68 — Image bytes from the disk cache, else the first URL that answers (retries; keeps good images, never caches failures; one lock per file).
- `_runelite_icon_url(file_name)` — approx. L105 — RuneLite sprite URL for the item a wiki file is named after ("Bronze_bar.png" → item 2349); loads/caches RuneLite's names.json.
- `_wiki_image_urls(rel)` — approx. L129 — URLs to try for a wiki image path: as given, the original file for a thumbnail, then the RuneLite sprite.
- `_wiki_cache_path(rel)` — approx. L139 — Disk cache path for a wiki image (SHA-1 of the path).
- `_get_pack_catalog()` — approx. L150 — Pack catalog JSON from api.osrs-tcg.net, re-fetched at most once per 24 h.
- `_run_generate_background(extra_args)` — approx. L176 — Runs generate_sources.py (quests skipped) to completion, logging to generate.log and updating the `_generate_*` job state.
- `_find_cloud_session(player)` — approx. L218 — Finds a player's `cloud-session.json` (via SHA-256 of accountHash from `$rsprofile*.properties`); cached; None for non-cloud accounts.
- `main()` — approx. L730 — Parses `--port` (default 8765) and serves until Ctrl+C.

`class Handler(http.server.SimpleHTTPRequestHandler)` — approx. L263 — static files rooted at scripts/ plus the API and image routes:
- `__init__(self, *args, **kwargs)` — approx. L266 — Serves from scripts/ whatever the current folder is.
- `end_headers(self)` — approx. L270 — Adds `Cache-Control: no-cache` unless one is already set.
- `log_message(self, fmt, *args)` — approx. L278 — Prints only `/api/` requests (static and image hits are too noisy).
- `do_GET(self)` — approx. L284 — Routes to the API, the image proxies, or a static file.
- `do_HEAD(self)` — approx. L296 — Routes HEAD to the image proxies or a static file.
- `do_POST(self)` — approx. L306 — Routes POST to the API; anything else 405.
- `_handle_api(self, path)` — approx. L314 — Dispatches an `/api/` path to its handler; 404 if unknown.
- `_api_collection_refresh(self)` — approx. L343 — Runs decode_collection.py (optionally for one player) and returns the collection.
- `_api_collection_status(self)` — approx. L376 — Card count and file time of my_collection.json.
- `_api_accounts_list(self)` — approx. L389 — Refreshes all_collections.json and returns the account list.
- `_api_generate_status(self)` — approx. L433 — Reports the background generate job.
- `_api_generate_run(self)` — approx. L458 — Starts generate_sources.py on a thread unless one is running; the run is claimed (`_generate_running = True`) under `_generate_lock` before the thread starts, so two quick requests can't start two runs.
- `_api_generate_log(self)` — approx. L473 — Returns generate.log text.
- `_api_hiscores(self)` — approx. L492 — Fetches levels from the hiscores lite CSV.
- `_api_quests_completed(self)` — approx. L535 — Lists completed quests from screenshot filenames.
- `_api_collection_source_mtime(self)` — approx. L578 — Newest mtime of any TCG save file.
- `_api_collection_revision(self)` — approx. L612 — Cloud revision check with 45 s cache and 429 back-off.
- `_api_packs(self)` — approx. L673 — Proxies the pack catalog (24 h cache).
- `_send_image(self, data, ext)` — approx. L681 — Sends image bytes with a 7-day cache header, or a no-store 502.
- `_proxy_tcg_image(self, path)` — approx. L696 — `/images/**` → osrs-tcg.net, disk-cached.
- `_proxy_wiki_image(self, path)` — approx. L704 — `/wikiimg/**` → wiki → original → RuneLite sprite, disk-cached.
- `_json_response(self, data, status)` — approx. L718 — Sends a JSON reply (UTF-8, CORS open).

Module constants and state: `_SCRIPTS_DIR`, `_OUT_DIR`, `_COLLECTION` (my_collection.json), `_GENERATE_LOG`, `_WIKI_IMG_DIR`, `_TCG_IMG_DIR`, `_IMG_LOCKS` / `_IMG_LOCKS_GUARD`, `_RL_NAMES_FILE` / `_rl_ids`, `_PACK_CATALOG_URL` / `_PACK_CATALOG_TTL` (86400) / `_pack_catalog_data` / `_pack_catalog_ts`, `_generate_lock` / `_generate_running` (True from the moment a run is accepted, set under `_generate_lock`, until it ends) / `_generate_proc` / `_generate_start` / `_generate_done` / `_generate_result`, `_PROFILES2_DIR`, `_TCG_PROFILES`, `_DISPLAY_NAME_RE`, `_ACCOUNT_HASH_RE`, `_revision_cache`, `_cloud_session_cache`. Class constants: `Handler._HISCORE_SKILLS` (CSV order), `Handler._SCREENSHOTS_BASE`, `Handler._TCG_PROFILES`, `Handler._TCG_BACKUPS`.

**Careful when editing:** an earlier edit dropped the `_COLLECTION` / pack-catalog constants and broke `/api/accounts/list` and refresh (21 Oct). After changing server.py, restart it and re-test every `/api` endpoint.

---

## Part 5. preview.html in detail

In plain words: preview.html is one long file. The top (approx. lines 1 to 912) is the page layout and styling. From approx. line 913 a single `<script>` holds all the logic, split into areas by comment lines that look like `// ─── Name ────`. Search for `// ─── ` to jump between areas. Every top-level function and variable is listed below, grouped by area in file order.

### How a page load works
1. The browser loads preview.html; the last line of the script calls `loadData()`.
2. `loadData()` fetches every JSON file (Part 3) at once, stores each in a global variable, expands requirement rows (`_expandReq`), builds reverse indexes (diaries/bosses by card), prepares clue steps and runs `_validateDataNames()` (the `[data check]` console warnings).
3. It loads the collection (`loadCollection()`, `output/my_collection.json`, or a random simulated collection if there is none), builds the card list, loads the wishlist from localStorage, asks the server for the pack catalog (`/api/packs`), fills the account dropdown from `all_collections.json`, switches to the selected account, and calls `refreshAll()` (accounts, collection, hiscores, quest sync from the server).
4. Clicking a tab calls `switchTab(name)` → `_renderTab(name)`, which draws that tab.

### Tabs and their render functions

| Tab (button) | `switchTab` name | Left list / grid | Right pane (detail / home) |
|---|---|---|---|
| Cards | `cards` | `filterCards` → `renderList` | `showCard` → `renderMonster` / `renderItem` / `renderClueScroll` / `renderIngredient` |
| Wishlist | `wishlist` | `renderWishlist` | (same function) |
| Equipment | `equipment` | `renderEquipmentTab` | equipment slots + DPS calculator |
| Skilling | `skilling` | `renderSkillGrid` | `showSkillDetail` / `_renderSkillHome` |
| Questing | `questing` | `renderQuestList` | `showQuestDetail` / Questing home (most-needed cards, progress bars) |
| Diaries | `diaries` | `renderDiaryList` | diary detail / `_renderDiaryHome` |
| Bosses | `bosses` | `renderBossList` | boss detail / `_renderBossHome` (defined in the Slayer area) |
| Slayer | `slayer` | `renderSlayerList` | master / task detail |
| Clues | `clues` | `renderClueList` | clue tier / step detail |
| Packs | `packs` | `renderPackList` | `showPackDetail` / `_renderPackHome` |
| Rules | `rules` | `renderRulesTab` | (same; text from `_rulesTabHtml`) |

### Key cross-cutting helpers (quick index)

These are used everywhere. Full one-line descriptions are in the area lists below.

| Helper | Where | Area |
|---|---|---|
| `isOwned` | approx. L2064 | Slayer wishlist group helper |
| `_cardInfo` | approx. L2075 | Slayer wishlist group helper |
| `canGetItem` | approx. L1774 | Recursive item reachability |
| `_itemGetNeeds` | approx. L1725 | Recursive item reachability |
| `_shopStatus` | approx. L1423 | Recursive item reachability |
| `_reqMet` | approx. L10592 | Quest requirement model |
| `_questReqRow` | approx. L10267 | Progress bars (quests + diaries) |
| `_expandReq` | approx. L10472 | Quest requirement model |
| `_accessMet` | approx. L10524 | Quest requirement model |
| `_routeMet` | approx. L10546 | Quest requirement model |
| `REQ_GROUPS` | approx. L10561 | Quest requirement model |
| `_cardUsable` | approx. L10511 | Quest requirement model |
| `_locGate` | approx. L8717 | Slayer tab |
| `_locReqOk` | approx. L8778 | Slayer tab |
| `_cardImg` | approx. L2113 | Slayer wishlist group helper |
| `_wikiImg` | approx. L2097 | Slayer wishlist group helper |
| `_placeTip` | approx. L3055 | Wishlist |
| `_validateDataNames` | approx. L9323 | Achievement Diaries tab |
| `loadData` | approx. L2320 | Data loading |
| `loadCollection` | approx. L2211 | Slayer wishlist group helper |
| `switchTab` | approx. L6656 | Tab navigation |
| `_renderTab` | approx. L6662 | Tab navigation |
| `refreshAll` | approx. L6456 | Refresh all — collection + levels + quest sync |
| `showCard` | approx. L2722 | Card display |

In short: `isOwned(name)` = do you own this card (versions count via `_cardInfo` / card_aliases). `canGetItem(name)` = can you actually obtain this item now (any source), and `_itemGetNeeds(name)` = what's missing if not. `_expandReq` turns a data requirement (cards, group, routes, access, spells, tool) into a full row once at load; `_reqMet(req)` says if a row is met; `_questReqRow` draws it. `_accessMet(key)` checks an access route (`access_routes.json`); `_locGate` / `_locReqOk` check a place's entry gate (`location_requirements.json`). `REQ_GROUPS` holds the named card groups a requirement can point to with `group`: `slash_weapon`, `light_source`, `dragonfire` and `warm_clothing` (Wintertodt warm clothing: four pieces in different slots, see `WARM_CLOTHING_BY_SLOT` / `_warmUsableSlots`); tool tiers (`TOOL_TIERS`) are handled separately as `tool:X` groups. `_cardImg` / `_wikiImg` build image URLs through the server's `/images/` and `/wikiimg/` proxies. `_placeTip` positions every hover popup inside the window.

### Areas, in file order

### Page markup (approx. lines 1 to 912)

The part of the file before `<script>` is the page's look and its fixed layout: what you see before any data loads.

- `<head>`: page title "OSRS TCG — Sourcing Panel Preview", an inline base64 favicon, `<meta name="referrer" content="no-referrer">` (so wiki images load without a referrer), and one large `<style>` block (approx. L8 to 822) with all CSS: dark theme, card list, drop rows, rarity badges, progress pills, tooltips (`.tt-*`), equipment/DPS calculator styles (`.dps-*`, `.combat-badge`, `.req-tag`).
- `#tab-bar` (approx. L826): the 11 tab buttons, each calling `switchTab(name)`: Cards (`cards`), Wishlist (`wishlist`), Equipment (`equipment`), Skilling (`skilling`), Questing (`questing`), Diaries (`diaries`), Bosses (`bosses`), Slayer (`slayer`), Clues (`clues`), Packs (`packs`), Rules (`rules`).
- `#global-nav` (approx. L839): account dropdown `#rsn-input` (calls `onAccountChange`), `#refresh-btn` "↻ Refresh" (calls `refreshAll`), `#sim-btn` "Re-roll" (calls `reroll`, only shown for the random simulated collection), and `#global-back-btn` / `#global-fwd-btn` (call `navigateBack` / `navigateForward`). A "made by Lottie" label follows.
- `#app-content` (approx. L850) holds two columns:
  - `#sidebar`: heading "Card Sourcing", `#controls` with `#search` (text, calls `filterCards`), `#owned-filter` (all / owned / not owned), `#cat-filter` (monsters, NPCs, weapons, ammo, tools, runes, equipment, food, potions, currency, clue scrolls, clue rewards, misc, wishlisted), `#set-filter` (filled with pack names once `/api/packs` loads), `#filter-row4` / `#sort-select` (name or "recently pulled", only shown when pull timestamps exist); `#sim-bar` / `#sim-summary` (collection summary line); `#card-list` (the clickable card list built by `renderList`).
  - `#main-content` → `#detail`: the right-hand pane every tab renders into (starts with "← Select a card to see sourcing info").
- `#toast` (approx. L909): the fixed pop-up message box used by `showToast`.

### Universal navigation helpers (approx. line 1020)

Lets any link on the page (a card name, a quest, a pack) jump you to the right tab and page, even when the name has quotes or apostrophes.

- `_navToCard(el)` — approx. L1023 — Opens the card named in a clicked element; reads `el.dataset.nav` / `data-nav-type` and calls `showCard`.
- `_navToQuest(el)` — approx. L1027 — Opens a quest on the Questing tab from a clicked element; pushes history, sets `selectedQuest` from `data-quest`, renders the tab and calls `showQuestDetail`.
- `_navToPack(el)` — approx. L1034 — Opens a pack on the Packs tab from a clicked element; hides the pack hover tip, pushes history, calls `showPackDetail(data-pack)`.

### Toast notifications (approx. line 1041)

Shows a short coloured message at the bottom of the screen (for example "refresh failed").

- `_toastTimer` (let) — approx. L1042 — Timeout handle for hiding the current toast.
- `showToast(msg, type='warn', duration=6000)` — approx. L1044 — Shows a pop-up message in the `#toast` box; `type` is warn / error / info (colour scheme), auto-hides after `duration` ms.

### Tool tiers (approx. line 1061)

Knows which tools a skill needs (hammer, needle, pickaxes by level) and the item lists for special requirements like light sources, dragonfire protection and Wintertodt warm clothing.

- `getImplicitTools(skill, ingredients, wikiTools, facilities)` — approx. L1067 — Works out the full tool list for a recipe: the wiki-scraped tools plus ones the wiki omits (Hammer for Smithing at an anvil/forge but not smelting or Superheat; Needle for Crafting with Thread). Used by `canGetItem`, `_itemGetNeeds` and production views.
- `TOOL_TIERS` (const) — approx. L1088 — Pickaxe, Axe and Harpoon tiers: each `{name, skillReq, rare?}` (the Mining/Woodcutting/Fishing level needed to use it). Any owned tier you have the level for satisfies a tool requirement.
- `LIGHT_SOURCE_ITEMS` (const) — approx. L1117 — Items that count as a light source for dark areas (Candle, lanterns, Mining helmet, Firemaking cape…); any one is enough.
- `DRAGONFIRE_ITEMS` (const) — approx. L1124 — Items that give meaningful dragonfire protection (anti-dragon shield, dragonfire shield/ward, super antifire potions).
- `WARM_CLOTHING_BY_SLOT` (const) — approx. L1132 — Wintertodt warm clothing: every carded item on the wiki's "Warm clothing" page, grouped by equipment slot (four pieces in different slots give full protection). Used by the `warm_clothing` requirement group.
- `WARM_CLOTHING_ITEMS` (const) — approx. L1150 — Flat list of all items in `WARM_CLOTHING_BY_SLOT`.
- `_warmItemOk` (const arrow) — approx. L1155 — True when a warm item's card is usable and it can be obtained (`_cardUsable` and no `_itemGetNeeds`).
- `_allSkills99` (const arrow) — approx. L1157 — True when every skill is level 99 (for the Max cape).
- `_maxCapeOk` (const arrow) — approx. L1159 — True when you can buy a Max cape: all 99s plus the Mac and Coins cards.
- `WARM_NO_CARD` (const) — approx. L1160 — Warm items that have no TCG card (Rainbow scarf/cape/jumper, Bomber cap/jacket, Yak-hide armour, Firemaking hood/cape, Max capes), each with slot, how-to text and an `ok()` check for whether you can get it now.
- `WARM_EVENT_ONLY` (const) — approx. L1178 — Text listing holiday-event warm items that are never counted (only claimable during events).

### Card level-order sort (approx. line 1181)

Sorts "any one of these" card lists by level (Bronze axe, Iron axe, Steel axe…) instead of alphabetically.

- `CARD_SORT_LEVEL` (const) — approx. L1184 — Lowercase card name → level, built from `TOOL_TIERS` plus spears and feathers.
- `sortCardsByLevel(cards)` — approx. L1203 — Returns a copy of a card-name list sorted by `CARD_SORT_LEVEL` (unknown = 999), then alphabetically.

### Compound tool resolution (approx. line 1211)

Splits tools like "Fishing rod + bait" into separate parts and checks each one against your cards.

- `FEATHER_CARDS` (const) — approx. L1214 — All feather cards; "feathers" in a tool string matches any of them.
- `TOOL_PART_ALIASES` (const) — approx. L1222 — Shorthand → real card name (bait → Fishing bait, sandworms, snare → Bird snare). Item versions go through `cardAliases` instead.
- `TANNING_MAP` (const) — approx. L1231 — Leather → the hide card it is tanned from (Leather/Hard leather → Cowhide, dragon leathers → dragonhides); tanning needs only the hide and Coins.
- `resolveToolParts(toolStr)` — approx. L1241 — Splits a tool string on " + " into `[{label, owned, note, noCard?}]`; handles Karambwan vessel bait (Karambwanji), "feathers" (any feather card), aliases; a tool with no card counts as owned (`noCard`).

### Recursive item reachability (approx. line 1267)

The heart of the planner: works out whether you can actually get an item (shop, drop, gathering, production, quest reward, boss chest, clue) with your cards, levels and quests, and if not, what you are missing. Also holds the clue-step and shop checks it relies on.

- `_spawnLocNames` (let) — approx. L1274 — Lazy cache of `LOC_REQS` place names, longest first, for `spawnLocGate`.
- `spawnLocGate(loc)` — approx. L1276 — If a ground-spawn location text starts with a known gated place from location_requirements.json (e.g. "Crafting Guild"), returns `{name, gate}`; else null.
- `_canGetCache` (let) — approx. L1286 — Memo object for `canGetItem` results; cleared when the collection, levels or quests change.
- `_acts(src)` — approx. L1297 — Returns an item source's `activity` entry as an array (it may be one object or a list of alternatives).
- `_activityMet(a, visited)` — approx. L1299 — True when an activity source (quest, minigame, NPC, diary…) is fully met: quests done, started quests, diary tiers, levels, area access, cards / anyCards / npcs owned, boss doable, and `from` items owned and obtainable.
- `_activityMissing(a)` — approx. L1309 — Lists what an activity source still needs as short labels (cards, "X card", "start Q", "Skill N", "reach area", "do boss"…), for `_itemGetNeeds` and card pages.
- `_bossRewardBusy` (const) — approx. L1326 — Set of boss names currently being checked, to stop `_bossDoable` recursing forever.
- `_bossDoable(bossName)` — approx. L1327 — True when a Bosses-tab encounter is "available" (`evaluateBoss`) and its `lootRequirements` are met (`_reqMet`); re-entry guarded.
- `_bossRewardOk(name)` — approx. L1335 — True when any boss whose chest/reward loot includes this item is doable (via `_bossRewardsFor`).
- `_hasKnownSource(name, src)` — approx. L1337 — True when our data names any way to get the item (shop, spawn, gathering, drop, curated gathering, production, always available, activity, clue tier, boss reward, tanning or marked unobtainable).
- `_gatherIdx` (let) — approx. L1348 — Lazy index: lowercase card / version name → curated gathering methods (from skilling.json) that yield it.
- `_gatherOut(o)` — approx. L1350 — Normalises a skilling.json output entry (string or object) to `{card, level?, levels?, tool?}`.
- `_curatedGathering(name)` — approx. L1352 — Returns `[{m, out}]` curated gathering methods (skilling.json `outputs`) that produce this card; builds `_gatherIdx` on first call.
- `_curatedGatherStatus(m, out, visited)` — approx. L1368 — Checks one curated gathering method for one output → `{ok, level, levelOk, gates, reqs}`: levels, quests, started quests, diaries, area access, the method's place (`_locGate`), skill unlock quest, and each requirement (tool tiers, usable cards, routes, skill alternatives).
- `SHOP_OWNERS` (let) — approx. L1405 — Shop seller → `{shop, owners, cards, locations}` from output/shop_owners.json; buying needs the owner NPC's card.
- `_shopSellerCards(seller)` — approx. L1407 — The NPC card(s) for a shop seller (empty = no card needed, e.g. general store "Shop keeper").
- `_npcReachable(card)` — approx. L1409 — True when an NPC card has no known location or at least one location you can reach (monster_locations.json + `_slLocOk`).
- `_shopPlaceReach(seller)` — approx. L1416 — Whether any of a shop's known locations is reachable; null when no location is known.
- `_shopStatus(s)` — approx. L1423 — Full check of one shop source → `{ok, sellerCards, sellerOk, sellerReach, curCard, curOk}`: seller card owned, shop/seller reachable, currency card (default Coins) owned.
- `_facilityCards(f)` — approx. L1437 — NPC card(s) needed for production at an NPC or shop facility (Aggie's dyes, Thormac's battlestaves…).
- `_facilityOk(f)` — approx. L1444 — True when a production facility needs no card, or you own and can reach one of its NPC cards.
- `CLUE_STEP_TYPES` (const) — approx. L1450 — The nine clue step types (emote, sherlock, falo, cryptic, anagram, cipher, map, coordinate, hotcold).
- `CLUE_TYPE_LABEL` (const) — approx. L1451 — Display label per clue step type.
- `CLUE_TRAIL_STEPS` (const) — approx. L1454 — Typical number of steps per trail by tier (wiki midpoints: beginner 2 … master 7).
- `CLUE_TRAIL_MIN` (const) — approx. L1458 — 0.05: a clue tier counts as realistically doable (its rewards obtainable) when at least 1 in 20 trails can be finished.
- `_clueCap` (const arrow) — approx. L1460 — Capitalises a tier name ("hard" → "Hard").
- `_defHidden` (const arrow) — approx. L1462 — Adds a non-enumerable property to an object (used to tag clue steps without polluting JSON).
- `_prepClueSteps()` — approx. L1465 — Runs once after load: tags every clue step with hidden `_type` / `_tier` and pre-expands its requirements.
- `_clueTierStepsMemo` (let) — approx. L1476 — Memo: tier → list of `{type, step}`.
- `_clueTierSteps(tier)` — approx. L1478 — All steps of one tier across every type (Falo only for Master), memoised.
- `_clueStepText(type, s)` — approx. L1489 — The text a step is known by (task, lyric, anagram, cipher, coords, location or clue text); used as the wishlist key.
- `_clueStepFind(type, tier, text)` — approx. L1498 — Finds a step object by type, tier and its text (to re-open starred clue steps).
- `_URI_REQ` (const) — approx. L1504 — The implicit "Uri" NPC requirement added to every emote step.
- `_clueStepReqs(step)` — approx. L1506 — The requirement list for a step: its own `requirements` from clue_steps.json, or (older data) gates derived per type (Spade, NPC, kills, Double agent, items/slots); adds Uri for emotes, runs `_expandReq` on each, caches on hidden `_reqs`.
- `_clueCardOk(c)` — approx. L1533 — True when a card is not a TCG card (unrestricted) or is usable.
- `_clueReqEval(r)` — approx. L1536 — Evaluates one clue requirement → `{ok, frac, cards}`: handles optional, item sets, random asks (share owned), "all" mode, any-of, routes and skill alternatives.
- `_clueStepCache, _clueTierMemo, _clueSig` (let) — approx. L1563 — Clue caches (per-step WeakMap, per-tier memo) and the state signature they belong to.
- `_clueSigCheck()` — approx. L1565 — Clears the clue caches when owned cards, quests or levels have changed.
- `_clueResetCaches()` — approx. L1570 — Empties all clue caches.
- `_clueStepOk(step)` — approx. L1572 — Can you do this clue step? → `{ok, p, missing}`: card requirements, quests, started quests, skills, access, diaries and the step's places; `p` is the chance a random ask is met. Cached unless quest propagation is in progress.
- `_clueMonsterKillable(card)` — approx. L1604 — Whether you can kill a monster for clues: own its card, its boss encounter is available, Slayer level, and a reachable location → `{ok, why}`.
- `_clueSourceStatus(s, tier)` — approx. L1623 — Whether one way of getting a clue scroll works → `{ok, why}`, by kind: casket (lower tier), npc-exchange (Watson), skilling (level + tool), impling (card + net + Hunter), pickpocket, monster, other item; keys/minigames not modelled.
- `_clueTierBusy` (const) — approx. L1673 — Set of tiers being evaluated (recursion guard).
- `_clueTierStatus(tier)` — approx. L1674 — Full roll-up of a clue tier → `{obtain, types, p, k, trail, steps, okSteps, blockers, neededCards}`: per-type step success weighted by step count (hot/cold weighted as an average type), trail estimate p^k, ways to obtain, top blockers and cards. Memoised.
- `_clueTierObtainable(tier)` — approx. L1714 — True when at least one source of that clue tier works.
- `_clueTierOk(tier)` — approx. L1716 — True when the tier is obtainable and its trail estimate is at least `CLUE_TRAIL_MIN`; used by `canGetItem` for clue rewards.
- `_getNeedsMemo, _getNeedsSig` (const/let) — approx. L1723 — Memo for `_itemGetNeeds` and its state signature (account `_currentRsn`, owned / completed / started quest counts, `_diaryTickVer`, levels).
- `_itemGetNeeds(name)` — approx. L1725 — "Why can't I get this?": `[]` when `canGetItem` is true, `['unobtainable']`, or the shortest list of missing pieces across all sources (shop currency/seller/reach, gathering level/tool/quest/area, production level/ingredients/tools, activities, bosses, a dropper card); `['no known source']` if none. Shown on cards and in requirement rows.
- `canGetItem(itemName, visited)` — approx. L1774 — Can the player actually obtain this item right now? Tries every source as an OR: item versions via `cardAliases`; unobtainable → false; no known source → false for cards; reachable ground spawn; usable shop (`_shopStatus`); activities; boss chest loot; gathering (level, quests, access, tool tier, skill unlocked); curated gathering; monster drop with owned card; clue tier (`_clueTierOk`); production (level, quests, facility, tools, recursive ingredients and `ingredientChoice`); tanning. Cycle-guarded with `visited`, memoised in `_canGetCache`.

### State (approx. line 1900)

All the page's memory: the loaded data files, your owned cards and levels, quest completions, current selections on each tab, and the wishlist. Also the core ownership and image helpers.

- `monsterDrops, itemSources, cardCategories, cardDetails, foodData` (let) — approx. L1901 — The main data files: output/monster_drops.json, item_sources.json, card_categories.json, card_details.json, food_data.json.
- `bossLoot` (let) — approx. L1902 — Boss name → `{source, page, drops}` for chest/reward bosses (boss_loot.json).
- `spellsData` (let) — approx. L1903 — Spell name → `{book, level, runes}` (spells.json).
- `runeSources` (let) — approx. L1904 — Elemental rune → staves / combination runes that supply it (rune_sources.json).
- `accessRoutes` (let) — approx. L1905 — Shared area-access routes, e.g. desert, Morytania (access_routes.json).
- `cardVersions` (let) — approx. L1906 — Card → item versions it covers `[{name, page, recipe?}]` (card_versions.json).
- `monsterLocations` (let) — approx. L1907 — NPC card → `{location: access key | null}` plus `_gates` (monster_locations.json).
- `selectedVersion` (let) — approx. L1908 — Version name the user opened (shown as a banner on its card's page).
- `cardAliases` (let) — approx. L1909 — Lowercase item version name → card name, from the catalog's `tcg.variants` (card_aliases.json).
- `collectionLog` (let) — approx. L1910 — Boss name → `{log, items}`; collection-log items mark a boss's uniques (collection_log.json).
- `packCatalog` (let) — approx. L1911 — `{catalogVersion, packSize, packs}` from the server's `/api/packs`.
- `packPools` (let) — approx. L1912 — Pack id → `{tier label: card count}`, built by `_buildPackPools`.
- `equipBySlot` (let) — approx. L1913 — Slot → gear list `[{name, value, is2h, itemIds}]` (equipment_data.json).
- `clueScrollSources` (let) — approx. L1914 — Clue tier → ways to get that clue (clue_scroll_sources.json).
- `clueRewardsByTier` (let) — approx. L1915 — Clue tier → reward item names (inverted from clue_sources.json in `loadData`).
- `clueRewardRarities` (let) — approx. L1916 — Clue tier → {item → rarity fraction} (clue_reward_rarities.json).
- `ingredientInfo` (let) — approx. L1917 — Non-card ingredient → `{production, shops, spawns}` (ingredient_info.json).
- `questsData` (let) — approx. L1918 — Quest name → prerequisites, skill requirements, etc. (quests.json).
- `bmQuestCards` (let) — approx. L1919 — Quest name → card requirement sections (bm_quest_cards.json); miniquests flagged `_miniquest`.
- `allCollections` (let) — approx. L1920 — Account name → `{cardCount, ownedCards, credits, updatedAt, cardTimestamps}` (all_collections.json profiles).
- `cardTimestamps` (let) — approx. L1921 — Card → most recent pull time (ms), cloud accounts only; drives "Recently pulled" sort.
- `cardFirstTimestamps` (let) — approx. L1922 — Card → earliest pull time (ms).
- `clueSteps` (let) — approx. L1923 — Contents of clue_steps.json (steps by type and tier, item index).
- `_currentRsn` (let) — approx. L1926 — The selected account name; localStorage keys for quests are per account.
- `_cqFile` (let) — approx. L1930 — Quest completions read from RuneLite screenshots (synced file).
- `_cqManual` (let) — approx. L1931 — Quest completions you ticked by hand.
- `completedQuests` (let) — approx. L1932 — Union of `_cqFile` and `_cqManual`; the set every quest check reads.

### Slayer wishlist group helper (approx. line 1934)

Adds or removes a whole Slayer task's monsters to the wishlist as one group; despite its name this section also holds quest-completion storage, tab selections, the wishlist state, and the core ownership and image helpers (`isOwned`, `_cardInfo`, `_cardImg`, `_wikiImg`).

- `toggleSlayerWishlistGroup(taskName)` — approx. L1935 — Adds a Slayer task's monster cards to the wishlist as an "any one of these" group (tagging each card's note with the task), or removes the group and those tags; saves and re-renders.
- `_cqFileKey(rsn)` — approx. L1969 — localStorage key for an account's synced quest completions (`cq_file_<rsn>`).
- `_cqManualKey(rsn)` — approx. L1971 — localStorage key for an account's hand-ticked completions (`cq_manual_<rsn>`).
- `startedQuests` (let) — approx. L1975 — Quests you marked as started (used by `partialQuests` gates).
- `_cqStartedKey(rsn)` — approx. L1977 — localStorage key for started quests (`cq_started_<rsn>`).
- `_questStartedOk(q)` — approx. L1979 — True when a quest is done, marked started, or completable now (`_questOk`).
- `toggleQuestStarted(name)` — approx. L1981 — Marks/unmarks a quest as started, saves, resets the completable cache and re-renders the quest list and detail.
- `_diaryOk(key)` — approx. L1989 — True when an Achievement Diary tier ("Morytania Hard") has every task ticked on the Diaries tab.
- `_saveCq()` — approx. L1997 — Saves file, manual and combined quest completions to localStorage.
- `_loadManualForRsn(rsn)` — approx. L2004 — Switches to an account's stored quest completions and started quests.
- `toggleQuestDone(name)` — approx. L2015 — Marks/unmarks a quest as complete by hand, saves and re-renders.
- `allCards` (let) — approx. L2030 — Every card shown in the sidebar list `{name, type, cats?, tier?}` (built by `buildCardList`).
- `selected, selectedType` (let) — approx. L2031 — The card open on the Cards tab and its type (monster / npc / item / clue / ingredient).
- `activeTab` (let) — approx. L2032 — The current tab id (starts 'cards').
- `selectedSkill` (let) — approx. L2033 — Skill open on the Skilling tab.
- `selectedQuest` (let) — approx. L2034 — Quest open on the Questing tab.
- `selectedPack` (let) — approx. L2035 — Pack open on the Packs tab.
- `selectedBoss` (let) — approx. L2036 — Boss open on the Bosses tab.
- `bossFilter` (let) — approx. L2037 — Bosses-tab category filter ('all' by default).
- `bossSearch` (let) — approx. L2038 — Bosses-tab search text.
- `selectedDiary` (let) — approx. L2039 — Diary area open on the Diaries tab.
- `selectedDiaryTier` (let) — approx. L2040 — Diary tier expanded in the detail pane.
- `diarySearch` (let) — approx. L2041 — Diaries-tab search text.
- `wishlist` (let) — approx. L2042 — Map card name → `{note}` of starred cards.
- `wishlistedQuests` (let) — approx. L2043 — Quests added to the wishlist in bulk.
- `wishlistQuestRec` (let) — approx. L2044 — Of those, quests wishlisted with their optional/recommended cards too.
- `wishlistGroups` (let) — approx. L2045 — "Any one of these" wishlist groups `[{name, cards}]` (e.g. Slayer tasks).
- `wishlistedClueSteps` (let) — approx. L2046 — Starred clue steps `[{type, tier, text, items}]`.
- `_wishlistTipCards` (let) — approx. L2047 — Sorted unowned wishlist targets, kept fresh by `renderWishlist` for pack hover tips.
- `_lastSourceMtime` (let) — approx. L2048 — Newest RuneLite save-file time seen at the last refresh.
- `_refreshInProgress` (let) — approx. L2049 — Guard so two refreshes don't run at once.
- `skills` (let) — approx. L2052 — Skill → level for all 24 skills (incl. Sailing); filled from hiscores, or random in simulation.
- `owned` (let) — approx. L2060 — Set of owned card names, lowercase.
- `isOwned(name)` — approx. L2064 — Do you own this card? Case-insensitive; an item version counts for its card through `cardAliases` ("Silver sickle (b)" → Silver sickle). Used by nearly every check on the page.
- `_cardLcMap` (let) — approx. L2074 — Lazy lowercase name → `{exact, type}` map over monster_drops and item_sources keys.
- `_cardInfo(name)` — approx. L2075 — Case-insensitive card lookup → `{exact, type: 'monster'|'item'}` or null; resolves item versions to their card.
- `_isCard(name)` — approx. L2087 — True when the name (or version) is a TCG card; things without a card are never restricted.
- `_imgRetry(img, fallback)` — approx. L2089 — On an image error, retries once with a cache-busting query, then calls the fallback.
- `_WIKI_IMG_PREFIX` (const) — approx. L2096 — `https://oldschool.runescape.wiki/images/`.
- `_wikiImg` (const arrow) — approx. L2097 — Rewrites a wiki image URL to the server's `/wikiimg/` proxy (disk cache, wiki → RuneLite sprite fallback) when served over http; unchanged when opened as a file. A document-level `error` listener just below (approx. L2105) retries a failed `/wikiimg/` image directly from the wiki once, then hides it instead of showing a broken box.
- `_cardImg(name)` — approx. L2113 — Image URL for a card or version: over http the card's own art from osrs-tcg.net (`cardDetails[].imagePath`, served via `/images/**`), else the version's or card's wiki image through `_wikiImg`.
- `_questLabelHtml` (const arrow) — approx. L2123 — Turns "Quest: X" / "Quest started: X" labels into the quest star icon + text (escaped).
- `questIcon(size=15)` — approx. L2125 — HTML for the blue quest-point icon (local assets/icons/Quest_point_icon.png), falling back to the text "Quest: ".
- `_cardImgRaw(name)` — approx. L2130 — The raw (wiki) image URL for a card or version from card_details.json / card_versions.json, without proxying.
- `cleanSpawnText(s)` — approx. L2144 — Tidies wiki spawn text ("1 st floor 2 nd floor" → "1st floor").
- `escHtml(str)` — approx. L2153 — Escapes &, <, >, quotes for safe HTML.
- `wikiLink(name)` — approx. L2158 — HTML for a small "↗ wiki" link to the item's OSRS Wiki page (strips a disambiguation suffix).
- `toggleOwned(name)` — approx. L2168 — Flips a card's owned state (simulation / testing) and re-renders the detail.
- `reroll()` — approx. L2175 — "Re-roll" button: makes a new random simulated account and refreshes.
- `updateSimBar()` — approx. L2182 — Writes the simulated-account summary into `#sim-summary`: the real "N cards owned (P%)" (P = share of `_simPoolSize`) plus levels.
- `_updateSortVisibility()` — approx. L2191 — Shows the "Recently pulled" sort only when pull timestamps exist; borrows timestamps from the matching all_collections.json profile (≥90% card overlap) when my_collection.json has none.
- `loadCollection()` — approx. L2211 — Loads output/my_collection.json as the owned set (real collection); if missing, makes a random simulated account.

### Collection switcher (approx. line 2228)

Switches the page between your RuneLite accounts (or a simulated one).

- `switchCollection(rsn)` — approx. L2232 — Switches the owned cards to an account from `allCollections`, clears caches, starts/stops live sync, and re-renders whichever tab is active; shows a hint if the account isn't decoded yet.
- `populateAccountDropdown(accounts)` — approx. L2264 — Fills the `#rsn-input` account dropdown with `name (card count)` options, keeping the current selection when possible.
- `onAccountChange(rsn)` — approx. L2288 — Dropdown handler: loads that account's quest ticks, switches collection, looks up hiscore levels and syncs quests from screenshots.
- `_simPoolSize` (let) — approx. L2297 — How many card names `simulateRandom` drew from; the denominator for the sim bar's owned share.
- `simulateRandom()` — approx. L2298 — Makes a random test account: levels 1–99 and ~15% of all cards owned; records the pool size in `_simPoolSize`.

### Data loading (approx. line 2317)

Loads every data file when the page opens and builds the indexes the tabs use; shows a "needs a local server" message if it can't.

- `loadData()` — approx. L2320 — Startup: fetches (cache-busted) all JSON data in parallel: output/ monster_drops, item_sources, card_categories, card_details, quests, equipment_data, food_data, bm_quest_cards, completed_quests, all_collections, clue_steps, boss_loot, collection_log, diaries, card_aliases, spells, rune_sources, access_routes, card_versions, bosses, slayer, monster_locations, skilling, recipes, method_icons, shop_owners; plus scripts/ clue_scroll_sources, clue_sources, clue_reward_rarities, ingredient_info, location_requirements. Then runs `_expandReq` on skilling/quest/boss/slayer requirements, builds diary/boss indexes, preps clue steps, runs `_validateDataNames()` (`[data check]` warnings), applies completed_quests.json only if its player tag matches, loads the collection, builds the card list and wishlist, fetches `/api/packs`, fills the account dropdown and calls `refreshAll()`. No automatic polling (it hit the TCG cloud rate limit).
- `CLUE_TIER_CONFIG` (const) — approx. L2473 — Label and colours per clue tier.
- `CLUE_TIER_ORDER` (const) — approx. L2481 — Tier order beginner → master.
- `buildCardList()` — approx. L2484 — Clears and rebuilds `allCards`: monsters/NPCs from monster_drops (monster if it has a combat level), item cards from item_sources with categories (Currency, Food or card_categories), plus six virtual "Clue scroll (tier)" cards at the top; then renders the list.
- `filterCards()` — approx. L2514 — Applies the sidebar search, owned filter, category filter, pack (set) filter and sort to `allCards` and re-renders the list.
- `CURRENCY_NAMES` (const) — approx. L2563 — Items always shown under Currency (Coins, Tokkul, Mark of grace, tickets…).
- `CAT_ABBR` (const) — approx. L2572 — Short category badge text for the sidebar (Wpn, Arm, Pot…).
- `renderList(cards, sortBy)` — approx. L2579 — Draws the sidebar card list: icon, name, a badge (category, +HP for food, NPC, combat level, clue tier) and owned styling; clicking calls `showCard`.

### Skill levels (approx. line 2623)

Reads your skill levels and combat level.

- `getLevel(skill)` — approx. L2624 — Your level in a skill (default 1).
- `getCombatLevel()` — approx. L2626 — OSRS combat level from current stats (Hitpoints defaults to 10).

### Cross-tab navigation history (approx. line 2635)

Makes the Back and Forward buttons work across tabs.

- `navHistory` (let) — approx. L2637 — Stack of earlier page states (max 50).
- `navForward` (let) — approx. L2638 — Stack of states for Forward.
- `captureState()` — approx. L2641 — Snapshot of the current tab and selections (card, skill, quest, pack, boss, slayer, clue).
- `pushHistoryEntry()` — approx. L2647 — Saves the current state onto Back history and clears Forward.
- `updateNavButtons()` — approx. L2658 — Enables/disables the Back and Forward buttons.
- `navigate(state)` — approx. L2666 — Restores a saved state: renders its tab and re-opens the skill / quest / pack / slayer task / clue / boss / card.
- `navigateBack()` — approx. L2705 — Back button: go to the previous state.
- `navigateForward()` — approx. L2713 — Forward button: go to the next state.

### Card display (approx. line 2720)

Opens a card's page on the Cards tab and picks the right view (monster, item, clue, ingredient).

- `showCard(name, type, push=true)` — approx. L2722 — Opens a card: clue scroll cards go to the Clues tab (`showClue`); a version opens its card's page with `selectedVersion` set; switches to the Cards tab, filters the list and renders.
- `refreshDetail(resetScroll=false)` — approx. L2737 — Re-renders the right pane for the current selection: `renderMonster`, `renderClueScroll`, `renderIngredient` or `renderItem` (or the Clues / Packs overview), keeping scroll position.
- `rarityClass(r)` — approx. L2753 — CSS class for a rarity badge (`rarity-Very-Rare`…).
- `fractionToRarity(frac)` — approx. L2756 — Converts "1/128" to a wiki rarity tier: Always, Common ≤1/25, Uncommon <1/100, Rare <1/1000, else Very Rare (same buckets as rarity_mapper.py).

### Rarity helpers (approx. line 2770)

Ranks and compares drop rates so the best way to get an item is shown first.

- `RARITY_RANK` (const) — approx. L2771 — Rarity label → rank (Always 0 … Extremely Rare 5).
- `fractionValue(f)` — approx. L2773 — "N/D" → numeric probability (1 when unknown).
- `dedupeMonsters(list)` — approx. L2783 — Keeps one entry per monster card, the most common rate (rank, then fraction).

### Progress pill HTML (approx. line 2799)

The small "12 / 40" bar shown on drop tables and lists.

- `progressPill(count, total, isRdt)` — approx. L2801 — HTML for a count / total pill with a fill bar (green when complete; blue style for the rare drop table).

### Drop row HTML (clickable to toggle owned) (approx. line 2817)

One row of a drop table: owned tick, name, rarity and rate.

- `monsterReqTags(monsterData)` — approx. L2820 — Small inline tags like "Slay 85 ✓" / "Sail 75 ✗" for a monster's Slayer or Sailing level requirement.
- `dropRowHtml(cardName, rarity, fraction, isRdt, note)` — approx. L2837 — HTML for one drop-table row: owned/locked/rare-drop-table indicator, name with req tags, rarity badge, fraction and wishlist star; clicking opens the card.

### Monster view (approx. line 2857)

Helpers for monster pages (the main `renderMonster` lives later in the file).

- `dedupeDrops(drops)` — approx. L2861 — Keeps one drop per card, the highest rate (some pages have several drop tables, e.g. Scurrius).

### Pack acquisition helpers (approx. line 2877)

Shows which TCG packs can contain a card and how big its pool is.

- `_buildPackPools()` — approx. L2880 — Builds `packPools`: per single pack, count of cards per tier, using card_details regions/tier and card_categories labels against each pack's category filters (Standard = all cards).
- `_cardInPack(name, pack)` — approx. L2912 — True when a card can come from a pack (pack has no filter, or the card's region/label matches).
- `packAcquisitionHtml(name)` — approx. L2924 — The "Pack Acquisition" table on a card page: each pack that can give it, price, and same-tier pool / total pool size (smaller = better odds); pack names link to the Packs tab.

### Wishlist (approx. line 2955)
The Wishlist tab: the cards, quests, card groups and clue steps you've starred, which ones you still miss, and which packs give the best chance at them. Saved in the browser (`localStorage` key `tcg_wishlist`, format v2).

- `_questWishCards(qn, includeRec, needOnly)` — approx. L2959 — The cards a starred quest adds to the wishlist; reads `bmQuestCards[qn].sections[].requirements`, optionally includes optional/recommended ones (`wishlistQuestRec`), and with `needOnly` skips requirements already met (`_reqMet`). Unique, requirement order.
- `_questWishUnits(qn, includeRec)` — approx. L2972 — A quest's requirements as wishlist "units" `{label, cards, any, met}` (an "any of" list is one unit); used by the wishlist quest sections.
- `_questMissingUnits(qn, includeRec)` — approx. L2986 — How many things are still missing for a quest, counting an "any of"/routed requirement once and an "all of" list per card; skips requirements already wishlisted.
- `_wishlistedCardSet()` — approx. L3000 — Every card name on the wishlist from any source (single stars, starred quests, groups), owned or not.
- `_wishlistUnownedTargets()` — approx. L3010 — Every unowned card you still need across all wishlist sources (stars, unmet quest requirements, unsatisfied groups, clue steps); feeds the pack suggestions.
- `_wishlistPackRecs(targets)` — approx. L3036 — For each normal (non-`_large`) pack, counts how many target cards are in its pool (`_cardInPack`); returns `[{id,name,thumbnail,count,totalPool,cards}]` sorted best first.
- `_placeTip(tip, rect)` — approx. L3055 — Shared hover-popup placement: puts a popup below the element if it fits, else above, else left/right, always clamped inside the window (measures at full width first). Used by the card-grid, pack and location hovers.
- `_cardGridTipAttrs(cards, caption)` — approx. L3077 — Returns HTML attributes that make any element show a hover grid of card images (owned bright and first, rest dimmed), via `_showCardGridTip`.
- `_cardRowsTipAttrs(rows, caption)` — approx. L3083 — Same hover popup but one row per option (e.g. each Barrows brother + set pieces); a row whose `need` cards are all owned shows as complete.
- `_textTipAttrs(text)` — approx. L3088 — Same hover popup with plain text only (used for things with no card image, e.g. warm-clothing hovers).
- `_showCardGridTip(el)` — approx. L3092 — Builds and shows the shared `#_card-grid-tip` popup from an element's `data-tipcards` / `data-tiprows` / `data-tiptext`, positioned with `_placeTip`.
- `_hideCardGridTip()` — approx. L3137 — Hides the shared card-grid popup.
- `_showPackTip(event, el)` — approx. L3143 — On hovering a pack in the wishlist's pack suggestions, shows which wishlist cards (`_wishlistTipCards`) that pack can give, with an "N/M wishlist cards can come from this pack" caption; grid cells resize to fit.
- `_hidePackTip(el)` — approx. L3194 — Hides the pack hover popup and resets the pack tile border.
- `_loadWishlist()` — approx. L3202 — Loads the wishlist (cards+notes, quests, quests-with-recommended, groups, clue steps) from `localStorage['tcg_wishlist']`; migrates the old v1 array format.
- `_saveWishlist()` — approx. L3224 — Writes the whole wishlist back to `localStorage['tcg_wishlist']` as `{v:2, items, quests, questsRec, groups, clueSteps}`.
- `_wlClueStepRes(s)` — approx. L3239 — For a starred clue step, finds the live step (`_clueStepFind`) and evaluates it with `_clueStepOk`; null if the step no longer exists.
- `_wlClueStepReady(s)` — approx. L3244 — Whether a starred clue step is doable now (full requirement model, or "all items owned" for old stars).
- `_isClueStepWishlisted(text)` — approx. L3249 — True if a clue step (by its text) is starred.
- `_removeClueStepCards(step)` — approx. L3254 — When a clue step is un-starred, removes its "<tier> clue" tag from the cards it added (deleting cards left with no tag).
- `_toggleClueStepWish(el)` — approx. L3269 — Star/un-star click handler for a clue step (reads `data-step-*` attributes); adds/removes the step and its cards, saves, re-renders.
- `removeClueStep(text)` — approx. L3303 — Removes a starred clue step from the wishlist page (✕ button) and its card tags.
- `_clueCardChipHtml(name, navType)` — approx. L3313 — A clue-step card chip: ✓/✗ ownership colours, click to open the card, with its own ★ wishlist toggle on the right.
- `_rowWishStar(name, owned, note)` — approx. L3335 — Small inline ☆/★ used in drop tables, quest requirement rows etc.; with a `note` tag it toggles only that page's contribution; stops click propagation.
- `toggleWishlist(name, note)` — approx. L3358 — Adds/removes a card on the wishlist; with a `note`, adds/removes just that context tag and keeps others. Saves and re-renders.
- `_buildAutoNote(name)` — approx. L3396 — Builds the comma-separated note for a newly added card from the wishlisted quests, groups and clue steps it belongs to.
- `_wlSearchInput(q)` — approx. L3415 — Wishlist left panel: searches cards and quests by name and renders clickable results (star toggles) into `#wl-search-results`.
- `_wlQuestToggle(questName)` — approx. L3481 — Left-panel quest result click: wishlists or removes the quest, then refreshes the results.
- `_wlSearchToggle(name)` — approx. L3492 — Left-panel card result click: adds (with auto note) or removes the card.
- `removeFromWishlist(name)` — approx. L3503 — Removes one card from the wishlist (tile ✕).
- `removeWishlistTag(name, tag)` — approx. L3510 — Removes one tag from a card's note (deleting the card if no tags remain).
- `removeQuestFromWishlist(questName)` — approx. L3522 — Un-stars a quest and strips its name from the notes of cards it added (removing cards left with no tags).
- `_noteRemoveTag(note, tag)` — approx. L3540 — Removes one tag from a comma-separated note string.
- `clearWishlist()` — approx. L3545 — "Clear all": confirms with a dialog listing what will go (cards/quests/groups/clue steps), then empties everything (including the `wishlistQuestRec` "required + recommended" flag).
- `saveWishlistNote(name, note)` — approx. L3565 — Saves a free-text note on a wishlisted card.
- `_notePopoverCloseHandler` (let) — approx. L3571 — The document click handler that closes the note popover (kept so it can be removed).
- `openNotePopover(btn, cardName)` — approx. L3574 — Opens a small fixed popover with a text box to edit a wishlisted card's note.
- `_closeNotePopover()` — approx. L3618 — Removes the note popover and its outside-click handler.
- `_saveNotePopover(cardName)` — approx. L3628 — Saves the popover's text as the note, closes it, re-renders the wishlist.
- `openGroupEditor(gi)` — approx. L3638 — Opens the overlay for creating (gi = -1) or editing a wishlist card group ("any one of these cards"); working state in `window._geCards` / `window._geIdx`.
- `_geRenderSearch(q)` — approx. L3677 — Group editor: shows up to 25 matching cards (2+ letters) not already in the group.
- `_geAddCard(name)` — approx. L3695 — Group editor: adds a card to the group being edited.
- `_geRemoveCard(name)` — approx. L3704 — Group editor: removes a card from the group being edited.
- `_geRenderChips()` — approx. L3712 — Group editor: renders the chosen cards as ✓/✗ chips and the count.
- `closeGroupEditor()` — approx. L3727 — Closes the group editor without saving.
- `saveGroupEditor(gi)` — approx. L3734 — Saves the group (new or edited), retagging card notes from the old group name to the new one.
- `removeGroup(gi)` — approx. L3772 — Deletes a group and strips its name from card notes.
- `wishlistQuest(questName, includeRec)` — approx. L3789 — Stars a quest and wishlists what it still needs requirement by requirement ("any of" lists become one group, "all of" lists add each missing card); with `includeRec` also optional/recommended cards. Returns cards added.
- `_EQUIP_CATS` (const) — approx. L3817 — Set of card-category names counted as "equipment" for wishlist grouping.
- `_wlCategory(name)` — approx. L3819 — Classifies a card for the wishlist layout: monster / npc / tool / equipment / currency / other (from `monsterDrops` and `cardCategories`).
- `_cardType(name)` — approx. L3829 — A card's type ('item'/'monster'/…) from `allCards`, guessing from `monsterDrops` if absent.
- `renderWishlist()` — approx. L3837 — Renders the Wishlist tab: main page plus the left-panel search, so removals show up in both.
- `_renderWishlistMain()` — approx. L3844 — Builds the main wishlist page into `#wishlist-content`: empty-state help, pack suggestions, starred quest sections (requirements met/missing), group sections, individual cards by category, starred clue steps.
- `renderWishlistList()` — approx. L4130 — Backwards-compatible alias for `renderWishlist()` (called from navigation/account switch).
- `showWishlistCard(name, type, push)` — approx. L4133 — Opens a card's detail from the wishlist (wraps `showCard`).

### Pack tab (approx. line 4137)
The Packs tab: each TCG pack with the cards it can contain, what you own of it, by rarity tier.

- `PACK_TIER_ORDER` (const) — approx. L4139 — Rarity tier order: Common → Uncommon → Rare → Epic → Legendary → Mythic → Godly.
- `_getPackCards(pack)` — approx. L4142 — All real cards (those with a tier in `cardDetails`) in a pack's pool, via `_cardInPack`.
- `renderPackList()` — approx. L4151 — Renders the Packs left pane (`#pack-list-pane`): an "Overview" entry plus each single pack with owned/total counts; highlights `selectedPack`.
- `showPackDetail(packId, filter, push, tier)` — approx. L4182 — Shows one pack in `#pack-detail-pane`: thumbnail (from `packCatalog` `thumbnail` URL), owned/total stats per tier, and card chips grouped by tier with an all/owned/missing filter; pushes history.

### Packs overview (no pack selected) (approx. line 4284)
The Packs home page: which packs and cards would help you most right now, based on everything you're working toward.

- `_PACK_NEED_SOURCES` (const) — approx. L4289 — The "needs" sources and their weights/caps for scoring cards: Wishlist (5), Quests, Bosses, Diaries, Clues, Skilling (starter sets).
- `_packHomeFocus` (let) — approx. L4297 — Which need source the Packs overview is focused on ('all' or one key).
- `_packNeeds()` — approx. L4299 — Builds Map card → `{value, src}` of unowned, pack-eligible cards that unlock something, from wishlist targets, quest/boss/diary/clue blockers and `_skillStarter` sets; value = weighted, capped sum (extra weight when a card is the last one needed).
- `_packNeedValue(e, focus)` — approx. L4345 — A card's need score for the current focus (total, or one source's points).
- `_packNeedWhy(e)` — approx. L4347 — Short text explaining why a card is needed ("Quests: 3 (last card ×1) · Wishlist").
- `_myCredits()` — approx. L4356 — The current account's TCG credits from `allCollections`.
- `setPackHomeFocus(v)` — approx. L4361 — Changes the overview focus and re-renders it.
- `showPackOverview()` — approx. L4364 — Clears the selected pack and shows the overview (pushes history).
- `_renderPackHome()` — approx. L4372 — Renders the Packs overview: best packs (uniform-pool estimate of needed cards per pack), most valuable cards with their most focused pack, collection-by-pack tier bars, collection by tier; keeps scroll position.
- `tierBadgeHtml(name)` — approx. L4510 — A small coloured rarity-tier badge for a card (from `cardDetails[name].tier`).
- `renderMonster(name, container)` — approx. L4517 — The monster/NPC card detail view: stats, main and rare-drop-table drops (owned first), where it's found and the area access each location needs (`monster_locations.json`), Slayer info (`slayer.json`), quests needing it, clue-step usage, boss and diary cross-links.

### Production card HTML (approx. line 4714)
How a "made by" recipe box is drawn: skill level, ingredients you own or not, tools and the facility you need.

- `FACILITY_NOTES` (const) — approx. L4719 — Facility (e.g. "Air Altar") → the items/routes that get you there (talisman, tiara, Abyss); card names get ✓/✗.
- `FACILITY_NPCS` (const) — approx. L4739 — Facilities that are an NPC doing the work (Aggie, Tannery, Sawmill-type services…), where you still supply the ingredients.
- `facilityNote(f)` — approx. L4744 — HTML note for a recipe's facility: the NPC/shopkeeper card chips with ✓/✗ (`_facilityCards`, `_facilityOk`) or the altar access options; null for none.

### Non-card ingredient row (navigates to its own page) (approx. line 4778)
Ingredients that have no TCG card (so no restriction) still get a clickable row with their own info page.

- `renderNonCardIngredient(itemName, quantity)` — approx. L4779 — A grey "○ no card" ingredient row that opens the ingredient detail page.
- `_shopReachLabel(seller)` — approx. L4792 — Explains why you can't reach a shop: its area access (`accessRoutes`) or location gate quests (`monsterLocations._gates`), using `SHOP_OWNERS`.
- `_shopRowHtml(shop)` — approx. L4803 — One shop row on card/ingredient pages: seller, the shopkeeper's NPC card ✓/✗ (or "can't reach"), price and currency card ✓/✗ (from `_shopStatus`).

### Ingredient detail page (approx. line 4833)
The page for a non-card item: how to make it, where to buy it, where it spawns, and what it is used in.

- `renderIngredient(name, container)` — approx. L4834 — Renders a non-card ingredient's page from `ingredientInfo` (production, shops, spawns) plus `_cardSkillingHtml` sections and a wiki link.
- `_recIdx` (let) — approx. L4997 — Cached recipe index (built once per load by `_recipeIndex`).
- `_recipeIndex()` — approx. L4999 — Indexes all production recipes (`_productionRecipes()`, from recipes.json + skilling.json) by output, ingredient and skill, filing each under the raw name and the card it's a version of; skips 0-xp steps.
- `_goSkill(sk)` — approx. L5014 — Jumps to the Skilling tab on a given skill.
- `_cardSkillingHtml(name, {madeBy})` — approx. L5016 — The "Made by", "Used to make" and "Training methods" sections for an item or ingredient page, tagged for `_orderSections`.
- `_SECTION_ORDER` (const) — approx. L5066 — Standard order of sections on card pages: top, versions, creation, obtain, combat, clues, uses.
- `_orderSections(html)` — approx. L5068 — Splits page HTML on `\u0001group\u0001` markers and reassembles it in `_SECTION_ORDER`.
- `_mergeRecipeBoxes(made)` — approx. L5076 — Merges recipes for the same output that differ only in facility or one ingredient (e.g. arrow shafts from each log) into one box with an "any of" slot.
- `_recipeCompactHtml(r, cardKey)` — approx. L5120 — One recipe as a compact row: version, skill level, ingredient chips ✓/✗ (no-card ones grey), tools, facility.
- `renderProduction(prod, opts)` — approx. L5141 — The full recipe box: skill/level check against your level (`getLevel`), ingredients with ownership, output quantity, tools and facility note.

### Clue Scroll view (approx. line 5239)
The detail page for a clue tier: how to get the clue, which steps you can do, and the rewards.

- `_CLUE_TIER_COLOR` (const) — approx. L5241 — Colour per clue tier (Beginner…Master).
- `_cluePct(p)` — approx. L5243 — Formats a probability as a percentage ("<0.1%" for tiny ones).
- `_clueStepCol(res)` — approx. L5249 — Border colour for a step: green doable, amber partly (random ask), red blocked.
- `_clueMissHtml(res)` — approx. L5251 — The "✗ Missing: Spade · [quest icon] Regicide" line under a step; quests are clickable (`_navToQuest`).
- `_clueNavType` (const) — approx. L5260 — Arrow function: 'monster' or 'item' navigation type for a clue card.
- `_clueReqChipsHtml(step, skipCards)` — approx. L5262 — Card chips for a step's required items/NPCs; long "any of" lists collapse into a hover grid.
- `_clueStepCards(step)` — approx. L5277 — Cards a starred step adds to the wishlist (its short requirement lists, 3 or fewer options).
- `_clueStarHtml(type, tier, text, items)` — approx. L5281 — The ☆/★ toggle for a clue step (data attributes read by `_toggleClueStepWish`).
- `_clueDigListHtml(type, capTier, steps, title, blurb)` — approx. L5291 — Collapsible per-step list for Map / Coordinate / Hot-cold steps, with doable count and missing lines.
- `renderClueScroll(tier, container)` — approx. L5322 — The clue tier page: step achievability (`_clueTierStatus`), where to get the clue (clue_scroll_sources.json), rewards (owned first), and step sections (emote, Sherlock, Falo, cryptic, anagram/cipher, map/coordinate/hot-cold).

### Item view (approx. line 5616)
The item card detail page: every way to get the item, what it's used for, and its versions.

- `_recipeHtml(rec)` — approx. L5619 — One-line card-version recipe ("Fishing 75 · Cooking 85 · Dragon harpoon + …") with level and material ✓/✗.
- `_cardVersionsHtml(card, part)` — approx. L5635 — Item versions box from `cardVersions` (card_versions.json): the selected version banner and/or the list of versions with icons and recipes.
- `_curatedGatherCardsHtml(name)` — approx. L5661 — "Gathering" boxes for curated skilling methods (skilling.json) that yield this card: skill+level, method link, requirement/quest/area ✓/✗ (`_curatedGatherStatus`).
- `renderItem(name, container)` — approx. L5692 — The item card detail view: tool tiers, production (made by / used to make / training), ground spawns, clue reward tiers, shops and rewards, monster and rare-drop-table drops, boss rewards, quest sources, quests that need it, clue-step usage, boss and diary cross-links (data from `itemSources`).

### Clue step usage section (item detail view) (approx. line 6075)
On an item's page, the clue steps that need that item.

- `clueStepUsageHtml(itemName)` — approx. L6077 — Lists every emote/Sherlock/Falo/other clue step requiring the item (`clueSteps.itemIndex`), grouped by tier with stars.

### Clue step NPC usage (monster/NPC card detail view) (approx. line 6238)
On an NPC's page, the clue steps where you talk to or fight that NPC.

- `clueStepNpcHtml(npcName)` — approx. L6240 — Clue steps involving the NPC (`clueSteps.npcIndex`; Uri gets every emote step).
- `_clueNpcGroupsHtml(npcName, steps, one, TIER_COLOR)` — approx. L6357 — Groups an NPC's clue steps by type+tier; short groups list each step, long ones collapse to one line.

### Tool tier rows HTML (approx. line 6394)
The pickaxe/axe-style tool ladder: which tool tiers you own and can use at your level.

- `renderToolTiers(tiers, skillName)` — approx. L6396 — Rows for each tool tier with owned/level status, marking the best one you own and can use.

### Live sync — disabled: refresh only on page load or ↻ Refresh (approx. line 6436)
Leftover hook for automatic refresh of cloud accounts; switched off (cloud API rate limits), so the collection only refreshes on page load or the ↻ Refresh button.

- `_liveStateHash` (let) — approx. L6437 — Last seen cloud state hash (baseline for change detection).
- `_liveTimer` (let) — approx. L6438 — Interval handle for live polling (never set now; `_stopLiveSync` still clears it).
- `_startLiveSync(rsn)` — approx. L6441 — Stub: stops any old timer (`_stopLiveSync`) and returns. The old inner `_poll` (cloud revision polling) was removed; live sync is disabled because of cloud API rate limits.
- `_stopLiveSync()` — approx. L6450 — Clears the poll timer and baseline hash.

### Refresh all — collection + levels + quest sync (approx. line 6455)
The ↻ Refresh button: reloads your cards, skill levels and completed quests in one go.

- `refreshAll()` — approx. L6456 — Runs `refreshCollection`, `lookupLevels` and `syncQuestsFromScreenshots` in parallel, then reloads the account dropdown (`GET /api/accounts/list`) and records `GET /api/collection/source-mtime`.

### Live collection refresh (requires server.py) (approx. line 6487)
Re-reads which cards you own from RuneLite / the cloud via the local server.

- `refreshCollection()` — approx. L6488 — `GET /api/collection/refresh[?player=]`: replaces `owned`, card timestamps and the `allCollections` entry, clears caches, warns (toast) on 401 / 0-card results, re-renders the current view.

### Hiscores level lookup (requires server.py) (approx. line 6548)
Fetches your skill levels from the OSRS HiScores.

- `_levelsRsn` (let) — approx. L6549 — Which account the current levels came from (so levels only go up for the same account).
- `lookupLevels(rsn)` — approx. L6551 — `GET /api/hiscores?player=`: merges levels into `skills`, ignoring lower values for the same account (the resolved `_rsn`, not the raw argument; flaky HiScores replies), clears caches, re-renders.

### Quest sync from RuneLite screenshots (approx. line 6583)
Reads which quests you've completed from RuneLite's quest-list screenshots.

- `syncQuestsFromScreenshots(rsn)` — approx. L6586 — Tries `GET /api/quests/completed?player=`, else falls back to `output/completed_quests.json` (only if its player matches); merges with manually ticked quests (`_cqManual`), saves, re-renders the quest list.

### Tab navigation (approx. line 6655)
Switching between the planner's tabs.

- `switchTab(tab)` — approx. L6656 — Switches tab, pushing a history entry if it changed.
- `_renderTab(tab, resetSelection)` — approx. L6662 — Builds a tab's layout and calls its renderer: cards (`filterCards`), skilling (`renderSkillGrid`/`_renderSkillHome`), questing (`renderQuestList`), packs (`renderPackList`/`_renderPackHome`), wishlist (`renderWishlist`), equipment (`renderEquipmentTab`), bosses (`renderBossList`/`_renderBossHome`), slayer (`renderSlayerList`), clues (`renderClueList`), diaries (`renderDiaryList`/`_renderDiaryHome`), rules (`renderRulesTab`).

### Skilling tab (approx. line 6836)
Shows each skill's level, how many training methods you can use with your cards, and a detail page per skill. Tab entry: `_renderTab('skilling')` calls `renderSkillGrid()` then `showSkillDetail()` (a skill selected) or `_renderSkillHome()` (overview). This section also holds page-wide helpers (skill icons, location hover tips) and the boss loot / quest reverse lookups.
- `SKILL_ORDER` (const) — approx. L6839 — The 24 skills in in-game order (3-column grid), used to lay out the skill grid and the Skilling home table.
- `SKILL_ICON_NAME` (const) — approx. L6851 — Skill name → icon file name where they differ (Runecrafting → "Runecraft").
- `_WIKI` (const) — approx. L6854 — Base URL of OSRS Wiki images (`https://oldschool.runescape.wiki/images/`).
- `skillIcon(skill, size=16)` — approx. L6856 — Small skill icon `<img>`; loads the local file `assets/icons/<Skill>_icon.png` (no network).
- `_SKILL_LVL_RE` (const) — approx. L6866 — Regex matching "<Skill> <level>" text (e.g. "Crafting 49") so an icon can be put in front of it.
- `_iconizeSkillLevels(root)` — approx. L6868 — Puts a skill icon in front of every "Skill N" text in a pane, so no renderer has to build icons itself; walks text nodes, skips inputs/scripts and `[data-noskillicon]`.
- `_locHoverRe` (let) — approx. L6900 — Cached regex of every gated place name from location_requirements.json (with `_locHoverKeys`, the name count it was built for).
- `_showLocTip(el)` — approx. L6902 — Hover popup for an underlined place name: each entry requirement with ✓/✗ for this account; reuses the `_card-grid-tip` popup and `_placeTip()`.
- `_hoverLocations(root)` — approx. L6924 — Underlines every gated place name found as text in a pane (green dotted = you can enter, red = not) and wires `_showLocTip` / `_hideCardGridTip` on hover.
- `_skIconQueued` (let) — approx. L6956 — Flag for the page-wide MutationObserver that runs `_iconizeSkillLevels` + `_hoverLocations` once per animation frame on `#detail`, `*-detail-pane` and `#rules-panel`.
- `BOSS_DATA` (let) — approx. L6972 — All bosses/raids/minigames; generated (generate_bosses.py + boss_curated.json → output/bosses.json), loaded at startup in the Data loading section, requirements expanded with `_expandReq`, names checked by `_validateDataNames`.
- `_RARITY_RANK` (const) — approx. L6980 — Sort order for loot rarities (Unique first … Conditional last).
- `_lootTip(d)` — approx. L6982 — Tooltip text for a boss loot row: "share of uniques" or wiki rate (+ per-chest rate) plus wiki notes.
- `_bossLoot(boss)` — approx. L6990 — A boss's loot table: the chest table from boss_loot.json if it has one, else its main monster's drops from monster_drops.json (`boss.lootFrom` / enemy requirement / first monster) plus wiki extras.
- `_bossLootByItem` (let) — approx. L7015 — Lazy index: item card (lowercase) → boss chest rewards that give it.
- `_bossRewardsFor(itemName)` — approx. L7017 — Which boss chests reward an item (for "Boss rewards" on item pages); builds `_bossLootByItem` from boss_loot.json on first use.
- `BOSS_BY_CARD` (var) — approx. L7029 — Reverse lookup card (lowercase) → [{bossName, role}] for the "Boss Encounters" cross-links on card pages.
- `_buildBossByCard()` — approx. L7031 — Rebuilds `BOSS_BY_CARD` from `BOSS_DATA` (monsters, requirement cards, loot); called after data load.
- `_questCardIndex` (let) — approx. L7056 — Lazy index: card name → quests that need it (from bm_quest_cards.json).
- `getQuestCardIndex()` — approx. L7058 — Builds/returns `_questCardIndex` by walking every quest section's requirement cards (`_reqCards`).
- `requiredForQuestsHtml(cardName)` — approx. L7079 — "Required For" section on a card page: each quest needing the card, coloured done / available / locked, clickable to the quest.
- `SPELLBOOK_GATES` (const) — approx. L7104 — What unlocks each non-standard spellbook (Ancient = Desert Treasure I, Lunar = Lunar Diplomacy, Arceuus = reach Kourend).
- `SPELL_ITEM_REQS` (const) — approx. L7110 — Spells that need a specific staff to cast (Iban Blast, god spells, Magic Dart) → accepted staff cards.

### Generated skilling methods (output/skilling.json) (approx. line 7129)
Works out, for every skill, which training methods you can do now, which are one card away, and what else blocks them; feeds the Skilling tab, its "Getting started" and "Recommended" boxes.
- `SKILLING` (let) — approx. L7131 — Wiki-built training methods from output/skilling.json (generate_skilling.py from skilling_curated.json): {skill, name, level, xp, type, requirements, quests, levels, access…}.
- `RECIPES` (let) — approx. L7134 — Every XP-giving production recipe from output/recipes.json (generate_recipes.py), including outputs with no card.
- `METHOD_ICONS` (let) — approx. L7136 — Icons for Skilling rows with no card art, from output/method_icons.json (generate_icons.py).
- `_methodIcon(m)` — approx. L7137 — Picks the icon for a method row: METHOD_ICONS entry (via `_wikiImg` proxy) or the card's art (`_cardImg`).
- `_bestAlt(alts)` — approx. L7145 — Of interchangeable ingredients, the first you can actually use (card owned + obtainable), else the first.
- `_recipeTag(p, recs)` — approx. L7151 — Short label telling apart recipes with the same output (the differing ingredient, or "Superheat Item").
- `_productionRecipes()` — approx. L7163 — The production recipe list: RECIPES, or (if recipes.json is missing) the older card-only `production` data from item_sources.json.
- `_recOutIdx` (let) — approx. L7173 — Index output → recipes (non-internal); with `_ingNeedsMemo` / `_ingNeedsSig` memo for `_ingNeeds`.
- `_recipesMaking(n)` — approx. L7175 — Recipes (not minigame/quest-internal) that produce item `n`.
- `_noDataItem(n)` — approx. L7180 — True if an ingredient has no data of its own (not an item card, not in item_sources / ingredient_info).
- `_ingNeeds(n, seen)` — approx. L7182 — What you still need to obtain a no-data ingredient by making it: {cards, other, why, none}; recursive through recipes, memoised per owned/quests/levels signature.
- `GENERATED_SKILLS` (const) — approx. L7223 — Skills whose methods come entirely from skilling.json (Agility, Thieving, Hunter, Prayer, Firemaking, Ranged, Sailing).
- `_TOOL_SKILL` (const) — approx. L7231 — Tool → its skill (Pickaxe → Mining, Axe → Woodcutting, Harpoon → Fishing).
- `_toolTierCards(tool, lvl)` — approx. L7233 — The tiers of a TOOL_TIERS tool usable at your level (rare tiers last), as card names.
- `_blkQuest` (const) — approx. L7239 — Arrow fn building a quest blocker {kind:'quest', key, label}.
- `_blkArea` (const) — approx. L7240 — Arrow fn building an area blocker (label from access_routes.json).
- `_blkDiary` (const) — approx. L7241 — Arrow fn building a diary blocker ("X Diary").
- `_blkLevel` (const) — approx. L7242 — Arrow fn building a skill-level blocker ("Skill N").
- `_routeOtherBlockers(rt)` — approx. L7244 — For an access route, the non-card parts not yet met (areas, quests, started quests, diaries, levels); null for manual routes.
- `_reqNeedSlots(r)` — approx. L7254 — For one unmet requirement (quest model): the missing card "slots" (each slot = alternatives), whether something other than cards blocks it, and the blockers.
- `_MELEE_SKILLS` (const) — approx. L7282 — Attack / Strength / Defence / Hitpoints (methods are monsters).
- `_bestMethod(avail, skill)` — approx. L7284 — Best available method: highest level then xp; for melee the strongest monster at or below combat level + 10.
- `_STARTER_MONSTERS` (const) — approx. L7291 — Common starter monsters (Chicken, Goblin, Man, Cow, Rat) preferred for new accounts.
- `_starterMonsterRank(m)` — approx. L7293 — Sort rank putting low-level starter monsters first (99 otherwise).
- `_GENERIC_TOOLS` (const) — approx. L7298 — Everyday tools (Hammer, Knife, Tinderbox, Coins…) treated as generic in method requirements.
- `_skillingMethods(skillName)` — approx. L7301 — Turns skilling.json methods for one skill into method rows with status (available / no-card / locked…), missing cards, quest/level/diary blockers.
- `SKILL_UNLOCK_QUESTS` (const) — approx. L7348 — Skills that can't be trained until a quest is done (Herblore = Druidic Ritual, Runecrafting = Rune Mysteries, Sailing = Pandemonium).
- `_skillUnlocked(skill)` — approx. L7350 — True if the skill has no unlock quest or you've done it.
- `getTrainingMethods(skillName)` — approx. L7352 — Main entry: all training methods for a skill, with every method marked locked by the unlock quest when the skill isn't unlocked yet.
- `_getTrainingMethodsRaw(skillName)` — approx. L7364 — The big per-skill builder: generated skills via `_skillingMethods`, gathering from item_sources (tool tiers), Magic spells (spells.json, spellbook gates), melee monsters, production recipes (ingredients, tools, tiaras, facilities), Smithing, Slayer; sorted available first.
- `_combatEval(mName, G, mySlayer)` — approx. L7696 — One monster as a combat target: reachable via monster_locations.json gates, Slayer level, boss gates (`evaluateBoss`); returns status + blockers, null if no combat level.
- `_ownsFightableMonster()` — approx. L7727 — Do you own any monster card you can reach and fight right now?
- `_combatStarterCandidates()` — approx. L7735 — Unowned monsters you could train on as soon as you own their card (reachable, no Slayer/boss lock).
- `_COMBAT_SPELL_RE` (const) — approx. L7756 — Regex recognising combat spells (Strike/Bolt/Blast… and god spells).
- `_skillStarter(skill, ms, combatCands)` — approx. L7758 — Cheapest ways to START a skill: methods at your level with no non-card lock, ranked by missing card slots → {canTrain, best, options}.
- `countAvailableMethods(skillName)` — approx. L7803 — Number of methods with status 'available' (the count on each skill tile).
- `renderSkillGrid()` — approx. L7808 — Draws the left skill grid (icon, level, available-method count, selection highlight).
- `showSkillOverview()` — approx. L7828 — Clicks back to the Skilling overview (history entry, clear selection, `_renderSkillHome`).
- `_starterLast` (let) — approx. L7835 — Last computed starter per skill, used by the ☆ wishlist buttons.
- `_starterTag` (const) — approx. L7837 — Arrow fn giving the wishlist tag "Start <Skill>: <method>".
- `_starterWished(tag)` — approx. L7839 — Is this starter option already on the wishlist (as a group or as tagged cards)?
- `toggleStarterWishlist(skill, i)` — approx. L7844 — ☆ button: adds/removes a starter option's cards (single-card slots as tagged cards, multi-card slots as "any one of" wishlist groups).
- `_slotChipsHtml(slots)` — approx. L7869 — Card chips "A / B / C + D" for card slots; owned alternatives ticked; click opens the card.
- `_starterOptHtml(skill, opt, i)` — approx. L7880 — One starter option line: method name, level, needed card chips and the ☆ button.
- `_starterLineHtml(skill, st)` — approx. L7888 — A skill's starter line on the home table: "✓ can train", "locked — needs quest", "no card-only start", or the first option with an expander for others.
- `_REC_BY_LEVEL` (const) — approx. L7897 — Skills ranked by level, not xp, in recommendations (Magic, Ranged).
- `_recEligible(m)` — approx. L7899 — Can a method be recommended? Excludes one-off / non-repeatable / reward-only / no-source methods and recipes using boss uniques or rare-only drops.
- `_recUniq` (let) — approx. L7911 — Cached set of all collection-log items.
- `_recUniqueItems()` — approx. L7913 — Builds/returns `_recUniq` from collection_log.json.
- `_recRareOnly(c)` — approx. L7918 — True if an item's only source is a Rare/Very rare monster drop (no shop, spawn, gathering, production, clue or activity).
- `_recCardGettable(c)` — approx. L7925 — Is a missing card realistically obtainable (has a known source you could use)? Stops recommending cards you can't get.
- `_recWithHouse(m)` — approx. L7939 — Treats "needs a house" as needing the Coins card (house costs 1,000 coins), so it counts as a card lock.
- `_skillRecommendations(skill, ms)` — approx. L7949 — Top 5 recommended methods: best doable now, plus "one card away" upgrades; dedupes look-alikes; combat uses monsters near your combat level.
- `_recCombatCands(cb)` — approx. L7981 — Combat recommendation candidates: unowned reachable monsters within combat level + 10.
- `_methodOutputCards(m)` — approx. L7999 — The card(s) a gathering/production method yields (to show whether you can use what you gather).
- `_methodOutputChip(m)` — approx. L8006 — Small chip on a method row: "free" (output has no card), owned or missing output card.
- `_skillRecommendHtml(skill, ms)` — approx. L8023 — The "Recommended" box on a skill page, from `_skillRecommendations`.
- `_starterBoxHtml(skill)` — approx. L8046 — The "Getting started" box on a skill page (only when you can't train yet), with ☆ wishlist buttons.
- `_areaRouteTip(key)` — approx. L8056 — Tooltip text for an area blocker: the cheapest access route's missing cards and other needs (access_routes.json).
- `_blockerHtml(b)` — approx. L8073 — Renders one blocker as a link: quest → quest page, area → "Reach X" with route tooltip, diary → diary page, level → text.
- `_renderSkillHome()` — approx. L8086 — Skilling overview pane: per-skill level, methods available, best method now, starter line, and the quests/areas/levels locking the most methods.
- `showSkillDetail(skillName, push=true)` — approx. L8120 — Skill detail pane: Getting started + Recommended boxes, then every method row (icon, level, status, missing cards, blockers, output chip); Slayer shows the master list.

### Bosses tab (approx. line 8284)
Scores each boss as available / partial / locked from your quests, levels and cards.
- `_bossProgress(boss)` — approx. L8288 — Counts met/total for required (quests, levels, requirements; any-of groups once), recommended (optional) and loot requirements.
- `evaluateBoss(boss)` — approx. L8304 — Boss status: 'locked' if a quest, level or access is missing, 'partial' if cards missing, else 'available'; returns missing lists + progress.

### Boss two-pane functions (approx. line 8317)
The Bosses tab list (left) and boss pages (right). Tab entry: `_renderTab('bosses')` → `renderBossList()` + `showBossDetail()` or `_renderBossHome()`.
- `_BOSS_CATEGORIES` (const) — approx. L8319 — List categories: Raids, Waves, Minigames, Skilling, Bosses (sub-groups Low/Mid/High/God Wars/Slayer/Wilderness).
- `_renderBossFilterBtns()` — approx. L8335 — Draws the category filter buttons above the boss list.
- `setBossFilter(key)` — approx. L8348 — Sets `bossFilter`, restyles the buttons, redraws the list.
- `renderBossList()` — approx. L8361 — Left boss list grouped by category with status dots and progress, honouring filter/search.
- `showBossDetail(name)` — approx. L8426 — Boss page: image, requirement rows (same model as Questing), quest/skill prerequisites, loot grouped by rarity with collection-log uniques marked ◆ and owned chips green.
- `_missingLink(r, bossName)` — approx. L8582 — A missing boss requirement as a link: single card → card page; any-of group/routes → boss page with a hover grid of options.

### Slayer tab (approx. line 8593)
Slayer masters and tasks: which masters you can use, which tasks they can assign you, and your chance a task is doable with your cards. Tab entry: `_renderTab('slayer')` → `renderSlayerList()` + `_renderSlayerDetail()`. Data is generated (output/slayer.json from generate_slayer.py + slayer_curated.json), loaded at startup in the Data loading section and checked by `_validateDataNames`. (The old hand-written SLAYER_TASKS / SLAYER_CARD_GATES no longer exist in this range.)
- `SLAYER` (let) — approx. L8599 — Slayer data {masters, tasks, unlocks} from output/slayer.json.
- `selectedSlayer` (let) — approx. L8600 — Current selection {kind:'master'|'task', name} or null (overview).
- `slayerSearch` (let) — approx. L8601 — Search text for the Slayer list.
- `_slayerUnlocks()` — approx. L8603 — Set of ticked Slayer reward unlocks, from localStorage `tcg_slayer_unlocks`.
- `toggleSlayerUnlock(name)` — approx. L8607 — Ticks/unticks a reward unlock (saved in the browser) and redraws.
- `_slCardIndex` (let) — approx. L8614 — Lazy index card (lowercase) → [{task, mon}] for every task monster.
- `_slCardEntries(card)` — approx. L8616 — Slayer task entries a card counts for.
- `_slayerCardFeasible(card)` — approx. L8625 — Owned and killable for Slayer somewhere (reachable location, Slayer level, equipment).
- `_slayerBlockReason(card)` — approx. L8631 — Why an owned card can't be used for Slayer ('' if it can).
- `_slMastersForCard(card)` — approx. L8637 — Slayer master records whose card (or replacement master's card) is this card.
- `_slMasterCard(m)` — approx. L8643 — The card a master needs (the replacement, e.g. after a quest, if that quest is done).
- `_slMasterStatus(m)` — approx. L8648 — Can you use this master? Checks card, combat/Slayer level, quests, area access → {ok, why, card}.
- `_slAssignable(entry)` — approx. L8659 — Can a master assign you this task (Slayer/combat level, quests, ticked reward unlock)?
- `LOC_REQS` (let) — approx. L8675 — Place entry requirements from scripts/location_requirements.json (with `_locIdx` lowercase index, `_locGateMemo`, `_locReviewed`). Same rules as scripts/location_reqs.py.
- `_LOC_GATE_KEYS` (const) — approx. L8676 — The gate fields that can be merged (quests, partialQuests, diaries, cards, cardGroup, skills, skillsSum, questPoints, access, anyOf, allOf).
- `_setLocReqs(d)` — approx. L8678 — Loads location_requirements.json into LOC_REQS and resets memos (called from data loading).
- `_locEntry(name)` — approx. L8683 — Case-insensitive lookup of a place's entry in LOC_REQS.
- `_gateCanon` (const) — approx. L8685 — Arrow fn: a copy of a gate with object keys sorted (recursively), so key order doesn't matter when comparing.
- `_gateSame` (const) — approx. L8687 — Arrow fn: structural equality of two gates (JSON of `_gateCanon` of each), independent of key order.
- `_mergeGate(a, b)` — approx. L8690 — Merges two gates idempotently (union quests/diaries, max skill levels, …) so generator-merged gates don't double up.
- `_locOwnGate(name, seen)` — approx. L8706 — A place's own requirements plus its parent chain, as a gate ({} if none curated).
- `_NO_GATE` (const) — approx. L8714 — Shared empty gate object (memo key).
- `_locGate(name, gate)` — approx. L8717 — The full gate for a location: data's own gate merged with the place's entry requirements; memoised.
- `_questPointsDone()` — approx. L8732 — Your total quest points from completed quests (quests.json).
- `_gateGroupCards(g)` — approx. L8734 — Cards in a gate's card group: TOOL_TIERS for 'tool:X', else REQ_GROUPS (e.g. light_source, warm_clothing).
- `_GROUP_LABEL` (const) — approx. L8738 — Friendly names for card groups ("a light source", "an axe", "a pickaxe").
- `_gateMissing(g)` — approx. L8740 — Everything a gate still needs → [{kind, key, label, cards?}] (empty = you meet it).
- `_gateOk(g)` — approx. L8762 — True if the gate has nothing missing.
- `_gateText(g)` — approx. L8764 — Plain-text summary of a gate for tooltips ("Farming 45 · Heroes' Quest · one of: …").
- `_locBoostNote(name)` — approx. L8776 — "level can be boosted" / "can't be boosted" note when the wiki says so.
- `_locReqOk(name)` — approx. L8778 — Can you enter this place (location_requirements.json only)? Unknown places are open.
- `_slLocOk(access, gate, name)` — approx. L8781 — Can you reach a location: area access (access_routes.json key; 'excluded' = never) plus merged gate.
- `_SL_BOSS_ALIAS` (const) — approx. L8788 — Slayer boss task names → Bosses-tab names (Barrows brothers → Barrows, …).
- `_slBossEncounter(name)` — approx. L8790 — Finds the BOSS_DATA entry for a boss-task monster.
- `_slMonsterStatus(mon, entry, isBoss)` — approx. L8798 — Is one task monster doable: card owned, Slayer level, reachable location, equipment; bosses judged by `evaluateBoss` → {ok, card, reason}.
- `_slTaskStatus(taskName, entry)` — approx. L8823 — Task status: each monster option (incl. master-specific alternatives) plus required Slayer equipment → doable or not.
- `_slMasterSummary(m)` — approx. L8834 — Per master: assignable weight, doable weight, and the doable chance (doable ÷ assignable weight), with task rows.
- `_pct` (const) — approx. L8847 — Arrow fn formatting a fraction as a percentage.
- `renderSlayerList()` — approx. L8851 — Left Slayer list: Overview, masters (with doable %), tasks; honours search.
- `selectSlayer(kind, name)` — approx. L8881 — Selects a master/task (or overview) within the tab, with history.
- `showSlayer(kind, name)` — approx. L8887 — Cross-tab jump to a Slayer master/task (switches tab if needed).
- `_slLink(kind, name, label)` — approx. L8892 — Clickable link to a master/task.
- `_slWhyHtml(why)` — approx. L8896 — Renders a list of reasons (quest, card or text) as links joined by " · ".
- `_slVariantTag(o)` — approx. L8902 — Small tag naming a monster variant when several wiki monsters share one card (e.g. Hill Giant (Dark)).
- `_renderSlayerDetail()` — approx. L8909 — Right pane wrapper: turns on the access cache for the render, then `_renderSlayerDetailInner`.
- `_renderSlayerDetailInner(pane)` — approx. L8917 — Overview (masters with doable chance, reward unlock checklist) or a master page (tasks, weights) or a task page (monsters that count, Slayer equipment, assigned by).
- `_renderBossHome()` — approx. L9006 — Bosses-tab home (sits in this section): status count tiles, closest-to-ready bosses, biggest blockers, most-needed cards.
- `showBoss(name)` — approx. L9052 — Cross-tab jump to a boss page (switches to Bosses tab if needed).
- `showBossOverview()` — approx. L9066 — Back to the Bosses overview.
- `renderBossing()` — approx. L9075 — Refresh hook (e.g. after `switchCollection`): redraws boss list and current boss/home if the Bosses tab is open.

### Clues tab (approx. line 9083)
One page per clue tier (beginner to master) plus an overview of what blocks your clue steps. Tab entry: `_renderTab('clues')` → `renderClueList()` + `_renderClueDetail()`; tier pages are `renderClueScroll()` and the engine `_clueTierStatus` / `_clueStepOk` live in the "Clue steps & tiers" section earlier.
- `selectedClue` (let) — approx. L9087 — Selected tier key ('beginner' … 'master') or null for overview.
- `CLUE_KEY_CARDS` (const) — approx. L9088 — Cards that matter across clues (Spade, Uri, Double agent, Sherlock, Falo the Bard, Watson).
- `_clueRealistic(st)` — approx. L9090 — A tier is realistic when you can obtain the clue and enough of its trail (`CLUE_TRAIL_MIN`) is doable.
- `renderClueList()` — approx. L9092 — Left list: Overview + each tier with a status dot.
- `selectClue(tier)` — approx. L9113 — Selects a tier within the tab, with history.
- `showClue(tier, push=true)` — approx. L9120 — Cross-tab jump to a clue tier.
- `_renderClueDetail(resetScroll=false)` — approx. L9128 — Right pane: home or `renderClueScroll(tier)`, keeping scroll position.
- `_clueStepScan()` — approx. L9141 — Scans every step of every tier: gates blocking steps and card demand from undoable steps (shared with the Packs overview).
- `_renderClueHome()` — approx. L9168 — Clues home: per-tier table, biggest blockers, most-needed cards, key cards.

### Achievement Diaries tab (approx. line 9240)
Each diary area and tier with its tasks, what you're missing and a manual tick list. Tab entry: `_renderTab('diaries')` → `renderDiaryList()` + `showDiaryDetail()` or `_renderDiaryHome()`. Diary data is generated (generate_diaries.py → output/diaries.json): never hand-edit tasks here.
- `DIARY_TIERS` (const) — approx. L9243 — ['easy','medium','hard','elite'].
- `DIARY_TIER_LABEL` (const) — approx. L9244 — Tier → display label.
- `DIARY_TIER_COLOR` (const) — approx. L9245 — Tier → text colour.
- `DIARY_TIER_BG` (const) — approx. L9246 — Tier → background colour.
- `AREA_QUESTS` (const) — approx. L9270 — Hand-written area-wide quest gates applied to every task in an area (Morytania = Priest in Peril).
- `DIARY_DATA` (let) — approx. L9279 — All diary areas/tiers/tasks/rewards, loaded from output/diaries.json at startup in the Data loading section; names checked by `_validateDataNames`.
- `DIARY_BY_CARD` (var) — approx. L9284 — Reverse lookup card (lowercase) → [{diaryName, tier, role, task}] for diary cross-links on card pages.
- `_buildDiaryByCard()` — approx. L9286 — Rebuilds `DIARY_BY_CARD` from DIARY_DATA tier and task cards (deduped).
- `_validateDataNames()` — approx. L9323 — After data load, logs `[data check]` console warnings for any card/quest name in slayer.json, bosses.json, DIARY_DATA, clue_steps.json, location_requirements.json and item_sources activities that isn't a TCG card or a quests.json quest. Keep the console free of these.
- `evaluateDiaryTier(area, tier)` — approx. L9392 — Status of one tier: area-wide quests (hard blockers), per-task quests, skill gates, item / monster / NPC cards (incl. reward NPC) missing.
- `renderDiaryList()` — approx. L9464 — Left list: Overview + each area with tier progress, filtered by `diarySearch`.
- `_diaryTickKey(dn, tier, type, task)` — approx. L9501 — localStorage key for a manually ticked diary task.
- `_diaryTickVer` (let) — approx. L9504 — Counter bumped by every `toggleDiaryTick`; part of the `_itemGetNeeds` / `_accessMet` cache signatures so diary ticks invalidate them.
- `isDiaryTicked(dn, tier, type, task)` — approx. L9506 — Is the task ticked done (browser storage)? False when storage is blocked (try/catch).
- `toggleDiaryTick(dn, tier, type, task)` — approx. L9510 — Ticks/unticks a task (storage write in try/catch: warns if blocked), bumps `_diaryTickVer`, resets clue caches (clue steps can need diaries), redraws.
- `_diaryTaskMissing(area, task)` — approx. L9522 — A task's unmet requirements as units {label, cards, quest?, skill?}, including area-wide quests.
- `_diaryMissingLink(m, area, tier)` — approx. L9550 — A missing unit as a link: quest → quest page, one card → card page, group → hover grid.
- `_diaryTierEval()` — approx. L9558 — Every tier with each task's done flag and missing list.
- `_diaryCardDemand(tiers)` — approx. L9572 — Unowned cards blocking diary tasks, counted per task (shared by Diaries and Packs homes).
- `_renderDiaryHome()` — approx. L9587 — Diaries home: tiers done/eligible, tasks eligible, closest tiers, most-needed cards.
- `selectDiaryTier(dn, tier)` — approx. L9655 — Selects a tier on a diary page.
- `_diaryTierCards(area, tier)` — approx. L9662 — Every card a tier needs: task items, monsters, NPCs, the reward NPC and reward cards.
- `wishlistDiaryTier(diaryName, tier)` — approx. L9672 — Adds all missing cards of a tier to the wishlist with a "Area Tier" note.
- `_diaryTaskUnits(task, add)` — approx. L9692 — Emits one requirement unit per distinct skill/quest/card/tool/any-of group via `add(key, ok)`.
- `_diaryTierProgress(area, tier)` — approx. L9716 — Requirements met / total for a tier (distinct units plus area quests and reward NPC).
- `_diaryTaskEligible(area, task)` — approx. L9730 — True when all of a task's requirements (and area quests) are met.
- `_diaryEligibleTasks(area, tier)` — approx. L9736 — Tasks ticked or eligible / total for a tier.
- `showDiaryDetail(name)` — approx. L9744 — Diary area page: tier strip, selected tier header + wishlist button, prerequisites, task checklist with requirement badges (any-of skills, ironman notes, no-card chips, Barrows sets), rewards.
- `showDiaryOverview()` — approx. L10101 — Back to the Diaries overview.
- `showDiary(name)` — approx. L10109 — Cross-tab jump to a diary area.

### Questing tab (approx. line 10162)
This marks the start of the Questing tab code. The section has no definitions of its own. The doc comment under it (about `{cardsOk, missingCount}`) belongs to `checkQuestCards` further down: it was left behind when the code was moved.

### Most-needed missing cards (Questing tab welcome panel) (approx. line 10118)
This is the "which cards would unlock the most quests (or bosses) for me" table on the Questing and Bosses overview pages.
- `_cardDemand(entries)` — approx. L10127 — Works out which unowned cards would help the most targets (quests or bosses). Takes `[{name, reqs}]` and returns `Map(card → {quests:Set, last:Set})`. A card gets credit for each unmet required requirement it could satisfy: any option of an "any of" group, or the first choice of each missing route slot. `last` means owning that one card would finish all of the target's card requirements.
- `_questCardDemand()` — approx. L10158 — Runs `_cardDemand` over every quest not yet done, using each quest's requirements from `bmQuestCards` sections.
- `_demandTableHtml(demand, title, unit, wishNote)` — approx. L10163 — Draws the top-30 "most-needed cards" table. Each row shows the card image and name (click to open it), a bar, the target count (hover lists the targets), a "last card ×N" count and a wishlist star. The Questing and Bosses home panels share it.
- `_renderQuestCardSummary()` — approx. L10189 — Fills `#quest-card-summary` on the Questing overview with the most-needed table for quests.

### Progress bars (quests + diaries) (approx. line 10195)
This draws the Required / Recommended progress bars on quest and diary pages, plus the shared requirement-row renderer and the wishlist stars on requirement rows.
- `_progressBar(label, p, color, title)` — approx. L10198 — HTML for one labelled done/total bar. It turns green when complete. Diaries use it too.
- `_questProgress(questName)` — approx. L10209 — Counts how far you are with a quest. Required covers prerequisite quests done, skill levels and required card requirements. Recommended covers optional requirements. An "any of" group counts as one. Returns `{req, rec, all}`.
- `_questProgressHtml(questName)` — approx. L10223 — Draws the Required bar, plus Recommended and All bars when the quest has optional requirements.
- `_checkedListsHtml(entries)` — approx. L10236 — Draws the "Checked — not required" (has a card, shows ✓/✗ owned) and "Checked — no card" (no restriction) chip lists for quests and bosses. It drops duplicate and bare-name repeats first.
- `_questRowOrder(rows)` — approx. L10261 — Sorts requirement rows: required-and-missing first, then required-and-met, then optional.
- `_questReqRow(req)` — approx. L10267 — **The shared requirement-row renderer** (quests, bosses, slayer, skilling). Turns one requirement into `{ok, optional, html}`. It handles:
  - info-only rows ("not tracked")
  - single cards, with a label note
  - "any of" / `mode:'all'` card groups, sorted owned+gettable → owned-but-blocked → unowned, with a hover grid after 10 options
  - the special `warm_clothing` group: "Wearable now x/4 slots" plus no-card items and holiday-event items
  - routes: one line each, with slot alternatives, quests, skills and areas
  - `skillAlt` ("OR Skill N")
  - a right-hand status ("owned", "can cast", "can reach", "can make", "missing"…) and a wishlist star

  Chip colours: green means owned. Yellow means not owned but obtainable. Red means not owned. Amber ◐ means owned but you can't get the item yet (it lists `_itemGetNeeds`).
- `_REQ_IMG_SPACER` (const) — approx. L10392 — An empty 16px span that keeps row icons lined up when a row has no image.
- `_REQ_STAR_SPACER` (const) — approx. L10393 — A hidden ☆ that keeps rows lined up when a row has no wishlist star.
- `_MAKE_ROUTE_RE` (const) — approx. L10395 — A regex for route labels that mean making the item yourself (mix, craft, smith…). It turns the row status into "can make".
- `_reqWishReg` (const) — approx. L10398 — A Map from a star's key string to its wishlist plan, so an onclick can look the plan up again.
- `_reqWishPlan(req, cards, routes)` — approx. L10400 — Decides what a requirement row's star adds. For an any-of group it adds a named wishlist group. For a `mode:'all'` requirement or a route it adds the missing cards (closest route first), tagged with the label.
- `_reqWishActive(plan)` — approx. L10414 — Returns whether that plan is already on the wishlist: the group exists, or every card is wishlisted.
- `_reqWishStar(req, ok, cards, routes)` — approx. L10419 — HTML for the ☆/★ star on a group or route row. It registers the plan in `_reqWishReg`, and the star is dimmed when the requirement is already met.
- `_toggleReqWish(key)` — approx. L10430 — Adds or removes a row's plan from the wishlist (groups, or card notes tagged with the label). Then it saves the wishlist and redraws the panes.
- `_rerenderReqPane()` — approx. L10450 — Redraws whichever pane shows requirement rows (quest, boss, slayer or card detail) so the stars update, keeping the scroll position.

### Quest requirement model (approx. line 10461)
This is the core "is this requirement met?" logic that quests, bosses, diaries, slayer, clues and skilling all share. It covers cards, routes, area access, spells, tool tiers and shared card groups.
- `_expandReq(r, questName)` — approx. L10472 — Runs once per requirement at load. It resolves `routes`, `access` keys (from access_routes.json), `spells` (the full rune cost from spells.json, where a rune slot also accepts staffs and combination runes from `runeSources`), `tool` (any `TOOL_TIERS` tier) and `group` (`REQ_GROUPS`). The results go into `r._routes` (slots/quests/skills/areas/partialQuests/diaries) and `r._cards`, the cards worth collecting. Unknown spells, access keys or groups print `[quest data]` warnings in the console.
- `_reqCards(r)` — approx. L10506 — Returns a requirement's collectable cards (`_cards` if it has been expanded, otherwise `cards`).
- `CRAFTED_CARD_ROUTES` (const) — approx. L10509 — Lists cards that an ironman must craft, so owning the card alone isn't enough. Currently only `slayer helmet` → the access route `slayer_helmet`.
- `_cardUsable(c)` — approx. L10511 — Returns whether a card counts as usable. For a crafted card the crafting access route must be met; otherwise this is `isOwned`.
- `_accessCache` (let) — approx. L10518 — The cache of area-access results. It is a Map during heavy renders and `null` when caching is off.
- `_accessSig` (let) — approx. L10522 — A signature of account (`_currentRsn`)/owned/quests/started/diary ticks (`_diaryTickVer`)/levels/routes. When it changes, `_accessCache` is reset.
- `_accessMet(key, seen)` — approx. L10524 — **Can you reach this area?** (`key` is an access_routes.json key such as "desert" or "morytania"). It is true if any route of the area is met. A `seen` set guards against cycles. Only top-level results are cached, because cycle-guard `false`s from nested checks would poison the cache (the fix for the bug where quest statuses changed depending on which tabs you had visited).
- `_routeExpandCache` (const) — approx. L10535 — A WeakMap that stores each access route after its one-time expansion.
- `_expandRoute(rt)` — approx. L10537 — Expands one raw access route through `_expandReq`, cached. An empty result becomes a manual route.
- `_routeMet(rt, seen)` — approx. L10546 — Returns whether one route is fully met. The route must not be manual, and it needs: all of its areas reachable, the Magic level, its quests done, its partial quests started, its diary tiers ticked, its skills, and one owned card in every slot. It is safe to use as a `.some` callback.
- `SLASH_WEAPONS` (const) — approx. L10560 — The cards that can cut webs or vines: knife, scimitars, swords, longswords, battleaxes, 2h swords, whip and so on.
- `REQ_GROUPS` (const) — approx. L10561 — The shared card lists a requirement can name with `group`: `slash_weapon`, plus `light_source`, `dragonfire` and **`warm_clothing`**. The last three are getters, so they read `LIGHT_SOURCE_ITEMS` / `DRAGONFIRE_ITEMS` / `WARM_CLOTHING_ITEMS` after those load.
- `_equipByName` (let) — approx. L10569 — An index of equipment items by lower-case name, built lazily once `equipBySlot` has loaded.
- `_warmUsableSlots()` — approx. L10571 — Works out which warm-clothing slots you can fill right now (for Wintertodt-style warmth). For each slot in `WARM_CLOTHING_BY_SLOT` it keeps the cards that are owned and gettable (`_warmItemOk`), not seasonal-only, and that meet the wield levels, plus any no-card `WARM_NO_CARD` items you can get. Returns `[{slot, cards}]`.
- `_reqMet(r)` — approx. L10592 — **Is this requirement met?** `warm_clothing` needs 4 or more usable slots. Otherwise the requirement is met by any usable card (every card for `mode:'all'`), or by any met route, or by a `skillAlt` level.
- `checkQuestCards(name, q)` — approx. L10603 — Counts a quest's unmet required card requirements from `bmQuestCards`. Without BM data it falls back to the wiki infobox `itemsRequired`/`killsRequired`. Returns `{cardsOk, missingCount}`.
- `_completableCache` / `_completableSig` / `_completableBusy` (let) — approx. L10626 — The cache of completable quests, its signature (quests/owned/levels), and a recursion guard.
- `_questOk(q)` — approx. L10628 — Returns whether a quest counts as met for planning: done, or completable now. It is cached, and guarded against re-entry because card checks can reach `canGetItem`.
- `computeCompletableQuests()` — approx. L10640 — Starts from the done quests and keeps adding quests whose prerequisites, skills and cards are all met (`checkQuestCards`) until nothing changes. Returns a Set.
- `questStatus(questName, completable)` — approx. L10667 — Returns a quest's status: `done`, `ok` (completable), `close` (prerequisites and skills fine, at most 2 cards missing) or `locked`.
- `isMiniquest(name)` — approx. L10682 — Returns whether a quest is a miniquest: BM data flags it `_miniquest`, or it is wiki-only with 0 quest points.
- `questItemHtml(name, data, completable)` — approx. L10691 — Draws one row of the quest list: status badge, name, ◐ if started, and QP/members/mini tags. Clicking opens the quest.
- `renderQuestStats(completable)` — approx. L10707 — Fills `#quest-stats` with the Completed / Available / Total counts and their quest points.
- `renderQuestList()` — approx. L10745 — Draws the left quest list. It applies the search and the status/members filter, splits quests from miniquests, sorts ok → close → locked → done, and puts an "Overview" entry at the top.
- `showQuestOverview()` — approx. L10797 — Clears the selected quest and redraws the Questing tab's overview (welcome) panel, recording the step for back navigation.
- `showQuestDetail(questName, push)` — approx. L10804 — Draws a quest's detail page:
  - title, status, and the Mark completed / Mark started buttons
  - the two wishlist buttons (required, or required + recommended) and the progress bars
  - the BM note and the miniquest warning
  - the start NPC, prerequisites, and skill requirements (tagged ⚔ when a skill can only be trained on monsters)
  - card requirement sections from BM data via `_questReqRow`: Access, NPC interactions, Enemies, Items & tools, Optional & recommended
  - the "checked" lists, or the wiki-infobox fallback, and the reward items

### Rules tab (approx. line 11029)
This is the static Rules reference page explaining which actions need a card under strict Bronzeman TCG rules, and how each tab judges requirements.
- `renderRulesTab()` — approx. L11030 — Wraps `_rulesTabHtml()`. It gives each `<h3>` an id and adds a contents sidebar entry for it, and colours Yes/No answer cells.
- `_rulesScrollSpy()` — approx. L11046 — On scroll, highlights the contents entry for the section you are reading.
- `_rulesTabHtml()` — approx. L11056 — The full rules text: core rule table, gathering, production, NPCs, stricter-than-plugin, item versions, diaries, ironman, shops, quests, bosses, slayer, clues (includes `CLUE_TRAIL_MIN`), skilling (`SKILL_UNLOCK_QUESTS` table), partly-done quests, foils, no-card, and the tab list. **Update this whenever the rules change.**

### Equipment tab (approx. line 11193)
This is the gear planner: a paper doll per combat style, a list of items per slot (equipped / owned / obtainable / locked), stat totals, and a stats tooltip. Choices are saved in the browser (localStorage).
- `activeEquipStyle` (let) — approx. L11196 — The selected combat style (melee/ranged/magic), saved as `equip_active_style`.
- `selectedEquipSlot` (let) — approx. L11197 — The slot whose item list is shown.
- `equipSortBy` (let) — approx. L11198 — The sort key for the slot item list, saved as `equip_sort_by`.
- `STAT_KEYS` (const) — approx. L11200 — The 14 equipment stat keys (attack, defence, strength, magic damage, prayer).
- `STAT_SHORT` (const) — approx. L11205 — Short display labels for each stat key.
- `computeTotalStats(swapSlot, swapItem)` — approx. L11216 — Adds up the bonuses of all equipped slots. The shield is ignored when a 2H weapon is equipped. Optional `swapSlot` / `swapItem`: the total as if `swapItem` were equipped in `swapSlot` (used by DPS previews).
- `renderGearStats()` — approx. L11239 — Fills `#equip-stats-panel` with the attack/defence/other totals and the DPS controls (prayer, attack style, enemy defence level and bonus).
- `buildItemTooltip(item, eqItem)` — approx. L11320 — HTML for an item's stats tooltip, with the difference (+/−) against the equipped item and its level requirements.
- `DOLL_LAYOUT` (const) — approx. L11351 — The paper-doll grid as rows of `[row, col, slot, label]`.

### DPS Calculator (approx. line 11361)
This gives a rough max hit / accuracy / DPS estimate for melee and ranged from the equipped gear, your levels and the chosen prayer. Magic is not calculated.
- `DPS_PRAYERS` (const) — approx. L11363 — Prayer multipliers for melee/ranged/magic attack and strength (Piety, Chivalry, Rigour, Eagle Eye, Augury, Mystic Might).
- `PRAYER_BY_STYLE` (const) — approx. L11374 — Which prayers each combat style can pick.
- `dpsSettings` (let) — approx. L11380 — The current DPS inputs: prayer, attack style, enemy defence level, enemy defence bonus.
- `loadDpsSettings()` — approx. L11388 — Loads `dpsSettings` from localStorage `dps_settings`.
- `saveDpsSettings()` — approx. L11395 — Saves `dpsSettings` to localStorage.
- `meetsReqLvl(item)` — approx. L11400 — Returns whether your levels meet an equipment item's `reqLvl`. The warm-clothing check uses it too.
- `calcDps()` — approx. L11410 — Calculates max hit, hit chance, DPS and speed for the equipped gear with the standard OSRS formulas (effective level, attack and defence rolls). Returns null for magic.
- `dpsSettingChanged()` — approx. L11461 — Reads the DPS controls, saves them and refreshes the output.
- `updateDpsOutput()` — approx. L11475 — Fills `#dps-output` with Max Hit / Accuracy / DPS / Speed, or a note for magic.
- `SLOT_FULL` (const) — approx. L11492 — Maps each slot key to its display name (11 slots).
- `STYLE_COLOR` (const) — approx. L11499 — The header colour for each combat style.
- `equipKey(slot)` — approx. L11502 — The localStorage key for a slot in the current style (`equip_<style>_<slot>`).
- `getEquipped(slot)` — approx. L11503 — The name of the item equipped in a slot, from localStorage.
- `setEquipped(slot, name)` — approx. L11505 — Equips or clears an item. A 2H weapon clears the shield, and a shield clears a 2H weapon. Then it refreshes the doll, stats, DPS and slot list.
- `slotItems(slot)` — approx. L11529 — The slot's items annotated with owned/equipped/gettable (`canGetItem`)/styleMatch/meetsReq. Sorted equipped → owned → gettable → locked, then style match first, then by value.
- `slotHasUpgrade(slot)` — approx. L11552 — Returns whether you own a wearable item for the slot that isn't equipped (this shows the doll's upgrade dot).
- `renderEquipmentTab()` — approx. L11560 — The static HTML shell of the Equipment tab: style buttons, doll, stats panel, detail pane.
- `initEquipmentTab()` — approx. L11582 — Runs after the shell is drawn. It restores the saved style and slot, loads DPS settings, and draws the doll, count, stats and DPS.
- `switchEquipStyle(style)` — approx. L11602 — Changes the combat style (each style keeps its own gear), saves it and redraws.
- `updateEquipCount()` — approx. L11616 — Shows "N / M owned" across all equipment items.
- `refreshEquipDoll()` — approx. L11626 — Draws the paper doll: item images, the selected slot, upgrade dots, and the shield shown blocked ("2H") under a 2H weapon.
- `SLOT_DEFAULT_SORT` (const) — approx. L11677 — The default sort per slot (weapon → dps, jewellery/ammo/cape → attack, armour → defence).
- `selectEquipSlot(slot)` — approx. L11692 — Selects a slot, applies its default sort, saves both and draws its item list.
- `EQUIP_SORT_OPTS` (const) — approx. L11703 — The sort options in the slot dropdown (value, dps, style attack/defence, each stat).
- `setEquipSort(key)` — approx. L11725 — Changes the slot list sort, saves it and redraws.
- `calcDpsForItem(slot, item)` — approx. L11732 — DPS with `item` swapped into `slot` while keeping the rest of the gear, using the same formulas as `calcDps`; totals come from `computeTotalStats(slot, item)`, so 2H weapon / shield previews match. Used for the "dps" sort.
- `styleAtkStat(stats)` — approx. L11782 — The best attack bonus for the current style (melee: max of stab/slash/crush; ranged: attack + strength; magic: attack + damage).
- `styleDefStat(stats)` — approx. L11795 — The defence bonus against the current style (melee: the sum of stab/slash/crush).
- `getStatVal(item, key)` — approx. L11809 — The value an item is sorted by for a given sort key.
- `renderEquipSlotDetail(slot)` — approx. L11818 — Draws a slot's item list in sections: Equipped, Owned — can equip, Owned — level required, Obtainable, Not yet accessible. Rows show an image, a 2H tag, a combat badge, a value, missing levels and ↗ Card / Clear buttons. A click equips or clears an owned item, or opens the card for an unowned one.
- `showEquipTooltip(event)` — approx. L11943 — Shows the floating stats tooltip (`#equip-tooltip-float`) next to the hovered row, flipping it above the row near the bottom of the screen.
- `hideEquipTooltip()` — approx. L11977 — Hides the equipment tooltip.
- `navigateToCard(name)` — approx. L11983 — Opens an item's card page from the Equipment tab (`showCard`, with the type from `allCards`).
- `formatGp(n)` — approx. L11990 — Formats a gp value as 1.2K / 3M.

**Startup code:** the last statement in the script (approx. L11998) is `loadData();`. That is the page's entry point: it loads all the data and draws the first tab. There is no other top-level startup code in this range.

---

## Part 6. Python scripts: every function

One line per function, class, method and nested helper, in file order. "Inner helper" means a function defined inside another one. File-level details (inputs, outputs, how to run) are in Part 3.4; server.py is in Part 4.

### scripts/card_groups.py

Functions: none (0 defs). Key constants: `CARD_GROUPS`.

### scripts/catalog_names.py

Functions:
- `npc_names(cat, versions)` — approx. L8 — Builds a lowercase-name → NPC card lookup: card name, name without "(…)", wiki page title, and (with `versions=True`) the in-game names of the card's versions.

### scripts/decode_collection.py

Functions:
- `_identity_names()` — approx. L74 — Maps `npc:<id>` / `item:<id>` identity names (used by the plugin for clashing names) to real card names, from the catalog; cached.
- `normalize_profile(d)` — approx. L97 — Replaces identity names in a profile's owned list and timestamp maps with card names.
- `xor_with_salt(data)` — approx. L115 — XORs bytes with the fixed salt (the RLTCG_v2 obfuscation step; running it twice undoes it).
- `decode_blob(blob)` — approx. L120 — Decodes an `RLTCG_v2` (Base64→XOR→gzip→JSON) or `RLTCG_v3` (Base64→gzip→JSON) string to the state dict.
- `extract_owned_names(state)` — approx. L138 — Returns (sorted unique card names, total instances) from either save schema (≤5 `cardInstances`, 6+ `cardEntries`).
- `_try_decode_save_file(f)` — approx. L160 — Tries to decode one save file; returns (path, state) or None if it has no cards.
- `find_best_backup(backups_dir)` — approx. L179 — Finds the most recently modified decodable save file across backups/ and profiles/.
- `find_best_backup._consider(f)` — approx. L188 — Inner helper: keeps `f` if it is newer than the current best and decodes with cards.
- `find_state_blobs_from_profiles(profiles_dir)` — approx. L220 — Scans `.properties` files and returns (label, blob, mtime) for each `.state=` entry.
- `_fetch_cloud_cards(account_dir)` — approx. L241 — For cloud accounts: pages through `/api/v1/me/cards` with the stored token; returns names, count and pull timestamps (cached, reused while rate-limited).
- `_cloud_result(all_cards)` — approx. L321 — Summarises cloud card instances into names, count, last and first pull times per card.
- `_build_dir_name_to_display(profiles_dir)` — approx. L348 — Maps TCG profile folder names (SHA-256 of accountHash) to RuneScape display names.
- `find_per_profile_collections(profiles_dir)` — approx. L372 — Builds `{displayName: {cardCount, ownedCards, updatedAt, credits, ...}}` from all three sources (properties blobs, tcg.save, cloud).
- `main()` — approx. L528 — CLI: writes `all_collections.json`, then `--out` for `--player` (or the single source with the most cards; profiles are never merged).

### scripts/decode_completed_quests.py

Functions:
- `scan_dir(quest_dir)` — approx. L37 — Returns `{quest name: filename}` for every quest screenshot in a folder.
- `main()` — approx. L52 — CLI: scans the player's folder and writes `completed_quests.json`.

### scripts/generate_boss_loot.py

Functions:
- `_canon(name, item_canon)` — approx. L156 — Card name for a wiki item name (exact or via the catalog's variants), in the card's own casing.
- `_num(s)` — approx. L163 — Parses a wiki number with thousands commas ("2,448" → 2448.0).
- `_rate(text)` — approx. L168 — Per-chest probability from rarity text ("Always", "1/50", "7 × 1/2,448" combined); None if not a fraction.
- `_footnotes(cell, soup)` — approx. L180 — Collects the wiki's data footnotes on a rarity cell (skips plain numbered citations).
- `parse_chest(html, cfg, item_canon, scale)` — approx. L194 — Parses every drops table on a reward page into card rows (rarity, fraction, notes), filtered by heading per the `BOSS_LOOT` config. Falls back to the whole page if it has no `.mw-parser-output`.
- `build_boss_loot(item_canon, in_dir=_OUT_DIR)` — approx. L280 — Builds the whole boss_loot dict: chest pages, fixed rewards, extra rows, plus final-monster drops from `in_dir`/monster_drops.json.
- `parse_collection_log(html, item_canon)` — approx. L351 — Collection log page → `{heading: [card names]}` (whole page if there is no `.mw-parser-output`).
- `_log_heading_for(boss, headings)` — approx. L373 — Finds a boss's collection-log heading (override, "X"/"The X", or "X and Y").
- `build_collection_log(boss_names, item_canon)` — approx. L388 — Boss → `{log, items}` from the Collection log page; unmatched bosses are printed.
- `_boss_names_from_preview(in_dir=_OUT_DIR)` — approx. L407 — Boss names, read from `in_dir`/bosses.json so the two never drift.
- `main()` — approx. L412 — CLI: writes boss_loot.json and collection_log.json into `--out-dir`, reading inputs from `--in-dir`.

Key constants: `BOSS_LOOT` (chest page config per boss), `BOSS_FIXED_LOOT`, `EXTRA_LOOT`, `LOG_HEADING_OVERRIDES`.

### scripts/generate_bosses.py

Functions:
- `_clean(text)` — approx. L59 — Strips `{{efn}}` notes and `<ref>` footnotes from wikitext.
- `parse_boss_tables(wikitext)` — approx. L67 — Reads the wiki Boss page tables into one dict per boss row (section, location, quests, levels, log...).
- `load_card_names(card_json)` — approx. L109 — Lowercase set of all card names plus the card_aliases map, for validation.
- `build(card_json)` — approx. L118 — Merges curated encounters with wiki rows; returns (bosses list, validation report).
- `main()` — approx. L179 — CLI: writes bosses.json and the validation report.

### scripts/generate_card_aliases.py

Functions:
- `main()` — approx. L22 — Builds `{variant name (lowercase): card name}` from the catalog and writes it.

### scripts/generate_card_versions.py

Functions:
- `fetch_image_urls(names)` — approx. L37 — Version name → `{icon, detail}` wiki thumbnail URLs (cached).
- `fetch_pages(titles)` — approx. L68 — Title → `{page, text}` wikitext with redirects followed, 50 per request (cached).
- `_template_params(block)` — approx. L92 — Splits a `{{Template|k=v}}` block into a lowercase-key params dict.
- `recipe_for(text, version)` — approx. L104 — Finds the `{{Recipe}}` whose output is this version (or the page's only recipe) and returns skills, materials, tools, facilities.
- `main()` — approx. L140 — CLI: collects each card's versions, attaches recipes and images, writes card_versions.json.

### scripts/generate_clue_sources.py

Key constants: `TIERS`, `SKILL_TIERS` (no master geodes/nests/bottles); `ITEM_LC`, `NPC_LC`, `ALIASES`, `VERSION_LC` (lookup tables built at import); `SOURCE_CARDS` (source pages whose card has another name, e.g. Grotesque Guardians → Dusk); `_CHESTISH` (regex for chest-like sources); `TREE_LEVELS` (Woodcutting level per tree); `FISH` (Fishing level + tool per fish); `SKILLING` (page, item prefix, skill, tool, multiplier for geodes/nests/bottles).

Functions:
- `card_for_item(name)` — approx. L81 — Matches a reward item to its item card (exact, case-insensitive, aliases, catalog variants and doses).
- `card_for_npc(name)` — approx. L95 — Matches a source page to its NPC card (exact, card versions, then without "(place)").
- `card_for_source(name, kind)` — approx. L107 — The card you must own to use a clue source of this kind, or None (chests, caskets, skilling).
- `_bucket_rows(where, cache, refresh)` — approx. L124 — Fetches all wiki "dropsline" bucket rows for a filter, 500 at a time, caching them.
- `_frac(s)` — approx. L148 — Turns a rate string ("11/8,856", "Always") into a number; None for "Rare", "Varies" etc.
- `_fmt_one_in(rate)` — approx. L161 — Formats a rate as "1/N".
- `_min_level(s)` — approx. L167 — Lowest number in a level string ("70, 85" → 70).
- `_kind(drop_type, name)` — approx. L180 — Classifies a source as monster, pickpocket, impling, chest, skilling, casket or other.
- `scroll_sources(tier, rows)` — approx. L207 — Turns bucket rows for "Clue scroll (tier)" into one entry per source page (versions merged, alt rates kept).
- `_wikitable_after(text, heading_re)` — approx. L283 — Data rows of the first wiki table after a given heading.
- `_link_target(cell)` — approx. L299 — First link target in a wikitext cell, else the cell text.
- `_num(cell)` — approx. L305 — Leading number in a cell, or None.
- `skilling_tables(page, refresh)` — approx. L311 — Reads a skilling clue page's base-chance table and per-tier modifiers.
- `_rate(base, mult, level, mod)` — approx. L326 — The wiki's skilling clue chance formula at a given level.
- `skilling_sources(cache, refresh)` — approx. L331 — Clue geode / nest / bottle sources per tier, one per tool, with the rate at your level and at 99; adds bird houses and the vessel for nests.
- `casket_rewards(tier, rows, html)` — approx. L417 — Each reward item's rate(s) for one casket tier; adds Mimic-table items from the rendered page.
- `_sum_rarities(rs)` — approx. L439 — Combines several rates for one card (adds numerators on equal denominators, else sums rates).
- `main()` — approx. L457 — Builds and writes the three clue JSON files plus the bucket cache, then prints a summary of unresolved names.

### scripts/generate_clue_steps.py

Key constants: `EMOTE_TIERS`, `SHERLOCK_TIERS`, `CRYPTIC_TIERS`, `ANAGRAM_TIERS`, `CIPHER_TIERS` (tiers per clue type); `DOUBLE_AGENT_TIERS` (Hard/Master emote steps fight a Double Agent); `CHARLIE_ITEMS` (beginner Charlie the Tramp items); `CUR` (the loaded `clue_curated.json`); `CLUE_NPC_FIXES` (= `CUR["npcFixes"]`); `MAP_CLUE_TIERS`; `COORDINATE_CLUE_TIERS` (combat NPC per coordinate tier); `HOT_COLD_TIERS`, `HOT_COLD_COMBAT`; `SKILLS`; regexes `_NEG_RE` / `_REQ_RE` / `_COND_RE` / `_OBTAIN_RE` / `_PARTIAL_RE` / `_TRAVEL_RE` that classify requirement sentences; `_SPADE_REQ`; global `R` (the `_Resolver`, set in `main`).

Functions:
- `_cell_text(td)` — approx. L99 — Gets the plain text of a table cell, dropping footnote markers.
- `_links_in_cell(td)` — approx. L106 — Lists the wiki pages a cell links to (from `<a title>`), skipping red links and File/Category/Template links.
- `_first_link_in_cell(td)` — approx. L129 — First linked page title in a cell, or None.
- `_split_by_tier_headers(soup, tier_names, header_tags)` — approx. L135 — Groups a page's tables under the tier heading (Easy, Hard…) that comes before each.
- `_marked(td)` — approx. L197 — Cell text with each link kept as a `⟦title|text⟧` marker so later parsing knows what was linked.
- `_plain(s)` — approx. L215 — Turns marked text back into readable plain text.
- `_sentences(s)` — approx. L222 — Splits marked text into sentences; bracketed asides become their own sentences.
- `_sentences._hold(m)` — approx. L226 — Swaps a link for a placeholder so splitting on `.`, `;`, `(` can't break it.
- `_sentences_ctx(s)` — approx. L243 — Like `_sentences`, but each bracketed aside keeps the sentence around it (so "(requires 76 Agility)" inside a travel tip stays a tip).
- `_sentences_ctx._hold(m)` — approx. L248 — Placeholder swap for links (restored afterwards).
- `_Resolver` (class) — approx. L269 — Shared lookups for every parser: wiki names → item cards, NPC cards, quests and access keys.
- `_Resolver.__init__(self)` — approx. L272 — Loads the live catalog, `card_aliases.json`, `quests.json`, `access_routes.json`, `diaries.json` and the curated `noCard` list.
- `_Resolver.item(self, name)` — approx. L288 — Item card for a wiki item name (curated name fixes, exact match, alias, dose spacing), or None.
- `_Resolver.npc(self, name)` — approx. L302 — NPC card for a wiki page or NPC name (exact, alias, then without a "(place)" suffix), or None.
- `_Resolver.quest(self, title)` — approx. L313 — Matches a quest page title to its `quests.json` key (curated aliases, "The …", "… quest").
- `_Resolver.card_exists(self, name)` — approx. L323 — True if the name is any item card, NPC card or card alias.
- `_new_reqs()` — approx. L332 — Empty requirement bundle with every shared field (requirements, quests, skills, access, diaries, notes…).
- `_merge(dst, src)` — approx. L338 — Combines two requirement bundles: skills keep the higher level, lists are unioned.
- `_skills_in(plain)` — approx. L351 — Finds skill levels mentioned in text ("70 Agility", "Agility level 70").
- `_diaries_in(plain)` — approx. L364 — Finds diary mentions ("hard Varrock diary") as "Area Tier" strings.
- `_item_token(title)` — approx. L376 — Classifies a linked title as a curated item group, a carded item, an uncarded item, or not an item.
- `_items_in_sentence(sent, optional)` — approx. L391 — Item requirements in one sentence; items joined by "or" / "/" become any-of choices.
- `_extract(marked)` — approx. L433 — Pulls quests, skills, diaries and items out of free wiki text; conditional sentences ("if…", "unless…") go to display-only notes instead of hard gates.
- `_location_text(marked_or_plain)` — approx. L513 — Location wording with travel tips (teleports, fairy rings, "close to…") removed.
- `_loc_rules(text)` — approx. L519 — Requirements from `clue_curated.json` `locationRules` whose regex matches the location text.
- `_finalize(step, acc)` — approx. L536 — Writes the collected requirement fields onto a step, dropping empty ones.
- `_npc_req(name, kind, label)` — approx. L573 — Requirement for an NPC you talk to or fight, or records it as "no card" when the NPC has none.
- `_slot_to_req(sl)` — approx. L583 — Converts an item slot into a requirement entry (None when the slot is unrestricted).
- `_group_slots(title)` — approx. L596 — Item slots for a curated `itemGroups` entry ("any god cape"), or None.
- `_drop_cardless(sl)` — approx. L614 — Items with no TCG card never block: an any-of slot containing one is always met; in all-of slots they're simply dropped.
- `_norm_slot(sl)` — approx. L644 — Normalises a curated slot (expands sets and group references).
- `_head(name)` — approx. L658 — Head noun of an item name ("Iron platebody (t)" → "platebody"), used to match alternatives.
- `_equip_slots(marked)` — approx. L670 — Parses an emote step's "Equip a X, Y and any Z." sentence into item slots, notes and uncarded names.
- `_equip_slots._hold(mm)` — approx. L681 — Placeholder swap for links while splitting the equip sentence.
- `_version_label(title, card)` — approx. L736 — Shows the item version the step names (e.g. "Emerald amulet") instead of its card name when they differ.
- `_add_alternatives(slots, names)` — approx. L745 — Attaches extra accepted items to the slot with the same head noun; returns leftovers.
- `_parse_emote_tier(tier, force_refresh)` — approx. L763 — Reads one tier's Emote clues guide page into steps with requirements.
- `_emote_requirements(step, clue_marked, notes_marked)` — approx. L806 — Works out an emote step's item slots, emote unlock, location gates and Notes-column requirements.
- `_apply_override(acc, ov)` — approx. L860 — Applies a curated per-step override: listed keys replace parsed ones, `requirements` are added.
- `scrape_emote_clues(force_refresh)` — approx. L873 — All emote steps, by tier.
- `_sherlock_item_slots(marked)` — approx. L880 — Parses a Sherlock "Items required" cell into all-of / any-of slots ("(X also works)" adds alternatives).
- `_sherlock_item_slots._hold(m)` — approx. L886 — Placeholder swap for links in the items cell.
- `_sherlock_item_slots._paren(m)` — approx. L893 — Handles a bracket: "(X also works)" → alternative marker, "(if …)" → note, anything else dropped.
- `_parse_sherlock_tier(tier, force_refresh)` — approx. L955 — Reads one tier's Sherlock page into tasks with requirements.
- `_sherlock_requirements(task, task_marked, items_marked, skill_marked, other_marked)` — approx. L1010 — Fills a Sherlock task's slots and requirement fields (curated `sherlockOverrides` win) and prunes non-item names.
- `scrape_sherlock(force_refresh)` — approx. L1062 — All Sherlock tasks, by tier.
- `scrape_falo(force_refresh)` — approx. L1069 — Falo the Bard steps: one per lyric with its accepted items.
- `scrape_falo._flush()` — approx. L1088 — Emits the lyric being collected (if it has items) and resets.
- `_load_monster_card_names()` — approx. L1131 — Loads monster card names once from `output/monster_drops.json` (used to spot "kill" cryptics).
- `_parse_cryptic_table(table, tier)` — approx. L1140 — Reads one cryptic clue table; each step typed kill / talk / dig / search.
- `scrape_cryptic_clues(force_refresh)` — approx. L1205 — All cryptic clue steps, by tier.
- `_parse_anagram_table(table, tier)` — approx. L1243 — Reads one anagram table (anagram → NPC, location, challenge answer).
- `scrape_anagram_clues(force_refresh)` — approx. L1288 — All anagram clue steps, by tier.
- `_parse_cipher_table(table, tier)` — approx. L1314 — Reads one cipher table; keeps rows whose answer is an NPC (plain-location rows skipped).
- `scrape_cipher_clues(force_refresh)` — approx. L1361 — All cipher steps that lead to an NPC, by tier.
- `_parse_hotcold_page(tier, force_refresh)` — approx. L1387 — Reads one hot/cold tier page (Master's combat type → Brassican Mage or Ancient Wizard).
- `scrape_hotcold_clues(force_refresh)` — approx. L1441 — All hot/cold steps, by tier.
- `scrape_map_clues(force_refresh)` — approx. L1453 — Map clue steps per tier from Treasure Trails/Guide/Maps (location, dig or search, requirements).
- `scrape_coordinate_clues(force_refresh)` — approx. L1490 — Coordinate steps per tier from Treasure Trails/Guide/Coordinates (coords, requirements, fight, location notes).
- `_cryptic_requirements(step)` — approx. L1564 — Fills a cryptic step's needs: talk NPC or kill target, Spade, Charlie items, location gates.
- `_talk_requirements(step)` — approx. L1592 — Anagram/cipher needs: the NPC's card plus the location's gates.
- `_hotcold_requirements(step)` — approx. L1605 — Hot/cold needs: Spade, combat NPC, region access, location gates.
- `_falo_requirements(step)` — approx. L1624 — Falo needs: any one of the lyric's items, plus requirements.
- `validate(output)` — approx. L1651 — Checks every step and the curated file for unknown cards, quests, access keys, diaries and groups; returns problem strings.
- `validate._chk_req(where, r)` — approx. L1656 — Checks one requirement or slot entry.
- `validate._chk_step(where, st)` — approx. L1675 — Checks one step's requirement fields.
- `_summary(output)` — approx. L1731 — Prints how many steps of each type/tier carry each requirement field, and the access keys used.
- `_build_indexes(emote, sherlock, falo, cryptic, anagram, cipher, hotcold)` — approx. L1751 — Builds `itemIndex` and `npcIndex` (item / NPC → steps that use it) for fast page lookups.
- `_build_indexes._add_item(item, ref)` — approx. L1764 — Adds a step reference under an item name.
- `_build_indexes._add_npc(npc, ref)` — approx. L1770 — Adds a step reference under an NPC name.
- `scrape_step_counts(emote, sherlock, falo, cryptic, anagram, cipher, hotcold, force_refresh)` — approx. L1872 — Total steps per type per tier (map/coordinate totals re-counted from their cached guide pages).
- `tag_locations(groups)` — approx. L1950 — Tags steps inside gated places (guilds etc.) with `locations`, using each `location_requirements.json` entry's `clueMatch` regex.
- `main()` — approx. L1975 — Runs every scraper, attaches requirements, writes `clue_steps.json`, prints a summary and validates (exit 1 on problems).

### scripts/generate_diaries.py

Key constants: `TIERS`; `AREAS` (our area name → wiki diary page); `REWARD_NPCS` (who hands out each area's rewards, when the infobox lacks it); `BARROWS_SETS` (brother + four pieces, for "wear any Barrows set" tasks); `CARD_OVERRIDES` (keyed `(area, tier, task n)`: extra `items` / `monsters` / `npcs` / `spells`, `remove`, `itemsAny`, `monstersAny`, `skills`, `skillsAny`, `anyOf`, `quests`, `partialQuests`, `notBoostable`, `lightSource`, `setsAny`, `note`); `REWARD_CARD_REMOVE` (reward cards that aren't real needs); `IRONMAN_ACCOUNT`; regexes `_SKILL_RE`, `_LINK_RE`, `_MAKE_RE`, `_TOOL_RE`, `_GE_CLAUSE_RE`, `_NOT_REQUIRED_RE`, `_PRODUCE_RE`, `_TALK_RE`, `_OTHER_TASK_RE` etc. that decide what counts as a requirement.

Functions:
- `_split_parens(line)` — approx. L267 — Pulls top-level bracketed groups out of a requirement line (ignoring brackets inside links/templates).
- `_top_level_split(line)` — approx. L298 — Splits a requirement line into separate required parts on " and " / ", " (commas inside an "or" list stay together).
- `_outside_brackets(s)` — approx. L311 — The text with links, templates and brackets removed (to test for a real "or").
- `_split_top(line, seps)` — approx. L316 — Splits a line on separators only at the top level (not inside links/templates/brackets).
- `_strip_markup(s)` — approx. L341 — Turns wikitext into readable text (comments, refs, skill/coin templates, links).
- `_tier_sections(wikitext)` — approx. L361 — Finds the Easy/Medium/Hard/Elite sections of a diary page.
- `_rows(section)` — approx. L373 — Each task row as (number, task cell, requirements cell).
- `_ironman_text(txt)` — approx. L399 — Removes Grand Exchange value clauses from reward text (None if the line is only about the GE).
- `_reward_cards(raw_line, ctx)` — approx. L413 — Item, monster and talk-only NPC cards linked in a reward's main line.
- `_rewards(section, ctx)` — approx. L433 — The tier's Rewards bullets as `{text, sub}` in wiki wording, with linked cards.
- `Ctx` (class) — approx. L462 — Shared lookup context: catalog cards, quests, item sources, spells, combat NPCs.
- `Ctx.__init__(self, card_json)` — approx. L468 — Loads the catalog, variant aliases, `quests.json`, `item_sources.json`, `spells.json`, `monster_drops.json`.
- `Ctx.item_card(self, title)` — approx. L488 — Item card for a wiki link (handles plurals, ignores burnt food and category pages like "Jewellery").
- `Ctx.npc_card(self, title)` — approx. L515 — NPC card for a wiki link (with or without a "(place)" suffix).
- `Ctx.is_quest(self, title)` — approx. L519 — True if the link is a quest in `quests.json`.
- `Ctx.quest(self, title)` — approx. L524 — The quest's `quests.json` name; unknown ones are recorded and reported at the end.
- `_only_made(src)` — approx. L532 — True if an item can only be obtained by making it (so its ingredients count).
- `_skills_in(seg)` — approx. L564 — Skill levels in a segment, with whether each is boostable.
- `_category_cards(ctx, title)` — approx. L577 — "any [[crossbow]]" → every item card in that category (and "any grimy herb").
- `parse_task(n, task_cell, req_cell, ctx)` — approx. L587 — The core parser: turns one task row into skills, combat, quests, partial quests, items, any-of groups, monsters, NPCs and notes.
- `parse_task.add_item(c, inferred)` — approx. L616 — Adds an item card, marking whether it was inferred (production/spells) or stated by the wiki.
- `parse_task.add_skill(sk, lv, bst)` — approx. L625 — Records a skill level (keeps the highest; "Combat" goes to the combat level).
- `parse_task.options_in(seg)` — approx. L637 — The alternatives in an "or" segment (skills, quests, item cards).
- `parse_task.add_ingredients(name, depth)` — approx. L797 — For "make X" tasks, adds X's tools and ingredients from `item_sources.json`, recursing into make-only ingredients.
- `_apply_override(area, tier, task, ctx)` — approx. L938 — Applies a task's `CARD_OVERRIDES` entry (add/remove cards, any-of groups, spells' runes, skills, notes, Barrows sets).
- `_tier_summary(tasks)` — approx. L996 — Tier-level skills/quests/items/monsters/NPCs derived from its tasks so they never drift.
- `_page_types(titles)` — approx. L1015 — Wiki infobox type per page (Item, NPC, Monster…), batched 50 per request and cached.
- `_tag_uncarded(result, ctx)` — approx. L1041 — Lists items and NPCs each task mentions that have no card, so the page shows them as "no card" (considered, not missed).
- `_tag_uncarded.carded(t)` — approx. L1044 — True if the title is an item or NPC card.
- `build(ctx)` — approx. L1080 — Builds every area: reward NPC, tasks per tier (with overrides), rewards and tier summary; checks overrides point at real tasks.
- `_fetch_wikitext(page, refresh)` — approx. L1112 — Raw wikitext of a page via `wiki_api.raw` (`?action=raw`), cached in `scripts/cache/wikitext/` (404s remembered); shared by several generators.
- `main()` — approx. L1139 — Parses flags, builds the data, writes `diaries.json`, reports quests not found in `quests.json`.

### scripts/generate_equipment.py

Functions:
- `fetch_json(url)` — approx. L55 — Downloads and parses a JSON URL (used for items-complete.json).
- `build_id_lookup(items_complete)` — approx. L69 — Builds item-id → data and name → data lookups from the OSRSBox dump.
- `classify_combat_type(name, slot, reqs, stats, weapon_type)` — approx. L126 — Decides melee / ranged / magic / all from weapon type, then level reqs, then stats, then name patterns.
- `merge_best(id_lookup, item_ids)` — approx. L189 — Merges reqs, stats, attack speed and weapon type across all item ids of a card (keeps the best stat set).
- `_load_equip_cards(path)` — approx. L221 — Loads equipment cards from the catalog, normalising the v1.0 `{items, npcs}` format.
- `main()` — approx. L246 — Loads cards, fetches OSRSBox, classifies and writes equipment_data.json.

### scripts/generate_food.py

Functions:
- `fetch_wiki_food()` — approx. L30 — Parses the Food/All_food table into `{food name: total HP}` (multi-bite foods summed).
- `main()` — approx. L76 — Keeps foods that are cards and writes food_data.json.

### scripts/generate_icons.py

Functions:
- `_file_url(f)` — approx. L33 — Wiki image URL for a file name.
- `page_images(titles)` — approx. L38 — Page title → thumbnail URL, 50 titles per API request (cached).
- `main()` — approx. L70 — Collects recipe, method and spell icons and writes method_icons.json.

### scripts/generate_ingredient_info.py

Functions:
- `main()` — approx. L35 — Scrapes each non-card ingredient's page and writes ingredient_info.json.

### scripts/generate_monster_locations.py

Functions:
- `base_place(loc)` — approx. L72 — Strips the " (nearby)" suffix from a place name.
- `_template_at(text, i)` — approx. L77 — Returns the balanced `{{...}}` template starting at a position.
- `_params(body)` — approx. L94 — Top-level `|key=value` params of a template body, keeping nested templates/links intact.
- `_links(v)` — approx. L115 — Place links in a location value; "south of [[X]]"-style reference links get " (nearby)".
- `parse_page(text)` — approx. L131 — One NPC page → its infobox versions (ids, locations, quest flag) and its `{{LocLine}}` rows.
- `npc_id_pages()` — approx. L168 — NPC id → wiki pages listing that id (wiki bucket query; cached).
- `page_versions(titles)` — approx. L191 — Page → parsed versions/loclines, batched 50 per request, cached (with a cache version stamp).
- `_norm(s)` — approx. L221 — Lowercases and strips non-word characters for comparing version labels.
- `card_locations(page, ids, pages, id_pages, pack, regions, why)` — approx. L226 — Locations of only the NPC versions the card covers, skipping quest-only copies outside the card's pack region.
- `card_locations.quest_copy_elsewhere(v)` — approx. L243 — Inner helper: True for a non-combat quest NPC version located wholly outside the pack region.
- `main()` — approx. L290 — Builds and writes monster_locations.json, applies overrides and prints checks.
- `main.access_of(loc)` — approx. L337 — Inner helper: access_routes key needed to reach a location (None = open).

### scripts/generate_quests.py

Functions:
- `QuestListEntry` (class) — approx. L45 — One row of List_of_quests: name, page slug, quest points, members flag.
- `QuestListEntry.__init__(self, name, page_slug, quest_points, members)` — approx. L47 — Stores the row's fields.
- `_fetch_quest_list()` — approx. L55 — Parses the three quest tables (free, members, mini-quests) on List_of_quests.
- `_extract_quest_points(rows)` — approx. L121 — Quest points from a quest infobox.
- `_extract_members(html)` — approx. L133 — The quest page infobox's "Members" row: True / False, or None if there is no such row (used for every quest, so mini-quests get the right flag).
- `main()` — approx. L148 — Fetches every quest page, writes quests.json into `--out-dir`, prints a summary. `--limit` needs an `--out-dir` other than scripts/output/.

### scripts/generate_recipes.py

Functions:
- `_item_internal(n)` — approx. L86 — Looks up whether an item is minigame/quest-only (exact `ITEM_INTERNAL` or regex list).
- `fetch()` — approx. L95 — Downloads (or loads cached) all recipe Bucket rows, 500 per request.
- `_plain(s)` — approx. L116 — Strips HTML tags, file links and wiki link markup to plain text.
- `_num(x)` — approx. L123 — Parses a number with commas; None if not numeric.
- `merge_alternatives(recipes)` — approx. L131 — Merges recipes that differ only by one interchangeable ingredient into one with `alts`.
- `fetch_item_quests()` — approx. L165 — Item → quest(s) its wiki infobox names (cached Bucket query).
- `tag_internal(recipes, is_card, has_data, item_quest, quests)` — approx. L188 — Marks recipes that only happen inside a minigame/quest as `internal` (plus minigame gates).
- `tag_internal.ok_item(n, sourced)` — approx. L217 — Inner helper: True if an item is a card, has data, or is made by a normal recipe.
- `_row(p, r, s, skill, xp, known)` — approx. L255 — Turns one Bucket production row into a recipe dict (output, level, xp, ingredients, tools, facility...).
- `main()` — approx. L277 — Builds, merges, tags, adds quest gates and writes recipes.json.

Key constants: `QUEST_RULES`, `FACILITY_INTERNAL`, `ITEM_INTERNAL`, `ITEM_INTERNAL_RE`.

### scripts/generate_shop_owners.py

Functions:
- `fetch()` — approx. L47 — Loads (or downloads, 500 per request) the infobox_shop Bucket rows (page, owner, location).
- `owner_names(owner)` — approx. L65 — In-game owner names from an Infobox Shop `|owner=` value.
- `main()` — approx. L79 — Maps each seller name to owner NPC card(s) and area, writes shop_owners.json.
- `main.access_of(loc)` — approx. L100 — Inner helper: access_routes key needed for a shop location.
- `main.shop_page(s)` — approx. L119 — Inner helper: matches a seller name to a shop page (with/without "(variant)" and trailing full stop).

### scripts/generate_skilling.py

Functions:
- `main()` — approx. L44 — Validates card names, quests, access keys and locations in skilling_curated.json, then writes skilling.json.

### scripts/generate_slayer.py

Functions:
- `_clean(text)` — approx. L54 — Strips HTML comments, refs and citation/note templates from wikitext.
- `_cells(row)` — approx. L62 — Splits a wikitable row into cell texts, dropping attribute prefixes.
- `_tables_with(text, col)` — approx. L71 — Every wikitable whose header has a column containing `col`, as (labels, rows).
- `_col(cols, row)` — approx. L94 — Cell under the first column whose label contains one of the names.
- `_task_name(cell)` — approx. L103 — `[[Aberrant spectre]]s` → (display name, link target).
- `_parse_unlock(cell, quests)` — approx. L112 — Task unlock cell → `{slayer, combat, quests, ability}`.
- `parse_master(name, quests)` — approx. L127 — A master's task table → task rows (weight, amount, extended, unlock, alternatives, Konar locations).
- `_fetch_follow(page)` — approx. L161 — Wikitext of a page following up to 2 redirects.
- `parse_task_page(task, target)` — approx. L172 — "Slayer task/<Task>" page → requirements and the monsters that count, with locations.
- `location_regions(titles)` — approx. L217 — Location page → wiki leagueRegion (batched 50, cached).
- `monster_slayer_levels(titles)` — approx. L251 — Monster page → Slayer level needed (batched, cached).
- `main()` — approx. L279 — Builds slayer.json in order: masters → tasks → regions → overrides → merge → access → levels → location gates.
- `main.access_of(loc)` — approx. L346 — Inner helper: access_routes key needed to reach a location.

Key constants: `REGION_ACCESS` (wiki region → access_routes key).

### scripts/generate_sources.py

Functions:
- `load_cards(card_json_path)` — approx. L87 — Loads the catalog as a flat card list (v1.0 `{items, npcs}` normalised to the old shape).
- `monster_cards(cards)` — approx. L143 — Cards in the "Monster" category (all NPC cards).
- `item_cards(cards)` — approx. L148 — Cards in the "Resource" category (all item cards).
- `quest_item_cards(cards)` — approx. L153 — Item cards flagged questItem. Always empty: the live catalog has no quest-item field, so pass 3 does nothing (documented in the code).
- `card_name_set(cards)` — approx. L158 — Lowercase set of card names.
- `wiki_page_name(card_name)` — approx. L163 — Guesses a wiki page name by stripping a "(…)" suffix.
- `card_wiki_page(card)` — approx. L173 — The card's wiki page: explicit `wikiPage` field first, else the guess.
- `build_monster_drops(monsters, item_names_lc, limit, only)` — approx. L189 — Pass 1: fetches each monster page (or /Loot subpage) and keeps drops that are item cards.
- `_is_redirect(html)` — approx. L260 — True if the wiki served the page via a redirect.
- `_alias_key(name)` — approx. L265 — Normalises item names for variant matching ("bolts (p)" = "bolts(p)").
- `load_variant_aliases(card_json_path)` — approx. L270 — Variant name → card name from the catalog's `tcg.variants` (the authoritative item→card mapping).
- `set_variant_aliases(aliases)` — approx. L300 — Installs the variant map used by `_card_for_drop`.
- `_card_for_drop(item, item_names_lc)` — approx. L306 — Card name for a wiki drop row (exact, variant, or same-name rule), or None. Reused by other generators.
- `_tcg_drops(raw_drops, item_names_lc)` — approx. L333 — Filters raw drop rows to card items with known rarity (keeps the higher rate on clashes).
- `_empty_monster_entry()` — approx. L348 — Blank monster_drops entry for a page that couldn't be fetched.
- `load_gathering()` — approx. L363 — Loads `gathering_sources.json` (skipping `_` keys).
- `build_item_sources(item_cards_list, monster_drops, gathering)` — approx. L372 — Pass 2: inverts monster drops into item → monsters, and adds gathering.
- `build_quest_chains(quest_items, item_names_lc, monster_names_lc, limit)` — approx. L423 — Pass 3: quest pages → prerequisites, reward cards, monster cards, quest NPC.
- `enrich_with_quests(item_sources, quest_chains)` — approx. L485 — Adds quest-reward names to item_sources entries.
- `_has_source(entry)` — approx. L520 — True if an item_sources entry already has any source.
- `build_production_spawns(item_cards_list, item_sources, monster_names_lc, limit)` — approx. L530 — Pass 4: item pages → production, spawns, shops, and "Item sources" backfill.
- `write_json(path, data, label)` — approx. L621 — Writes indented UTF-8 JSON with LF endings and logs it.
- `_wiki_image_url(image_path)` — approx. L633 — Catalog imagePath → wiki 130px thumbnail URL.
- `_write_card_metadata(cards, out_dir)` — approx. L647 — Writes card_categories.json and card_details.json (examine, imageUrl, imagePath, tier, regions).
- `parse_args()` — approx. L684 — CLI flags (see How to run).
- `_backup_outputs(out_dir)` — approx. L604 — Copies the existing `_OUTPUT_FILES` in `out_dir` to `_BACKUP_DIR`/generate_sources-<timestamp>/; returns that folder (None if nothing to back up).
- `main()` — approx. L705 — Refuses a partial run (`--limit` / `--monster`) into scripts/output/, backs up the outputs before a full run there (`_backup_outputs`), creates the output folder (no longer done at import), then runs passes 1-6 in order and writes outputs.

Key constants: `_OUT_DIR` (scripts/output/), `_BACKUP_DIR` (scripts/cache/output_backup/), `_OUTPUT_FILES` (the five files a run rewrites: monster_drops, item_sources, quest_chains, card_categories, card_details), `_CLUE_SOURCES`, `_GATHERING_JSON`, `_SUFFIX_RE`, `_NON_MAIN_GAME_RE`.

### scripts/generate_spells.py

Functions:
- `parse_book(book, wikitext)` — approx. L58 — One spellbook page → `{spell: {book, level, runes, members}}`.
- `rune_sources()` — approx. L88 — Elemental rune → combination runes and staves that also supply it (plus `EXTRA_SOURCES`).
- `rune_sources.add(rune, item)` — approx. L92 — Inner helper: adds a source once.
- `main()` — approx. L123 — Parses all books (drops removed spells) and writes both files.

### scripts/item_scraper.py

Functions:
- `parse_production(html)` — approx. L60 — Production methods on the page (skill, level, facilities, ingredients, output quantity).
- `parse_spawns(html)` — approx. L137 — Spawn location names (deduplicated, in order).
- `parse_shop_available(html)` — approx. L175 — True if the page lists any shop.
- `parse_item_sources(html)` — approx. L193 — Rows of the "Item sources" table (source, level, quantity, fraction, label).
- `_currency_from_price_cell(cell)` — approx. L294 — Currency name from a shop price cell (coin image or seller lookup).
- `parse_shop_locations(html)` — approx. L329 — Shops selling the item `{seller, price, currency}`, skipping zero-stock resellers.
- `_row_texts(tr)` — approx. L383 — Stripped text of every cell in a table row.
- `_parse_skill_table(table)` — approx. L390 — Skill/Level/XP table → `{skill, level, xp, facilities, quests}`.
- `_parse_ingredient_table(table)` — approx. L453 — Item/Quantity/Cost table → (ingredients, output quantity).

### scripts/location_reqs.py

Functions:
- `load()` — approx. L35 — `{location: entry}` from the file without `_` meta keys (cached).
- `reviewed_no_gate()` — approx. L44 — The `_reviewedNoGate` map (places checked and found open).
- `_index()` — approx. L49 — Lowercase name → name as written, for case-insensitive lookup.
- `lookup(name)` — approx. L54 — The entry for a place (case-insensitive) or None.
- `own_gate(entry)` — approx. L60 — Just the non-empty gate fields of an entry.
- `gate_for(name, _seen)` — approx. L65 — Full gate of a place including its parent chain.
- `_same(a, b)` — approx. L80 — Deep equality ignoring key order.
- `merge_gate(a, b)` — approx. L85 — Gate that needs both a and b (quests/diaries union, higher skill level, different any-of lists moved to `allOf`).
- `validate(quests, card_ok, diary_areas, access)` — approx. L117 — Returns problems: unknown quests, cards, diaries, access keys, parents.
- `validate.check(where, g)` — approx. L122 — Inner helper: checks one gate, recursing into anyOf/allOf.
- `validate_with_outputs()` — approx. L167 — Runs `validate()` against the committed outputs and the live catalog.

Key constants: `GATE_KEYS`, `CARD_GROUPS` (location card groups, unrelated to card_groups.py).

### scripts/loot_parser.py

Functions:
- `DropRow` (class) — approx. L54 — One parsed drop row: item, quantity, fraction, wiki label, our rarity, rare-drop-table flag.
- `_fraction_rate(frac)` — approx. L65 — "N/D" → probability, for picking the better duplicate; understands decimals and thousands commas ("1/26.9", "1/2,448").
- `parse_drops(html)` — approx. L80 — All drop rows from the page's item-drops tables, deduplicated per item.
- `_parse_row(tr, section, is_rdt)` — approx. L115 — One table row → DropRow (None for headers).
- `_extract_item_name(cell)` — approx. L140 — Item name from the item cell.
- `_extract_rarity(cell)` — approx. L148 — (fraction, colour label) from the rarity cell.
- `parse_monster_info(html)` — approx. L181 — Slayer level and combat level from the monster infobox.

### scripts/quest_parser.py

Functions:
- `SkillReq` (class) — approx. L38 — A skill level a quest needs, with boostable flag.
- `QuestInfo` (class) — approx. L45 — Everything parse_quest extracts from one page.
- `parse_quest(html)` — approx. L56 — Parses the questdetails table into a QuestInfo (empty if not found).
- `_find_infobox(soup)` — approx. L87 — Finds the quest infobox table.
- `_parse_infobox_rows(infobox)` — approx. L96 — Infobox header → cell map.
- `_parse_questdetails(qd)` — approx. L109 — Questdetails header → cell map.
- `_extract_prerequisites(cell)` — approx. L121 — Prerequisite quest names from the Requirements cell.
- `_extract_skill_requirements(cell)` — approx. L164 — Skill requirements from the `scp` spans.
- `_extract_items_required(cell)` — approx. L199 — Required item names (first link of each list item).
- `_extract_kills(cell)` — approx. L236 — (required kills, avoidable kills) from "Enemies to defeat".
- `_extract_start_npc(cell)` — approx. L281 — Start NPC name when the start point is "talk to" someone.

### scripts/rarity_mapper.py

Functions:
- `from_fraction(fraction)` — approx. L41 — Rarity label from a fraction string ("Unknown" if unparseable).
- `from_wiki_label(label)` — approx. L76 — Normalises a wiki rarity label.
- `best(fraction, wiki_label)` — approx. L84 — Prefers the fraction, falls back to the label.

### scripts/reorder_categories.py

Functions:
- `prioritise(tags, first, last, remove)` — approx. L38 — Reorders a tag list: given tags first, others last, some removed.
- `f2p_last(tags)` — approx. L55 — Moves "F2P" to the end.
- `apply_rules(name, tags)` — approx. L82 — Applies all the per-item-type ordering rules to one card.
- `main()` — approx. L235 — Applies the rules to every card and writes (or prints) the result.

### scripts/scan_location_requirements.py

Functions:
- `used_location_names()` — approx. L28 — Every location name used by the outputs and curated methods.
- `_field(text, key)` — approx. L50 — Values of a numbered infobox field (`|requirement1 = …`).
- `infobox_requirements(titles)` — approx. L57 — Page → `{requirement, quest, type}` from its Infobox Location (cached).
- `main()` — approx. L88 — Prints places with wiki requirements not covered by location_requirements.json.

### scripts/wiki_api.py

Functions:
- `_read(r, deadline)` — approx. L28 — Reads a whole response, raising TimeoutError past a wall-clock deadline.
- `_get(url, timeout)` — approx. L40 — Rate-limited GET (~1.1 s apart) with 3 attempts and back-off; 404 raised at once.
- `get_json(url, timeout)` — approx. L65 — GET + JSON decode for action=query / action=bucket; refuses any `action=parse` URL.
- `raw(title, timeout)` — approx. L72 — Raw wikitext via `/w/<Page>?action=raw`, following up to 3 redirects.

### scripts/wiki_fetcher.py

Functions:
- `_cache_path(page_name)` — approx. L42 — Disk cache path for a page name.
- `_get_with_deadline(url, total_secs)` — approx. L48 — GET with per-read timeouts and a total time cap.
- `fetch(page_name)` — approx. L62 — Page HTML from cache, else the wiki (sleeps ~1.1 s after each live request; failures not cached).
- `fetch_with_loot_fallback(page_name)` — approx. L94 — Monster page, or its /Loot subpage when the main page has no drops table.
- `_has_drops_table(html)` — approx. L115 — Quick check for a drops table (loose on purpose).

---

## Part 7. Conventions and gotchas

### Guiding principle
- Every feature must work for **any account**, brand-new or an established cardcore account. Show starter / first-unlock paths as well as advanced progress, and test with a simulated new account (the page's random "Re-roll" collection, or an account with few cards).

### Strict Bronzeman rules the planner follows (Lottie's rules)
- **Any interaction with an NPC that has a card needs that card**: talking, trading, starting a quest, slayer masters, NPCs who speak in a cutscene. No exceptions: not for NPCs of started quests, not Veos, not the Ironman tutor. This is stricter than the plugin; never copy the plugin's exemptions into planner data, only list them in the Rules tab as differences.
- Killing or pickpocketing an NPC needs its card. Using, eating, equipping or using an item as an ingredient needs its card.
- Buying from a shop needs the **Coins** card (or the currency's card) and the shopkeeper's card, if one exists.
- Gathering (mine, chop, fish, hunt) needs only level and tool. Thieving from a stall needs only level.
- Producing an output does **not** need the output's card. Picking up loot / ground spawns and receiving quest rewards need no card. Items held without a card can only be banked.
- Foil cards are the same as regular. Selling a card loses access until you get it back.
- NPCs or items with no card in the catalog can't be restricted; the page shows them as grey "no card" chips.
- When the rules change, update the Rules tab (`_rulesTabHtml` in preview.html). Note: its text still says "5,200 cards / 1,391 NPCs / 3,809 items"; the live catalog is 5,172 (1,400 NPC + 3,772 item).

### Data you must not hand-edit, and where fixes go
- **Committed output JSONs carry hand fixes** (monster_drops, item_sources, card_categories, card_details, boss_loot, collection_log). Never copy a full regeneration over them: run into a scratch `--out-dir`, diff, and patch only what you meant to change.
- **item_sources.json:** never edit directly. Put fixes in `scripts/item_sources_overrides.json` (applied by generate_sources.py pass 6; a field replaces the generated one, `null` deletes it).
- **Diaries are generated.** Don't hand-edit diary tasks (in diaries.json or DIARY_DATA). Fix the parser in generate_diaries.py, or add to its `CARD_OVERRIDES` / `REWARD_NPCS` / `REWARD_CARD_REMOVE`. `build()` stops if a `CARD_OVERRIDES` key names a task that no longer exists.
- **Bosses, Slayer, skilling, clue steps, monster locations are generated** from curated files: edit `boss_curated.json`, `slayer_curated.json`, `skilling_curated.json`, `clue_curated.json`, `monster_locations_overrides.json`, then re-run the generator.
- **Out-of-date note in CLAUDE.md:** it calls SLAYER_TASKS, SLAYER_CARD_GATES, BOSS_DATA and DIARY_DATA "hand-written data in preview.html". That is no longer true: `SLAYER` is loaded from output/slayer.json, `BOSS_DATA` from output/bosses.json and `DIARY_DATA` from output/diaries.json; SLAYER_TASKS / SLAYER_CARD_GATES no longer exist. The remaining hand-written data in the page is small constants (e.g. `AREA_QUESTS`, `SPELLBOOK_GATES`, `SPELL_ITEM_REQS`, `SKILL_UNLOCK_QUESTS`, `TOOL_TIERS`, `WARM_CLOTHING_BY_SLOT`, `REQ_GROUPS`, `CRAFTED_CARD_ROUTES`).
- **Hand-curated outputs:** `output/access_routes.json` and `output/bm_quest_cards.json` have no generator. Edit them directly (keep the wiki quotes).
- **Item → card matching** uses the catalog's `tcg.variants` (via `generate_sources._card_for_drop` in Python, `card_aliases.json` / `_cardInfo` in the page). Never invent suffix-stripping rules.
- **Wiki page variants:** the catalog's `wiki.page` sometimes points at a "(Deadman)" page; generate_sources skips Deadman / NMZ / PvM Arena / Construction pages (`_NON_MAIN_GAME_RE`). If a monster's drops look odd, check its `wiki.page` first.
- **NPC cards renamed off item clashes** ("Manta ray (sailing)", "Rock Golem (monster)"): look NPCs up with `catalog_names.npc_names()`.
- **Catalog refresh:** copy `~/.runelite/OSRS-TCG/catalog/cards.live.json` over `research/card-catalog-live.json`, diff names against the old one, map removed/renamed names (record them in `research/catalog_migration.json`), patch curated data, regenerate into a scratch folder and patch outputs.

### Wiki access rules (wiki staff request, GitHub issue #1, 18 Jul 2026)
- **Never use `api.php?action=parse`**, not even for a one-off check: it forces an uncached page render. `wiki_api.get_json()` refuses such URLs.
- Raw page text: the plain page URL `https://oldschool.runescape.wiki/w/<Page>?action=raw` (served from cache) via `wiki_api.raw(title)`. Rendered HTML: plain page URLs via `wiki_fetcher.fetch()`. Batched reads of stored data (`action=query`, `action=bucket`) via `wiki_api.get_json()`.
- About 1 request per second, a descriptive User-Agent, and cache everything so re-runs hit the wiki zero times.
- **The bot check:** since 21 Oct 2026 the wiki's Weird Gloop bot check answers uncached requests from this machine with a JS challenge (502 for images, 403 for pages), probably triggered by heavy scripted use. Retrying never helps. Cached pages still work. This is why card art comes from osrs-tcg.net, skill/quest/clue icons are local files, and other images go through `/wikiimg/` with the RuneLite fallback. Some icons (spells, Construction furniture) stay blank until the wiki serves them again. Go easy on uncached wiki fetches.
- The user's global notes mention `api.php?action=parse` for OSRS; this project's rule wins.

### The data check
- On every page load `loadData()` runs `_validateDataNames()`, which checks that card, quest and access names in slayer.json, bosses.json, DIARY_DATA, clue_steps.json, location_requirements.json and item_sources activity sources all resolve. Problems are printed to the browser console as `[data check]` warnings (the page still works). **Keep the console free of `[data check]` warnings**; after any data change, open the console (Cmd+Option+J in Chrome) or run the headless check.
- Python side: `python3 scripts/location_reqs.py` validates location_requirements.json; generate_bosses / generate_slayer write validation reports to `scripts/cache/`; generate_clue_steps exits 1 when its validation finds problems.

### Rarity labels
- Wiki tiers only: Always; Common ≤1/25; Uncommon <1/100; Rare <1/1,000; Very Rare beyond. Raid unique-table items are "Unique" with their share of the unique roll (e.g. 2/60), never an invented per-raid rate. Items gated by a wiki footnote (consolation loot, first completions, CM time limits, Konar-only keys, KC milestones) are "Conditional". Multi-roll chests are combined (Barrows 7 × 1/2,448 ≈ 1/350).

### Ironman
- `generate_diaries.IRONMAN_ACCOUNT = True` folds ironman requirements into the normal ones and strips Grand Exchange wording. The planner assumes no GE and self-sourced items.

### Page-side caches to remember
- Many lookups are memoised (`_canGetCache`, `_getNeedsMemo`, `_accessCache`, `_completableCache`, clue caches). They reset when a signature of account / owned cards / quests / started quests / diary ticks (`_diaryTickVer`) / levels changes. `renderMonster` and `_recCombatCands` swap in their own `_accessCache` and restore the caller's in a `finally`. If a status looks stale after a change, check the cache is reset (the 20 Oct "quest statuses depended on which tabs you'd visited" bug was `_accessCache` storing nested cycle-guard results).
- Live sync (`_startLiveSync`) is deliberately disabled because of cloud API rate limits; Refresh is manual.

### Working rules
- `PROJECT_LOG.md` gets an entry at the end of each session; keep README.md and CLAUDE.md current when the project state changes.
- Git: only push to the charbottie repo; never commit or push inside `plugins/`.
- The Bronzeman plugin (`plugins/bronzeman-tcg/`) had its own handoff doc, `CLAUDE.md`, until plugin v0.2.15 removed it; read the last copy with `git -C plugins/bronzeman-tcg show e91d56b^:CLAUDE.md`. Never rename a config keyName, never set a non-empty default on user-editable list fields, plan before implementing, and Felmeme commits.

---

## Part 8. Completeness check

Counted with a script on 22 Oct 2026: "Found" = definitions found in the code (preview.html: lines matching `^(async )?function NAME(` or `^(const|let|var) NAME` inside `<script>`; Python: every `def` / `class`, including methods and nested functions, via the `ast` module). "Documented" = entries with an approx. line in this document. A line that declares several variables at once (e.g. `let monsterDrops = {}, itemSources = {}, ...`) counts once and has one entry naming them all.

| File / range | Found | Documented | Match |
|---|---|---|---|
| scripts/preview.html (Part 5) | 575 | 575 | yes |
| card_groups.py | 0 | 0 | yes |
| catalog_names.py | 1 | 1 | yes |
| decode_collection.py | 14 | 14 | yes |
| decode_completed_quests.py | 2 | 2 | yes |
| generate_boss_loot.py | 11 | 11 | yes |
| generate_bosses.py | 5 | 5 | yes |
| generate_card_aliases.py | 1 | 1 | yes |
| generate_card_versions.py | 5 | 5 | yes |
| generate_clue_sources.py | 18 | 18 | yes |
| generate_clue_steps.py | 73 | 73 | yes |
| generate_diaries.py | 32 | 32 | yes |
| generate_equipment.py | 6 | 6 | yes |
| generate_food.py | 2 | 2 | yes |
| generate_icons.py | 3 | 3 | yes |
| generate_ingredient_info.py | 1 | 1 | yes |
| generate_monster_locations.py | 12 | 12 | yes |
| generate_quests.py | 6 | 6 | yes |
| generate_recipes.py | 10 | 10 | yes |
| generate_shop_owners.py | 5 | 5 | yes |
| generate_skilling.py | 1 | 1 | yes |
| generate_slayer.py | 13 | 13 | yes |
| generate_sources.py | 27 | 27 | yes |
| generate_spells.py | 4 | 4 | yes |
| item_scraper.py | 9 | 9 | yes |
| location_reqs.py | 11 | 11 | yes |
| loot_parser.py | 7 | 7 | yes |
| quest_parser.py | 11 | 11 | yes |
| rarity_mapper.py | 3 | 3 | yes |
| reorder_categories.py | 4 | 4 | yes |
| scan_location_requirements.py | 4 | 4 | yes |
| wiki_api.py | 4 | 4 | yes |
| wiki_fetcher.py | 5 | 5 | yes |
| server.py | 31 | 31 | yes |
| **Total** | **916** | **916** | yes |

Files: every file under `scripts/` (excluding `scripts/cache/`) has an entry in Part 3: 1 page, 1 server, 1 requirements.txt, 1 dev script, the icons folder (31 PNGs), `output/.gitkeep`, 12 JSON files in `scripts/`, 28 JSON/log files in `scripts/output/`, and 32 Python scripts besides server.py.

Re-checked by an audit script on 22 Oct 2026, after the comment pass: all 912 names were present, every preview.html function has a `//` comment above it, every Python `def` / `class` has a docstring, and every "approx. L" number in Parts 4 to 6 was reset to the current line (the comment pass had moved preview.html lines down by up to ~450).

Re-checked again on 22 Oct 2026 after the KNOWN_ISSUES.md fixes: 916 names (preview.html 575, up 3: `_simPoolSize`, `_gateCanon`, `_diaryTickVer`; generate_sources.py 27, up 1: `_backup_outputs`), all documented, every "approx. L" number in Parts 4 to 6 reset to the current line by script, and the removed names (`_KILL_RE`, `_USE_RE`, `generate_food.UA`, the inner `_poll` of `_startLiveSync`) dropped.

To re-run this check after the code changes, count definitions the same way (e.g. `grep -cE '^(async )?function |^(const|let|var) ' scripts/preview.html`, which also counts a few lines before `<script>` if any) and compare with this document.
