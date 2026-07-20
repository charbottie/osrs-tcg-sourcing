"""Fetch OSRS Wiki pages with disk caching and polite rate limiting.

Usage rules (per wiki staff, github issue #1, 2026-07-18):
  - Plain page URLs ONLY — never api.php?action=parse (forces uncached parse)
  - Pace at ~1 req/sec for uncached requests
  - Descriptive User-Agent naming this project
  - Cache every raw fetch so re-runs hit the wiki zero times
  - The shipped plugin makes NO wiki requests at runtime
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

import requests

WIKI_BASE = "https://oldschool.runescape.wiki/w/"
USER_AGENT = "osrs-tcg-sources/dev (github.com/Felmeme/bronzeman-tcg)"
RATE_LIMIT_SECS = 1.1  # slightly over 1s to be safe
_REQUEST_TIMEOUT = (10, 20)  # (connect_secs, read_secs)

_SCRIPT_DIR = Path(__file__).parent
_CACHE_DIR = _SCRIPT_DIR / "cache" / "wiki_html"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Pages whose /Loot subpage hangs the connection indefinitely on this network.
# Hardcoded to skip the live fetch — the main page has no drops table anyway.
_SKIP_LOOT_PAGES: frozenset[str] = frozenset({
    "Warrior_of_Murahs",
})

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _cache_path(page_name: str) -> Path:
    """Return the disk cache path for a page name."""
    safe = page_name.replace("/", "__SLASH__").replace("\\", "_")
    return _CACHE_DIR / (safe + ".html")


def fetch(page_name: str, *, force_refresh: bool = False) -> str | None:
    """Return HTML for an OSRS Wiki page, using disk cache when available."""
    page_name = page_name.replace(" ", "_")
    cache = _cache_path(page_name)

    if not force_refresh and cache.exists():
        return cache.read_text(encoding="utf-8")

    url = WIKI_BASE + urllib.parse.quote(page_name, safe="/")
    try:
        resp = _session.get(url, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  [FETCH ERROR] {url}: {exc}")
        return None
    finally:
        time.sleep(RATE_LIMIT_SECS)

    if resp.status_code == 404:
        print(f"  [404] {url}")
        return None
    if not resp.ok:
        print(f"  [HTTP {resp.status_code}] {url}")
        return None

    html = resp.text
    cache.write_text(html, encoding="utf-8")
    return html


def fetch_with_loot_fallback(page_name: str) -> tuple[str | None, str]:
    """Fetch a monster page; if no drops table found, try the /Loot subpage."""
    html = fetch(page_name)
    if html and _has_drops_table(html):
        return html, page_name

    if page_name in _SKIP_LOOT_PAGES:
        print(f"  [SKIP /Loot] {page_name} is on the skip list")
        return html, page_name

    loot_page = page_name.rstrip("/") + "/Loot"
    loot_html = fetch(loot_page)
    if loot_html and _has_drops_table(loot_html):
        return loot_html, loot_page

    return html, page_name


def _has_drops_table(html: str) -> bool:
    """Quick check (no BS4) — does this page contain a drops table?"""
    return "item-drops" in html or "wikitable" in html
