"""Generate card_aliases.json — item name → TCG card, from the catalog's tcg.variants lists.

The page uses this so its card lookup (`_cardInfo`) resolves item versions the same way the
data generators do (generate_sources._card_for_drop): "Silver sickle (b)" → Silver sickle,
"Prayer potion(3)" → Prayer potion, "Grimy ranarr weed" → Ranarr weed, etc.

Output: scripts/output/card_aliases.json  { "<variant name, lowercase>": "<card name>" }

Usage:
  python3 scripts/generate_card_aliases.py --card-json research/card-catalog-v1.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_OUT = Path(__file__).resolve().parent / "output" / "card_aliases.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card-json", required=True)
    args = p.parse_args()
    cat = json.loads(Path(args.card_json).read_text(encoding="utf-8"))
    cards = {i["name"].lower() for i in cat["items"]}
    aliases: dict[str, str] = {}
    for item in cat["items"]:
        for v in item.get("tcg", {}).get("variants", []):
            name = (v.get("name") or "").strip()
            key = name.lower()
            # a variant spelled like a different card's own name stays that card's
            if name and key not in cards and key != item["name"].lower():
                aliases.setdefault(key, item["name"])
    _OUT.write_text(json.dumps(dict(sorted(aliases.items())), indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {_OUT} ({len(aliases)} aliases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
