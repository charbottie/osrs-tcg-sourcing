"""Shared, polite access to the OSRS Wiki for the planner's generators.

Rules (per wiki staff, github issue #1, 2026-07-18; see wiki_fetcher.py):
  - Never api.php?action=parse (it forces an uncached parse). Raw page text comes from the plain
    page URL with ?action=raw, which the wiki serves from cache.
  - Batched reads of stored data (action=query revisions/pageimages/imageinfo, action=bucket) go
    through get_json(): one shared User-Agent, ~1 request/second, retries on errors.
  - Every caller caches what it fetches, so re-runs hit the wiki zero times.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

USER_AGENT = "osrs-tcg-planner/1.0 (github.com/charbottie/osrs-tcg-sourcing)"
RATE_LIMIT_SECS = 1.1
_last = 0.0


def _get(url: str, timeout: int = 60) -> bytes:
    global _last
    for attempt in range(3):
        wait = RATE_LIMIT_SECS - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def get_json(url: str, timeout: int = 60) -> dict:
    """GET an api.php query/bucket URL (never action=parse) and decode the JSON."""
    if "action=parse" in url:
        raise ValueError("action=parse is not allowed (wiki staff request); use raw() instead")
    return json.loads(_get(url, timeout))


def raw(title: str, timeout: int = 30) -> str:
    """Raw wikitext of a page via the plain page URL (?action=raw), following redirects."""
    for _ in range(3):
        url = "https://oldschool.runescape.wiki/w/" + urllib.parse.quote(title.replace(" ", "_"), safe="/:()'") + "?action=raw"
        text = _get(url, timeout).decode("utf-8")
        m = text.lstrip()[:200]
        if m.upper().startswith("#REDIRECT"):
            import re
            t = re.search(r"\[\[([^\]|#]+)", m)
            if t:
                title = t.group(1).strip()
                continue
        return text
    return text
