#!/usr/bin/env python3
"""
Enriches Card.json with itemIds (for Resource cards) and npcIds (for Monster cards).

Data sources:
  Items: osrsbox-db + 0xNeffarion/osrsreboxed-db (combined, ~87% coverage)
  Monsters: osrsbox/osrsbox-db monsters-complete.json (~70% coverage)

Unmatched cards get an empty array. Coverage is limited by the data sources
being archived (2022); newer OSRS content will have [] until sources are updated.

Usage:
  python3 scripts/enrich_card_ids.py [--dry-run]
"""
import json
import sys
import urllib.request
import time
import os
from collections import defaultdict

DRY_RUN = '--dry-run' in sys.argv

CARD_JSON = os.path.join(os.path.dirname(__file__), '..', 'plugins/osrs-tcg/src/main/resources/Card.json')
RESEARCH_JSON = os.path.join(os.path.dirname(__file__), '..', 'research/card-catalog.json')

SOURCES = {
    'items': [
        'https://raw.githubusercontent.com/0xNeffarion/osrsreboxed-db/master/docs/items-summary.json',
        'https://raw.githubusercontent.com/osrsbox/osrsbox-db/master/docs/items-summary.json',
    ],
    'monsters': [
        'https://raw.githubusercontent.com/osrsbox/osrsbox-db/master/docs/monsters-complete.json',
        'https://raw.githubusercontent.com/0xNeffarion/osrsreboxed-db/master/docs/monsters-complete.json',
    ],
}

UA = 'OSRS-TCG-enrichment/1.0 (github.com/Azderi/osrs-tcg)'


def fetch_json(url):
    print(f'  Fetching {url} ...')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build_name_to_ids(urls):
    name_to_ids = defaultdict(set)
    for url in urls:
        try:
            data = fetch_json(url)
            for entry in data.values():
                name = entry.get('name', '').strip()
                id_val = entry.get('id')
                if name and id_val is not None:
                    name_to_ids[name].add(int(id_val))
            time.sleep(0.3)
        except Exception as e:
            print(f'  WARNING: could not fetch {url}: {e}')
    return {k: sorted(v) for k, v in name_to_ids.items()}


def main():
    print('Building item ID mapping...')
    item_name_to_ids = build_name_to_ids(SOURCES['items'])
    print(f'  {len(item_name_to_ids)} unique item names, '
          f'{sum(len(v) for v in item_name_to_ids.values())} total IDs')

    print('Building NPC ID mapping...')
    npc_name_to_ids = build_name_to_ids(SOURCES['monsters'])
    print(f'  {len(npc_name_to_ids)} unique NPC names, '
          f'{sum(len(v) for v in npc_name_to_ids.values())} total IDs')

    print(f'\nLoading Card.json...')
    with open(CARD_JSON) as f:
        cards = json.load(f)
    print(f'  {len(cards)} cards')

    item_matched = item_unmatched = 0
    npc_matched = npc_unmatched = 0

    for card in cards:
        name = card['name']
        is_monster = 'Monster' in card.get('category', [])

        if is_monster:
            ids = npc_name_to_ids.get(name, [])
            card['npcIds'] = ids
            if ids:
                npc_matched += 1
            else:
                npc_unmatched += 1
        else:
            ids = item_name_to_ids.get(name, [])
            card['itemIds'] = ids
            if ids:
                item_matched += 1
            else:
                item_unmatched += 1

    total_items = item_matched + item_unmatched
    total_npcs = npc_matched + npc_unmatched
    print(f'\nResults:')
    print(f'  Items:    {item_matched}/{total_items} matched '
          f'({item_matched/total_items*100:.1f}%), {item_unmatched} empty')
    print(f'  Monsters: {npc_matched}/{total_npcs} matched '
          f'({npc_matched/total_npcs*100:.1f}%), {npc_unmatched} empty')

    if DRY_RUN:
        print('\n(dry run — no files written)')
        return

    output = json.dumps(cards, indent=2, ensure_ascii=False)
    for path in [CARD_JSON, RESEARCH_JSON]:
        with open(path, 'w') as f:
            f.write(output)
        print(f'  Written: {path}')

    print('\nDone.')


if __name__ == '__main__':
    main()
