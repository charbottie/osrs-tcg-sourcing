"""Generate card_versions.json — every item version of each TCG card, with how the
version is made (the wiki's {{Recipe}} template) where it has one.

A version (from the catalog's tcg.variants, e.g. Infernal harpoon → Dragon harpoon card)
is covered by its card: owning the card unlocks every version. The card page lists the
versions so it's clear what the card covers and how each upgrade is created.

Wiki pages are read in batches of 50 (action=query, redirects resolved) and cached in
scripts/cache/version_pages.json.

Output: scripts/output/card_versions.json
  { "<card>": [ {name, page, icon?, detail? (image URLs), recipe?: {skills: {Skill: lvl}, materials: [[name, qty]],
                 tools: [...], facilities: "…", members: bool}} ] }

Usage:
  python3 scripts/generate_card_versions.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_OUT = _HERE / "output" / "card_versions.json"
_CACHE = _HERE / "cache" / "version_pages.json"
_IMG_CACHE = _HERE / "cache" / "version_images.json"


def fetch_image_urls(names: list[str]) -> dict[str, dict]:
    """version name → {icon, detail} thumbnail URLs from the wiki API (the same form as
    card_details.json image URLs); missing files are left out. Cached."""
    cache = json.loads(_IMG_CACHE.read_text(encoding="utf-8")) if _IMG_CACHE.exists() else {}
    files = {}
    for n in names:
        if n not in cache:
            files[f"File:{n}.png"] = (n, "icon")
            files[f"File:{n} detail.png"] = (n, "detail")
    todo = list(files)
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&prop=imageinfo"
               "&iiprop=url&iiurlwidth=130&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read())["query"]
        norm = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for pg in q.get("pages", {}).values():
            info = (pg.get("imageinfo") or [{}])[0]
            src = norm.get(pg["title"], pg["title"])
            if src in files and (info.get("thumburl") or info.get("url")):
                name, kind = files[src]
                cache.setdefault(name, {})[kind] = info.get("thumburl") or info.get("url")
        for f in batch:
            cache.setdefault(files[f][0], {})
        _IMG_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(1)
        if (i // 50) % 10 == 0:
            print(f"  images {min(i + 50, len(todo))}/{len(todo)}")
    return cache


def fetch_pages(titles: list[str]) -> dict[str, dict]:
    """title → {page, text} (redirects followed); cached."""
    cache = json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1"
               "&prop=revisions&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-planner (charbottie)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.loads(r.read())["query"]
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {n["from"]: n["to"] for n in q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", {}).values()}
        for t in batch:
            title = redir.get(norm.get(t, t), norm.get(t, t))
            p = pages.get(title, {})
            text = (p.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            cache[t] = {"page": title if text else None, "text": text}
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(1)
        print(f"  fetched {min(i + 50, len(todo))}/{len(todo)}")
    return cache


def _template_params(block: str) -> dict[str, str]:
    params = {}
    for line in block.split("\n|")[1:]:
        if "=" in line:
            k, v = line.split("=", 1)
            params[k.strip().lower()] = re.sub(r"\}\}\s*$", "", v).strip()
    return params


def recipe_for(text: str, version: str) -> dict | None:
    """The {{Recipe}} whose output is this version (falls back to the page's only recipe)."""
    blocks = re.findall(r"\{\{Recipe\s*\n.*?\n\}\}", text, flags=re.S)
    chosen = None
    for b in blocks:
        p = _template_params(b)
        outs = [v.lower() for k, v in p.items() if re.fullmatch(r"output\d+", k)]
        if version.lower() in outs:
            chosen = p
            break
    if chosen is None and len(blocks) == 1:
        p = _template_params(blocks[0])
        outs = [v.lower() for k, v in p.items() if re.fullmatch(r"output\d+", k)]
        chosen = p if not outs or version.lower() in outs else None
    if chosen is None:
        return None
    skills = {}
    for k, v in chosen.items():
        m = re.fullmatch(r"skill(\d+)", k)
        if m and v:
            lvl = chosen.get(f"skill{m.group(1)}lvl", "")
            if lvl.isdigit():
                skills[v] = int(lvl)
    mats = []
    for k, v in sorted(chosen.items()):
        m = re.fullmatch(r"mat(\d+)", k)
        if m and v:
            qty = chosen.get(f"mat{m.group(1)}quantity", "1") or "1"
            mats.append([v, qty])
    tools = [t.strip() for t in re.split(r",|<br\s*/?>", chosen.get("tools", "")) if t.strip()]
    return {"skills": skills, "materials": mats, "tools": tools,
            "facilities": chosen.get("facilities", "") or None,
            "members": chosen.get("members", "").lower() == "yes"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    cards = {i["name"].lower() for i in cat["items"]}
    versions: dict[str, list[str]] = {}
    for item in cat["items"]:
        seen = set()
        for v in item.get("tcg", {}).get("variants", []):
            name = (v.get("name") or "").strip()
            if name and name.lower() not in cards and name.lower() != item["name"].lower() and name.lower() not in seen:
                seen.add(name.lower())
                versions.setdefault(item["name"], []).append(name)
    pages = fetch_pages([v for vs in versions.values() for v in vs])
    images = fetch_image_urls([v for vs in versions.values() for v in vs])
    out, with_recipe = {}, 0
    for card, vs in sorted(versions.items()):
        rows = []
        for v in vs:
            pg = pages.get(v, {})
            row = {"name": v, "page": pg.get("page"), **{k: u for k, u in images.get(v, {}).items()}}
            rec = recipe_for(pg.get("text", ""), v) if pg.get("text") else None
            if rec:
                row["recipe"] = rec
                with_recipe += 1
            rows.append(row)
        out[card] = rows
    _OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT} ({len(out)} cards, {sum(map(len, out.values()))} versions, {with_recipe} with a recipe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
