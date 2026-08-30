"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re

from tradingagents.agents.utils.report_i18n import (
    rating_label_spellings,
    rating_value_aliases,
)

# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

# English + all locale-pack display forms produced by localized render helpers.
_RATING_ALIASES: dict[str, str] = rating_value_aliases()

# Escape for regex alternation; longer labels first so multi-word forms win.
_RATING_LABEL_PATTERN = "|".join(
    sorted(
        (re.escape(label) for label in rating_label_spellings()),
        key=len,
        reverse=True,
    )
)
_FINAL_RATING_LABEL_PATTERN = "|".join(
    sorted(
        (
            re.escape(label)
            for label in (*rating_label_spellings(), "Final Rating", "\u6700\u7ec8\u8bc4\u7ea7")
        ),
        key=len,
        reverse=True,
    )
)

# Matches "Rating: X" / "评级：增持" / "권고: 매수" — tolerates markdown bold
# wrappers and either a colon, fullwidth colon, or hyphen separator.
_RATING_LABEL_RE = re.compile(
    rf"(?:{_RATING_LABEL_PATTERN}).*?[:：\-][\s*]*([^\s*]+)",
    re.IGNORECASE,
)

_RATING_LINE_RE = re.compile(
    rf"^\s*(?:\*\*)?(?:{_RATING_LABEL_PATTERN})(?:\*\*)?\s*"
    rf"[:：\-]\s*(?:\*\*)?([^\s*]+)(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_RATING_TABLE_ROW_RE = re.compile(
    rf"^\s*\|\s*(?:\*\*)?(?:{_FINAL_RATING_LABEL_PATTERN})(?:\*\*)?\s*"
    rf"\|\s*(?P<value>[^|]+?)\s*\|\s*$",
    re.IGNORECASE,
)
_TABLE_SEPARATOR_RE = re.compile(r"^[\s|:-]+$")
_RATING_HEADER_LABELS = frozenset(
    label.casefold()
    for label in (*rating_label_spellings(), "Final Rating", "\u6700\u7ec8\u8bc4\u7ea7")
)


def markdown_table_cells(line: str) -> list[str] | None:
    """Split a Markdown table row into cells; return None when it is not a row."""
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return None
    if _TABLE_SEPARATOR_RE.fullmatch(stripped.replace(" ", "")):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def normalize_markdown_header_cell(cell: str) -> str:
    """Strip emphasis and a trailing ``(USD)`` / ``（USD）`` suffix from a header."""
    cleaned = re.sub(r"[*_`]", "", cell).strip()
    return re.sub(r"\s*[\(（][^）)]*[\)）]\s*$", "", cleaned).strip()


def iter_markdown_header_tables(text: str):
    """Yield ``(headers, data_row)`` for columnar Markdown summary tables.

    Requires a separator row so key-value tables such as
    ``| 目标价 | 4.90 元 |`` are not misread as a header plus the next field.
    """
    lines = str(text or "").splitlines()
    index = 0
    while index < len(lines) - 1:
        headers = markdown_table_cells(lines[index])
        if headers is None:
            index += 1
            continue
        separator_at = index + 1
        if separator_at >= len(lines) or not _TABLE_SEPARATOR_RE.fullmatch(
            lines[separator_at].strip().replace(" ", "")
        ):
            index += 1
            continue
        data_at = separator_at + 1
        if data_at >= len(lines):
            break
        data = markdown_table_cells(lines[data_at])
        if data is None:
            index += 1
            continue
        yield headers, data
        index = data_at + 1


def _canonical_rating(token: str) -> str | None:
    cleaned = token.strip("*:.,，。")
    if not cleaned:
        return None
    return _RATING_ALIASES.get(cleaned) or _RATING_ALIASES.get(cleaned.lower())


def _canonical_rating_cell(value: str) -> str | None:
    cleaned = re.sub(r"[*_`]", "", value).strip()
    direct = _canonical_rating(cleaned)
    if direct:
        return direct
    primary = re.split(r"[\s(\uff08]", cleaned, maxsplit=1)[0]
    return _canonical_rating(primary)


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from prose text.

    Two-pass strategy:
    1. Look for an explicit rating/recommendation label (any known locale).
    2. Fall back to the first known rating token found anywhere in the text.

    Returns a canonical English rating string, or ``default`` if none appear.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m:
            rating = _canonical_rating(m.group(1))
            if rating:
                return rating

    for line in text.splitlines():
        for word in line.split():
            rating = _canonical_rating(word)
            if rating:
                return rating
        # CJK / non-spaced scripts may glue the token without ASCII whitespace.
        # Only scan non-ASCII aliases here so English substrings like
        # "hold" inside "shareholder" cannot false-match.
        for alias, canonical in _RATING_ALIASES.items():
            if alias.isascii():
                continue
            if alias in line:
                return canonical

    return default


def parse_authoritative_rating(text: str) -> str | None:
    """Parse an explicit standalone rating and reject conflicting candidates."""
    candidates: set[str] = set()
    for line in str(text or "").splitlines():
        match = _RATING_LINE_RE.fullmatch(line)
        rating = _canonical_rating(match.group(1)) if match else None
        if rating:
            candidates.add(rating)
            continue
        table_match = _RATING_TABLE_ROW_RE.fullmatch(line)
        rating = (
            _canonical_rating_cell(table_match.group("value"))
            if table_match
            else None
        )
        if rating:
            candidates.add(rating)

    for headers, data in iter_markdown_header_tables(text):
        for column, header in enumerate(headers):
            label = normalize_markdown_header_cell(header)
            if label.casefold() not in _RATING_HEADER_LABELS:
                continue
            if column >= len(data):
                continue
            rating = _canonical_rating_cell(data[column])
            if rating:
                candidates.add(rating)

    if len(candidates) == 1:
        return next(iter(candidates))
    if candidates:
        return None
    return _canonical_rating(str(text or "").strip())
