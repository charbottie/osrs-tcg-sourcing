"""Generate boss_loot.json — loot for bosses whose rewards come from a chest or
reward pool rather than the boss monster's own drop table.

Bosses not listed here get their loot in the frontend from monster_drops.json
(the main boss monster's drop table), so this file only covers the exceptions.

Rarity rules (kept consistent with monster drops):
  - Absolute per-chest rates use rarity_mapper's buckets. Multi-roll rates like
    "7 × 1/2,448" are combined: P = 1 - (1 - a/b)^n  (Barrows → ~1/350 per piece).
  - Raid unique tables (CoX/ToB/ToA) list each item's share *of the unique roll*,
    not a per-raid chance — the roll itself depends on points/team/raid level.
    These are labelled "Unique" with the wiki share kept verbatim ("2/56"), and
    the wiki's unique-roll rule is stored alongside as `uniqueRoll`.
  - Rows footnoted "Only obtained if…" / "Awarded if…" (consolation items,
    first-completion rewards) are labelled "Conditional" with the footnote text.
  - "Varies" rows (Wintertodt) stay "Varies".

Also writes collection_log.json — each BOSS_DATA boss's collection-log items
(TCG cards only), from the wiki's Collection log page. The frontend uses it to
split boss loot into "Uniques" (log items) and "Other drops".

Output: scripts/output/boss_loot.json
  { "<BOSS_DATA name>": { source, page, uniqueRoll?, basis?,
      drops: [{card, rarity, fraction, rate?, notes?}] } }

Usage:
  python3 scripts/generate_boss_loot.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

import loot_parser
import rarity_mapper
import wiki_fetcher
from generate_sources import _card_for_drop, item_cards, load_cards, load_variant_aliases, set_variant_aliases

_OUT_DIR = Path(__file__).resolve().parent / "output"

# Per-boss config:
#   page        wiki page with the reward tables
#   include     only tables under these headings (any level); default = all
#   skip        drop tables under these headings (e.g. Challenge/Hard mode variants)
#   unique      headings whose tables are conditional unique-roll weights
#   only_uniques  restrict the unique table to these items (Moons share one chest)
#   uniqueRoll / basis  wiki-stated context, shown on the boss page
_MOON_UNIQUES = {
    "Blood Moon":   ["Dual macuahuitl", "Blood moon helm", "Blood moon chestplate", "Blood moon tassets"],
    "Blue Moon":    ["Blue moon spear", "Blue moon helm", "Blue moon chestplate", "Blue moon tassets"],
    "Eclipse Moon": ["Eclipse atlatl", "Eclipse moon helm", "Eclipse moon chestplate", "Eclipse moon tassets"],
}
BOSS_LOOT: dict[str, dict] = {
    "Chambers of Xeric": dict(
        page="Ancient chest", unique=["Unique drop table"], skip=["Challenge mode"],
        uniqueRoll="1% unique chance per 8,676 points (capped at 65.7%). Normal-mode weights shown."),
    "Theatre of Blood": dict(
        page="Monumental chest", unique=["Pre-roll"], skip=["Hard mode"],
        uniqueRoll="1/9.1 unique chance per raid across the team with no deaths (Hard Mode 1/7.7). "
                   "Normal-mode weights shown."),
    "Tombs of Amascut": dict(
        page="Chest (Tombs of Amascut)", unique=["Uniques"],
        uniqueRoll="Unique chance scales with raid level and points (capped at 55%)."),
    "Fortis Colosseum": dict(
        page="Rewards Chest (Fortis Colosseum)",
        basis="Rates are per wave claimed; the best wave's rate is shown."),
    "The Gauntlet":       dict(page="Reward Chest (The Gauntlet)", include=["Regular loot table"]),
    "Corrupted Gauntlet": dict(page="Reward Chest (The Gauntlet)", include=["Corrupted loot table"]),
    "Barrows": dict(
        page="Chest (Barrows)",
        basis="Assumes all 6 brothers killed and full reward potential."),
    "Grotesque Guardians": dict(page="Grotesque Guardians"),
    **{moon: dict(page="Lunar Chest", only_uniques=items,
                  basis="Lunar Chest — uniques shown are this Moon's own set.")
       for moon, items in _MOON_UNIQUES.items()},
    # Sire uniques come from offering an Unsired (a 1/100 Sire drop) at the Font of
    # Consumption; Unsired rates are scaled by that drop rate to give per-kill rates.
    "Abyssal Sire": dict(page="Unsired", also_monster="Abyssal Sire", via_drop=("Abyssal Sire", "Unsired"),
                         basis="Uniques come from offering an Unsired at the Font of Consumption."),
    # Lair chests opened with a key after the kill — loot = boss drops + chest
    "Obor":      dict(page="Chest (Obor's lair)", also_monster="Obor",
                      basis="Chest opened with a Giant key after the kill, plus Obor's own drops."),
    "Bryophyta": dict(page="Chest (Bryophyta's lair)", also_monster="Bryophyta",
                      basis="Chest opened with a Mossy key after the kill, plus Bryophyta's own drops."),
    "Wintertodt": dict(page="Reward cart"),
    "Tempoross":  dict(page="Reward pool"),
}

# Fixed rewards with no wiki drop table (completion rewards / points shops),
# plus the final monster whose own drop table also applies (e.g. Jad's pet).
BOSS_FIXED_LOOT: dict[str, tuple[str, list[str], str | None]] = {
    "Fight Caves":       ("Completion reward", ["Fire cape", "Tokkul"], "TzTok-Jad"),
    "Inferno":           ("Completion reward", ["Infernal cape", "Tokkul"], "TzKal-Zuk"),
    "Barbarian Assault": ("Honour points shop",
                          ["Fighter hat", "Ranger hat", "Runner hat", "Healer hat", "Fighter torso",
                           "Penance skirt", "Runner boots", "Penance gloves", "Granite helm", "Granite body"],
                          None),
}

# Wiki-stated rewards that aren't on any drop table (milestones, gambles, dossiers).
# (card, rarity or None to derive from fraction, fraction text, note)
EXTRA_LOOT: dict[str, list[tuple[str, str | None, str, str]]] = {
    "Barbarian Assault": [("Pet penance queen", None, "1/1,000", "Per high-level gamble.")],
    "Yama": [("Rite of vile transference", None, "1/181.5",
              "From dossiers: 1/15 per dossier, and dossiers are a 1/12.1 drop.")],
    "Chambers of Xeric": [("Xeric's cape", "Conditional", "Always",
                           "Received at 100, 500, 1,000, 1,500 and 2,000 completions.")],
    "Theatre of Blood": [("Sinhaza shroud", "Conditional", "Always",
                          "Received from the Mysterious Stranger at 100, 500, 1,000, 1,500 and 2,000 completions.")],
    "Tombs of Amascut": [("Icthlarin's shroud", "Conditional", "Always",
                          "Received at 100, 500, 1,000, 1,500 and 2,000 completions.")],
}

# BOSS_DATA name -> Collection log heading, where it isn't a case-insensitive /
# "The X" / "X and Y" match (see _log_heading_for)
LOG_HEADING_OVERRIDES: dict[str, str] = {
    "Barrows":             "Barrows Chests",
    "Blood Moon":          "Moons of Peril",
    "Blue Moon":           "Moons of Peril",
    "Eclipse Moon":        "Moons of Peril",
    "Corrupted Gauntlet":  "The Gauntlet",
    "Phosani's Nightmare": "The Nightmare",
    "Revenant Maledictus": "Revenants",
}
# Bosses with no collection log entry (The Mimic's items sit in the clue logs,
# Mad Angel / Gemstone Crab have none) show one undivided loot list.

_RATE_RE = re.compile(r"^(?:([\d.]+)\s*×\s*)?([\d.,]+)\s*/\s*([\d.,]+)")
_CONDITIONAL_RE = re.compile(r"\b(only (obtained|obtainable|received|awarded|dropped|given)|awarded) (if|in)\b", re.I)
_ON_UNIQUE_RE = re.compile(r"\bonly rolled when\b.*\bunique\b", re.I)  # e.g. Olmlet
_BACKREF_RE = re.compile(r"^\^\s*(?:[\d.]+\s+)*")  # "^ 1.0 1.1 " prefix on footnotes


def _canon(name: str, item_canon: dict[str, str]) -> str | None:
    """Card name for a wiki item name — exact, or via the catalog's variant lists
    (see generate_sources._card_for_drop), canonicalised to the card's casing."""
    card = _card_for_drop(name, item_canon)  # membership checks only — dict works
    return item_canon.get(card.lower()) if card else None


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _rate(text: str) -> float | None:
    """Per-chest probability from wiki rarity text; None if not a fraction."""
    if text.lower() == "always":
        return 1.0
    m = _RATE_RE.match(text)
    if not m:
        return None
    rolls = _num(m.group(1)) if m.group(1) else 1.0
    p = _num(m.group(2)) / _num(m.group(3))
    return 1.0 - (1.0 - min(p, 1.0)) ** rolls


def _footnotes(cell: Tag, soup: BeautifulSoup) -> list[str]:
    """Wiki data notes on a rarity cell ("[d 1]", "[a]"). Plain numeric
    references ("[2]") are source citations (news posts etc.) and are skipped."""
    notes = []
    for a in cell.select("sup.reference a[href^='#']"):
        label = a.get_text(strip=True).strip("[]")
        if label.isdigit():
            continue
        li = soup.find(id=a["href"][1:])
        if li:
            notes.append(_BACKREF_RE.sub("", li.get_text(" ", strip=True)).strip())
    return notes


def parse_chest(html: str, cfg: dict, item_canon: dict[str, str], scale: float = 1.0) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".mw-parser-output") or soup
    include, skip, unique = cfg.get("include"), cfg.get("skip", []), cfg.get("unique", [])
    only_uniques = {n.lower() for n in cfg.get("only_uniques", [])}

    path: dict[str, str] = {}
    best: dict[str, dict] = {}
    for el in body.find_all(["h2", "h3", "h4", "table"]):
        if el.name != "table":
            lvl = el.name
            path[lvl] = el.get_text(strip=True)
            for deeper in ("h3", "h4"):  # entering a heading clears its children
                if deeper > lvl:
                    path.pop(deeper, None)
            continue
        if "item-drops" not in el.get("class", []):
            continue
        heads = list(path.values())
        if include and not any(h in include for h in heads):
            continue
        if any(h in skip for h in heads):
            continue
        in_unique = any(h in unique for h in heads)
        is_unique_heading = any(h.lower().startswith("unique") for h in heads)

        for tr in el.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            link = cells[1].find("a")
            name = (link or cells[1]).get_text(strip=True)
            card = _canon(name, item_canon)
            if not card:
                continue
            if only_uniques and is_unique_heading and card.lower() not in only_uniques:
                continue

            rcell = cells[3]
            notes = _footnotes(rcell, soup)
            for sup in rcell.select("sup"):
                sup.decompose()
            text = rcell.get_text(" ", strip=True)
            p = _rate(text)
            if p is not None and scale != 1.0:
                p *= scale

            if any(_CONDITIONAL_RE.search(n) for n in notes):
                rarity = "Conditional"
            elif in_unique or any(_ON_UNIQUE_RE.search(n) for n in notes):
                rarity = "Unique"
            elif text.lower() == "varies":
                rarity = "Varies"
            elif p is not None:
                rarity = rarity_mapper.from_fraction(f"1/{1 / p:.6g}") if p < 1 else "Always"
            else:
                continue

            entry = {"card": card, "rarity": rarity, "fraction": text + (cfg.get("per_label") or "")}
            if p is not None and rarity not in ("Unique", "Conditional") and p < 1 and ("×" in text or scale != 1.0):
                entry["rate"] = f"1/{1 / p:,.1f}"
            if notes:
                entry["notes"] = notes
            entry["_p"] = p if p is not None else 0.0

            prev = best.get(card)
            # Keep the most informative row: Unique/Conditional status wins,
            # otherwise the highest per-chest chance (e.g. best Colosseum wave).
            if (prev is None
                    or (rarity in ("Unique", "Conditional") and prev["rarity"] not in ("Unique", "Conditional"))
                    or (prev["rarity"] not in ("Unique", "Conditional") and entry["_p"] > prev["_p"])):
                best[card] = entry

    for e in best.values():
        e.pop("_p", None)
    return list(best.values())


def build_boss_loot(item_canon: dict[str, str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    monster_drops = json.loads((_OUT_DIR / "monster_drops.json").read_text(encoding="utf-8"))
    for boss, cfg in BOSS_LOOT.items():
        page = cfg["page"]
        html = wiki_fetcher.fetch(page.replace(" ", "_"))
        if not html:
            print(f"  [SKIP] {boss}: could not fetch {page}")
            continue
        scale = 1.0
        if cfg.get("via_drop"):
            mon, via = cfg["via_drop"]
            mon_html = wiki_fetcher.fetch(mon.replace(" ", "_")) or ""
            row = next((d for d in loot_parser.parse_drops(mon_html) if d["item"] == via), None)
            scale = _rate(row["fraction"]) if row and row["fraction"] else None
            if not scale:
                print(f"  [SKIP] {boss}: no {via} rate on {mon}")
                continue
            cfg = {**cfg, "per_label": f" per {via}"}
        drops = parse_chest(html, cfg, item_canon, scale)
        source = page
        if cfg.get("also_monster"):
            have = {d["card"] for d in drops}
            drops += [{"card": d["card"], "rarity": d["rarity"], "fraction": d["fraction"]}
                      for d in monster_drops.get(cfg["also_monster"], {}).get("drops", [])
                      if not d.get("fromRdt") and d["card"] not in have]
            source = f"{cfg['also_monster']} drops + {page}"
        entry = {"source": source, "page": page.replace(" ", "_"), "drops": drops}
        for k in ("uniqueRoll", "basis"):
            if cfg.get(k):
                entry[k] = cfg[k]
        result[boss] = entry
        counts = {}
        for d in drops:
            counts[d["rarity"]] = counts.get(d["rarity"], 0) + 1
        print(f"  {boss:<22} {len(drops):>3} cards from /w/{page}  {counts}")

    for boss, (source, cards, final_monster) in BOSS_FIXED_LOOT.items():
        drops = [{"card": item_canon[c.lower()], "rarity": "Always", "fraction": "Always"}
                 for c in cards if c.lower() in item_canon]
        if final_monster:
            have = {d["card"] for d in drops}
            drops += [{"card": d["card"], "rarity": d["rarity"], "fraction": d["fraction"]}
                      for d in monster_drops.get(final_monster, {}).get("drops", [])
                      if not d.get("fromRdt") and d["card"] not in have]
            source += f" + {final_monster} drops"
        result[boss] = {"source": source, "page": None, "drops": drops}
        print(f"  {boss:<22} {len(drops):>3} fixed rewards / final-boss drops")

    # Extras: for bosses using monster drops (no boss_loot entry yet), the frontend
    # merges these with the monster table via the "extra" list.
    for boss, rows in EXTRA_LOOT.items():
        extra = []
        for card, rarity, fraction, note in rows:
            if card.lower() not in item_canon:
                continue
            p = _rate(fraction)
            r = rarity or (rarity_mapper.from_fraction(f"1/{1 / p:.6g}") if p else "Unknown")
            extra.append({"card": item_canon[card.lower()], "rarity": r, "fraction": fraction, "notes": [note]})
        if boss in result:
            have = {d["card"] for d in result[boss]["drops"]}
            result[boss]["drops"] += [e for e in extra if e["card"] not in have]
        else:
            result[boss] = {"extra": extra}
        print(f"  {boss:<22} +{len(extra)} wiki-stated extras")
    return result


def parse_collection_log(html: str, item_canon: dict[str, str]) -> dict[str, list[str]]:
    """Collection log heading -> TCG card names listed under it (first table only)."""
    body = BeautifulSoup(html, "html.parser").select_one(".mw-parser-output")
    out: dict[str, list[str]] = {}
    cur = None
    for el in body.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h3", "h4"):
            cur = el.get_text(strip=True)
        elif el.name == "table" and cur and cur not in out:
            cards: list[str] = []
            for a in el.select("a[title]"):
                # Log titles carry state suffixes the card name doesn't:
                # "Tome of fire (empty)", "Craw's bow (u)", "Giant egg sac(full)",
                # "Icthlarin's shroud (tier 3)". Exact match only after stripping.
                card = _canon(a["title"], item_canon)
                if card and card not in cards:
                    cards.append(card)
            out[cur] = cards
    return out


def _log_heading_for(boss: str, headings: list[str]) -> str | None:
    if boss in LOG_HEADING_OVERRIDES:
        return LOG_HEADING_OVERRIDES[boss]
    low = {h.lower(): h for h in headings}
    for cand in (boss, "The " + boss):
        if cand.lower() in low:
            return low[cand.lower()]
    for h in headings:  # "Callisto and Artio", "Vet'ion and Calvar'ion"
        if " and " in h and boss.lower() in [x.strip().lower() for x in h.split(" and ")]:
            return h
    return None


def build_collection_log(boss_names: list[str], item_canon: dict[str, str]) -> dict[str, dict]:
    html = wiki_fetcher.fetch("Collection_log")
    if not html:
        print("  [SKIP] could not fetch Collection log")
        return {}
    log = parse_collection_log(html, item_canon)
    result, unmapped = {}, []
    for boss in boss_names:
        heading = _log_heading_for(boss, list(log))
        if heading and heading in log:
            result[boss] = {"log": heading, "items": log[heading]}
        else:
            unmapped.append(boss)
    print(f"  Collection log: {len(result)} bosses mapped; no log entry: {unmapped}")
    return result


def _boss_names_from_preview() -> list[str]:
    """BOSS_DATA names, read from preview.html so the two never drift."""
    src = (Path(__file__).resolve().parent / "preview.html").read_text(encoding="utf-8")
    start = src.index("const BOSS_DATA = [")
    end = src.index("\n];", start)
    names = re.findall(r"\{ name:(?:'((?:[^'\\]|\\.)*)'|\"([^\"]*)\")", src[start:end])
    return [(a or b).replace("\\'", "'") for a, b in names]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    p.add_argument("--out-dir", default=str(_OUT_DIR))
    args = p.parse_args()

    items = item_cards(load_cards(args.card_json))
    set_variant_aliases(load_variant_aliases(args.card_json))
    item_canon = {c["name"].lower(): c["name"] for c in items}

    loot = build_boss_loot(item_canon)
    out = Path(args.out_dir) / "boss_loot.json"
    out.write_text(json.dumps(loot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(loot)} bosses)")

    clog = build_collection_log(_boss_names_from_preview(), item_canon)
    out = Path(args.out_dir) / "collection_log.json"
    out.write_text(json.dumps(clog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(clog)} bosses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
