# 03 — ID-Based Entity Lookup

**Status**: Requires Az's buy-in to add IDs to Card.json. Data generation is Lottie's contribution.  
**Repo**: `Azderi/osrs-tcg` (Card.json change) + `Felmeme/bronzeman-tcg` (consumer update)  
**Effort**: Medium (data work is the main effort)  
**Dependencies**: Az agreement + PR to OSRS TCG to add ID fields  

---

## Problem

Every entity lookup in Bronzeman (NPC lock check, item lock check) currently goes through name matching:

```java
entityToCardsLowerCase.get(entityName.trim().toLowerCase(Locale.ROOT))
```

This has three failure modes:

1. **Disambiguation suffixes**: 67 monster cards have wiki-style bracket suffixes (`"Monkey (monster)"`) that the in-game NPC name (`"Monkey"`) never contains. Handled by the `entityToCards` map, but requires a custom disambiguation script to maintain.

2. **Name drift**: If Jagex renames an NPC in-game, or Az changes a card name, the match silently breaks. No runtime error, just the restriction silently lifting.

3. **Degraded equipment / item variants**: In-game, "Abyssal whip" (item ID 4151) and its ornament kit variants have different item IDs but map to one card. Item-based checks use the item name from `ItemManager.getItemComposition(id).getName()`, which usually works, but degraded/repaired variants of the same item can have different names.

---

## Proposed Change

Az adds two optional fields to Card.json:

```json
{
  "name": "Abyssal demon",
  "category": ["Monster"],
  "npcIds": [415, 7091, 7092],
  "level": 124,
  ...
}
```

```json
{
  "name": "Abyssal whip",
  "category": ["Resource", "Weapon"],
  "itemIds": [4151],
  "equipmentSlot": "weapon",
  ...
}
```

Fields are optional — cards without IDs fall back to name matching (100% backwards-compatible).

---

## Why This Is Achievable

The OSRS Wiki already has NPC IDs and item IDs in infoboxes:
- NPC page: `https://oldschool.runescape.wiki/w/Abyssal_demon` → infobox has `id = 415, 7091, 7092`
- Item page: `https://oldschool.runescape.wiki/w/Abyssal_whip` → infobox has `id = 4151`

Lottie's data script (`scripts/enrich_card_ids.py`) would:
1. For each card in Card.json, fetch its wiki page
2. Parse the infobox `id` field
3. Add `npcIds: [...]` or `itemIds: [...]` to the card entry
4. Output an enriched `Card.json`

Az merges the enriched card data. One-time effort (IDs rarely change).

---

## Impact on Bronzeman

Once IDs are in Card.json, the generation script (`generate_tracked_monsters.py`) is updated to:
- Include NPC IDs in the monster snapshot: `{entityToCards: {...}, npcIdToCards: {415: ["Abyssal demon"], ...}}`
- Include item IDs in the item snapshot: `{entityToCards: {...}, itemIdToCards: {4151: ["Abyssal whip"], ...}}`

`CardNameCatalog` gets new methods:
```java
public Set<String> getCardVariantsById(int npcId) { ... }
public boolean isTrackedById(int npcId) { ... }
```

`BronzemanTcgPlugin` checks ID first, falls back to name:
```java
NPC npc = event.getMenuEntry().getNpc();
Set<String> cards = catalog.getCardVariantsById(npc.getId());
if (cards.isEmpty()) {
    // fallback: name-based
    cards = catalog.getCardVariantsLowerCase(Text.removeTags(npc.getName()));
}
```

This makes NPC locking **bulletproof**: no disambiguation suffix juggling, no silent name drift.

---

## Data Generation Script Outline

```python
# scripts/enrich_card_ids.py
import json, requests, time, re, pathlib

CARD_JSON = pathlib.Path("../../research/card-catalog.json")
CACHE_DIR = pathlib.Path("cache/wiki_pages")
USER_AGENT = "osrs-tcg-id-enricher/dev (github.com/Azderi/osrs-tcg)"
RATE_LIMIT = 1.0  # seconds between uncached requests

def fetch_wiki_page(name: str) -> str:
    """Fetch plain wiki page HTML, cached to CACHE_DIR."""
    cache_path = CACHE_DIR / (name.replace("/", "_") + ".html")
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    url = f"https://oldschool.runescape.wiki/w/{name.replace(' ', '_')}"
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    time.sleep(RATE_LIMIT)
    cache_path.write_text(r.text, encoding="utf-8")
    return r.text

def parse_infobox_ids(html: str) -> list[int]:
    """Extract | id = 415, 7091 from wiki infobox HTML."""
    # Parse the <td> with class "infobox-data" after "id" label
    # Returns list of ints
    ...

cards = json.loads(CARD_JSON.read_text())
for card in cards:
    is_monster = "Monster" in card.get("category", [])
    page_name = card["name"]  # may need disambiguation e.g. "Goblin (monster)"
    html = fetch_wiki_page(page_name)
    ids = parse_infobox_ids(html)
    if ids:
        if is_monster:
            card["npcIds"] = ids
        else:
            card["itemIds"] = ids
        
json.dump(cards, open("Card_enriched.json", "w"), indent=2)
```

---

## Effort Breakdown

| Task | Effort |
|------|--------|
| `scripts/enrich_card_ids.py` (write + test) | 1 session |
| Run against full Card.json (1,227 monsters + 5,149 items) | ~3 hours runtime (rate limited) |
| Manual fixes for edge cases (disambiguation, wiki redirects) | 0.5 sessions |
| PR to OSRS TCG: add npcIds/itemIds to Card.json + CardDefinition | Small |
| PR to Bronzeman: update CardNameCatalog + plugin to prefer IDs | Small |

---

## Open Questions

1. NPC ID disambiguation: RuneLite's `NPC.getId()` returns the specific NPC ID (e.g. 415 for a normal Abyssal demon, 7091 for the Stronghold variant). Card.json would need ALL variant IDs. Are all variant IDs reliably in the wiki infobox?
2. For multi-phase bosses (Zulrah, Vorkath, Cerberus): they have multiple NPC IDs per fight phase. All IDs map to one card — need to include all.
3. Az's Card.json is not the same as what's in the plugin JAR at runtime (the JAR is bundled at build time). The enrichment must happen to the source Card.json in the repo, not the live website version.
4. Some wiki pages redirect (e.g. "Goblin" → "Goblin/Drops") — need redirect handling in the scraper.

---

## Risk

Low. The change is fully additive to Card.json (new optional fields), fully backwards-compatible in Bronzeman (falls back to name), and the data generation is the main effort. The only risk is Az declining to merge the enriched Card.json, but given he said "I'm happy to add anything that's necessary" this seems unlikely.
