# 06 — Fix Encoded Name Defect in Snapshot Generator

**Status**: Known bug in Bronzeman CLAUDE.md. Quick fix.  
**Repo**: `Felmeme/bronzeman-tcg` — `scripts/generate_tracked_monsters.py`  
**Effort**: Tiny (< 1 hour)  
**Dependencies**: None  

---

## Problem

Per Bronzeman CLAUDE.md:

> **Tracked-name encoding defect (found 2026-07-19)**: four tracked names (rosé wines, "grubs à la mode") carry a literal U+FFFD replacement char from the snapshot generator; consumables.json preserves them byte-for-byte so matching holds. Real fix belongs in `scripts/generate_tracked_monsters.py` encoding handling; regenerate both snapshots + consumables when fixed.

Items with non-ASCII characters (é, à) in their names are being processed with incorrect encoding, replacing the character with the Unicode replacement character `\uFFFD` (the "?" diamond). The match still works because both sides get the same wrong character, but:

1. It's technically wrong
2. It would break if the encoding is ever fixed on only one side
3. The wiki data pipeline (opportunity 05) would produce correctly-encoded names that wouldn't match

---

## Root Cause

The `generate_tracked_monsters.py` script almost certainly opens the Card.json file without specifying `encoding='utf-8'`:

```python
# Wrong:
with open(card_json_path) as f:
    data = json.load(f)

# Or the file write is wrong:
with open(output_path, 'w') as f:
    json.dump(data, f)  # Missing: ensure_ascii=False
```

Python 3 on Windows defaults to the system's ANSI encoding (e.g. CP1252) rather than UTF-8, causing non-ASCII characters to be misread.

---

## Fix

```python
# Reading Card.json:
with open(card_json_path, encoding='utf-8') as f:
    data = json.load(f)

# Writing output JSON:
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

Also ensure the resource files in `src/main/resources/` are UTF-8 encoded, and that the Java loading code reads them as UTF-8:

```java
// CardNameCatalog.java — already correct:
new InputStreamReader(stream, StandardCharsets.UTF_8)
```

Java side is fine. The fix is purely in the Python script.

---

## After Fix

1. Fix `generate_tracked_monsters.py`
2. Regenerate all snapshots: `python scripts/generate_tracked_monsters.py research/card-catalog.json`
3. Verify the four affected names are now correct:
   - `rosé wine` (and dose variants)
   - `grubs à la mode`
   - (check for any others with non-ASCII)
4. Bump version + CHANGELOG entry, commit, submit Plugin Hub PR

---

## Verification

```python
# Quick check script:
import json
with open("src/main/resources/tracked_item_names.json", encoding='utf-8') as f:
    data = json.load(f)
for name in data["entityToCards"]:
    if '\ufffd' in name:
        print(f"Still broken: {name!r}")
```

If it prints nothing, the fix is complete.

---

## Note

Fix this as part of the catalog auto-regeneration work (opportunity 04) since you'll be touching `generate_tracked_monsters.py` anyway. Don't do it as a standalone PR — bundle it with the next meaningful update to avoid churn.
