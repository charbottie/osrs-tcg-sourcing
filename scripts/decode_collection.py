#!/usr/bin/env python3
"""Decode an OSRS TCG collection from RuneLite backup files or properties file.

Checks two sources (most-recent wins):
  1. ~/.runelite/OSRS-TCG/backups/*/<hash-files>  — written on every pack open / credit spend
  2. ~/.runelite/profiles2/*.properties            — written on RuneLite exit / periodic save

The backup files are written far more frequently and have fresher state.

Usage:
  python scripts/decode_collection.py
  python scripts/decode_collection.py --out scripts/output/my_collection.json
"""

from __future__ import annotations

import argparse
import base64
import datetime
import gzip
import json
import pathlib
import sys

# XOR salt from TcgStateStorageEncoding.java
XOR_SALT = bytes([
    0x52, 0x4c, 0x54, 0x43, 0x47,
    0x7c, 0x6f, 0x73, 0x72, 0x73,
    0x2d, 0x74, 0x63, 0x67, 0x21,
])

PREFIX = "RLTCG_v2:"

BACKUPS_DIR  = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "backups"
PROFILES_DIR = pathlib.Path.home() / ".runelite" / "profiles2"


def xor_with_salt(data: bytes) -> bytes:
    return bytes(b ^ XOR_SALT[i % len(XOR_SALT)] for i, b in enumerate(data))


def decode_blob(blob: str) -> dict:
    """Decode an RLTCG_v2 blob and return the parsed JSON state."""
    if not blob.startswith(PREFIX):
        raise ValueError(f"Expected {PREFIX!r} prefix, got: {blob[:20]!r}")
    b64 = blob[len(PREFIX):]
    compressed = base64.b64decode(b64)
    decompressed = xor_with_salt(compressed)
    return json.loads(gzip.decompress(decompressed))


def extract_owned_names(state: dict) -> tuple[list[str], int]:
    """Return (unique_names_sorted, total_instance_count).

    Handles two schema shapes:
      - schema ≤5: cardInstances / collectionState.instances — list of {cardName, ...}
      - schema 6+: cardEntries — list of {cardName, variants: [...]}
    """
    # Schema 6+: cardEntries with per-card variants list
    entries = state.get("cardEntries", [])
    if entries:
        names = sorted({e["cardName"] for e in entries if "cardName" in e})
        total = sum(len(e.get("variants", [])) for e in entries)
        return names, total

    # Schema ≤5: flat instances list
    instances = state.get("cardInstances", [])
    if not instances:
        instances = state.get("collectionState", {}).get("instances", [])
    names = sorted({inst["cardName"] for inst in instances if "cardName" in inst})
    return names, len(instances)


def find_best_backup(backups_dir: pathlib.Path) -> tuple[pathlib.Path, dict] | None:
    """Return (path, state) for the most recently modified backup file, or None."""
    if not backups_dir.exists():
        return None

    best_path = None
    best_mtime = 0.0
    best_state = None

    for account_dir in backups_dir.iterdir():
        if not account_dir.is_dir():
            continue
        for f in account_dir.iterdir():
            if not f.is_file():
                continue
            mtime = f.stat().st_mtime
            if mtime <= best_mtime:
                continue
            try:
                raw = f.read_bytes()
                text = raw.decode("utf-8", errors="replace")
                if PREFIX not in text:
                    continue
                idx = text.index(PREFIX)
                blob = text[idx:].strip().replace("\\:", ":")
                state = decode_blob(blob)
                has_data = (
                    state.get("cardEntries")
                    or state.get("cardInstances")
                    or state.get("collectionState", {}).get("instances")
                )
                if not has_data:
                    continue  # skip empty states (e.g. the 'default' folder)
                best_path = f
                best_mtime = mtime
                best_state = state
            except Exception:
                continue

    return (best_path, best_state) if best_path else None


def find_state_blobs_from_profiles(profiles_dir: pathlib.Path) -> list[tuple[str, str, float]]:
    """Scan .properties files; return (label, blob, mtime) for .state= entries."""
    results = []
    if not profiles_dir.exists():
        return results
    for props_file in profiles_dir.glob("*.properties"):
        mtime = props_file.stat().st_mtime
        text = props_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if ".state=" in line and "RLTCG_v2" in line:
                key, _, value = line.partition("=")
                value = value.replace("\\:", ":")
                results.append((props_file.name, value.strip(), mtime))
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="scripts/output/my_collection.json",
                   help="Output JSON path (default: scripts/output/my_collection.json)")
    args = p.parse_args()

    # ── Source 1: OSRS-TCG backup files (preferred — most up-to-date) ──────
    backup_result = find_best_backup(BACKUPS_DIR)

    # ── Source 2: RuneLite profiles2 .properties ────────────────────────────
    profile_blobs = find_state_blobs_from_profiles(PROFILES_DIR)

    if not backup_result and not profile_blobs:
        print("ERROR: No RLTCG_v2 state found in backup files or profiles2.")
        return 1

    all_names: set[str] = set()

    # Decode backup (if found)
    backup_names: set[str] = set()
    if backup_result:
        path, state = backup_result
        names, instance_count = extract_owned_names(state)
        credits = state.get("credits", 0)
        schema = state.get("schemaVersion", "?")
        unique = len(names)
        mt = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        print(f"OSRS-TCG backup  ({mt}): {unique} unique, {instance_count - unique} dupes/foils, {credits:,} credits")
        backup_names.update(names)

    # Decode profiles2
    profile_names: set[str] = set()
    for source, blob, mtime in profile_blobs:
        try:
            state = decode_blob(blob)
            names, instance_count = extract_owned_names(state)
            credits = state.get("credits", 0)
            schema = state.get("schemaVersion", "?")
            unique = len(names)
            mt = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
            print(f"RuneLite profile ({mt}): {unique} unique, {instance_count - unique} dupes/foils, {credits:,} credits")
            profile_names.update(names)
        except Exception as e:
            print(f"  {source}: FAILED — {e}")

    # Prefer whichever source has more cards — the OSRS-TCG backup is written on
    # every pack opening so it reflects the freshest state even if the profiles
    # file has a newer mtime (RuneLite can re-write it with stale data).
    if len(backup_names) >= len(profile_names):
        all_names = backup_names
        print(f"\nUsing: OSRS-TCG backup ({len(all_names)} unique cards)")
    else:
        all_names = profile_names
        print(f"\nUsing: RuneLite profile ({len(all_names)} unique cards — backup had fewer)")

    if not all_names:
        print("No cards found.")
        return 1

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "cardCount": len(all_names),
        "ownedCards": sorted(all_names),
    }
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nWrote {len(all_names)} unique owned card names → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
