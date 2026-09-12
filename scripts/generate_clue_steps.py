#!/usr/bin/env python3
"""Scrape clue step data from the OSRS Wiki.

Produces scripts/output/clue_steps.json with sections:
  emote    — emote clues per tier (items + combat NPC for Hard/Elite/Master)
  sherlock — Sherlock tasks per tier (Elite / Master, items required)
  falo     — Falo the Bard steps (lyric → valid items)
  cryptic  — cryptic "talk to NPC" steps per tier
  anagram  — anagram clues per tier (anagram → NPC to talk to)
  cipher   — cipher clues per tier (cipher → NPC to talk to)
  digInfo  — map/coordinate tiers with Spade requirement + combat NPC info

Plus two reverse indexes:
  itemIndex — item name → [step refs]
  npcIndex  — NPC card name → [step refs]

Usage:
  python scripts/generate_clue_steps.py
  python scripts/generate_clue_steps.py --force-refresh   # re-fetch cached pages
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bs4 import BeautifulSoup, Tag
import wiki_fetcher

_OUT = Path(__file__).parent / "output" / "clue_steps.json"

EMOTE_TIERS    = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]
SHERLOCK_TIERS = ["Elite", "Master"]
CRYPTIC_TIERS  = ["Beginner", "Easy", "Medium", "Hard", "Elite", "Master"]
ANAGRAM_TIERS  = ["Beginner", "Medium", "Hard", "Elite", "Master"]
CIPHER_TIERS   = ["Easy", "Medium", "Hard"]   # Easy has no challenge answer; Medium/Hard do

# Emote clue tiers where a Double Agent must be defeated before collecting reward
DOUBLE_AGENT_TIERS = {"Hard", "Elite", "Master"}

# Charlie the Tramp asks for one of these items in beginner clue scrolls.
# Source: https://oldschool.runescape.wiki/w/Charlie_the_Tramp
CHARLIE_ITEMS = ["Iron ore", "Iron dagger", "Raw herring", "Raw trout"]

# Tiers that contain map clues (dig at X) — Spade required.
# Source: https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Maps
MAP_CLUE_TIERS = ["Beginner", "Easy", "Medium", "Hard", "Elite"]

# Tiers that contain coordinate clues — Spade required.
# Hard tier also spawns a combat NPC at the dig spot (Saradomin wizard outside Wilderness,
# Zamorak wizard inside Wilderness).
# Source: https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Coordinates
COORDINATE_CLUE_TIERS: dict[str, dict] = {
    "Medium": {},
    "Hard":   {"combatNpc": "Saradomin wizard", "wildernessNpc": "Zamorak wizard"},
    "Elite":  {},
    "Master": {},
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cell_text(td: Tag) -> str:
    """Return normalised plain text for a cell, stripping footnote refs."""
    for tag in td.find_all(["sup", "ref"]):
        tag.decompose()
    return " ".join(td.get_text(" ").split())


def _links_in_cell(td: Tag) -> list[str]:
    """Return canonical page names from all wiki links in a <td>.

    Uses the `title` attribute of <a> tags.
    Skips red links, File/Category/Template namespaced links.
    """
    items: list[str] = []
    for a in td.find_all("a", href=True):
        href: str = a["href"]
        if not href.startswith("/w/"):
            continue
        title = a.get("title", "").strip()
        if not title:
            continue
        if title.endswith("(page does not exist)"):
            title = a.get_text().strip()
        if ":" in title:
            continue  # File:, Category:, Template:, etc.
        if title and title not in items:
            items.append(title)
    return items


def _first_link_in_cell(td: Tag) -> str | None:
    links = _links_in_cell(td)
    return links[0] if links else None


def _split_by_tier_headers(soup: BeautifulSoup, tier_names: list[str],
                             header_tags: tuple = ("h2", "h3")
                             ) -> dict[str, list[Tag]]:
    """Walk the page and group <table> elements by the nearest preceding tier header."""
    result: dict[str, list[Tag]] = {t: [] for t in tier_names}
    current: str | None = None

    for el in soup.find_all(True):
        if el.name in header_tags:
            text = el.get_text(" ").strip()
            for tier in tier_names:
                if tier.lower() in text.lower():
                    current = tier
                    break
        elif el.name == "table" and current:
            result[current].append(el)

    return result


# ── Emote clues ───────────────────────────────────────────────────────────────

def _parse_emote_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Treasure_Trails/Guide/Emote_clues/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        if "clue" not in headers or "item" not in " ".join(headers):
            continue

        col_clue  = next((i for i, h in enumerate(headers) if h == "clue"), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), 1)

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_clue, col_items):
                continue

            clue_text = _cell_text(cells[col_clue])
            items     = _links_in_cell(cells[col_items])

            if not clue_text:
                continue

            step: dict = {"tier": tier, "clueText": clue_text, "items": items}
            if tier in DOUBLE_AGENT_TIERS:
                step["combatNpc"] = "Double agent"
            steps.append(step)

    print(f"  Emote {tier}: {len(steps)} steps")
    return steps


def scrape_emote_clues(force_refresh: bool) -> dict[str, list[dict]]:
    return {tier: _parse_emote_tier(tier, force_refresh) for tier in EMOTE_TIERS}


# ── Sherlock ─────────────────────────────────────────────────────────────────

def _parse_sherlock_tier(tier: str, force_refresh: bool) -> list[dict]:
    page = f"Sherlock/{tier}"
    html = wiki_fetcher.fetch(page, force_refresh=force_refresh)
    if not html:
        print(f"  [WARN] Could not fetch {page}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    tasks: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        joined  = " ".join(headers)
        if "task" not in joined and "skill" not in joined:
            continue

        col_task  = next((i for i, h in enumerate(headers) if "task" in h), 0)
        col_items = next((i for i, h in enumerate(headers) if "item" in h), -1)
        if col_items < 0:
            continue

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(col_task, col_items):
                continue

            task_text = _cell_text(cells[col_task])
            items_td  = cells[col_items]
            items     = _links_in_cell(items_td)
            if not items:
                raw = _cell_text(items_td)
                if raw and raw.lower() not in ("none", "-", ""):
                    for part in re.split(r"\s*/\s*", raw):
                        part = part.strip()
                        if part and part.lower() != "none":
                            items.append(part)

            if not task_text:
                continue

            tasks.append({
                "tier":  tier,
                "task":  task_text,
                "items": items,
                "npc":   "Sherlock",
            })

    print(f"  Sherlock {tier}: {len(tasks)} tasks")
    return tasks


def scrape_sherlock(force_refresh: bool) -> dict[str, list[dict]]:
    return {tier: _parse_sherlock_tier(tier, force_refresh) for tier in SHERLOCK_TIERS}


# ── Falo the Bard ─────────────────────────────────────────────────────────────

def scrape_falo(force_refresh: bool) -> list[dict]:
    html = wiki_fetcher.fetch("Falo_the_Bard", force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch Falo_the_Bard")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    steps: list[dict] = []

    for table in soup.find_all("table", class_="wikitable"):
        headers = [th.get_text().strip().lower() for th in table.find_all("th")]
        if "lyric" not in " ".join(headers) and "item" not in " ".join(headers):
            continue

        current_lyric: str  = ""
        lyric_items: list[str] = []
        remaining_rows: int = 0

        def _flush():
            nonlocal current_lyric, lyric_items
            if current_lyric and lyric_items:
                steps.append({"lyric": current_lyric, "items": list(lyric_items),
                               "npc": "Falo the Bard"})
            current_lyric = ""
            lyric_items   = []

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            if remaining_rows > 0:
                remaining_rows -= 1
                for item in _links_in_cell(cells[0]):
                    if item not in lyric_items:
                        lyric_items.append(item)
            else:
                _flush()
                if len(cells) < 2:
                    continue
                rowspan        = int(cells[0].get("rowspan", 1))
                remaining_rows = rowspan - 1
                current_lyric  = _cell_text(cells[0])
                lyric_items    = list(_links_in_cell(cells[1]))

        _flush()
        break

    print(f"  Falo: {len(steps)} steps")
    return steps


# ── Cryptic clues — "talk to NPC" type ───────────────────────────────────────

_TALK_RE = re.compile(r'\b(talk|speak)\b', re.IGNORECASE)


def _parse_cryptic_table(table: Tag, tier: str) -> list[dict]:
    """Extract talk-to-NPC rows from one cryptic clue wikitable."""
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    # Identify which column is "Solution" / "Notes" (contains NPC location)
    # Typical columns: Clue | Solution / Notes | ...
    # The Notes/Solution cell usually has the NPC name as a wikilink.
    col_clue  = next((i for i, h in enumerate(headers) if "clue" in h), 0)
    col_notes = next((i for i, h in enumerate(headers)
                      if any(k in h for k in ("solution", "note", "task", "answer"))), 1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        idx_clue  = min(col_clue,  len(cells) - 1)
        idx_notes = min(col_notes, len(cells) - 1)

        clue_text  = _cell_text(cells[idx_clue])
        notes_text = _cell_text(cells[idx_notes]) if idx_notes < len(cells) else ""

        # Only keep rows that are "talk to NPC" type
        combined = clue_text + " " + notes_text
        if not _TALK_RE.search(combined):
            continue

        # Extract NPC: first wikilink in the notes cell, then clue cell
        npc = _first_link_in_cell(cells[idx_notes])
        if not npc and idx_clue != idx_notes:
            npc = _first_link_in_cell(cells[idx_clue])

        if not clue_text or not npc:
            continue

        steps.append({
            "tier":      tier,
            "clueText":  clue_text,
            "npc":       npc,
            "location":  notes_text,
        })

    return steps


def scrape_cryptic_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape talk-to-NPC type cryptic clue steps from the wiki."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Cryptic_clues",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch cryptic clues page")
        return {t: [] for t in CRYPTIC_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, CRYPTIC_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in CRYPTIC_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_cryptic_table(table, tier))
        # Deduplicate by (clueText, npc)
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for s in steps:
            key = (s["clueText"], s["npc"])
            if key not in seen:
                seen.add(key)
                deduped.append(s)
        result[tier] = deduped
        print(f"  Cryptic {tier} (talk-to): {len(deduped)} steps")

    return result


# ── Anagram clues ─────────────────────────────────────────────────────────────

def _parse_anagram_table(table: Tag, tier: str) -> list[dict]:
    """Extract rows from one anagram clue wikitable.

    Expected columns: Anagram | Solution (NPC) | Location | Challenge Answer
    """
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    col_anagram  = next((i for i, h in enumerate(headers) if "anagram" in h), 0)
    col_solution = next((i for i, h in enumerate(headers)
                         if any(k in h for k in ("solution", "npc", "answer to anagram"))), 1)
    col_location = next((i for i, h in enumerate(headers) if "location" in h), 2)
    col_challenge = next((i for i, h in enumerate(headers)
                          if "challenge" in h or "puzzle" in h), -1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        anagram  = _cell_text(cells[min(col_anagram,  len(cells)-1)])
        npc_cell = cells[min(col_solution, len(cells)-1)]
        npc      = _first_link_in_cell(npc_cell) or _cell_text(npc_cell).strip()
        location = _cell_text(cells[min(col_location, len(cells)-1)]) if len(cells) > 2 else ""
        challenge = None
        if col_challenge >= 0 and col_challenge < len(cells):
            raw = _cell_text(cells[col_challenge]).strip()
            if raw and raw.lower() not in ("-", "", "none", "puzzle box", "light box"):
                challenge = raw

        if anagram and npc:
            steps.append({
                "tier":      tier,
                "anagram":   anagram,
                "npc":       npc,
                "location":  location,
                "challenge": challenge,
            })

    return steps


def scrape_anagram_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape all anagram clue steps from the wiki."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Anagrams",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch anagram clues page")
        return {t: [] for t in ANAGRAM_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, ANAGRAM_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in ANAGRAM_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_anagram_table(table, tier))
        result[tier] = steps
        print(f"  Anagram {tier}: {len(steps)} clues")

    return result


# ── Cipher clues ──────────────────────────────────────────────────────────────

def _parse_cipher_table(table: Tag, tier: str) -> list[dict]:
    """Extract rows from one cipher clue wikitable.

    Columns: Cipher | Solution (NPC or location) | Shift distance | Location | Challenge answer
    Rows where Solution is a plain location string (no wikilink) are dig/search steps — skip.
    """
    steps: list[dict] = []
    headers = [th.get_text(" ").strip().lower() for th in table.find_all("th")]

    col_cipher    = next((i for i, h in enumerate(headers) if "cipher" in h), 0)
    col_solution  = next((i for i, h in enumerate(headers)
                          if "solution" in h or "npc" in h), 1)
    col_challenge = next((i for i, h in enumerate(headers)
                          if "challenge" in h), -1)

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        cipher_text  = _cell_text(cells[min(col_cipher,   len(cells)-1)])
        solution_cell = cells[min(col_solution, len(cells)-1)]
        npc = _first_link_in_cell(solution_cell)
        if not npc:
            continue   # plain-text location (no NPC card) — skip

        challenge = None
        if col_challenge >= 0 and col_challenge < len(cells):
            raw = _cell_text(cells[col_challenge]).strip()
            if raw and raw.lower() not in ("-", "", "none"):
                challenge = raw

        if cipher_text and npc:
            steps.append({
                "tier":      tier,
                "cipher":    cipher_text,
                "npc":       npc,
                "challenge": challenge,
            })

    return steps


def scrape_cipher_clues(force_refresh: bool) -> dict[str, list[dict]]:
    """Scrape cipher clue steps that resolve to an NPC."""
    html = wiki_fetcher.fetch("Treasure_Trails/Guide/Ciphers",
                               force_refresh=force_refresh)
    if not html:
        print("  [WARN] Could not fetch cipher clues page")
        return {t: [] for t in CIPHER_TIERS}

    soup    = BeautifulSoup(html, "html.parser")
    by_tier = _split_by_tier_headers(soup, CIPHER_TIERS)
    result: dict[str, list[dict]] = {}

    for tier in CIPHER_TIERS:
        steps: list[dict] = []
        for table in by_tier[tier]:
            if "wikitable" not in table.get("class", []):
                continue
            steps.extend(_parse_cipher_table(table, tier))
        result[tier] = steps
        print(f"  Cipher {tier}: {len(steps)} clues")

    return result


# ── Reverse indexes ───────────────────────────────────────────────────────────

def _build_indexes(
    emote:    dict[str, list[dict]],
    sherlock: dict[str, list[dict]],
    falo:     list[dict],
    cryptic:  dict[str, list[dict]],
    anagram:  dict[str, list[dict]],
    cipher:   dict[str, list[dict]],
) -> tuple[dict, dict]:
    """Return (itemIndex, npcIndex) for fast O(1) browser lookup."""
    item_index: dict[str, list[dict]] = {}
    npc_index:  dict[str, list[dict]] = {}

    def _add_item(item: str, ref: dict):
        k = item.strip()
        if k:
            item_index.setdefault(k, []).append(ref)

    def _add_npc(npc: str, ref: dict):
        k = npc.strip()
        if k:
            npc_index.setdefault(k, []).append(ref)

    # Emote — items + Double Agent
    for tier, steps in emote.items():
        for step in steps:
            ref = {"type": "emote", "tier": tier,
                   "clueText": step["clueText"], "items": step["items"]}
            for item in step["items"]:
                _add_item(item, ref)
            if step.get("combatNpc"):
                _add_npc(step["combatNpc"],
                         {"type": "emote_combat", "tier": tier,
                          "clueText": step["clueText"]})

    # Sherlock — items + NPC
    for tier, tasks in sherlock.items():
        for task in tasks:
            ref = {"type": "sherlock", "tier": tier,
                   "task": task["task"], "items": task["items"]}
            for item in task["items"]:
                _add_item(item, ref)
            _add_npc("Sherlock", {"type": "sherlock", "tier": tier,
                                  "task": task["task"]})

    # Falo — items + NPC
    for step in falo:
        ref = {"type": "falo", "lyric": step["lyric"], "items": step["items"]}
        for item in step["items"]:
            _add_item(item, ref)
        _add_npc("Falo the Bard", {"type": "falo", "lyric": step["lyric"],
                                    "items": step["items"]})

    # Cryptic — NPC; Charlie the Tramp steps also index his possible items
    for tier, steps in cryptic.items():
        for step in steps:
            if not step.get("npc"):
                continue
            ref = {"type": "cryptic", "tier": tier, "clueText": step["clueText"]}
            if step["npc"] == "Charlie the Tramp" and step.get("charlieItems"):
                ref["charlieItems"] = step["charlieItems"]
            _add_npc(step["npc"], ref)
            # Charlie's item requests go into the item index too
            if step["npc"] == "Charlie the Tramp":
                for item in CHARLIE_ITEMS:
                    _add_item(item, {"type": "charlie", "tier": "Beginner",
                                     "clueText": step["clueText"],
                                     "charlieItems": CHARLIE_ITEMS})

    # Anagram — NPC only
    for tier, steps in anagram.items():
        for step in steps:
            if step.get("npc"):
                _add_npc(step["npc"], {"type": "anagram", "tier": tier,
                                        "anagram": step["anagram"],
                                        "challenge": step.get("challenge")})

    # Cipher — NPC only
    for tier, steps in cipher.items():
        for step in steps:
            if step.get("npc"):
                _add_npc(step["npc"], {"type": "cipher", "tier": tier,
                                        "cipher": step["cipher"],
                                        "challenge": step.get("challenge")})

    # Map clues — Spade required for each tier
    for tier in MAP_CLUE_TIERS:
        _add_item("Spade", {"type": "map", "tier": tier})

    # Coordinate clues — Spade + optional wizard NPCs
    for tier, info in COORDINATE_CLUE_TIERS.items():
        _add_item("Spade", {"type": "coordinate", "tier": tier})
        if info.get("combatNpc"):
            _add_npc(info["combatNpc"],
                     {"type": "coordinate_combat", "tier": tier, "wilderness": False})
        if info.get("wildernessNpc"):
            _add_npc(info["wildernessNpc"],
                     {"type": "coordinate_combat", "tier": tier, "wilderness": True})

    return item_index, npc_index


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force-refresh", action="store_true",
                   help="Re-fetch pages even if cached")
    args = p.parse_args()
    force = args.force_refresh

    print("Scraping emote clue steps…")
    emote = scrape_emote_clues(force)

    print("Scraping Sherlock tasks…")
    sherlock = scrape_sherlock(force)

    print("Scraping Falo the Bard…")
    falo = scrape_falo(force)

    print("Scraping cryptic clue talk-to steps…")
    cryptic = scrape_cryptic_clues(force)

    print("Scraping anagram clues…")
    anagram = scrape_anagram_clues(force)

    print("Scraping cipher clues…")
    cipher = scrape_cipher_clues(force)

    # Inject Charlie the Tramp's item requests into his cryptic clue steps
    for step in cryptic.get("Beginner", []):
        if step.get("npc") == "Charlie the Tramp":
            step["charlieItems"] = CHARLIE_ITEMS

    print("Building indexes…")
    item_index, npc_index = _build_indexes(emote, sherlock, falo, cryptic, anagram, cipher)

    # Structured dig-clue info for the browser (tiers + Spade + combat NPCs)
    dig_info = {
        "map": {tier: {} for tier in MAP_CLUE_TIERS},
        "coordinate": {
            tier: info for tier, info in COORDINATE_CLUE_TIERS.items()
        },
    }

    output = {
        "emote":      emote,
        "sherlock":   sherlock,
        "falo":       falo,
        "cryptic":    cryptic,
        "anagram":    anagram,
        "cipher":     cipher,
        "digInfo":    dig_info,
        "itemIndex":  item_index,
        "npcIndex":   npc_index,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

    total_emote    = sum(len(v) for v in emote.values())
    total_sherlock = sum(len(v) for v in sherlock.values())
    total_cryptic  = sum(len(v) for v in cryptic.values())
    total_anagram  = sum(len(v) for v in anagram.values())
    total_cipher   = sum(len(v) for v in cipher.values())
    print(f"\nWrote {_OUT}")
    print(f"  Emote steps:         {total_emote}")
    print(f"  Sherlock tasks:      {total_sherlock}")
    print(f"  Falo steps:          {len(falo)}")
    print(f"  Cryptic talk-to:     {total_cryptic}")
    print(f"  Anagram clues:       {total_anagram}")
    print(f"  Cipher clues:        {total_cipher}")
    print(f"  Item index entries:  {len(item_index)}")
    print(f"  NPC index entries:   {len(npc_index)}")


if __name__ == "__main__":
    main()
