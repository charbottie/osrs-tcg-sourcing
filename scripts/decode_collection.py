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

Cloud-managed (v1.0+) accounts: when OSRS-TCG/profiles/<hash>/cloud-session.json exists, the
live card list and pull timestamps are fetched from api.osrs-tcg.net with the stored token
(cached in scripts/cache/cloud_cards_<hash>.json for 30 s, and reused while rate-limited).
Card names are normalised through research/card-catalog-live.json (see _identity_names).

Outputs:
  --out (default scripts/output/my_collection.json)
      {cardCount, ownedCards: [...], cardTimestamps?, cardFirstTimestamps?}
  scripts/output/all_collections.json
      {profiles: {displayName: {cardCount, ownedCards, credits, updatedAt, cardTimestamps?, ...}},
       updatedAt}

Run by server.py's /api/collection/refresh and /api/accounts/list.

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
import urllib.error
import urllib.parse
import urllib.request

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


# Card catalog snapshot: resolves the plugin's identity names ("npc:6616") to card names
CATALOG_JSON = pathlib.Path(__file__).parent.parent / "research" / "card-catalog-live.json"
_ID_NAMES: dict[str, str] | None = None


def _identity_names() -> dict[str, str]:
    """{"npc:<id>" / "item:<id>": card name} for every card id and version id in the catalog.

    The OSRS TCG plugin names an NPC card "npc:<id>" when its name clashes with an item card
    (Manta ray, Scorpia's offspring); cards pulled then keep that name in the save/cloud even
    after the catalog renames the card ("Scorpia's offspring (monster)")."""
    global _ID_NAMES
    if _ID_NAMES is None:
        _ID_NAMES = {}
        try:
            cat = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cat = {}
        for kind, prefix in (("items", "item"), ("npcs", "npc")):
            for e in cat.get(kind, []):
                _ID_NAMES.setdefault(f"{prefix}:{e['id']}", e["name"])
            for e in cat.get(kind, []):
                for v in (e.get("tcg") or {}).get("variants") or []:
                    if "id" in v:
                        _ID_NAMES.setdefault(f"{prefix}:{v['id']}", e["name"])
    return _ID_NAMES


def normalize_profile(d: dict) -> dict:
    """Replace identity names in a profile's ownedCards / timestamp maps with card names."""
    ids = _identity_names()
    fix = lambda n: ids.get(n, n)
    if not any(n in ids for n in d.get("ownedCards", [])):
        return d
    d["ownedCards"] = sorted({fix(n) for n in d.get("ownedCards", [])})
    d["cardCount"] = len(d["ownedCards"])
    for key, pick in (("cardTimestamps", max), ("cardFirstTimestamps", min)):
        if isinstance(d.get(key), dict):
            out: dict = {}
            for n, ts in d[key].items():
                n = fix(n)
                out[n] = pick(out[n], ts) if n in out else ts
            d[key] = out
    return d


def xor_with_salt(data: bytes) -> bytes:
    """XOR *data* with the repeating XOR_SALT (the v2 obfuscation step; self-inverse)."""
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
        """Keep *f* as the best candidate if it is newer than the current best and decodes with cards."""
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


# ── Cloud API fetch ──────────────────────────────────────────────────────────

_CLOUD_API_BASE = "https://api.osrs-tcg.net"


def _fetch_cloud_cards(account_dir: pathlib.Path) -> tuple[list[str], int, dict[str, int], dict[str, int]] | None:
    """Fetch card collection from the OSRS TCG cloud API.

    Reads cloud-session.json from the TCG profiles directory for this account,
    then paginates through /api/v1/me/cards using the stored JWT access token.

    Returns (sorted_unique_names, total_instance_count, last_timestamps, first_timestamps),
    or None if unavailable.
    last_timestamps maps card name → most recent pulledAt (ms epoch).
    first_timestamps maps card name → earliest pulledAt (ms epoch).
    """
    cloud_session_file = account_dir / "cloud-session.json"
    if not cloud_session_file.is_file():
        return None

    try:
        sess = json.loads(cloud_session_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    token = sess.get("accessToken")
    if not token:
        return None

    # The cloud API rate-limits (HTTP 429). Cache every good fetch per account: reuse it for 30 s,
    # and fall back to it (not the older local tcg.save) when the API refuses.
    cache_file = pathlib.Path(__file__).parent / "cache" / f"cloud_cards_{account_dir.name[:16]}.json"
    cached = None
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else None
    except Exception:
        cached = None
    if cached and datetime.datetime.now().timestamp() - cached.get("fetchedAt", 0) < 30:
        all_cards = cached["cards"]
        print(f"  [cloud API] using cached cards from {int(datetime.datetime.now().timestamp() - cached['fetchedAt'])} s ago")
        return _cloud_result(all_cards)
    if cached and datetime.datetime.now().timestamp() < cached.get("backoffUntil", 0):
        print("  [cloud API] rate-limited earlier — using the last good cloud fetch")
        return _cloud_result(cached["cards"])

    all_cards: list[dict] = []
    cursor: str | None = None

    try:
        while True:
            url = f"{_CLOUD_API_BASE}/api/v1/me/cards"
            if cursor:
                url += f"?cursor={urllib.parse.quote(cursor)}"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {token}",
                "User-Agent":    "osrs-tcg-preview/1.0",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            all_cards.extend(data.get("cards", []))
            if not data.get("hasMore"):
                break
            cursor = data.get("nextCursor")
    except Exception as exc:
        print(f"  [cloud API] fetch failed — {exc}")
        if cached:
            wait = 60
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                try: wait = max(30, int(exc.headers.get("Retry-After") or 60))
                except Exception: pass
            cached["backoffUntil"] = datetime.datetime.now().timestamp() + wait
            try: cache_file.write_text(json.dumps(cached), encoding="utf-8")
            except Exception: pass
            print(f"  [cloud API] using the last good cloud fetch ({len(cached['cards'])} card instances); retry in {wait} s")
            return _cloud_result(cached["cards"])
        return None

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"fetchedAt": datetime.datetime.now().timestamp(), "cards": all_cards}), encoding="utf-8")
    except Exception:
        pass
    return _cloud_result(all_cards)


def _cloud_result(all_cards: list[dict]):
    """Summarise cloud card instances: (sorted names, instance count, last pulledAt, first pulledAt)."""
    names = sorted({c["cardName"] for c in all_cards if "cardName" in c})

    # Per-card first/last pulledAt (ms epoch) across all instances.
    last_timestamps:  dict[str, int] = {}
    first_timestamps: dict[str, int] = {}
    for c in all_cards:
        name = c.get("cardName")
        ts   = c.get("pulledAt")
        if name and ts:
            if name not in last_timestamps or ts > last_timestamps[name]:
                last_timestamps[name] = ts
            if name not in first_timestamps or ts < first_timestamps[name]:
                first_timestamps[name] = ts

    return names, len(all_cards), last_timestamps, first_timestamps


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
                entry: dict = {
                    "cardCount":  len(names),
                    "ownedCards": names,
                    "credits":    credits,
                    "updatedAt":  updated,
                }
                # Cloud accounts cache data locally but may be stale for current-session cards
                # (tcg.save is written on logout; cloud API always reflects live state).
                # Use cloud names + timestamps if available so newly-pulled cards are included.
                cloud_ts_result = _fetch_cloud_cards(account_dir)
                if cloud_ts_result:
                    cloud_names, _, timestamps, first_timestamps = cloud_ts_result
                    if cloud_names:
                        entry["cardCount"] = len(cloud_names)
                        entry["ownedCards"] = cloud_names
                        print(f"  [{display_name}] cloud names used ({len(cloud_names)} cards, local save had {len(names)})")
                    if timestamps:
                        entry["cardTimestamps"] = timestamps
                        entry["cardFirstTimestamps"] = first_timestamps
                        print(f"  [{display_name}] cloud timestamps fetched ({len(timestamps)} cards)")
                result[display_name] = entry
            else:
                # Save exists but has no local cards — this account is cloud-managed.
                # Try fetching the collection from the OSRS TCG cloud API.
                cloud_result = _fetch_cloud_cards(account_dir)
                mtime = save_file.stat().st_mtime
                updated = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                if cloud_result:
                    names, instance_count, timestamps, first_timestamps = cloud_result
                    print(f"  [{display_name}] cloud account — {len(names)} cards via API")
                    result[display_name] = {
                        "cardCount":           len(names),
                        "ownedCards":          names,
                        "credits":             0,
                        "updatedAt":           updated,
                        "cardTimestamps":      timestamps,
                        "cardFirstTimestamps": first_timestamps,
                    }
                else:
                    # Cloud fetch unavailable — show placeholder so account appears in dropdown
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
    """Write all_collections.json, then --out for --player (or the best single source). Returns exit code.

    Without --player (or if it isn't found) --out comes from the legacy path: the newest
    OSRS-TCG save file vs. the largest single profiles2 .properties blob, whichever has more
    cards. Profiles are never merged; pass --player to pick a specific account.
    """
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
    for d in per_profile.values():
        normalize_profile(d)
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
            result: dict = {"cardCount": match["cardCount"], "ownedCards": match["ownedCards"]}
            if match.get("cardTimestamps"):
                result["cardTimestamps"] = match["cardTimestamps"]
            if match.get("cardFirstTimestamps"):
                result["cardFirstTimestamps"] = match["cardFirstTimestamps"]
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

    # Decode profiles2: keep the single profile with the most cards (a union would merge
    # every account's cards into one collection)
    profile_names: set[str] = set()
    for source, blob, mtime in profile_blobs:
        try:
            state = decode_blob(blob)
            names, instance_count = extract_owned_names(state)
            credits = state.get("credits", 0)
            unique = len(names)
            mt = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
            print(f"RuneLite profile ({mt}): {unique} unique, {instance_count - unique} dupes/foils, {credits:,} credits")
            if len(set(names)) > len(profile_names):
                profile_names = set(names)
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
    result = normalize_profile({
        "cardCount":  len(all_names),
        "ownedCards": sorted(all_names),
    })
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nWrote {len(all_names)} unique owned card names → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
