# 05 — Wiki Loot Table Data Pipeline

**Status**: Prerequisite for the sourcing panel (02). Core data infrastructure.  
**Repo**: `scripts/` in whichever repo houses the sourcing panel  
**Effort**: Large (2-3 sessions of focused data work)  
**Dependencies**: None — purely a scripting task  

---

## What This Is

A Python data pipeline that fetches OSRS Wiki loot tables for every monster card and every quest, cross-references them against Card.json, and generates three bundled JSON files:

1. `monster_drops.json` — monster → its TCG card drops with rarity labels
2. `item_sources.json` — item card → which monsters drop it + which quests reward it
3. `quest_chains.json` — quest → prerequisite chain + cards involved

These files are generated at dev-time and bundled into the plugin JAR. **No wiki requests happen at runtime.**

---

## Wiki Access Rules (Non-Negotiable)

Per Bronzeman CLAUDE.md (the wiki team told Felmeme directly):

- Use **plain page URLs only**: `https://oldschool.runescape.wiki/w/Abyssal_Sire`
- **Never** `api.php?action=parse` — forces uncached server-side parse
- Pace at **~1 req/sec** to avoid rate limiting
- Set a **descriptive User-Agent**: `osrs-tcg-sources/dev (github.com/Felmeme/bronzeman-tcg)`
- **Cache every raw fetch** in `scripts/cache/wiki_html/` so re-runs are free
- Plugin makes **zero wiki requests at runtime** — data is static in JAR

---

## Pipeline Architecture

```
Card.json (6,376 cards)
    ↓
Step 1: Build card name sets
    Monster cards: {Abyssal Sire, Zulrah, Goblin, ...}  (1,227 names)
    Item cards:    {Abyssal whip, Dragon bones, ...}    (5,149 names)
    ↓
Step 2: For each monster card → fetch wiki page → parse loot table
    https://oldschool.runescape.wiki/w/Abyssal_Sire
    Extract: {{DropsLine}} template calls from wiki markup
    Filter: only rows where item name ∈ item_card_names
    Map rarity fraction → rarity label
    ↓
Step 3: Build reverse index (item → monster sources)
    For each monster→drops mapping: invert to item→[monsters]
    ↓
Step 4: For each quest → fetch wiki page → parse infobox
    Extract: prerequisites, item rewards, start NPC
    Filter: rewards ∩ card_names, start NPC ∩ monster_card_names
    ↓
Step 5: Write output JSON files
    monster_drops.json
    item_sources.json
    quest_chains.json
```

---

## Step 2: Parsing Wiki Loot Tables

OSRS Wiki uses a `{{DropsLine}}` template in wikitext, but the rendered HTML has a structured drops table with class `item-drops`. Fetching the plain page HTML and parsing with BeautifulSoup is the reliable approach.

### Loot Table HTML Structure
```html
<table class="item-drops wikitable sortable">
  <thead>...</thead>
  <tbody>
    <tr>
      <td class="item-col"><a href="/w/Abyssal_whip">Abyssal whip</a></td>
      <td class="qty-col">1</td>
      <td class="rarity-col"><span class="rare">Rare</span></td>
    </tr>
    ...
  </tbody>
</table>
```

### Rarity Extraction
The wiki shows both a label ("Rare") and an exact fraction ("1/512" in the fraction column or title). Parse both:
- **Label**: from `<span class="rare">`, `<span class="uncommon">`, etc.
- **Fraction**: from `title="1/512"` attribute or a `<td>` with the fraction

When both are available, use the fraction to standardize our own buckets:

| Fraction range | Our label |
|---------------|-----------|
| Always / 100% | Always |
| 1/1 – 1/25 | Common |
| 1/26 – 1/128 | Uncommon |
| 1/129 – 1/512 | Rare |
| 1/513 – 1/5000 | Very Rare |
| 1/5001+ | Extremely Rare |

### Filtering to TCG Cards Only
After parsing a loot table, filter rows to only items whose name is in `item_card_names`. A Goblin's drops include 5 items with TCG cards out of ~20 total drops. We only store the 5.

---

## Step 4: Parsing Quest Pages

Quest pages have a sidebar infobox with `Prerequisites`, `Items required`, `Start point` (NPC name).

```html
<table class="infobox">
  <tr><th>Start point</th><td><a href="/w/King_Narnode">King Narnode</a></td></tr>
  <tr><th>Requirements</th><td>Tree Gnome Village</td></tr>
  <tr><th>Items required</th><td>...</td></tr>
  <tr><th>Rewards</th><td>Zenyte shard...</td></tr>
</table>
```

Parse:
- `prerequisites`: list of quest names that must be completed first
- `rewardCards`: items rewarded that have TCG cards
- `monsterCards`: NPCs killed as part of the quest that have monster cards
- `startNpc`: quest-giver NPC (for quest NPC unlock info)

---

## Edge Cases

### Multi-phase bosses
Zulrah, Vorkath, Cerberus fight through phases — each phase is a separate NPC ID but one wiki page. The loot table is on the main boss page. Simple case: fetch the boss card's wiki page, parse its drops table.

### Bosses with no drop table on main page
Some bosses (Raids, CoX, ToA) have drops on a separate "/Loot" subpage. E.g.:
- `https://oldschool.runescape.wiki/w/Chambers_of_Xeric/Loot`
- Handle by trying `{name}/Loot` as fallback

### Redirect handling
Some card names differ from wiki page names:
- Card: `"Monkey (monster)"` → wiki page: `"Monkey"` (strip the `(monster)` suffix)
- Card: `"Guard (Barbarian Village)"` → try `"Guard"` or `"Guard/Barbarian_Village"`
- Strategy: strip bracket suffix, try exact name, try `_` for spaces

### Items sold in shops (not dropped)
Some item cards are bought from shops (e.g. "Hammer", "Tinderbox"). Their wiki page won't have a loot table. These would appear in `item_sources.json` with `monsters: []` and a note. That's fine — the sourcing panel would show "Bought from: various shops" (static text, not wiki-sourced).

### Quest-only items
Items like "Monkey talisman" that come from quests, not drops. The quest parsing handles these via `rewardCards`.

---

## Output Schema

### `monster_drops.json`
```json
{
  "Abyssal Sire": {
    "drops": [
      {"card": "Abyssal whip", "rarity": "Common", "fraction": "1/100"},
      {"card": "Abyssal dagger", "rarity": "Uncommon", "fraction": "1/200"},
      {"card": "Abyssal orphan", "rarity": "Very Rare", "fraction": "1/2000"},
      {"card": "Abyssal head", "rarity": "Rare", "fraction": "1/400"}
    ],
    "slayerLevel": 85,
    "quests": []
  },
  "Zulrah": {
    "drops": [
      {"card": "Tanzanite fang", "rarity": "Rare", "fraction": "1/512"},
      {"card": "Magic fang", "rarity": "Rare", "fraction": "1/512"},
      {"card": "Serpentine visage", "rarity": "Rare", "fraction": "1/512"},
      {"card": "Onyx", "rarity": "Uncommon", "fraction": "1/128"}
    ],
    "slayerLevel": null,
    "quests": ["Regicide"]
  }
}
```

### `item_sources.json`
```json
{
  "Abyssal whip": {
    "monsters": [
      {"card": "Abyssal demon", "rarity": "Rare", "fraction": "1/512"},
      {"card": "Grotesque Guardians", "rarity": "Rare", "fraction": "1/1000"}
    ],
    "quests": [],
    "shopBought": false,
    "alwaysAvailable": false
  },
  "Zenyte shard": {
    "monsters": [
      {"card": "Demonic gorilla", "rarity": "Uncommon", "fraction": "1/100"}
    ],
    "quests": ["Monkey Madness II"],
    "shopBought": false,
    "alwaysAvailable": false
  },
  "Hammer": {
    "monsters": [],
    "quests": [],
    "shopBought": true,
    "alwaysAvailable": true
  }
}
```

### `quest_chains.json`
```json
{
  "Monkey Madness II": {
    "prerequisites": ["Monkey Madness I", "Tree Gnome Village"],
    "rewardCards": ["Zenyte shard"],
    "monsterCards": ["Demonic gorilla"],
    "questNpc": "King Narnode Shareen"
  },
  "Dragon Slayer I": {
    "prerequisites": [],
    "rewardCards": ["Rune platebody"],
    "monsterCards": ["Elvarg"],
    "questNpc": "Guildmaster"
  }
}
```

---

## Script Structure

```
scripts/
├── generate_sources.py         # Main entry point
├── wiki_fetcher.py             # Fetch + cache wiki pages
├── loot_parser.py              # Parse loot table HTML
├── quest_parser.py             # Parse quest infobox HTML
├── rarity_mapper.py            # Fraction → rarity label
├── compare_catalogs.py         # (see opportunity 04)
└── cache/
    └── wiki_html/              # Cached page fetches (gitignored)
```

`generate_sources.py`:
```bash
python scripts/generate_sources.py \
    --card-json research/card-catalog.json \
    --out-dir src/main/resources/sources/
```

Generates the three JSON files into the plugin's resources directory.

---

## Coverage Expectations

| Card type | Expected wiki coverage | Notes |
|-----------|----------------------|-------|
| Boss monsters (100-350 combat level) | ~95% | Well-documented on wiki |
| Slayer monsters | ~90% | Most have detailed loot pages |
| Common monsters (Goblins, etc.) | ~80% | Some drop tables incomplete |
| Quest boss monsters | ~85% | May be on quest page not NPC page |
| Item cards — drop sources | ~75% | Depends on monster coverage |
| Item cards — quest rewards | ~90% | Quest infoboxes are thorough |
| Shop-bought items | 0% (static) | Mark as shopBought=true manually or via category heuristic |

Gaps show as empty `monsters: []` — sourcing panel shows "Sources unknown" gracefully.

---

## Effort Breakdown

| Task | Effort |
|------|--------|
| `wiki_fetcher.py` + cache layer | 1 hour |
| `loot_parser.py` (HTML parsing, rarity mapping) | 2-3 hours |
| `quest_parser.py` | 2 hours |
| `generate_sources.py` (orchestration + output) | 1 hour |
| Test run on 50 monster cards, fix edge cases | 2-3 hours |
| Full run (1,227 monsters at 1 req/sec ≈ 20 min) | automated |
| Manual review + fixes for problem cards | 1-2 hours |

Total: 1-2 sessions of focused work.
