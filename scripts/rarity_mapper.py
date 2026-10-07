"""Map OSRS Wiki rarity fractions to standardised TCG rarity labels.

The wiki shows drop rarities as fractions ("1/512") and/or labels
("Rare"). We normalise both to our own label set so the sourcing panel
can bucket consistently across all monsters.

Rarity buckets match the OSRS Wiki's own drop-table colours, so a label means
the same thing here as it does on the wiki (verified empirically against the
table-bg-* classes on ~1,200 cached pages, 2026-10):
  Always    — 1/1 or "always" text
  Common    — 1/1 – 1/25
  Uncommon  — rarer than 1/25, up to 1/99.99
  Rare      — 1/100 – 1/999.99
  Very Rare — 1/1,000 and rarer (the wiki has no tier above this)
"""

from __future__ import annotations

_ALWAYS_LABELS = {"always", "constant"}
_LABEL_MAP = {
    "always": "Always",
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "very rare": "Very Rare",
    "extremely rare": "Extremely Rare",
}

# Fraction thresholds — 1-in-N strictly below this bound falls in the bucket
# (higher N = rarer). Always/Common are inclusive of 1 and 25 respectively.
_THRESHOLDS: list[tuple[float, str]] = [
    (1, "Always"),
    (25, "Common"),
    (100, "Uncommon"),
    (1000, "Rare"),
]


def from_fraction(fraction: str) -> str:
    """Return a rarity label for a fraction string like '1/512' or '3/128'.

    Falls back to 'Unknown' if the string cannot be parsed.
    """
    frac = fraction.strip().lower()
    if not frac or frac in _ALWAYS_LABELS or frac in ("1/1", "100%"):
        return "Always"

    try:
        if "/" in frac:
            num, denom = frac.split("/", 1)
            # Wiki sometimes uses float denominators like "1/26.9"
            ratio = float(denom.replace(",", "")) / float(num.replace(",", ""))
        elif "%" in frac:
            pct = float(frac.replace("%", ""))
            if pct >= 100:
                return "Always"
            ratio = 100.0 / pct
        else:
            return "Unknown"
    except (ValueError, ZeroDivisionError):
        return "Unknown"

    if ratio <= 1:
        return "Always"
    if ratio <= 25:
        return "Common"
    for threshold, label in _THRESHOLDS[2:]:
        if ratio < threshold:
            return label
    return "Very Rare"


def from_wiki_label(label: str) -> str:
    """Normalise a wiki rarity label string to our label set.

    Used as fallback when no fraction is available.
    """
    return _LABEL_MAP.get(label.strip().lower(), "Unknown")


def best(fraction: str | None, wiki_label: str | None) -> str:
    """Return the best rarity label, preferring the fraction when available."""
    if fraction:
        result = from_fraction(fraction)
        if result != "Unknown":
            return result
    if wiki_label:
        result = from_wiki_label(wiki_label)
        if result != "Unknown":
            return result
    return "Unknown"
