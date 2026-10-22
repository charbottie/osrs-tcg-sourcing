# Bronzeman Planner: User Guide

The planner shows what your Bronzeman TCG account can do with the cards it owns.
It runs on your own computer and opens in your web browser.

## Starting the planner

1. Open the **Terminal** app. Press Cmd+Space, type `Terminal` and press Enter.
   (Or go to Applications, then Utilities, then Terminal.)
2. Copy this line, paste it into Terminal and press Enter:

   ```
   cd ~/git/osrs_tcg && python3 scripts/server.py
   ```

3. **Leave that Terminal window open** while you use the planner. Closing it stops the planner.
4. In your browser, open **http://localhost:8765/preview.html**
   (If you only type `localhost:8765` you get a plain list of files. Click `preview.html` in it.)

If Terminal shows some error text ending in **"Address already in use"**, the planner is already running
(probably in another Terminal window). Nothing is broken. Just open the link.

**To stop it:** click the Terminal window and press Ctrl+C, or close the window.

## Choosing your account

- Pick your account from the drop-down at the top right. The planner finds every OSRS TCG account
  on this computer by itself.
- Press **↻ Refresh** after opening packs or finishing quests. It reloads your cards, your skill
  levels (from the hiscores) and your completed quests. The page does not update on its own.
- If no account is found, the planner shows a random made-up collection, with a **Re-roll** button.
  That is a demo, not your account.

## The tabs

| Tab | What it answers |
|-----|-----------------|
| Cards | Everything about one card: where it drops, how to make it, what uses it. |
| Wishlist | The cards, quests, Slayer tasks and clue steps you are working towards, and which packs help most. |
| Equipment | The best gear you can wear with your cards, with a DPS calculator. |
| Skilling | Which training methods you can use for each skill, and what is a card away. |
| Questing | Which quests you can do now, which are close, and what blocks the rest. |
| Diaries | Every Achievement Diary task, the cards each one needs, and the rewards. Tick tasks you have done. |
| Bosses | Which bosses, raids and minigames you can do, what they need, and their loot. ◆ marks collection-log items. |
| Slayer | Which masters you can use and which of their tasks you can do. Tick your Slayer unlocks here. |
| Clues | For each clue tier: can you get the clue, and can you finish the steps. |
| Packs | What is in each pack, what you own, and which packs fill your biggest gaps. |
| Rules | The Bronzeman rules the planner follows, and how each tab decides things. |

Most tabs open on an **Overview** page: what is ready, what is closest, and the cards you need most.

## Symbols and colours

- **✓** you meet this requirement.
- **✗** you don't meet it yet.
- **◐** almost: you own the card but can't get the item yet, it is a card away, or a quest is marked started.
- **Green / Ready**: you can do it now. **Amber / Partial**: some cards missing.
  **Red / Locked**: a quest, level or area is still in the way.

**Hover popups:** hover over underlined places, "any of" chips and pack names to see what they need,
with a ✓ or ✗ for your account. Click a card or quest name to jump to it. Use ← Back and Forward → at the top.

## If something looks wrong

- **Page looks old or broken:** do a hard refresh with **Cmd+Shift+R**.
- **Nothing loads, or errors everywhere:** the planner is probably not running. Start it again (see above).
- **Some icons are blank:** the OSRS Wiki now runs a bot check that blocks pictures it hasn't sent before.
  This is not your fault and the planner still works. Card art comes from osrs-tcg.net. Skill, quest
  and clue icons are stored in the project (`scripts/assets/icons/`). Other icons fill in over time.
- **Be gentle with the wiki.** Don't run the update scripts over and over, and avoid rebuilding
  everything from the wiki at once. The wiki may block this computer.

## Advanced (only after a card catalog update)

Only do this when the OSRS TCG plugin adds, removes or renames cards. Day-to-day use never needs it.
The "update scripts" rebuild the planner's data from the card catalog and the OSRS Wiki.

1. Make a copy of the `scripts/output` folder first, so you can undo. In Finder, open the `osrs_tcg` folder,
   then `scripts`, right-click `output` and choose **Duplicate**.
2. Copy the new catalog over the old one:
   ```
   cd ~/git/osrs_tcg
   cp ~/.runelite/OSRS-TCG/catalog/cards.live.json research/card-catalog-live.json
   ```
3. One time only, install what the update scripts need: `pip3 install -r scripts/requirements.txt`
4. Run the update scripts in this order, one line at a time:
   ```
   python3 scripts/generate_sources.py --card-json research/card-catalog-live.json
   python3 scripts/generate_boss_loot.py --card-json research/card-catalog-live.json
   python3 scripts/generate_spells.py
   python3 scripts/generate_diaries.py --card-json research/card-catalog-live.json
   python3 scripts/generate_recipes.py
   python3 scripts/generate_skilling.py --card-json research/card-catalog-live.json
   python3 scripts/generate_shop_owners.py --card-json research/card-catalog-live.json
   python3 scripts/generate_icons.py
   ```
5. Restart the planner: in its Terminal window press Ctrl+C, then paste the start line from
   "Starting the planner" again. Then press Cmd+Shift+R in the browser.

Some data files contain fixes made by hand. A full rebuild can undo them. If things look worse
afterwards, put your copy of `scripts/output` back. Then compare old and new before replacing
anything. `generate_sources.py` also saves its own copy of the old files before a full run, in
`scripts/cache/output_backup/`. (For whoever does the comparing: `generate_sources.py`,
`generate_boss_loot.py`, `generate_diaries.py` and `generate_quests.py` accept `--out-dir <folder>` to
write their files somewhere else first; `generate_boss_loot.py --in-dir <folder>` reads that folder's
`monster_drops.json` / `bosses.json`. The test options `--limit` / `--monster` only work with an
`--out-dir` other than `scripts/output`.)
