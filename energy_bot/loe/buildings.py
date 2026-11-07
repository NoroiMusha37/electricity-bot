"""Building number normalisation shared by the address lookup and emergency matching.

LOE writes building numbers like ``116``, ``116-А`` (uppercase Cyrillic letter after a dash),
``111/1`` or ``11-13``. Users type ``116а``, ``116 А`` or even a Latin ``116A``.
"""

import re

# Latin letters that look like Cyrillic ones and are commonly typed by mistake.
_LATIN_TO_CYRILLIC = str.maketrans("ABCEHIKMOPTXY", "АВСЕНІКМОРТХУ")
_WHITESPACE = re.compile(r"\s+")
_NUMBER_WITH_LETTER = re.compile(r"^(\d+)-?([А-ЯІЇЄҐ])$")


def normalize_building(text: str) -> str:
    """Return the canonical LOE spelling: ``" 116 а "`` -> ``"116-А"``."""
    value = _WHITESPACE.sub("", text).upper().translate(_LATIN_TO_CYRILLIC)
    if match := _NUMBER_WITH_LETTER.match(value):
        return f"{match.group(1)}-{match.group(2)}"
    return value


def building_variants(text: str) -> list[str]:
    """Spellings to try against the LOE address API, most likely first, without duplicates."""
    stripped = text.strip()
    candidates = (normalize_building(text), stripped, stripped.upper(), stripped.lower())
    return [variant for variant in dict.fromkeys(candidates) if variant]


def parse_building_names(value: str | None) -> list[str]:
    """Split an accident's ``buildingNames`` ("5, 9, 30-А") into normalised numbers."""
    if not value:
        return []
    return [name for part in value.split(",") if (name := normalize_building(part))]


def building_matches(building: str, affected: list[str]) -> bool:
    """True if `building` is in the affected list; an empty list means the whole street."""
    return not affected or normalize_building(building) in affected
