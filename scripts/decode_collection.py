#!/usr/bin/env python3
"""Decode an OSRS TCG collection from RuneLite backup files or properties file.

Checks three sources (most-recent wins):
  1. ~/.runelite/OSRS-TCG/profiles/*/tcg.save     — v1.0+ primary save (cloud-migrated accounts)
  2. ~/.runelite/OSRS-TCG/backups/*/<hash-files>  — pre-v1.0 backups (written on pack open / credit spend)
  3. ~/.runelite/profiles2/*.properties            — written on RuneLite exit / periodic save

The OSRS-TCG save files are written far more frequently and have fresher state.

Also writes scripts/output/all_collections.json with every RS profile that has
TCG data, keyed by displayName — so the preview tool can switch accounts
client-side without rerunning this script.

Usage:
  python scripts/decode_collection.py
  python scripts/decode_collection.py --player lottie_tcg
  python scripts/decode_collection.py --out scripts/output/my_collection.json
"""

from __future__ import annotations

import argparse
import base64
import datetime
import gzip
import hashlib
import json
import pathlib
import re
import sys

# XOR salt from TcgStateStorageEncoding.java (v2 format only)
XOR_SALT = bytes([
    0x52, 0x4c, 0x54, 0x43, 0x47,
    0x7c, 0x6f, 0x73, 0x72, 0x73,
    0x2d, 0x74, 0x63, 0x67, 0x21,
])

PREFIX_V2 = "RLTCG_v2:"  # Base64(XOR(gzip(JSON)))  — pre-v1.0
PREFIX_V3 = "RLTCG_v3:"  # Base64(gzip(JSON))        — v1.0+
KNOWN_PREFIXES = (PREFIX_V3, PREFIX_V2)

BACKUPS_DIR      = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "backups"
TCG_PROFILES_DIR = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "profiles"  # v1.0+
PROFILES_DIR     = pathlib.Path.home() / ".runelite" / "profiles2"

# Written alongside my_collection.json — all RS profiles with TCG data
ALL_COLLECTIONS_JSON = pathlib.Path(__file__).parent / "output" / "all_collections.json"


def xor_with_salt(data: bytes) -> bytes:
    return bytes(b ^ XOR_SALT[i % len(XOR_SALT)] for i, b in enumerate(data))


def decode_blob(blob: str) -> dict:
    """Decode an RLTCG_v2 or RLTCG_v3 blob and return the parsed JSON state.

    v2: Base64(XOR(gzip(JSON)))  — pre-v1.0
    v3: Base64(gzip(JSON))       — v1.0+ (XOR removed)
    """
    if blob.startswith(PREFIX_V3):
        b64 = blob[len(PREFIX_V3):]
        return json.loads(gzip.decompress(base64.b64decode(b64)))
    elif blob.startswith(PREFIX_V2):
        b64 = blob[len(PREFIX_V2):]
        compressed = base64.b64decode(b64)
        decompressed = xor_with_salt(compressed)
        return json.loads(gzip.decompress(decompressed))
    else:
        raise ValueError(f"Unknown prefix, got: {blob[:20]!r}")


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


def _try_decode_save_file(f: pathlib.Path) -> tuple[pathlib.Path, dict] | None:
    """Try to decode a save file and return (path, state), or None if it fails / has no cards."""
    try:
        text = f.read_bytes().decode("utf-8", errors="replace")
        prefix = next((p for p in KNOWN_PREFIXES if p in text), None)
        if prefix is None:
            return None
        blob = text[text.index(prefix):].strip().replace("\\:", ":")
        state = decode_blob(blob)
        has_data = (
            state.get("cardEntries")
            or state.get("cardInstances")
            or state.get("collectionState", {}).get("instances")
        )
        return (f, state) if has_data else None
    except Exception:
        return None


def find_best_backup(backups_dir: pathlib.Path) -> tuple[pathlib.Path, dict] | None:
    """Return (path, state) for the most recently modified save file, or None.

    Scans both the legacy backups/ directory tree and the v1.0+ profiles/ directory.
    """
    best_path = None
    best_mtime = 0.0
    best_state = None

    def _consider(f: pathlib.Path) -> None:
        nonlocal best_path, best_mtime, best_state
        mtime = f.stat().st_mtime
        if mtime <= best_mtime:
            return
        result = _try_decode_save_file(f)
        if result:
            best_path, best_state = result
            best_mtime = mtime

    # v1.0+ profiles dir: ~/.runelite/OSRS-TCG/profiles/<hash>/tcg.save
    if TCG_PROFILES_DIR.exists():
        for account_dir in TCG_PROFILES_DIR.iterdir():
            if not account_dir.is_dir():
                continue
            save = account_dir / "tcg.save"
            if save.is_file():
                _consider(save)

    # Legacy backups dir: ~/.runelite/OSRS-TCG/backups/<hash>/<hash-files>
    if backups_dir.exists():
        for account_dir in backups_dir.iterdir():
            if not account_dir.is_dir():
                continue
            for f in account_dir.iterdir():
                if f.is_file():
                    _consider(f)

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
            if ".state=" in line and any(p in line for p in KNOWN_PREFIXES):
                key, _, value = line.partition("=")
                value = value.replace("\\:", ":")
                results.append((props_file.name, value.strip(), mtime))
    return results


# ── Per-profile extraction (keyed by RS displayName) ────────────────────────

_STATE_KEY_RE         = re.compile(r'^osrstcg\.rsprofile\.([^.]+)\.state=(.+)$')
_NAME_KEY_RE          = re.compile(r'^rsprofile\.rsprofile\.([^.]+)\.displayName=(.+)$')
_CLOUD_ACCOUNT_KEY_RE = re.compile(r'^osrstcg\.rsprofile\.([^.]+)\.cloudAccountId=(.+)$')
_ACCOUNT_HASH_KEY_RE  = re.compile(r'^rsprofile\.rsprofile\.([^.]+)\.accountHash=(.+)$')


def _build_dir_name_to_display(profiles_dir: pathlib.Path) -> dict[str, str]:
    """Return {tcg_profiles_dir_name: displayName} for all RS profiles.

    The v1.0+ TCG backup dir name is SHA-256(str(accountHash)), matching
    ProfileKeyHasher.accountDirName() in osrs-tcg source.
    """
    mapping: dict[str, str] = {}
    for props_file in profiles_dir.glob("$rsprofile*.properties"):
        text = props_file.read_text(encoding="utf-8", errors="replace")
        pk_to_ah: dict[str, str] = {}
        pk_to_name: dict[str, str] = {}
        for line in text.splitlines():
            m = _ACCOUNT_HASH_KEY_RE.match(line)
            if m:
                pk_to_ah[m.group(1)] = m.group(2).strip()
            m = _NAME_KEY_RE.match(line)
            if m:
                pk_to_name[m.group(1)] = m.group(2).strip()
        for pk, ah in pk_to_ah.items():
            dir_name = hashlib.sha256(ah.encode("utf-8")).hexdigest()
            mapping[dir_name] = pk_to_name.get(pk, pk)
    return mapping


def find_per_profile_collections(profiles_dir: pathlib.Path) -> dict[str, dict]:
    """Return {displayName: {"cardCount": int, "ownedCards": [...], "updatedAt": str}}.

    Reads three sources:
      1. $rsprofile.properties RLTCG blobs (pre-v1.0 local state)
      2. OSRS-TCG/profiles/*/tcg.save (v1.0+ primary saves)
      3. cloudAccountId keys (v1.0+ accounts with no local state yet — shown as 0 cards)
    """
    if not profiles_dir.exists():
        return {}

    # Find the rsprofile properties file (named $rsprofile-<profileId>.properties)
    rsprofile_files = list(profiles_dir.glob("$rsprofile*.properties"))
    if not rsprofile_files:
        return {}

    hash_to_name: dict[str, str] = {}
    hash_to_state: dict[str, tuple[str, float]] = {}  # profile_key → (blob, mtime)
    hash_to_cloud: set[str] = set()   # profile_keys with a cloudAccountId (v1.0+)

    for props_file in rsprofile_files:
        mtime = props_file.stat().st_mtime
        text = props_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            m = _NAME_KEY_RE.match(line)
            if m:
                hash_to_name[m.group(1)] = m.group(2).strip()
                continue
            m = _STATE_KEY_RE.match(line)
            if m:
                blob = m.group(2).replace("\\:", ":").strip()
                hash_to_state[m.group(1)] = (blob, mtime)
                continue
            m = _CLOUD_ACCOUNT_KEY_RE.match(line)
            if m:
                hash_to_cloud.add(m.group(1))

    result: dict[str, dict] = {}

    # Pre-build a map of display_name → tcg.save mtime from TCG_PROFILES_DIR.
    # The .properties mtime is updated by RuneLite on every plugin save (XP tracker,
    # quest helper, etc.) so it's not a reliable "last TCG activity" timestamp.
    # The tcg.save mtime is written only on logout/shutdown — use it when available.
    name_to_save_mtime: dict[str, float] = {}
    if TCG_PROFILES_DIR.exists():
        dir_to_name_pre = _build_dir_name_to_display(profiles_dir)
        for _acct_dir in TCG_PROFILES_DIR.iterdir():
            if not _acct_dir.is_dir():
                continue
            _save = _acct_dir / "tcg.save"
            if _save.is_file():
                _dname = dir_to_name_pre.get(_acct_dir.name, _acct_dir.name)
                name_to_save_mtime[_dname] = _save.stat().st_mtime

    # Source 1: decode local state blobs from profiles2 properties
    for profile_hash, (blob, mtime) in hash_to_state.items():
        display_name = hash_to_name.get(profile_hash, profile_hash)
        try:
            state = decode_blob(blob)
            names, instance_count = extract_owned_names(state)
            if not names:
                continue  # skip empty local state — cloud entry (if any) will cover it
            credits = state.get("credits", 0)
            # Prefer tcg.save mtime (TCG-specific) over .properties mtime (updated by all plugins)
            best_mtime = name_to_save_mtime.get(display_name, mtime)
            updated = datetime.datetime.fromtimestamp(best_mtime).isoformat(timespec="seconds")
            result[display_name] = {
                "cardCount":  len(names),
                "ownedCards": names,
                "credits":    credits,
                "updatedAt":  updated,
            }
        except Exception as e:
            print(f"  [{display_name}] decode failed — {e}")

    # Source 2: v1.0+ TCG profiles dir — OSRS-TCG/profiles/<hash>/tcg.save
    if TCG_PROFILES_DIR.exists():
        dir_to_name = _build_dir_name_to_display(profiles_dir)
        for account_dir in TCG_PROFILES_DIR.iterdir():
            if not account_dir.is_dir():
                continue
            save_file = account_dir / "tcg.save"
            if not save_file.is_file():
                continue
            display_name = dir_to_name.get(account_dir.name, account_dir.name)
            if display_name in result:
                continue  # cards already decoded from profiles2 blob; updatedAt already corrected above
            result_entry = _try_decode_save_file(save_file)
            if result_entry:
                _, state = result_entry
                names, _ = extract_owned_names(state)
                credits = state.get("credits", 0)
                mtime = save_file.stat().st_mtime
                updated = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                result[display_name] = {
                    "cardCount":  len(names),
                    "ownedCards": names,
                    "credits":    credits,
                    "updatedAt":  updated,
                }
            else:
                # Save exists but has no cards — still include so account appears in dropdown
                mtime = save_file.stat().st_mtime
                updated = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                result[display_name] = {
                    "cardCount":  0,
                    "ownedCards": [],
                    "credits":    0,
                    "updatedAt":  updated,
                }

    # Source 3: cloud-only accounts with no local save at all (0 cards placeholder)
    for profile_hash in hash_to_cloud:
        display_name = hash_to_name.get(profile_hash, profile_hash)
        if display_name not in result:
            print(f"  [{display_name}] cloud-managed account — no local save yet (0 cards shown)")
            result[display_name] = {
                "cardCount":  0,
                "ownedCards": [],
                "credits":    0,
                "updatedAt":  "",
            }

    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="scripts/output/my_collection.json",
                   help="Output JSON path (default: scripts/output/my_collection.json)")
    p.add_argument("--player", default=None,
                   help="RS display name to write to --out (case-insensitive). "
                        "If omitted, the best available source is used.")
    args = p.parse_args()

    # ── Always extract per-profile data and write all_collections.json ───────
    per_profile = find_per_profile_collections(PROFILES_DIR)
    if per_profile:
        ALL_COLLECTIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
        ALL_COLLECTIONS_JSON.write_text(
            json.dumps({"profiles": per_profile,
                        "updatedAt": datetime.datetime.now().isoformat(timespec="seconds")},
                       indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(per_profile)} profile(s) → {ALL_COLLECTIONS_JSON}")
        for name, d in sorted(per_profile.items()):
            print(f"  {name}: {d['cardCount']} cards, {d['credits']:,} credits")

    # ── If --player specified, use that profile for --out ────────────────────
    if args.player:
        player_lower = args.player.lower()
        match = next(
            (d for name, d in per_profile.items() if name.lower() == player_lower),
            None,
        )
        if match:
            out_path = pathlib.Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            result = {"cardCount": match["cardCount"], "ownedCards": match["ownedCards"]}
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
            print(f"\nWrote {match['cardCount']} cards for '{args.player}' → {out_path}")
            return 0
        else:
            print(f"WARNING: player '{args.player}' not found in profiles2. "
                  f"Known: {', '.join(per_profile.keys()) or '(none)'}. Falling back to best source.")

    # ── Source 1: OSRS-TCG backup files (preferred — most up-to-date) ────────
    backup_result = find_best_backup(BACKUPS_DIR)

    # ── Source 2: RuneLite profiles2 .properties ──────────────────────────────
    profile_blobs = find_state_blobs_from_profiles(PROFILES_DIR)

    if not backup_result and not profile_blobs:
        print("ERROR: No RLTCG state found in backup files or profiles2.")
        return 1

    all_names: set[str] = set()

    # Decode backup (if found)
    backup_names: set[str] = set()
    if backup_result:
        path, state = backup_result
        names, instance_count = extract_owned_names(state)
        credits = state.get("credits", 0)
        unique = len(names)
        mt = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        print(f"\nOSRS-TCG backup  ({mt}): {unique} unique, {instance_count - unique} dupes/foils, {credits:,} credits")
        backup_names.update(names)

    # Decode profiles2
    profile_names: set[str] = set()
    for source, blob, mtime in profile_blobs:
        try:
            state = decode_blob(blob)
            names, instance_count = extract_owned_names(state)
            credits = state.get("credits", 0)
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
