"""Map OSRS Wiki rarity fractions to standardised TCG rarity labels.

The wiki shows drop rarities as fractions ("1/512") and/or labels
("Rare"). We normalise both to our own label set so the sourcing panel
can bucket consistently across all monsters.

Rarity buckets:
  Always        — 1/1 or "always" text
  Common        — 1/2 – 1/25
  Uncommon      — 1/26 – 1/128
  Rare          — 1/129 – 1/512
  Very Rare     — 1/513 – 1/5000
  Extremely Rare — 1/5001+
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

# Fraction thresholds — upper bound of each bucket (1-in-N, higher N = rarer)
_THRESHOLDS: list[tuple[int, str]] = [
    (1, "Always"),
    (25, "Common"),
    (128, "Uncommon"),
    (512, "Rare"),
    (5000, "Very Rare"),
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

    for threshold, label in _THRESHOLDS:
        if ratio <= threshold:
            return label
    return "Extremely Rare"


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
