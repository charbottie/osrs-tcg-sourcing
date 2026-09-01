#!/usr/bin/env python3
"""Dev server for the OSRS TCG sourcing panel preview.

Serves static files from scripts/ AND exposes API endpoints for live
data refresh — so the browser can trigger collection decodes and
re-generation without leaving the page.

Usage:
  python scripts/server.py              # default port 8765
  python scripts/server.py --port 9000

Endpoints:
  GET /                         → preview.html
  GET /api/collection/refresh   → decode RuneLite collection, return JSON
  GET /api/collection/status    → card count + last-updated timestamp
  GET /api/generate/status      → is a generate job running? progress?
  POST /api/generate/run        → start background re-generation (non-blocking)
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

_SCRIPTS_DIR = pathlib.Path(__file__).parent
_OUT_DIR     = _SCRIPTS_DIR / "output"
_COLLECTION  = _OUT_DIR / "my_collection.json"
_GENERATE_LOG = _OUT_DIR / "generate.log"

# ── Background job state ────────────────────────────────────────────────────
_generate_lock   = threading.Lock()
_generate_proc   = None   # subprocess.Popen while running
_generate_start  = None   # time.time() when started
_generate_done   = None   # time.time() when finished
_generate_result = None   # "ok" | "error"


def _run_generate_background(extra_args: list[str]) -> None:
    global _generate_proc, _generate_start, _generate_done, _generate_result
    cmd = [
        sys.executable, str(_SCRIPTS_DIR / "generate_sources.py"),
        "--card-json", str(_SCRIPTS_DIR.parent / "research" / "card-catalog-v1.json"),
        "--skip-quests",
        *extra_args,
    ]
    _GENERATE_LOG.write_text("", encoding="utf-8")
    with open(_GENERATE_LOG, "w", encoding="utf-8") as log:
        _generate_proc   = subprocess.Popen(
            cmd, stdout=log, stderr=log,
            cwd=str(_SCRIPTS_DIR.parent),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        _generate_start  = time.time()
        _generate_done   = None
        _generate_result = None
    _generate_proc.wait()
    _generate_done   = time.time()
    _generate_result = "ok" if _generate_proc.returncode == 0 else "error"
    _generate_proc   = None


# ── Request handler ─────────────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(_SCRIPTS_DIR), **kwargs)

    def log_message(self, fmt, *args):
        # Suppress per-request noise; only print API calls
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api(path)
        else:
            super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self._handle_api(path)
        else:
            self.send_error(405)

    def _handle_api(self, path: str):
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
        global _generate_proc, _generate_start, _generate_done, _generate_result
        if _generate_proc is not None:
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
        global _generate_proc
        with _generate_lock:
            if _generate_proc is not None:
                self._json_response({"started": False, "reason": "already running"})
                return
            t = threading.Thread(target=_run_generate_background, args=([], ), daemon=True)
            t.start()
        self._json_response({"started": True})

    def _api_generate_log(self):
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
        import re
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        player = (qs.get("player") or [""])[0].strip()

        search_dirs: list[pathlib.Path] = []
        if player:
            search_dirs.append(self._SCREENSHOTS_BASE / player / "Quests")
        # Also scan all player dirs if no player specified, or as fallback
        if self._SCREENSHOTS_BASE.exists():
            for d in self._SCREENSHOTS_BASE.iterdir():
                candidate = d / "Quests"
                if candidate not in search_dirs and candidate.is_dir():
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
            "completedQuests": sorted(found.keys()),
            "screenshotCount": len(found),
            "dirsScanned": [str(d) for d in search_dirs],
        })

    # ── Helpers ───────────────────────────────────────────────────────────

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    server = http.server.HTTPServer(("", args.port), Handler)
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
