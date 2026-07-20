"""Parse production info, spawn locations, and shop data from OSRS Wiki item pages.

Wiki page structure (as verified from live pages 2026-07):

Creation section (h2 "Creation"):
  - Skill/level table: header ['Skill','Level','XP'], data row ['SkillName','NN(b)','XP']
  - Ingredient table: header ['Item','Quantity','Cost'],
    data rows ['', 'ItemName', 'qty', 'cost'],
    'Total cost' row (separator),
    output row ['', 'OutputName', 'qty', 'cost'],
    'Profit' row (stop)

Spawns (h2/h3/h4 containing "spawn"):
  - Table with header starting 'Location'
  - Data rows: cells[0] = location name text

Shop locations:
  - <table class="store-locations-list">
  - Columns: Seller | Location | Stock | Restock | Price sold at | Price bought at | ...
  - Price cell (col 4): data-sort-value holds integer; child <img> src encodes currency
  - No-img shops use seller name → currency lookup table
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

_SKILL_NAMES = {
    "fletching", "smithing", "crafting", "cooking", "herblore",
    "runecrafting", "runecraft",   # wiki uses "Runecraft" (no -ing)
    "construction", "farming", "magic", "firemaking",
    "thieving", "mining", "woodcutting", "fishing", "agility",
    "hunter", "slayer",
}

# Map wiki short names → display names
_SKILL_DISPLAY = {"runecraft": "Runecrafting"}

# h2 headings that indicate a production/creation section
_CREATION_H2 = {
    "creation",
    "runecraft info",     # rune pages
    "herblore info",      # potion pages
    "cooking info",       # some food pages
    "cooking",            # pizza toppings (Anchovy pizza, Meat pizza, etc.)
    "recipe",             # some food/item pages (Pineapple pizza, Hunter kit, etc.)
    "smithing info",      # some smithed item pages
}


def parse_production(html: str) -> list[dict]:
    """Return production methods found on the page.

    Each method is a dict:
      {skill, level, facilities, ingredients: [{item, quantity}], outputQuantity}

    Multiple methods may be returned (e.g. furnace vs blast furnace). The
    caller should use the first entry as the primary method.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    in_creation = False
    pending_skill: dict | None = None

    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h2", "h3", "h4"):
            text = el.get_text(strip=True).lower()
            if el.name == "h2":
                in_creation = text in _CREATION_H2
                pending_skill = None
            # Don't reset in_creation for sub-headings — stay inside Creation block
            continue

        if not in_creation or el.name != "table":
            continue

        headers = _row_texts(el.find("tr"))

        if headers[:2] == ["Skill", "Level"]:
            pending_skill = _parse_skill_table(el)

        elif headers[:2] == ["Item", "Quantity"] and pending_skill:
            ingredients, output_qty = _parse_ingredient_table(el)
            if ingredients:
                results.append({
                    "skill":         pending_skill["skill"],
                    "level":         pending_skill["level"],
                    "xp":            pending_skill.get("xp"),
                    "facilities":    pending_skill.get("facilities"),
                    "tools":         pending_skill.get("tools"),
                    "ingredients":   ingredients,
                    "outputQuantity": output_qty,
                })
            # Each ingredient table consumes its pending skill table.
            # A new skill table will follow if there's another method.
            pending_skill = None

    return results


def parse_spawns(html: str) -> list[str]:
    """Return spawn location names from the page (deduplicated, ordered)."""
    soup = BeautifulSoup(html, "html.parser")
    locations: list[str] = []
    seen: set[str] = set()

    in_spawns = False
    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h2", "h3", "h4"):
            text = el.get_text(strip=True).lower()
            in_spawns = "spawn" in text and "shop" not in text
            continue

        if not in_spawns or el.name != "table":
            continue

        headers = _row_texts(el.find("tr"))
        if not headers or headers[0].lower() != "location":
            continue

        for tr in el.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            raw = cells[0].get_text(" ", strip=True)
            # Strip citation refs [1], trailing notes, wiki map links
            loc = re.sub(r"\[.*?\]", "", raw).strip()
            loc = re.sub(r"\s{2,}", " ", loc)
            # Trim after common separators that indicate qualifiers
            loc = re.split(r"[-–](?:\s*on\b|\s*north|\s*south|\s*east|\s*west|\s*2nd|\s*building)", loc)[0].strip()
            if loc and loc not in seen:
                seen.add(loc)
                locations.append(loc)

    return locations


def parse_shop_available(html: str) -> bool:
    """Return True if the item has any shop locations listed."""
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.find("table", class_="store-locations-list"))


_ITEM_SRC_BG: dict[str, str] = {
    "table-bg-blue":   "Always",
    "table-bg-green":  "Common",
    "table-bg-yellow": "Uncommon",
    "table-bg-orange": "Rare",
    "table-bg-red":    "Very Rare",
}

_FRACTION_RE2 = re.compile(r"^\d+(?:\.\d+)?/[\d,.]+$")


def parse_item_sources(html: str) -> list[dict]:
    """Parse the 'Item sources' table from a wiki item page.

    Returns a list of dicts:
      {source: str, level: str, quantity: str, fraction: str, wiki_label: str}

    The 'Item sources' section lists monsters, chests, and activities that
    yield the item as a drop or reward (columns: Source | Level | Quantity |
    Rarity | League region).
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()

    in_sources = False
    for el in soup.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h2", "h3", "h4"):
            in_sources = "item sources" in el.get_text().lower()
            continue
        if not in_sources or el.name != "table":
            continue

        for tr in el.find_all("tr")[1:]:  # skip header
            cells = tr.find_all(["td", "th"])
            if len(cells) < 4:
                continue

            # Source name — prefer link title/text, fall back to cell text
            source_cell = cells[0]
            link = source_cell.find("a")
            source = (link.get("title") or link.get_text(strip=True)) if link \
                else source_cell.get_text(strip=True)
            # Strip trailing qualifiers added inline (e.g. "VorkathPost-quest")
            source = re.sub(r"(Post-quest|Pre-quest|Members|Free-to-play).*$", "", source).strip()
            if not source or source in seen:
                continue
            seen.add(source)

            level    = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            quantity = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            # Rarity — same extraction as loot_parser
            rarity_cell = cells[3]
            fraction = ""
            wiki_label = ""
            for cls in rarity_cell.get("class", []):
                if cls in _ITEM_SRC_BG:
                    wiki_label = _ITEM_SRC_BG[cls]
                    break
            for span in rarity_cell.find_all("span"):
                frac = span.get("data-drop-fraction", "").strip()
                if frac and _FRACTION_RE2.match(frac):
                    fraction = frac
                    break
            if not fraction:
                clean = re.sub(r"\[\d+\]", "", rarity_cell.get_text(strip=True)).strip()
                if _FRACTION_RE2.match(clean):
                    fraction = clean

            results.append({
                "source":     source,
                "level":      level,
                "quantity":   quantity,
                "fraction":   fraction,
                "wiki_label": wiki_label,
            })

    return results


# ── Shop currency helpers ─────────────────────────────────────────────────────

# Maps seller name (normalised — no trailing "(N)") → currency card name.
# Used only when the price cell has no currency <img> (point-based reward shops).
_SELLER_CURRENCY: dict[str, str] = {
    "Slayer Rewards":                               "Slayer points",
    "Dom Onion's Reward Shop":                      "Nightmare Zone points",
    "Justine's stuff for the Last Shopper Standing":"LMS points",
    "Soul Wars Reward Shop":                        "Zeal tokens",
    "Void Knights' Reward Options":                 "Pest Control points",
    "Mahogany Homes Reward Shop":                   "Mahogany Homes points",
    "Farmer Gricoller's Rewards":                   "Tithe Farm points",
    "Giants' Foundry Reward Shop":                  "Foundry reputation",
    "Petrified Pete's Ore Shop":                    "Volcanic Mine points",
    "Bounty Hunter Store":                          "Bounty Hunter points",
    "Leagues Reward Shop":                          "League points",
    "Events Reward Shop":                           "Event tokens",
    "PvP Arena Rewards":                            "PvP Arena points",
    "Speedrunning Reward Shop":                     "Giant stopwatch",
    "Castle Wars Ticket Exchange":                  "Castle wars ticket",
    "Grace's Graceful Clothing":                    "Mark of grace",
    "Dusuri's Star Shop":                           "Stardust",
    "Mining Guild Mineral Exchange":                "Unidentified minerals",
    "Prospector Percy's Nugget Shop":               "Golden nugget",
    "Agility Arena Store":                          "Brimhaven voucher",
    "Mysterious Hallowed Goods":                    "Hallowed mark",
    "Ranging Guild Ticket Exchange":                "Archery ticket",
    "Chest (Theatre of Blood)":                     "Theatre of Blood points",
}


def _currency_from_price_cell(cell: Tag) -> str:
    """Derive canonical currency name from the 'Price sold at' table cell."""
    img = cell.find("img")
    if img:
        src = img.get("src", "")
        fname = unquote(src.split("/")[-1].split("?")[0]).lower()

        if fname.startswith("coins_"):           return "Coins"
        if fname.startswith("tokkul"):           return "Tokkul"
        if fname.startswith("castle_wars_ticket"): return "Castle wars ticket"
        if fname.startswith("mark_of_grace"):    return "Mark of grace"
        if fname.startswith("golden_nugget"):    return "Golden nugget"
        if fname.startswith("hallowed_mark"):    return "Hallowed mark"
        if fname.startswith("unidentified_minerals"): return "Unidentified minerals"
        if fname.startswith("stardust"):         return "Stardust"
        if fname.startswith("molch_pearl"):      return "Molch pearl"
        if fname.startswith("mermaid"):          return "Mermaid's tear"
        if fname.startswith("archery_ticket"):   return "Archery ticket"
        if fname.startswith("brimhaven_voucher"): return "Brimhaven voucher"
        if fname.startswith("anima-infused_bark"): return "Anima-infused bark"
        if fname.startswith("pieces_of_eight"): return "Pieces of eight"
        if fname.startswith("trading_sticks"):   return "Trading sticks"
        if fname.startswith("abyssal_pearls"):   return "Abyssal pearls"
        if fname.startswith("league_points"):    return "League points"
        if fname.startswith("frog_token"):       return "Frog token"
        if fname.startswith("minnow"):           return "Minnow"
        if fname.startswith("termites"):         return "Termites"
        if fname.startswith("numulite"):         return "Numulite"
        # Fallback: use img alt text
        alt = img.get("alt", "")
        if alt:
            return alt
    return ""   # caller will fall back to seller-name lookup


def parse_shop_locations(html: str) -> list[dict]:
    """Return shop locations from a wiki item page.

    Each entry: {seller: str, price: int|None, currency: str}
    Deduplicates by (seller, currency) — strips trailing (N) from seller names.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen: set[tuple] = set()

    for table in soup.find_all("table", class_="store-locations-list"):
        for tr in table.find_all("tr")[1:]:          # skip header row
            cells = tr.find_all(["td", "th"])
            if len(cells) < 5:
                continue

            # Seller: strip trailing (N) from multi-instance shop names
            seller_raw = cells[0].get_text(strip=True)
            seller = re.sub(r"\s*\(\d+\)\s*$", "", seller_raw).strip()

            # Price: prefer data-sort-value (clean integer string)
            price_cell = cells[4]
            raw_price = (price_cell.get("data-sort-value") or
                         price_cell.get_text(strip=True).replace(",", ""))
            try:
                price = int(raw_price)
            except (ValueError, TypeError):
                price = None

            # Currency
            currency = _currency_from_price_cell(price_cell)
            if not currency:
                currency = _SELLER_CURRENCY.get(seller, "Coins")

            key = (seller, currency)
            if key in seen:
                continue
            seen.add(key)

            results.append({"seller": seller, "price": price, "currency": currency})

    return results


# ── Helpers ─────────────────────────────────────────────────────────────────

def _row_texts(tr: Tag | None) -> list[str]:
    if tr is None:
        return []
    return [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]


def _parse_skill_table(table: Tag) -> dict | None:
    """Extract {skill, level, xp, facilities} from a Skill/Level/XP table."""
    skill = None
    level = None
    xp: float | None = None
    facilities = None
    tools_list: list[str] = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        c0 = cells[0].get_text(strip=True)

        if c0 == "Skill":
            continue  # header row

        if c0.lower() in _SKILL_NAMES:
            skill = _SKILL_DISPLAY.get(c0.lower(), c0)  # normalise "Runecraft" → "Runecrafting"
            if len(cells) >= 2:
                m = re.search(r"(\d+)", cells[1].get_text(strip=True))
                if m:
                    level = int(m.group(1))
            if len(cells) >= 3:
                raw_xp = cells[2].get_text(strip=True).replace(",", "")
                m = re.search(r"[\d.]+", raw_xp)
                if m:
                    xp = float(m.group())

        elif c0 in ("Tools", "Facilities", "Facility") and len(cells) >= 4:
            # cells[1] = tool (icon only — text is empty, read from link title/text)
            # cells[3] = facility (text label)
            tool_cell = cells[1]
            tool_link = tool_cell.find("a")
            if tool_link:
                tool_name = tool_link.get("title") or tool_link.get_text(strip=True)
                if tool_name and tool_name.lower() not in ("none", ""):
                    tools_list.append(tool_name)

            # Facility: prefer first link title, fall back to text
            raw_fac = cells[3].get_text(" ", strip=True)
            first_link = cells[3].find("a")
            if first_link:
                raw_fac = first_link.get("title") or first_link.get_text(strip=True)
            facilities = raw_fac or None

    if not skill or level is None:
        return None
    return {"skill": skill, "level": level, "xp": xp, "facilities": facilities,
            "tools": tools_list if tools_list else None}


def _parse_ingredient_table(table: Tag) -> tuple[list[dict], int | None]:
    """Extract (ingredients, output_quantity) from an Item/Quantity/Cost table."""
    ingredients: list[dict] = []
    output_qty: int | None = None
    past_total = False

    for tr in table.find_all("tr")[1:]:  # skip header
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        c0 = cells[0].get_text(strip=True).lower()

        if c0.startswith("total"):
            past_total = True
            continue
        if c0.startswith("profit") or c0.startswith("loss"):
            break

        # 4-cell data row: [image, name, qty, cost]
        if len(cells) < 3:
            continue

        # Item name from link in cell[1]
        name_cell = cells[1]
        link = name_cell.find("a")
        item_name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)
        if not item_name:
            continue

        qty_text = cells[2].get_text(strip=True).replace(",", "")
        m = re.search(r"\d+", qty_text)
        qty = int(m.group()) if m else 1

        if past_total:
            # Output row — record quantity and stop
            output_qty = qty
            break
        else:
            ingredients.append({"item": item_name, "quantity": qty})

    return ingredients, output_qty
