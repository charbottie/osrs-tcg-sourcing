# 04 — Auto-Regenerate Catalogs via CI

**Status**: Quick win — no dependency on external parties.  
**Repo**: `Felmeme/bronzeman-tcg`  
**Effort**: Small (1 session)  
**Dependencies**: None  

---

## Problem

When Az ships a Card.json update (new cards, renamed cards, category changes), Felmeme must:
1. Manually notice the update
2. Download the new Card.json from `osrs-tcg.xyz/catalog/Card.json`
3. Run `python scripts/generate_tracked_monsters.py <path-to-Card.json>`
4. Commit the updated snapshot JSONs
5. Push + submit Plugin Hub PR

This is error-prone and creates drift between Az's catalog and Bronzeman's snapshots. New cards won't be restrictable until Felmeme manually runs the regeneration.

Per Bronzeman CLAUDE.md: *"If its Card.json changes: regenerate both snapshot resources with `python scripts/generate_tracked_monsters.py`"*

---

## What We're Building

A GitHub Actions workflow that:
1. Runs on a schedule (e.g. daily at 06:00 UTC)
2. Fetches the live `osrs-tcg.xyz/catalog/Card.json`
3. Compares it against the repo's `research/card-catalog.json` snapshot
4. If changed: runs `generate_tracked_monsters.py`, opens a PR with the updated snapshots
5. Comments on the PR with a diff summary (how many cards added/removed/changed)

---

## Workflow Design

### `.github/workflows/catalog-sync.yml`

```yaml
name: Sync TCG catalog

on:
  schedule:
    - cron: '0 6 * * *'   # daily at 06:00 UTC
  workflow_dispatch:        # allow manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Fetch live Card.json
        run: |
          curl -s "https://osrs-tcg.xyz/catalog/Card.json" -o /tmp/Card_live.json
          echo "Live card count: $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' /tmp/Card_live.json)"

      - name: Compare with snapshot
        id: diff
        run: |
          python3 scripts/compare_catalogs.py \
            research/card-catalog.json /tmp/Card_live.json > /tmp/diff_summary.txt
          cat /tmp/diff_summary.txt
          if [ -s /tmp/diff_summary.txt ]; then
            echo "changed=true" >> $GITHUB_OUTPUT
          else
            echo "changed=false" >> $GITHUB_OUTPUT
          fi

      - name: Regenerate snapshots
        if: steps.diff.outputs.changed == 'true'
        run: |
          cp /tmp/Card_live.json research/card-catalog.json
          python3 scripts/generate_tracked_monsters.py research/card-catalog.json

      - name: Open PR
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: sync TCG catalog snapshot"
          title: "Catalog sync: $(date +%Y-%m-%d)"
          body-path: /tmp/diff_summary.txt
          branch: catalog-sync-auto
          labels: catalog-sync
```

### `scripts/compare_catalogs.py`

```python
"""Print a human-readable diff summary between two Card.json files."""
import json, sys

old = {c["name"]: c for c in json.load(open(sys.argv[1]))}
new = {c["name"]: c for c in json.load(open(sys.argv[2]))}

added   = sorted(set(new) - set(old))
removed = sorted(set(old) - set(new))
changed = sorted(
    n for n in set(old) & set(new)
    if old[n].get("category") != new[n].get("category")
)

if not added and not removed and not changed:
    sys.exit(0)

print(f"## Catalog diff")
print(f"- Added: {len(added)} cards")
print(f"- Removed: {len(removed)} cards")  
print(f"- Category changed: {len(changed)} cards")
print()
for name in added[:20]:
    print(f"+ {name} ({', '.join(new[name].get('category', []))})")
for name in removed[:20]:
    print(f"- {name}")
for name in changed[:20]:
    print(f"~ {name}: {old[name].get('category')} → {new[name].get('category')}")
if len(added) > 20 or len(removed) > 20:
    print(f"... and more (truncated for PR body)")
```

---

## Update to `generate_tracked_monsters.py`

The existing script needs to be runnable without arguments (using the repo's `research/card-catalog.json` by default) and write output to `src/main/resources/`:

```python
# Current: python generate_tracked_monsters.py <path>
# New: python generate_tracked_monsters.py [path]  (default: research/card-catalog.json)
```

Also fix the U+FFFD encoding defect (see opportunity 06) while touching this file.

---

## Alternative: Don't Auto-Commit — Just Alert

If Felmeme prefers to review regenerated snapshots before they're committed, the workflow can instead:
- Detect catalog changes
- Open a GitHub issue tagging Felmeme: "Card.json changed — run `generate_tracked_monsters.py`"
- No automatic PR

This is lower-trust but gives more human oversight. Given the plugin has real users, Felmeme may prefer this for reviewing changes before they ship.

---

## Effort Breakdown

| Task | Effort |
|------|--------|
| `compare_catalogs.py` | 30 min |
| `.github/workflows/catalog-sync.yml` | 30 min |
| Update `generate_tracked_monsters.py` for default args + CI | 30 min |
| Fix encoding defect while here | 30 min |
| Test workflow manually via `workflow_dispatch` | 30 min |

---

## Open Questions

1. Auto-PR or just alert? Felmeme's preference.
2. Should the PR auto-merge if only new cards were added (no removals or category changes)? Or always require manual review?
3. Daily check appropriate? If Az ships infrequently, weekly might be fine.
4. Should this also check for changes in the encoding format (RLTCG_v2 prefix) in case Az updates the storage scheme?
