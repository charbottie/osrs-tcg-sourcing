# OSRS TCG — Bronzeman Planner

A local web app for **OSRS TCG** players running the **Bronzeman TCG** RuneLite plugin. It reads your card collection from RuneLite and shows you exactly what you can and can't do — quest requirements, skill training methods, monster drops, equipment, and more — all filtered to your owned cards.

---

## What it does

- **Collection browser** — view all 6,000+ TCG cards; filter by owned, skill, tier
- **Questing tab** — see which quests you can complete with your current cards, what's blocking you, and what each quest unlocks
- **Skilling tab** — find available training methods per skill based on cards you own
- **Monster detail** — drops, Slayer task probabilities, area access requirements (gated zones like Morytania, Kourend, Varlamore)
- **Item detail** — how to obtain it, which quests need it, production requirements
- **Equipment tab** — gear setups and DPS calculator filtered to owned cards
- **Multi-account** — auto-discovers all TCG accounts in your RuneLite profiles

---

## Requirements

- Python 3.9+
- [RuneLite](https://runelite.net/) with the **OSRS TCG** plugin installed
- `pip install -r scripts/requirements.txt`

---

## Quick start

```bash
git clone https://github.com/your-username/osrs_tcg.git
cd osrs_tcg
pip install -r scripts/requirements.txt
python scripts/server.py
```

Then open **http://localhost:8765** in your browser.

On first load the server finds your RuneLite profiles automatically (macOS, Windows, and Linux paths are all supported). Click **↻ Refresh** to decode your collection.

> **No server?** Open `scripts/preview.html` directly in a browser for read-only browsing of the pre-bundled data. Collection sync and hiscores lookup require the server.

---

## Loading your collection

1. Make sure RuneLite is installed and you've opened it with the OSRS TCG plugin at least once (so your collection is saved to disk)
2. Start the server: `python scripts/server.py`
3. Open http://localhost:8765
4. Your accounts appear in the dropdown — select one and click **↻ Refresh**

The server decodes the RuneLite config format (`RLTCG_v2` / `RLTCG_v3`) directly from disk — no login required.

---

## Syncing quest completions

Quest completions are read from RuneLite's quest-list screenshots. To sync them:

```bash
python scripts/decode_completed_quests.py --player YOUR_RSN
```

Or click **↻ Sync** in the Questing tab while the server is running.

---

## Data files

All game data lives in `scripts/output/` and is pre-generated from the OSRS Wiki. You don't need to regenerate it unless the game has updated significantly.

| File | Contents |
|------|----------|
| `monster_drops.json` | Drop tables for all monster cards |
| `item_sources.json` | How to obtain every item card |
| `bm_quest_cards.json` | Quest card requirements for Bronzeman mode (hand-curated) |
| `quests.json` | Quest list with skill requirements and prerequisites |
| `quest_chains.json` | Quest prerequisite graph |
| `equipment_data.json` | Gear stats |
| `food_data.json` | Food heal values |
| `card_categories.json` | Card → skill/category mapping |
| `card_details.json` | Card metadata (tier, description) |

### Regenerating data from the wiki

```bash
# Re-scrape monster drops and item sources (hits the OSRS Wiki — takes a while)
python scripts/generate_sources.py

# Rebuild quest data
python scripts/generate_quests.py

# Rebuild equipment / food
python scripts/generate_equipment.py
python scripts/generate_food.py
```

Scraped HTML is cached in `scripts/cache/` (~800 MB, gitignored) so repeat runs are fast.

---

## File structure

```
osrs_tcg/
├── scripts/
│   ├── preview.html              # The web app (single-file, no build step)
│   ├── server.py                 # Local API server (collection decode, hiscores)
│   ├── decode_collection.py      # Decodes RuneLite RLTCG config blobs
│   ├── decode_completed_quests.py
│   ├── generate_sources.py       # Scrapes wiki → monster_drops + item_sources
│   ├── generate_quests.py        # Scrapes wiki → quests + quest_chains
│   ├── generate_equipment.py
│   ├── generate_food.py
│   ├── quest_parser.py           # HTML parser for quest detail pages
│   ├── loot_parser.py            # HTML parser for monster loot tables
│   ├── card_groups.py            # Canonical card group definitions
│   ├── requirements.txt
│   └── output/                   # Pre-generated data (committed, except personal files)
├── discord/
│   ├── announcements.md          # OSRS TCG plugin announcements
│   └── faq.md                    # Community FAQ
└── docs/                         # Architecture notes and data structure docs
```

---

## Personal data (gitignored)

These files are generated locally and never committed:

| File | Contents |
|------|----------|
| `scripts/output/my_collection.json` | Decoded collection cache |
| `scripts/output/all_collections.json` | All detected RuneLite accounts |
| `scripts/output/completed_quests.json` | Synced quest completions |

---

## Related projects

| Project | Link |
|---------|------|
| OSRS TCG plugin | [Azderi/osrs-tcg](https://github.com/Azderi/osrs-tcg) |
| Bronzeman TCG plugin | [Felmeme/bronzeman-tcg](https://github.com/Felmeme/bronzeman-tcg) |
| Card catalog API | https://osrs-tcg.xyz/catalog/Card.json |
