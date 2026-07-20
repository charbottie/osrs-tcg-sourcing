#!/usr/bin/env python3
"""Decode an OSRS TCG collection from a RuneLite properties file.

Reads the RLTCG_v2 encoded state blob, decodes it using the same
XOR+gzip+base64 scheme as TcgStateStorageEncoding.java, and writes
a plain JSON file listing all owned card names.

Usage:
  python scripts/decode_collection.py
  python scripts/decode_collection.py --out scripts/output/my_collection.json
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import pathlib
import re
import sys

# XOR salt from TcgStateStorageEncoding.java
XOR_SALT = bytes([
    0x52, 0x4c, 0x54, 0x43, 0x47,
    0x7c, 0x6f, 0x73, 0x72, 0x73,
    0x2d, 0x74, 0x63, 0x67, 0x21,
])

PREFIX = "RLTCG_v2:"

# Default RuneLite profiles directory (Mac/Linux)
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
    json_bytes = gzip.decompress(decompressed)
    return json.loads(json_bytes)


def find_state_blobs(profiles_dir: pathlib.Path) -> list[tuple[str, str]]:
    """Scan all .properties files and return (source_file, blob) pairs."""
    results = []
    for props_file in profiles_dir.glob("*.properties"):
        text = props_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if ".state=" in line and "RLTCG_v2" in line:
                key, _, value = line.partition("=")
                # Properties files escape colons with backslash
                value = value.replace("\\:", ":")
                results.append((str(props_file.name), value.strip()))
    return results


def extract_owned_names(state: dict) -> list[str]:
    """Extract all owned card names (foil + normal) from a decoded state."""
    # Schema version 3: top-level cardInstances list
    instances = state.get("cardInstances", [])
    # Older schema: collectionState.instances
    if not instances:
        instances = state.get("collectionState", {}).get("instances", [])
    return sorted({inst["cardName"] for inst in instances if "cardName" in inst})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profiles-dir", default=str(PROFILES_DIR),
                   help=f"RuneLite profiles2 directory (default: {PROFILES_DIR})")
    p.add_argument("--out", default="scripts/output/my_collection.json",
                   help="Output JSON path (default: scripts/output/my_collection.json)")
    args = p.parse_args()

    profiles_dir = pathlib.Path(args.profiles_dir)
    if not profiles_dir.exists():
        print(f"ERROR: profiles dir not found: {profiles_dir}")
        return 1

    blobs = find_state_blobs(profiles_dir)
    if not blobs:
        print(f"No RLTCG_v2 state found in {profiles_dir}")
        return 1

    print(f"Found {len(blobs)} state blob(s):")
    all_names: set[str] = set()

    for source, blob in blobs:
        try:
            state = decode_blob(blob)
            names = extract_owned_names(state)
            credits = state.get("credits", 0)
            schema = state.get("schemaVersion", "?")
            print(f"  {source}: {len(names)} cards, {credits:,} credits (schema v{schema})")
            all_names.update(names)
        except Exception as e:
            print(f"  {source}: FAILED — {e}")

    if not all_names:
        print("No cards found across all profiles.")
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
