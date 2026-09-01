#!/usr/bin/env python3
"""
Generate scripts/output/equipment_data.json from Card.json + OSRSBox data.

Adds to each item:
  combatType  — 'melee' | 'ranged' | 'magic' | 'all'
  reqLvl      — {skill: level, ...} dict (only skills with requirements > 0)
  stats       — {attack_stab, attack_slash, attack_crush, attack_magic,
                  attack_ranged, defence_stab, defence_slash, defence_crush,
                  defence_magic, defence_ranged, melee_strength,
                  ranged_strength, magic_damage, prayer}
                Only non-zero values are included.

Combat type is determined first by the item's attack stats
(highest attack type wins), then by skill requirements,
then by name patterns for items with no useful data.

Usage:
  python3 scripts/generate_equipment.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

CARD_JSON = os.path.join(os.path.dirname(__file__), '..', 'research', 'card-catalog-v1.json')
OUT_JSON  = os.path.join(os.path.dirname(__file__), 'output', 'equipment_data.json')

UA = 'OSRS-TCG-enrichment/1.0 (github.com/Azderi/osrs-tcg)'

ITEMS_COMPLETE_URLS = [
    'https://raw.githubusercontent.com/0xNeffarion/osrsreboxed-db/master/docs/items-complete.json',
    'https://raw.githubusercontent.com/osrsbox/osrsbox-db/master/docs/items-complete.json',
]

STAT_KEYS = [
    'attack_stab', 'attack_slash', 'attack_crush', 'attack_magic', 'attack_ranged',
    'defence_stab', 'defence_slash', 'defence_crush', 'defence_magic', 'defence_ranged',
    'melee_strength', 'ranged_strength', 'magic_damage', 'prayer',
]


def fetch_json(url: str) -> dict:
    print(f'  Fetching {url[:80]} ...')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


# Known TCG card name → OSRSBox item name mismatches
NAME_ALIASES: dict[str, str] = {
    'Runite crossbow': 'Rune crossbow',
    'Amulet of Glory': 'Amulet of glory',
}

def build_id_lookup(items_complete: dict) -> tuple[dict[int, dict], dict[str, dict]]:
    """Build (itemId → data, name_lower → data) mappings."""
    id_lookup:   dict[int, dict] = {}
    name_lookup: dict[str, dict] = {}
    for entry in items_complete.values():
        item_id = entry.get('id')
        if item_id is None:
            continue
        equip = entry.get('equipment')
        if not equip:
            continue
        reqs = equip.get('requirements') or {}
        clean_reqs = {k.lower(): v for k, v in reqs.items() if v and int(v) > 0}
        stats = {k: equip.get(k, 0) for k in STAT_KEYS}
        clean_stats = {k: v for k, v in stats.items() if v and v != 0}
        weapon_data  = entry.get('weapon') or {}
        attack_speed = weapon_data.get('attack_speed')
        weapon_type  = weapon_data.get('weapon_type')
        data = {
            'reqs':         clean_reqs,
            'stats':        clean_stats,
            'attack_speed': attack_speed,
            'weapon_type':  weapon_type,
        }
        id_lookup[int(item_id)] = data
        name_key = (entry.get('name') or '').lower()
        if name_key:
            name_lookup[name_key] = data
    return id_lookup, name_lookup


# Name-pattern fallbacks when OSRSBox has no data
RANGED_WEAPON_KW = [
    'bow', 'crossbow', 'dart', 'knife', 'thrownaxe', 'javelin',
    'blowpipe', 'ballista', 'chinchompa',
]
MAGIC_WEAPON_KW = [
    'staff', 'wand', 'trident', 'nightmare staff', 'kodai',
    'harmonised nightmare', 'volatile nightmare', 'eldritch nightmare',
    "tumeken's shadow", 'sanguinesti', 'crystal staff', 'ancient staff',
]
RANGED_ARMOUR_KW = [
    'leather', 'dragonhide', "d'hide", "karil's", 'armadyl',
    'crystal body', 'crystal helm', 'crystal legs', 'masori', 'void ranger',
]
MAGIC_ARMOUR_KW = [
    "ahrim's", 'mystic', 'ancestral', 'void mage', 'monk robe',
    'vestment', 'splitbark', 'lunar', 'infinity', 'occult',
]


# OSRSBox weapon_type values that map to each combat style
# (All use underscores, not hyphens — verified against items-complete.json)
WEAPON_TYPE_ALL    = {'salamander'}                                     # multi-style
WEAPON_TYPE_MAGIC  = {'staff', 'powered_staff', 'bladed_staff'}         # staves, tridents, etc.
WEAPON_TYPE_RANGED = {'bow', 'crossbow', 'chinchompas', 'thrown', 'gun'} # bows, crossbows, blowpipe

def classify_combat_type(name: str, slot: str, reqs: dict[str, int],
                         stats: dict[str, int], weapon_type: str | None = None) -> str:
    """Determine combat type using weapon_type → reqs → stats → name patterns."""
    # 1. weapon_type is authoritative for weapons (avoids battlestaff misclassification)
    if weapon_type and slot in ('weapon', '2h'):
        if weapon_type in WEAPON_TYPE_ALL:
            return 'all'
        if weapon_type in WEAPON_TYPE_MAGIC:
            return 'magic'
        if weapon_type in WEAPON_TYPE_RANGED:
            return 'ranged'
        return 'melee'

    # 2. Requirements: the required skill tells us the combat style directly.
    #    Prioritise the highest-level requirement when multiple exist.
    if reqs:
        if 'ranged' in reqs:
            return 'ranged'
        # Magic beats attack (e.g. Toxic staff requires both magic 75 + attack 75)
        if 'magic' in reqs:
            return 'magic'
        if 'attack' in reqs or 'strength' in reqs:
            return 'melee'

    # 3. Stats: secondary signal (skip melee_strength to avoid battlestaff trap)
    melee_atk  = max(stats.get('attack_stab', 0), stats.get('attack_slash', 0),
                     stats.get('attack_crush', 0))
    ranged_atk = max(stats.get('attack_ranged', 0), stats.get('ranged_strength', 0))
    magic_atk  = stats.get('attack_magic', 0)
    magic_dmg  = stats.get('magic_damage', 0)

    if melee_atk or ranged_atk or magic_atk or magic_dmg:
        best = max(melee_atk, ranged_atk, magic_atk + magic_dmg)
        if best > 0:
            if ranged_atk == best:
                return 'ranged'
            if magic_atk + magic_dmg == best:
                return 'magic'
            if melee_atk == best:
                return 'melee'

    # 4. Name patterns — weapons
    name_l = name.lower()
    if slot in ('weapon', '2h'):
        for kw in MAGIC_WEAPON_KW:
            if kw in name_l:
                return 'magic'
        for kw in RANGED_WEAPON_KW:
            if kw in name_l:
                return 'ranged'
        return 'melee'

    # 5. Name patterns — armour
    for kw in RANGED_ARMOUR_KW:
        if kw in name_l:
            return 'ranged'
    for kw in MAGIC_ARMOUR_KW:
        if kw in name_l:
            return 'magic'

    return 'all'


def merge_best(id_lookup: dict[int, dict], item_ids: list[int]) -> tuple[dict, dict, int | None, str | None]:
    """Merge reqs, stats, attack_speed, weapon_type from all item IDs."""
    best_reqs:   dict[str, int] = {}
    best_stats:  dict[str, int] = {}
    best_speed:  int | None     = None
    best_wtype:  str | None     = None
    best_stat_sum = -1

    for iid in item_ids:
        data = id_lookup.get(iid)
        if not data:
            continue
        reqs  = data['reqs']
        stats = data['stats']
        speed = data.get('attack_speed')
        wtype = data.get('weapon_type')
        stat_sum = sum(abs(v) for v in stats.values())
        if stat_sum > best_stat_sum:
            best_stat_sum = stat_sum
            best_stats = stats
            best_reqs  = reqs
        if best_speed is None and speed is not None:
            best_speed = speed
        if best_wtype is None and wtype is not None:
            best_wtype = wtype

    return best_reqs, best_stats, best_speed, best_wtype


def _load_equip_cards(path: str) -> list[dict]:
    """Load equipment cards, normalising v1.0 {items, npcs} format if needed."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    # v1.0 format: {items: [...], npcs: [...]}
    if isinstance(data, dict) and 'items' in data:
        result = []
        for entry in data['items']:
            tcg_tags = entry.get('tcg', {}).get('tags', {})
            slot = tcg_tags.get('slot')
            if not slot:
                continue
            item_ids = ([entry['id']] if 'id' in entry else [])
            item_ids += [v['id'] for v in entry.get('tcg', {}).get('variants', []) if 'id' in v]
            result.append({
                'name':         entry['name'],
                'equipmentSlot': slot,
                'itemIds':       item_ids,
                'value':         0,
            })
        return result
    # Beta flat format
    return [c for c in data if 'equipmentSlot' in c]


def main() -> int:
    # Load Card.json
    print('Loading Card.json ...')
    equip_cards = _load_equip_cards(CARD_JSON)
    print(f'  {len(equip_cards)} equipment cards')

    # Fetch OSRSBox items-complete
    id_lookup:   dict[int, dict] = {}
    name_lookup: dict[str, dict] = {}
    for url in ITEMS_COMPLETE_URLS:
        try:
            items_complete = fetch_json(url)
            print(f'  {len(items_complete)} items loaded from OSRSBox')
            id_lookup, name_lookup = build_id_lookup(items_complete)
            print(f'  {len(id_lookup)} items with equipment data')
            break
        except Exception as e:
            print(f'  WARNING: failed {url[:70]}: {e}')
            time.sleep(1)

    if not id_lookup:
        print('  WARNING: no OSRSBox data — combat types and stats from name patterns only')

    # Build slot → items list
    by_slot: dict[str, list[dict]] = defaultdict(list)

    for card in equip_cards:
        slot     = card['equipmentSlot']
        name     = card['name']
        item_ids: list[int] = card.get('itemIds', [])
        value: int          = card.get('value', 0)
        is2h = slot == '2h'
        out_slot = 'weapon' if is2h else slot

        reqs, stats, attack_speed, weapon_type = merge_best(id_lookup, item_ids)

        # Fallback: if no itemIds matched, try by name (handles aliases like Runite→Rune)
        if not reqs and not stats:
            alias = NAME_ALIASES.get(name, name)
            nb = name_lookup.get(alias.lower()) or name_lookup.get(name.lower())
            if nb:
                reqs        = nb['reqs']
                stats       = nb['stats']
                attack_speed = nb.get('attack_speed') if attack_speed is None else attack_speed
                weapon_type  = nb.get('weapon_type')  if weapon_type  is None else weapon_type

        combat_type = classify_combat_type(name, slot, reqs, stats, weapon_type)

        entry: dict = {
            'name':       name,
            'value':      value,
            'is2h':       is2h,
            'itemIds':    item_ids,
            'combatType': combat_type,
        }
        if reqs:
            entry['reqLvl'] = reqs
        if stats:
            entry['stats'] = stats
        if attack_speed is not None and out_slot == 'weapon':
            entry['attackSpeed'] = attack_speed

        by_slot[out_slot].append(entry)

    # Sort each slot by value descending (tie-break: name)
    for slot_items in by_slot.values():
        slot_items.sort(key=lambda x: (-x['value'], x['name']))

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(dict(by_slot), f, ensure_ascii=False)

    total = sum(len(v) for v in by_slot.values())
    has_stats = sum(1 for items in by_slot.values() for i in items if i.get('stats'))
    has_reqs  = sum(1 for items in by_slot.values() for i in items if i.get('reqLvl'))
    print(f'\nWrote {OUT_JSON}')
    for slot, items in sorted(by_slot.items()):
        type_counts = defaultdict(int)
        for i in items:
            type_counts[i['combatType']] += 1
        tc = ' '.join(f'{k}:{v}' for k, v in sorted(type_counts.items()))
        print(f'  {slot:8s}: {len(items):4d} items  [{tc}]')
    print(f'  {"total":8s}: {total:4d} items  ({has_reqs} with level reqs, {has_stats} with stats)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
