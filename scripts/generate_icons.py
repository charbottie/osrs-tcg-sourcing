"""Generate method_icons.json — an icon for every Skilling-tab row that has no card art:
recipe outputs (recipes.json; the wiki recipe Bucket's output image), wiki-built methods
(skilling.json; the main image of the method's wiki page) and spells (spells.json; the
spell page's image).

Page images come from the wiki API (action=query&prop=pageimages, 50 titles per request),
cached in cache/page_images.json (a title with no image is cached as "").
Also reads cache/wiki_recipes.json (written by generate_recipes.py — it must exist),
output/skilling.json and output/spells.json. No CLI flags.

Output: scripts/output/method_icons.json
  { "recipe|<output lowercase>": url, "method|<skill>|<name>": url, "spell|<name>": url }

Run after generate_recipes.py / generate_skilling.py / generate_spells.py:
  python3 scripts/generate_icons.py
"""

from __future__ import annotations

import json
import wiki_api
import time
import urllib.parse
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_OUT = _HERE / "output" / "method_icons.json"
_CACHE = _HERE / "cache" / "page_images.json"
_IMG = "https://oldschool.runescape.wiki/images/"


def _file_url(f: str) -> str:
    """Wiki image URL for a File: name ("Oak logs.png" -> .../images/Oak_logs.png)."""
    return _IMG + urllib.parse.quote(f.replace(" ", "_"))


def page_images(titles: list[str]) -> dict[str, str]:
    """{title: 50px thumbnail URL or ""} for the titles, fetching only ones not in the cache.

    Returns the whole cache (a superset of titles). The cache is saved after every batch.
    """
    cache = json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t and t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=pageimages"
               "&piprop=thumbnail&pithumbsize=50&pilimit=50&titles=" + urllib.parse.quote("|".join(batch)))
        q = wiki_api.get_json(url)["query"]
        # map each resolved title back to the title(s) we asked for, through normalisation and
        # redirects (two hops: "a" -normalized-> "A" -redirect-> "B"), so the cache is keyed by request
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            src = (pg.get("thumbnail") or {}).get("source", "")
            names = [pg["title"]] + back.get(pg["title"], [])
            for t in list(names):
                names += back.get(t, [])
            for t in names:
                cache[t] = src
        for t in batch:
            cache.setdefault(t, "")
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(1)
    return cache


def main() -> int:
    """Collect recipe/method/spell icons and write _OUT. Returns 0."""
    out: dict[str, str] = {}
    bucket = json.loads((_HERE / "cache" / "wiki_recipes.json").read_text(encoding="utf-8"))
    for r in bucket:
        p = json.loads(r["production_json"])
        o = p.get("output")
        o = o[0] if isinstance(o, list) and o else o
        if isinstance(o, dict) and o.get("name") and o.get("image"):
            out.setdefault("recipe|" + o["name"].lower(), _file_url(o["image"]))
    methods = json.loads((_HERE / "output" / "skilling.json").read_text(encoding="utf-8"))
    spells = json.loads((_HERE / "output" / "spells.json").read_text(encoding="utf-8"))
    imgs = page_images([m.get("page") for m in methods] + list(spells))
    for m in methods:
        if imgs.get(m.get("page") or ""):
            out["method|%s|%s" % (m["skill"], m["name"])] = imgs[m["page"]]
    for s in spells:
        if imgs.get(s):
            out["spell|" + s] = imgs[s]
    _OUT.write_text(json.dumps(out, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    n = lambda pre: sum(1 for k in out if k.startswith(pre))
    print(f"Wrote {_OUT}: recipes {n('recipe|')}, methods {n('method|')}/{len(methods)}, spells {n('spell|')}/{len(spells)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
