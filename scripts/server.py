#!/usr/bin/env python3
"""Dev server for the Bronzeman Planner (scripts/preview.html).

Serves static files from scripts/ AND exposes API endpoints for live
data refresh — so the browser can trigger collection decodes and
re-generation without leaving the page. Also proxies card art and wiki
images through a disk cache, since the browser can't load them directly
(the wiki's bot check blocks uncached <img> requests).

Usage:
  python3 scripts/server.py              # default port 8765
  python3 scripts/server.py --port 9000
  then open http://localhost:8765/preview.html

Reads:  scripts/output/*.json and other static files (served as-is),
        ~/.runelite/OSRS-TCG/profiles|backups, ~/.runelite/profiles2/*.properties,
        ~/.runelite/screenshots/<player>/Quests/
Writes: scripts/output/my_collection.json + all_collections.json (via decode_collection.py),
        scripts/output/generate.log, scripts/cache/wiki_img/, scripts/cache/tcg_img/,
        scripts/cache/runelite_item_names.json
Network: osrs-tcg.net (pack catalog, card art, cloud revision), the OSRS hiscores,
        wiki images (via /wikiimg/), static.runelite.net (sprite fallback).

Endpoints (API routes accept GET or POST unless noted):
  GET  /<file>                      → static file from scripts/ (no-cache, so edits show on reload)
  GET  /images/<path>               → card art / pack images from osrs-tcg.net, cached on disk
  GET  /wikiimg/<path>              → oldschool.runescape.wiki/images/<path>, cached on disk
  /api/collection/refresh[?player=] → run decode_collection.py, return the collection JSON
  /api/collection/status            → card count + last-updated timestamp of my_collection.json
  /api/collection/source-mtime      → newest mtime of any RuneLite TCG save file (cheap change check)
  /api/collection/revision?player=  → cloud account's current revision/stateHash (cached 45s)
  /api/accounts/list                → every TCG account found locally, with card counts + credits
  /api/generate/run                 → start generate_sources.py --skip-quests in the background
  /api/generate/status              → is a generate job running? elapsed / result
  /api/generate/log                 → the generate job's log text
  /api/hiscores?player=             → skill levels from the OSRS hiscores (lite CSV)
  /api/quests/completed[?player=]   → quest names from RuneLite quest-completion screenshots
  /api/packs                        → TCG pack catalog from api.osrs-tcg.net (cached 24h)
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

_SCRIPTS_DIR = pathlib.Path(__file__).parent
_OUT_DIR     = _SCRIPTS_DIR / "output"
_COLLECTION  = _OUT_DIR / "my_collection.json"
_GENERATE_LOG = _OUT_DIR / "generate.log"
_WIKI_IMG_DIR = _SCRIPTS_DIR / "cache" / "wiki_img"   # wiki images (skill/quest/clue icons, item versions)
_TCG_IMG_DIR  = _SCRIPTS_DIR / "cache" / "tcg_img"    # card art + pack images from osrs-tcg.net
_IMG_LOCKS: dict = {}                                 # cache path → lock, so one image is fetched once
_IMG_LOCKS_GUARD = threading.Lock()


def _fetch_image_cached(cache: pathlib.Path, urls: list[str], tries: int = 3) -> bytes | None:
    """Image bytes from the disk cache, else the first URL that answers (with retries).

    Good images are kept forever; failures aren't cached, so the next request tries again.
    """
    if cache.exists():
        return cache.read_bytes()
    with _IMG_LOCKS_GUARD:
        lock = _IMG_LOCKS.setdefault(str(cache), threading.Lock())
    with lock:
        if cache.exists():
            return cache.read_bytes()
        for url in urls:
            for attempt in range(tries):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-preview/1.0 (local planner)"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = r.read()
                    if data:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        tmp = cache.with_suffix(".part")
                        tmp.write_bytes(data)
                        tmp.replace(cache)
                        return data
                except urllib.error.HTTPError as e:
                    if e.code in (403, 404, 502):   # bot check / missing: retrying won't help, next source
                        break
                    time.sleep(0.6 * (attempt + 1))
                except Exception:
                    time.sleep(0.6 * (attempt + 1))
    return None


_RL_NAMES_FILE = _SCRIPTS_DIR / "cache" / "runelite_item_names.json"
_rl_ids: dict | None = None   # item name (lowercase) → RuneLite item id


def _runelite_icon_url(file_name: str) -> str | None:
    """RuneLite's sprite for the item a wiki file is named after ("Bronze_bar.png" → item 2349)."""
    global _rl_ids
    if _rl_ids is None:
        try:
            if not _RL_NAMES_FILE.exists():
                req = urllib.request.Request("https://static.runelite.net/cache/item/names.json",
                                             headers={"User-Agent": "osrs-tcg-preview/1.0 (local planner)"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    _RL_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
                    _RL_NAMES_FILE.write_bytes(r.read())
            ids: dict = {}
            for k, v in json.loads(_RL_NAMES_FILE.read_text()).items():
                ids.setdefault(v.lower(), int(k))   # lowest id = the base item
            _rl_ids = ids
        except Exception:
            return None   # try again next time
    name = re.sub(r"(_detail)?\.\w+$", "", file_name).replace("_", " ").strip().lower()
    for n in (name, re.sub(r"\s*\(\d+\)$", "", name)):
        if n in _rl_ids:
            return f"https://static.runelite.net/cache/item/icon/{_rl_ids[n]}.png"
    return None


def _wiki_image_urls(rel: str) -> list[str]:
    """A wiki image path → URLs to try: as given, the original file for a thumbnail, then the
    RuneLite sprite of the same item (the wiki's bot check refuses uncached images)."""
    base = "https://oldschool.runescape.wiki/images/"
    m = re.match(r"^thumb/(.+?)/\d+px-", rel)
    urls = [base + urllib.parse.quote(rel)] + ([base + urllib.parse.quote(m.group(1))] if m else [])
    rl = _runelite_icon_url((m.group(1) if m else rel).rsplit("/", 1)[-1])
    return urls + ([rl] if rl else [])


def _wiki_cache_path(rel: str) -> pathlib.Path:
    """Disk-cache path for a wiki image path (SHA-1 of the path, so any characters are safe)."""
    return _WIKI_IMG_DIR / hashlib.sha1(rel.encode()).hexdigest()

# ── Pack catalog cache ───────────────────────────────────────────────────────
_PACK_CATALOG_URL = "https://api.osrs-tcg.net/api/v1/packs"
_PACK_CATALOG_TTL = 86400   # 24 hours
_pack_catalog_data: dict | None = None
_pack_catalog_ts: float = 0.0


def _get_pack_catalog() -> dict:
    """The TCG pack catalog JSON, re-fetched from the API at most once per _PACK_CATALOG_TTL.

    Raises on network errors (the caller turns that into a 502).
    """
    global _pack_catalog_data, _pack_catalog_ts
    if _pack_catalog_data is None or (time.time() - _pack_catalog_ts) > _PACK_CATALOG_TTL:
        req = urllib.request.Request(
            _PACK_CATALOG_URL,
            headers={"User-Agent": "osrs-tcg-preview/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            _pack_catalog_data = json.loads(r.read())
        _pack_catalog_ts = time.time()
    return _pack_catalog_data


# ── Background job state ────────────────────────────────────────────────────
_generate_lock   = threading.Lock()
_generate_running = False # True from the moment a run is accepted (set under _generate_lock) until it ends
_generate_proc   = None   # subprocess.Popen while running
_generate_start  = None   # time.time() when started
_generate_done   = None   # time.time() when finished
_generate_result = None   # "ok" | "error"


def _run_generate_background(extra_args: list[str]) -> None:
    """Run generate_sources.py (quests skipped) to completion, logging to generate.log.

    Blocks until the subprocess exits; meant to run on a daemon thread. Updates the
    module-level _generate_* job state that /api/generate/status reports. The caller has
    already set _generate_running (under _generate_lock); this clears it when the run ends.
    """
    global _generate_running, _generate_proc, _generate_done, _generate_result
    cmd = [
        sys.executable, str(_SCRIPTS_DIR / "generate_sources.py"),
        "--card-json", str(_SCRIPTS_DIR.parent / "research" / "card-catalog-live.json"),
        "--skip-quests",
        *extra_args,
    ]
    result = "error"
    try:
        with open(_GENERATE_LOG, "w", encoding="utf-8") as log:
            _generate_proc = subprocess.Popen(
                cmd, stdout=log, stderr=log,
                cwd=str(_SCRIPTS_DIR.parent),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        result = "ok" if _generate_proc.wait() == 0 else "error"
    finally:
        with _generate_lock:
            _generate_done    = time.time()
            _generate_result  = result
            _generate_proc    = None
            _generate_running = False


# ── Cloud account helpers ────────────────────────────────────────────────────

_PROFILES2_DIR   = pathlib.Path.home() / ".runelite" / "profiles2"
_TCG_PROFILES    = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "profiles"
_DISPLAY_NAME_RE = re.compile(r'^rsprofile\.rsprofile\.([^.]+)\.displayName=(.+)$')
_ACCOUNT_HASH_RE = re.compile(r'^rsprofile\.rsprofile\.([^.]+)\.accountHash=(.+)$')

_revision_cache: dict[str, dict] = {}         # player_lower → {at, payload, backoffUntil}
_cloud_session_cache: dict[str, dict] = {}   # player_lower → session dict (or {})


def _find_cloud_session(player: str) -> dict | None:
    """Return the cloud-session.json dict for *player*, or None if not a cloud account.

    Uses the same SHA-256(accountHash) directory-name scheme as decode_collection.py.
    Result is cached in-process (sessions don't rotate during a server run).
    """
    key = player.lower()
    if key in _cloud_session_cache:
        sess = _cloud_session_cache[key]
        return sess if sess else None

    # Build hash → displayName map from $rsprofile*.properties
    hash_to_name: dict[str, str] = {}
    for props_file in _PROFILES2_DIR.glob("$rsprofile*.properties"):
        text = props_file.read_text(encoding="utf-8", errors="replace")
        pk_ah: dict[str, str]   = {}
        pk_name: dict[str, str] = {}
        for line in text.splitlines():
            m = _ACCOUNT_HASH_RE.match(line)
            if m: pk_ah[m.group(1)] = m.group(2).strip()
            m = _DISPLAY_NAME_RE.match(line)
            if m: pk_name[m.group(1)] = m.group(2).strip()
        for pk, ah in pk_ah.items():
            dir_name = hashlib.sha256(ah.encode("utf-8")).hexdigest()
            hash_to_name[dir_name] = pk_name.get(pk, pk)

    # Scan TCG profiles dirs for matching display name
    if _TCG_PROFILES.exists():
        for acct_dir in _TCG_PROFILES.iterdir():
            if not acct_dir.is_dir():
                continue
            name = hash_to_name.get(acct_dir.name, "")
            if name.lower() != key:
                continue
            cs = acct_dir / "cloud-session.json"
            if cs.is_file():
                sess = json.loads(cs.read_text(encoding="utf-8"))
                _cloud_session_cache[key] = sess
                return sess

    _cloud_session_cache[key] = {}   # not a cloud account — cache negative result
    return None


# ── Request handler ─────────────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    """Static file server rooted at scripts/, plus the /api/, /images/ and /wikiimg/ routes."""

    def __init__(self, *args, **kwargs):
        """Serve files from scripts/ regardless of the current working directory."""
        super().__init__(*args, directory=str(_SCRIPTS_DIR), **kwargs)

    def end_headers(self):
        """Add Cache-Control: no-cache unless the handler already set a Cache-Control header."""
        # Static files (preview.html, data JSON): make the browser revalidate every load, so an
        # edited page shows up on a normal reload. Handlers that set their own Cache-Control keep it.
        if not any(h.lower().startswith(b"cache-control") for h in getattr(self, "_headers_buffer", [])):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        """Log only /api/ requests (static file and image hits are too noisy)."""
        # Suppress per-request noise; only print API calls
        if "/api/" in str(args[0] if args else ""):
            super().log_message(fmt, *args)

    def do_GET(self):
        """Route GET to the API, the image proxies, or a static file."""
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api(path)
        elif path.startswith("/images/"):
            self._proxy_tcg_image(path)
        elif path.startswith("/wikiimg/"):
            self._proxy_wiki_image(path)
        else:
            super().do_GET()

    def do_HEAD(self):
        """Route HEAD to the image proxies (headers only) or a static file."""
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/images/"):
            self._proxy_tcg_image(path)
        elif path.startswith("/wikiimg/"):
            self._proxy_wiki_image(path)
        else:
            super().do_HEAD()

    def do_POST(self):
        """Route POST to the API; anything else is 405."""
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api(path)
        else:
            self.send_error(405)

    def _handle_api(self, path: str):
        """Dispatch an /api/ path to its handler (same routes for GET and POST); 404 if unknown."""
        if path == "/api/collection/refresh":
            self._api_collection_refresh()
        elif path == "/api/collection/status":
            self._api_collection_status()
        elif path == "/api/generate/status":
            self._api_generate_status()
        elif path == "/api/generate/run":
            self._api_generate_run()
        elif path == "/api/generate/log":
            self._api_generate_log()
        elif path == "/api/hiscores":
            self._api_hiscores()
        elif path == "/api/quests/completed":
            self._api_quests_completed()
        elif path == "/api/accounts/list":
            self._api_accounts_list()
        elif path == "/api/collection/source-mtime":
            self._api_collection_source_mtime()
        elif path == "/api/collection/revision":
            self._api_collection_revision()
        elif path == "/api/packs":
            self._api_packs()
        else:
            self.send_error(404)

    # ── Collection endpoints ──────────────────────────────────────────────

    def _api_collection_refresh(self):
        """Run decode_collection.py and return the new collection.

        Optional query param: ?player=<display_name>
        If provided, decodes only that RS profile and returns its collection.
        Always regenerates all_collections.json regardless.
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        player = (qs.get("player") or [""])[0].strip()

        cmd = [sys.executable, str(_SCRIPTS_DIR / "decode_collection.py"),
               "--out", str(_COLLECTION)]
        if player:
            cmd += ["--player", player]

        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            cwd=str(_SCRIPTS_DIR.parent),
        )
        if result.returncode != 0:
            self._json_response({"error": result.stderr.strip()}, status=500)
            return
        try:
            data = json.loads(_COLLECTION.read_text(encoding="utf-8"))
            data["refreshedAt"] = datetime.now().isoformat(timespec="seconds")
            data["log"] = result.stdout.strip()
            if player:
                data["player"] = player
            self._json_response(data)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)

    def _api_collection_status(self):
        """Card count and file mtime of my_collection.json, or {"exists": False}. No decode."""
        if not _COLLECTION.exists():
            self._json_response({"exists": False})
            return
        data = json.loads(_COLLECTION.read_text(encoding="utf-8"))
        mtime = datetime.fromtimestamp(_COLLECTION.stat().st_mtime)
        self._json_response({
            "exists":    True,
            "cardCount": data.get("cardCount", 0),
            "updatedAt": mtime.isoformat(timespec="seconds"),
        })

    def _api_accounts_list(self):
        """Return all discovered TCG accounts.

        Runs decode_collection.py (no player arg) to refresh all_collections.json,
        then returns the account list with card counts + credits.
        """
        try:
            _ALL_COLLECTIONS = _OUT_DIR / "all_collections.json"

            result = subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "decode_collection.py"),
                 "--out", str(_COLLECTION)],
                capture_output=True, text=True,
                cwd=str(_SCRIPTS_DIR.parent),
            )

            if not _ALL_COLLECTIONS.exists():
                self._json_response({"accounts": [], "log": result.stdout.strip()})
                return

            data = json.loads(_ALL_COLLECTIONS.read_text(encoding="utf-8"))
            profiles = data.get("profiles", {})
            accounts = sorted(
                [
                    {
                        "name":      name,
                        "cardCount": info.get("cardCount", 0),
                        "credits":   info.get("credits", 0),
                        "updatedAt": info.get("updatedAt", ""),
                    }
                    for name, info in profiles.items()
                ],
                key=lambda a: a["updatedAt"],
                reverse=True,
            )
            self._json_response({
                "accounts":  accounts,
                "updatedAt": data.get("updatedAt", ""),
            })
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)

    # ── Generate endpoints ────────────────────────────────────────────────

    def _api_generate_status(self):
        """Report the background generate job: running (elapsed, log lines), finished, or never run."""
        global _generate_proc, _generate_start, _generate_done, _generate_result
        if _generate_running:
            elapsed = int(time.time() - _generate_start)
            # Count lines in log as a progress proxy
            lines = 0
            try:
                lines = _GENERATE_LOG.read_text(encoding="utf-8").count("\n")
            except Exception:
                pass
            self._json_response({
                "running":     True,
                "elapsedSecs": elapsed,
                "logLines":    lines,
            })
        elif _generate_done is not None:
            self._json_response({
                "running":    False,
                "result":     _generate_result,
                "tookSecs":   int(_generate_done - _generate_start),
            })
        else:
            self._json_response({"running": False, "result": None})

    def _api_generate_run(self):
        """Start generate_sources.py on a background thread unless a run is already in progress."""
        global _generate_running, _generate_start, _generate_done, _generate_result
        with _generate_lock:
            if _generate_running:
                self._json_response({"started": False, "reason": "already running"})
                return
            _generate_running = True              # claimed before the thread starts: no double run
            _generate_start   = time.time()
            _generate_done    = None
            _generate_result  = None
            t = threading.Thread(target=_run_generate_background, args=([], ), daemon=True)
            t.start()
        self._json_response({"started": True})

    def _api_generate_log(self):
        """Return the full text of generate.log ("" if it doesn't exist yet)."""
        try:
            text = _GENERATE_LOG.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        self._json_response({"log": text})

    # ── Hiscores endpoint ─────────────────────────────────────────────────

    # Skills in the order the hiscores lite CSV returns them
    _HISCORE_SKILLS = [
        "Overall", "Attack", "Defence", "Strength", "Hitpoints",
        "Ranged", "Prayer", "Magic", "Cooking", "Woodcutting",
        "Fletching", "Fishing", "Firemaking", "Crafting", "Smithing",
        "Mining", "Herblore", "Agility", "Thieving", "Slayer",
        "Farming", "Runecrafting", "Hunter", "Construction",
    ]

    def _api_hiscores(self):
        """Fetch ?player='s levels from the OSRS hiscores lite CSV; returns {player, levels: {Skill: lvl}}.

        Unranked skills (-1) are left out. Only the first len(_HISCORE_SKILLS) CSV lines are skills;
        the rest (activities, bosses) are ignored.
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        player = (qs.get("player") or [""])[0].strip()
        if not player:
            self._json_response({"error": "missing player parameter"}, status=400)
            return

        url = (
            "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws"
            f"?player={urllib.parse.quote(player)}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "osrs-tcg-sources/dev"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=502)
            return

        levels: dict[str, int] = {}
        for i, line in enumerate(raw.strip().splitlines()):
            if i >= len(self._HISCORE_SKILLS):
                break
            parts = line.split(",")
            if len(parts) >= 2:
                lvl = int(parts[1])
                if lvl > 0:  # -1 means unranked
                    levels[self._HISCORE_SKILLS[i]] = lvl

        self._json_response({"player": player, "levels": levels})

    # ── Quest completion from RuneLite screenshots ────────────────────────

    # RuneLite Screenshot plugin names quest-completion screenshots:
    #   Quest(<quest name>) YYYY-MM-DD_HH-MM-SS.png
    # The quest name is exactly what OSRS displays on completion.
    _SCREENSHOTS_BASE = pathlib.Path.home() / ".runelite" / "screenshots"

    def _api_quests_completed(self):
        """List completed quests from RuneLite screenshot filenames (one player, or all if no ?player=)."""
        import re
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        player = (qs.get("player") or [""])[0].strip()

        search_dirs: list[pathlib.Path] = []
        if player:
            # Player specified — only scan that player's directory, never others.
            search_dirs.append(self._SCREENSHOTS_BASE / player / "Quests")
        elif self._SCREENSHOTS_BASE.exists():
            # No player specified — scan all player directories.
            for d in self._SCREENSHOTS_BASE.iterdir():
                candidate = d / "Quests"
                if candidate.is_dir():
                    search_dirs.append(candidate)

        pattern = re.compile(r'^Quest\((.+?)\)\s+\d{4}-\d{2}-\d{2}')
        found: dict[str, str] = {}   # quest name → screenshot filename (latest)

        for quest_dir in search_dirs:
            if not quest_dir.is_dir():
                continue
            for f in quest_dir.iterdir():
                m = pattern.match(f.name)
                if m:
                    name = m.group(1)
                    # Keep most recent screenshot for each quest name
                    if name not in found or f.name > found[name]:
                        found[name] = f.name

        self._json_response({
            "player": player,
            "completedQuests": sorted(found.keys()),
            "screenshotCount": len(found),
            "dirsScanned": [str(d) for d in search_dirs],
        })

    # ── Collection source-mtime (for auto-refresh detection) ─────────────

    _TCG_PROFILES = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "profiles"
    _TCG_BACKUPS  = pathlib.Path.home() / ".runelite" / "OSRS-TCG" / "backups"

    def _api_collection_source_mtime(self):
        """Return the newest mtime of any RuneLite TCG save file.

        Fast filesystem stat scan — no decode. Used by the browser to
        detect when new packs have been opened / the player has logged out.
        """
        best = 0.0

        # v1.0+ profiles: ~/.runelite/OSRS-TCG/profiles/<hash>/tcg.save
        if self._TCG_PROFILES.exists():
            for account_dir in self._TCG_PROFILES.iterdir():
                save = account_dir / "tcg.save"
                if save.is_file():
                    best = max(best, save.stat().st_mtime)

        # Legacy backups: ~/.runelite/OSRS-TCG/backups/<hash>/*
        if self._TCG_BACKUPS.exists():
            for account_dir in self._TCG_BACKUPS.iterdir():
                if account_dir.is_dir():
                    for f in account_dir.iterdir():
                        if f.is_file():
                            best = max(best, f.stat().st_mtime)

        # profiles2/*.properties (pre-v1.0 fallback)
        for f in (pathlib.Path.home() / ".runelite" / "profiles2").glob("*.properties"):
            best = max(best, f.stat().st_mtime)

        self._json_response({
            "sourceMtime": best,
            "sourceTime":  datetime.fromtimestamp(best).isoformat(timespec="seconds") if best else None,
        })

    # ── Cloud revision check ──────────────────────────────────────────────

    def _api_collection_revision(self):
        """Return the current cloud revision for a player without fetching all cards.

        Calls /api/v1/me/cards?limit=1 (≈450 bytes) so the browser can detect
        when new cards have been pulled without triggering a full decode.

        Query params:
          ?player=<display_name>   — required; must be a cloud account
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        player = (qs.get("player") or [""])[0].strip()
        if not player:
            self._json_response({"error": "missing player parameter"}, status=400)
            return

        sess = _find_cloud_session(player)
        if not sess:
            self._json_response({"isCloud": False, "player": player})
            return

        token = sess.get("accessToken")
        if not token:
            self._json_response({"isCloud": False, "player": player})
            return

        # Cache per player (every open tab polls this) and back off on HTTP 429 (cloud rate limit)
        import time as _t
        hit = _revision_cache.get(player.lower())
        now = _t.time()
        if hit and (now - hit["at"] < 45 or now < hit.get("backoffUntil", 0)):
            self._json_response(hit["payload"])
            return
        url = "https://api.osrs-tcg.net/api/v1/me/cards?limit=1"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent":    "osrs-tcg-preview/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            payload = {
                "isCloud":   True,
                "player":    player,
                "revision":  data.get("revision"),
                "stateHash": data.get("stateHash"),
            }
            _revision_cache[player.lower()] = {"at": now, "payload": payload}
            self._json_response(payload)
        except Exception as exc:
            if hit:   # keep answering with the last good revision while rate-limited
                wait = 60
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                    try: wait = max(30, int(exc.headers.get("Retry-After") or 60))
                    except Exception: pass
                hit["backoffUntil"] = now + wait
                self._json_response(hit["payload"])
                return
            self._json_response({"error": str(exc)}, status=502)

    # ── Pack catalog + image proxy ────────────────────────────────────────

    def _api_packs(self):
        """Proxy /api/packs to the OSRS TCG API with a 24-hour cache."""
        try:
            data = _get_pack_catalog()
            self._json_response(data)
        except Exception as exc:
            self._json_response({"error": str(exc)}, status=502)

    def _send_image(self, data: bytes | None, ext: str = "png"):
        """Send image bytes with a 7-day cache header, or an uncacheable 502 when data is None."""
        if data is None:
            self.send_response(502)
            self.send_header("Cache-Control", "no-store")  # never let a failure stick in the browser cache
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/" + ext))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=604800")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _proxy_tcg_image(self, path: str):
        """Proxy /images/** (card art, pack images) from osrs-tcg.net, cached on disk."""
        rel = urllib.parse.unquote(path[len("/images/"):])
        if ".." in rel or not re.match(r"^[\w ./%()'&,!+-]+\.(png|gif|jpg|jpeg|webp)$", rel, re.I):
            self.send_response(400); self.end_headers(); return
        data = _fetch_image_cached(_TCG_IMG_DIR / rel, ["https://osrs-tcg.net/images/" + urllib.parse.quote(rel)])
        self._send_image(data, rel.rsplit(".", 1)[-1].lower())

    def _proxy_wiki_image(self, path: str):
        """Proxy /wikiimg/<path> → oldschool.runescape.wiki/images/<path>, cached on disk.

        The wiki's bot check (Weird Gloop) answers uncached image requests with a JS challenge
        (502/403) that an <img> can't pass, so icons went blank. Retries, falls back to the
        original file and then RuneLite's sprite, and keeps every good image.
        """
        rel = urllib.parse.unquote(path[len("/wikiimg/"):])
        if not rel or ".." in rel or not re.match(r"^[\w ./%()'&,!+-]+\.(png|gif|jpg|jpeg|webp)$", rel, re.I):
            self.send_response(400); self.end_headers(); return
        self._send_image(_fetch_image_cached(_wiki_cache_path(rel), _wiki_image_urls(rel)), rel.rsplit(".", 1)[-1].lower())

    # ── Helpers ───────────────────────────────────────────────────────────

    def _json_response(self, data: dict, status: int = 200):
        """Send *data* as a JSON response (UTF-8, CORS open) with the given status."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    """Parse --port and serve until Ctrl+C (threaded, so slow image fetches don't block the page)."""
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    server = http.server.ThreadingHTTPServer(("", args.port), Handler)   # image proxy fetches mustn't block the page
    print(f"OSRS TCG preview server → http://localhost:{args.port}/preview.html")
    print(f"  Refresh collection: http://localhost:{args.port}/api/collection/refresh")
    print(f"  Trigger re-generate: POST http://localhost:{args.port}/api/generate/run")
    print("  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
