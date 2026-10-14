"""Scan the wiki for entry requirements of every location name the planner uses, and report the
ones scripts/location_requirements.json doesn't cover yet (maintenance helper; writes no output).

Location names ("X (nearby)" counted as X) come from output/monster_locations.json, output/slayer.json, output/shop_owners.json
and the "location" fields of skilling_curated.json methods. For each name the page's
{{Infobox Location}} (and any version of it) |requirement / |quest fields are read (batched 50 per
request with action=query revisions; cached in cache/location_infobox_reqs.json).

Usage:
  python3 scripts/scan_location_requirements.py            # report uncovered requirements
  python3 scripts/scan_location_requirements.py --all      # every location with a requirement field
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from pathlib import Path

import wiki_api

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "cache" / "location_infobox_reqs.json"


def used_location_names() -> list[str]:
    out = _HERE / "output"
    names: set[str] = set()
    ml = json.loads((out / "monster_locations.json").read_text(encoding="utf-8"))
    for k, v in ml.items():
        names |= set(v)
    for v in json.loads((out / "shop_owners.json").read_text(encoding="utf-8")).values():
        names |= set(v.get("locations") or {})
    sl = json.loads((out / "slayer.json").read_text(encoding="utf-8"))
    for t in sl["tasks"].values():
        for m in t["monsters"]:
            names |= set(m.get("locations", [])) | set(m.get("locationAccess", {}))
    for m in json.loads((_HERE / "skilling_curated.json").read_text(encoding="utf-8")):
        if m.get("location"):
            names.add(m["location"])
    nb = " (nearby)"
    return sorted({n[:-len(nb)] if n.endswith(nb) else n for n in names})


def _field(text: str, key: str) -> list[str]:
    return [v.strip() for v in re.findall(r"\|\s*" + key + r"\d*\s*=(.*?)(?=\n\s*\||\n\}\})", text, flags=re.S) if v.strip()]


def infobox_requirements(titles: list[str]) -> dict[str, dict]:
    """page → {"requirement": [...], "quest": [...], "type": "..."} from its Infobox Location (cached)."""
    cache = json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        url = ("https://oldschool.runescape.wiki/api.php?action=query&format=json&redirects=1&prop=revisions"
               "&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(batch)))
        q = wiki_api.get_json(url)["query"]
        back = {}
        for n in q.get("normalized", []) + q.get("redirects", []):
            back.setdefault(n["to"], []).append(n["from"])
        for pg in q.get("pages", {}).values():
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            m = re.search(r"\{\{\s*Infobox Location", text, re.I)
            box = text[m.start():m.start() + 6000] if m else ""
            info = {"requirement": _field(box, "requirement"), "quest": _field(box, "quest"),
                    "type": (_field(box, "type") or [""])[0]} if box else {}
            srcs = [pg["title"]] + back.get(pg["title"], [])
            for t in list(srcs):
                srcs += back.get(t, [])
            for t in srcs:
                cache[t] = info
        for t in batch:
            cache.setdefault(t, {})
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"  pages {min(i + 50, len(todo))}/{len(todo)}")
    return cache


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    names = used_location_names()
    info = infobox_requirements(names)
    cur = json.loads((_HERE / "location_requirements.json").read_text(encoding="utf-8")) \
        if (_HERE / "location_requirements.json").exists() else {}
    covered_lc = {k.lower() for k in cur} | {k.lower() for k in cur.get("_reviewedNoGate", {})}
    # places already gated by the Slayer verification (slayer_curated.json → monster_locations _gates)
    ml = json.loads((_HERE / "output" / "monster_locations.json").read_text(encoding="utf-8"))
    covered_lc |= {k.lower() for k in ml.get("_gates", {}) if k not in cur}
    n = 0
    for name in names:
        i = info.get(name) or {}
        req = [r for r in i.get("requirement", []) if not re.fullmatch(r"(none|no|n/a|-)", r, re.I)]
        if not req and not i.get("quest"):
            continue
        covered = name.lower() in covered_lc
        if args.all or not covered:
            n += 1
            print(f"{'  ' if covered else '! '}{name}: requirement={req} quest={i.get('quest')}")
    print(f"{len(names)} location names; {n} {'with requirement fields' if args.all else 'not covered by location_requirements.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
