"""Name lookups over the TCG catalog shared by the generators."""

from __future__ import annotations

import re


def npc_names(cat: dict, versions: bool = False) -> dict[str, str]:
    """lowercase name -> NPC card. A card's own name wins, then its name without a "(…)"
    disambiguator, then its wiki page title. The live catalog renames NPC cards whose name clashes
    with an item card ("Manta ray (sailing)", "Rock Golem (monster)"), so wiki text naming the
    in-game NPC still finds its card. versions=True also maps the in-game names of a card's versions
    (tcg.variants: "Phosani's Nightmare" -> The Nightmare); use it only for monster names, not
    free-text wiki links (Rock Crab versions are called "Rocks")."""
    out = {x["name"].lower(): x["name"] for x in cat["npcs"]}
    for x in cat["npcs"]:   # "Manta ray (sailing)" -> also "manta ray" (unless another NPC card has that name)
        base = re.sub(r"\s*\([^)]*\)$", "", x["name"])
        if base != x["name"]:
            out.setdefault(base.lower(), x["name"])
    for x in cat["npcs"]:   # the card's wiki page ("Vanguard" -> Vanguards)
        page = (x.get("wiki") or {}).get("page") or ""
        if page:
            out.setdefault(page.lower(), x["name"])
    if versions:
        for x in cat["npcs"]:
            for v in (x.get("tcg") or {}).get("variants") or []:
                if v.get("name"):
                    out.setdefault(v["name"].lower(), x["name"])
    return out
