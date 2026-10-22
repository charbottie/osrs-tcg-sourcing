# OSRS TCG: Bronzeman Planner

A local web app for **OSRS TCG** players on the **Bronzeman TCG** RuneLite plugin.
It reads your card collection from RuneLite and shows what you can and can't do with it:
quests, skilling, diaries, bosses, Slayer, clues, gear and packs. It works for a brand-new
account as well as an established one.

**New here? Read the [User Guide](docs/USER_GUIDE.md).** It explains every tab in plain language.

---

## Quick start

1. Open the Terminal app (Cmd+Space, type `Terminal`, press Enter).
2. Paste `cd ~/git/osrs_tcg && python3 scripts/server.py` and press Enter. Leave the window open.
3. Open **http://localhost:8765/preview.html** in your browser, pick your account, press **↻ Refresh**.

To stop it, click the Terminal window and press Ctrl+C. "Address already in use" means it is already running.

Running the planner needs only Python 3.9 or newer (type `python3 --version` in Terminal to check) and
RuneLite with the OSRS TCG plugin opened at least once. The update scripts also need `pip3 install -r scripts/requirements.txt`.

---

## What it does

- **Cards**: all 5,172 TCG cards (live catalog snapshot). Drops, sources, recipes, and which quests, bosses and diaries use each card
- **Wishlist**: cards, quests, Slayer tasks and clue steps you're working towards, with pack suggestions
- **Equipment**: gear setups and a DPS calculator, filtered to owned cards
- **Skilling**: training methods per skill from your levels, tools and cards
- **Questing**: what you can complete now, what's close, what blocks the rest
- **Diaries**: every Achievement Diary task with its cards and rewards
- **Bosses**: raids, wave content, minigames, skilling bosses and bosses, with requirements and loot (collection-log uniques marked ◆)
- **Slayer**: masters and tasks you can do, monsters that count, equipment and locations
- **Clues**: per tier, whether you can get the clue and finish the steps
- **Packs**: each pack's card pool, what you own, which packs fill your gaps
- **Rules**: the Bronzeman rules the planner applies
- **Multi-account**: finds every TCG account in your RuneLite folder (local saves and cloud accounts)

## Where your data comes from

- **Cards**: `scripts/decode_collection.py` reads RuneLite's saves (`RLTCG_v2` / `RLTCG_v3`, and
  `~/.runelite/OSRS-TCG/profiles/*/tcg.save`). Cloud accounts are fetched from api.osrs-tcg.net with
  the plugin's stored session. No login needed.
- **Skill levels**: the OSRS hiscores.
- **Completed quests**: RuneLite quest-list screenshots (`scripts/decode_completed_quests.py`).
  Quests you've only started can be marked by hand on the quest's page.

All of this reloads when the page opens and when you press **↻ Refresh**. Nothing refreshes on its own.

---

## Repo map

```
osrs_tcg/
├── scripts/
│   ├── preview.html            # The planner itself (one file, no build step)
│   ├── server.py               # Local server: serves the page, decodes collections, hiscores, image cache
│   ├── decode_collection.py    # Reads RuneLite / cloud card collections
│   ├── decode_completed_quests.py
│   ├── generate_*.py           # Update scripts: rebuild scripts/output/ from the catalog + OSRS Wiki
│   ├── *_curated.json          # Hand-checked data the wiki doesn't give (skilling, slayer, bosses, clues)
│   ├── item_sources_overrides.json  # Hand fixes, applied by generate_sources.py
│   ├── location_requirements.json   # Entry requirements for gated places (hover tips)
│   ├── wiki_api.py             # Shared, polite wiki access for the update scripts (~1 request/second)
│   ├── dev/cdp_check.mjs       # Headless browser check
│   ├── output/                 # The planner's data (generated, committed, some hand fixes)
│   ├── assets/icons/           # Local skill, quest and clue icons
│   └── cache/                  # Wiki pages and images (large, gitignored)
├── research/                   # Card catalog snapshots (card-catalog-live.json is the current one)
├── docs/                       # Guides and architecture notes
└── plugins/                    # Local clones of the two plugin repos (gitignored)
```

Key files in `scripts/output/` include `item_sources.json`, `monster_drops.json`, `quests.json`,
`bm_quest_cards.json` (hand-curated quest cards), `bosses.json`, `boss_loot.json`,
`collection_log.json`, `diaries.json`, `slayer.json`, `clue_steps.json`, `recipes.json`,
`skilling.json`, `spells.json`, `shop_owners.json` and `method_icons.json`.

Personal files are generated locally and never committed: `scripts/output/my_collection.json`,
`all_collections.json` and `completed_quests.json`.

## Updating the data

Only needed after a card catalog update. The steps and the order of the update scripts are in the
[User Guide](docs/USER_GUIDE.md#advanced-only-after-a-card-catalog-update).

> **Careful:** committed output files carry hand fixes. Back up `scripts/output/`, regenerate
> (into `--out-dir` where a script supports it), and diff before replacing anything. Keep wiki use
> light: the wiki's bot check blocks this machine if it fetches too much.

### How drops and rarity are read

- **Item → card matching** uses the catalog's `tcg.variants` lists, the same mapping Bronzeman uses.
  So *Grimy ranarr weed* counts for the Ranarr weed card and *Prayer potion(4)* for Prayer potion.
- **Rarity labels follow the OSRS Wiki's tiers:** Common ≤1/25, Uncommon <1/100, Rare <1/1,000, Very Rare beyond.
- **Unique**: raid unique-table items (CoX/ToB/ToA), shown with their share of the unique roll (e.g. Twisted bow 2/60).
- **Conditional**: items gated by an extra requirement in the wiki's footnotes (CM time limits, first completions, KC milestones).
- Multi-roll chest rates are combined (Barrows `7 × 1/2,448` ≈ 1/350 per piece).

---

## Documentation

| Doc | For |
|-----|-----|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Using the planner, symbols, troubleshooting, updating data |
| [docs/CODE_BIBLE.md](docs/CODE_BIBLE.md) | How the code works, for changing it |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | Small known bugs, written down but not yet fixed |
| [docs/data-structures.md](docs/data-structures.md) | Card.json schema, save format, catalog snapshot format |
| `PROJECT_LOG.md` | Session-by-session history (local only, gitignored) |
| `docs/osrs-tcg-architecture.md`, `docs/bronzeman-architecture.md`, `docs/opportunities.md` | Plugin architecture notes and contribution ideas (local only, gitignored) |

---

## Known limitations

- **Quest completions come from screenshots.** If RuneLite has no recent quest-list screenshot,
  completions won't sync. Started quests must be marked by hand.
- **`bm_quest_cards.json` is hand-curated.** New quests and reworks need manual updates
  (format in `docs/data-structures.md`).
- **Game data goes stale.** It is built from the OSRS Wiki. There is no automatic refresh, and the
  wiki's bot check now limits how much can be re-fetched.
- **Some icons stay blank** while the wiki blocks uncached images (mostly Magic spell and Construction icons).
- **Card names are the only key.** If the TCG renames a card, references across the data files need updating
  (`research/catalog_migration.json` records past renames).
- **Local only, desktop only.** Collection data lives on your disk, so there is no hosted version.
  The UI hasn't been tested on small screens.

---

## Related projects

| Project | Link |
|---------|------|
| OSRS TCG plugin | [Azderi/osrs-tcg](https://github.com/Azderi/osrs-tcg) |
| Bronzeman TCG plugin | [Felmeme/bronzeman-tcg](https://github.com/Felmeme/bronzeman-tcg) |
| Card catalog API | https://osrs-tcg.xyz/catalog/Card.json |
