#!/usr/bin/env python3
"""
Generate scripts/output/food_data.json — map of card name → HP healed.

Fetches the Food/All_food page from the OSRS wiki and parses heal amounts.
Only cards that exist in Card.json are included.

Usage:
  python3 scripts/generate_food.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

CARD_JSON = os.path.join(os.path.dirname(__file__), '..', 'plugins/osrs-tcg/src/main/resources/Card.json')
OUT_JSON  = os.path.join(os.path.dirname(__file__), 'output', 'food_data.json')

UA = 'OSRS-TCG-enrichment/1.0 (github.com/Azderi/osrs-tcg)'

WIKI_API = ('https://oldschool.runescape.wiki/api.php'
            '?action=parse&page=Food/All_food&prop=wikitext&format=json')


def fetch_wiki_food() -> dict[str, int]:
    """Parse Food/All_food wikitext and return {name: total_hp}."""
    print('Fetching OSRS wiki Food/All_food ...')
    req = urllib.request.Request(WIKI_API, headers={'User-Agent': UA})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    wikitext = data['parse']['wikitext']['*']

    food: dict[str, int] = {}
    for row in wikitext.split('|-'):
        m_name = re.search(r'\{\{plinkt\|([^}|]+)', row)
        if not m_name:
            continue
        name = m_name.group(1).strip()

        lines = [l.strip() for l in row.split('\n')
                 if l.strip().startswith('|') and not l.strip().startswith('|-')]
        heal: int | None = None
        for i, line in enumerate(lines):
            if 'plinkt' not in line:
                continue
            for j in range(i + 1, min(i + 3, len(lines))):
                hl = lines[j]
                # data-sort-value is set for multi-bite rows (total HP)
                m = re.search(r'data-sort-value="(-?\d+)"', hl)
                if m:
                    heal = int(m.group(1)); break
                # Simple integer
                m = re.match(r'^\|?\s*(\d+)\s*$', hl)
                if m:
                    heal = int(m.group(1)); break
                # N × M (total = N*M)
                m = re.search(r'(\d+)\s*[x×]\s*(\d+)', hl)
                if m:
                    heal = int(m.group(1)) * int(m.group(2)); break
                # "Random" or "0" → skip
                if re.match(r'^\|?\s*(Random|0)\s*$', hl, re.I):
                    heal = 0; break
            break

        if name and heal and heal > 0:
            food[name] = heal

    print(f'  Parsed {len(food)} food items from wiki')
    return food


def main() -> int:
    wiki_food = fetch_wiki_food()

    print('Loading Card.json ...')
    with open(CARD_JSON, encoding='utf-8') as f:
        cards: list[dict] = json.load(f)
    card_names = {c['name'] for c in cards}
    print(f'  {len(card_names)} cards')

    # Only keep entries that match a card name
    matched = {name: hp for name, hp in wiki_food.items() if name in card_names}
    unmatched = len(wiki_food) - len(matched)
    print(f'  Matched {len(matched)} food cards '
          f'(skipped {unmatched} wiki-only entries)')

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(matched, f, ensure_ascii=False, sort_keys=True)

    print(f'\nWrote {OUT_JSON}')
    print('Top 10 by heal amount:')
    for name, hp in sorted(matched.items(), key=lambda x: -x[1])[:10]:
        print(f'  {name}: {hp}hp')
    return 0


if __name__ == '__main__':
    sys.exit(main())
