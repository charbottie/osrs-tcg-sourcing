# Known issues

Small problems found while documenting the code in October 2026. **None of them stopped the planner from working day to day.** They were written down first, so the documentation pass changed no behaviour, and then **fixed on 22 Oct 2026**. The numbered record below says how each one was fixed. A short list of things that are still open, or need checking before the next data regeneration, is at the end.

Search the file for the name (Cmd+F) rather than relying on line numbers: they move when code is added above.

How much each one mattered:
- **Data**: could make an update script produce slightly wrong data.
- **Display**: something on the page showed the wrong text or a stale value.
- **Tidy**: unused or confusing code; harmless.

## Fixed: the planner page (`scripts/preview.html`)

| # | Where | How it was fixed | Impact |
|---|-------|------------------|--------|
| 1 | `lookupLevels` | Remembers levels under the resolved account (`_rsn`), not the raw argument. | Display |
| 2 | `_itemGetNeeds` / `_accessMet` caches | Cache signatures now include the account (`_currentRsn`), `startedQuests.size` and the new `_diaryTickVer` (bumped by `toggleDiaryTick`). | Display |
| 3 | `renderMonster`, `_recCombatCands` | Save the caller's `_accessCache` and restore it in a `finally`. | Display |
| 4 | `calcDpsForItem` | `computeTotalStats(swapSlot, swapItem)` takes optional swap arguments; the DPS preview uses it, so 2H weapon and shield previews match. | Display |
| 5 | `_renderSkillHome` | The three tables that were never shown were removed. | Tidy |
| 6 | `_startLiveSync` | The dead inner `_poll` was removed; the section header says live sync is disabled (refresh on page load or ↻ Refresh). | Tidy |
| 7 | Duplicate `m.label === b.label` test | Now `m.label === b.label \|\| (b.kind === 'quest' && m.quest === b.key)`. | Display |
| 8 | (withdrawn) | An earlier note said `_shopStatus` never uses `curCard`. That was wrong: it is returned and used by `_shopRowHtml` to colour the shop currency. Kept so the numbering doesn't change. | n/a |
| 9 | `updateSimBar` | Shows the real "N cards owned (P%)", using the new `_simPoolSize`. | Display |
| 10 | `clearWishlist`, `wishlistDiaryTier` | Clearing the wishlist resets `wishlistQuestRec`; the tier button label goes back to "☆ Wishlist missing cards". | Display |
| 11 | Unescaped names and notes | `escHtml` added in `openNotePopover`, `_renderSlayerDetailInner`, `questItemHtml`, `showQuestDetail` and the `showPackDetail` heading; `renderDiaryList` passes the diary name through `data-dn`. | Display |
| 12 | `isDiaryTicked` / `toggleDiaryTick` | Browser storage access is wrapped in try/catch. | Display |
| 13 | `renderDiaryList` pips | Show "locked" from `evaluateDiaryTier`. | Display |
| 14 | `_gateSame` | Compares through the new `_gateCanon` (object keys sorted), so key order no longer matters. | Tidy |
| 15 | `buildCardList` | Clears `allCards` before building. | Tidy |
| 16 | Misplaced comments | Moved or corrected. | Tidy |

## Fixed: the update scripts (`scripts/*.py`)

| # | Where | How it was fixed | Impact |
|---|-------|------------------|--------|
| 17 | `generate_diaries.py` `CARD_OVERRIDES` | The duplicate `("Desert", "easy", 8)` entries were merged; `output/diaries.json` was patched for that Desert easy task (+3 lines). | Data |
| 18 | `generate_sources.py` pass 3 | Not fixable; see "Still open" below. | Data |
| 19 | `generate_sources.py` `--limit` / `--monster` | Both need an `--out-dir` other than `scripts/output/` (the script exits with a message otherwise). `--limit` now limits monsters only. | Data |
| 20 | `generate_sources.py` full runs | A full run into `scripts/output/` first copies the five output files to `scripts/cache/output_backup/generate_sources-<timestamp>/` (new `_backup_outputs`, `_BACKUP_DIR`, `_OUTPUT_FILES`). Still diff before keeping a run. | Data |
| 21 | `server.py` `/api/generate/run` | The run is claimed under the lock (`_generate_running`) before the thread starts, so two quick requests can't start two runs. | Data |
| 22 | `decode_collection.py` | Without `--player`, uses the single source with the most cards instead of merging profiles. | Display |
| 23 | `generate_clue_sources.skilling_sources` | Guards against a missing tier modifier. | Data |
| 24 | `generate_clue_steps._parse_cryptic_table` | A one-cell row gets an empty location; the file is read as UTF-8. | Data |
| 25 | `generate_boss_loot.py` | Handles a page with no `.mw-parser-output`; new `--in-dir` sets where inputs are read. | Data |
| 26 | `generate_slayer.py` | A pending `taskOverrides` entry without `"task"` falls back to its override key. | Data |
| 27 | `loot_parser._fraction_rate` | Parses decimal and comma rates ("1/26.9", "1/2,448"). **Review before the next regeneration**, see below. | Data |
| 28 | `quest_parser.parse_quest` | The early-return path includes `avoidable_kills`. | Data |
| 29 | `generate_quests.py` | Uses `removeprefix`; `members` comes from each quest's infobox (`_extract_members(html)`); new `--out-dir`, and `--limit` requires it. | Data |
| 30 | `generate_recipes.py` | `merge_alternatives` runs before the "add alternatives" step. | Data |
| 31 | `rarity_mapper.py` | "Extremely rare" maps to Very Rare. | Data |
| 32 | `card_groups.py` | Marked DOCUMENTATION ONLY at the top of the file. | Tidy |
| 33 | Minor unused code | Removed: `_KILL_RE` / `_USE_RE` (generate_diaries), `UA` and the `urllib` import (generate_food), the `tier` parameter of `generate_clue_sources._kind`, the argument of `generate_sources._empty_monster_entry`; generate_sources no longer creates the output folder when imported. | Tidy |

## Still open / to review

- **#18 can't be fixed here.** The live card catalog has no quest-item field, so `generate_sources.py` pass 3 finds no quest items and does nothing, and `quest_chains.json` stays `{}`. This is noted in the code.
- **Review before the next `generate_sources.py` regeneration (#27).** Now that decimal rates like "1/26.9" parse, the dedup step keeps a different duplicate drop row for some monsters. A cache-only test run changed 30+ monsters: all revenants, Lesser and Greater demon, Jelly, Ice giant, Lizardman, Lobstrosity, Zygomite and White Knight. Examples: Revenant goblin Manta ray 1/431.95 → 1/15.67; Lesser demon Sapphire 1/128 → 1/31.2. The committed `monster_drops.json` was not changed. Check these rates against the wiki before keeping a regeneration. Some look suspicious (the revenant Manta ray especially). The dedup rule "keep the most common row" may be wrong for drops that appear in several tables, such as a main table plus a rare-drop or secondary table. The rule may need changing, not just the rate parser.
- **Mini-quests in `quests.json`.** The committed file still marks the 19 mini-quests `members: false`. The next `generate_quests.py` run corrects this (#29).
- **Hand fixes in committed outputs.** A cache-only regeneration differs from the committed `diaries.json`, `quests.json`, `card_details.json` and `card_categories.json` in places that are older hand fixes. Always back up and diff before keeping a regeneration.
