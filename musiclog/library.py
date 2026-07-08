"""Load the station library from .xlsx or .csv.

Header matching is fuzzy so the loader tolerates the naming used in
"KQBL Active Library" exports (e.g. "Song Title" vs "Title",
"Category" vs "Cat", "Tempo Code" vs "Tempo").
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import ArtistTier, Mood, Song, Sound

# Map free-form category labels from the spreadsheet to internal codes.
CATEGORY_ALIASES: dict[str, str] = {
    "power current": "PC", "pc": "PC", "current": "PC", "power": "PC",
    "power recurrent": "PR", "pr": "PR", "recurrent": "PR",
    "power 20-teens": "PT", "power 20 teens": "PT", "power teens": "PT",
    "power 2010s": "PT", "pt": "PT",
    "secondary teens": "ST", "secondary 20-teens": "ST",
    "secondary 2010s": "ST", "st": "ST",
    "power 2000s": "P2K", "power 2000's": "P2K", "p2k": "P2K",
    "secondary 2000s": "S2K", "secondary 2000's": "S2K", "s2k": "S2K",
    "power 90s": "P90", "power 90's": "P90", "90s power": "P90",
    "90's power": "P90", "p90": "P90",
    "secondary 90s": "S90", "secondary 90's": "S90", "s90": "S90",
    "throwback": "TB", "throwbacks": "TB", "tb": "TB",
    "affiliate fill": "AF", "fill": "AF", "affiliate": "AF", "af": "AF",
}

# Column name candidates -> canonical field.
HEADER_ALIASES: dict[str, list[str]] = {
    "title": ["title", "song title", "song", "name"],
    "artist": ["artist", "artists", "performer"],
    "category": ["category", "cat", "rotation", "wideorbit category",
                 "wideorbit cateogry"],
    "tempo": ["tempo", "tempo code", "energy"],
    "sound": ["sound", "sound code", "style", "sound coding"],
    "mood": ["mood", "mood code", "feel"],
    "year": ["year", "release year", "era", "yr"],
    "artist_tier": ["artist tier", "tier", "artist type", "core/secondary",
                    "artist level"],
    "length": ["length", "runtime", "duration", "time"],
    "song_id": ["id", "song id", "cart", "cart number", "cut", "media id",
                "wide orbit cart", "wideorbit cart", "cart #"],
}

# When no year column exists, use a category-based era default.
_CAT_ERA: dict[str, int] = {
    "PC": 2025, "PR": 2023, "PT": 2015, "ST": 2015,
    "P2K": 2004, "S2K": 2004, "P90": 1995, "S90": 1995,
    "TB": 1988, "AF": 2010,
}


def _canonical_header(raw: str) -> str | None:
    cleaned = re.sub(r"[^a-z0-9/ ]", "", (raw or "").strip().lower()).strip()
    for field_name, candidates in HEADER_ALIASES.items():
        if cleaned in candidates:
            return field_name
    return None


def normalize_category(raw: str) -> str | None:
    return CATEGORY_ALIASES.get((raw or "").strip().lower())


def _parse_length(raw) -> int:
    import datetime
    if raw is None or raw == "":
        return 210
    # openpyxl returns song length as datetime.time(minutes, seconds)
    if isinstance(raw, datetime.time):
        return raw.hour * 60 + raw.minute or 210
    text = str(raw).strip()
    if ":" in text:
        parts = [int(float(p)) for p in text.split(":")]
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + p
        return seconds or 210
    try:
        return int(float(text)) or 210
    except ValueError:
        return 210


def _parse_tempo(raw) -> int:
    """Decode a 1–5 scale or WideOrbit 3-digit code (111/333/555)."""
    if raw is None:
        return 3
    try:
        v = int(float(raw))
        s = str(v)
        if len(s) == 3 and all(c in "135" for c in s):
            avg = sum(int(c) for c in s) / 3
            return max(1, min(5, round(avg)))
        return max(1, min(5, v))
    except (ValueError, TypeError):
        return 3


def _rows_from_xlsx(path: Path) -> list[list]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


def _rows_from_csv(path: Path) -> list[list]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [row for row in csv.reader(fh)]


def load_library(path: str | Path) -> list[Song]:
    path = Path(path)
    rows = _rows_from_xlsx(path) if path.suffix.lower() in (".xlsx", ".xlsm") \
        else _rows_from_csv(path)
    if not rows:
        raise ValueError(f"{path}: empty library file")

    # Find the header row (first row where we can map title + artist).
    header_idx, columns = None, {}
    for i, row in enumerate(rows[:10]):
        mapped = {}
        for col, cell in enumerate(row):
            canon = _canonical_header(str(cell) if cell is not None else "")
            if canon and canon not in mapped:
                mapped[canon] = col
        if "title" in mapped and "artist" in mapped:
            header_idx, columns = i, mapped
            break
    if header_idx is None:
        raise ValueError(
            f"{path}: could not locate a header row with Title and Artist "
            f"columns. Found headers: {rows[0]}")

    def cell(row, key, default=""):
        col = columns.get(key)
        if col is None or col >= len(row) or row[col] is None:
            return default
        return row[col]

    songs: list[Song] = []
    skipped = 0
    for n, row in enumerate(rows[header_idx + 1:], start=1):
        title = str(cell(row, "title")).strip()
        artist = str(cell(row, "artist")).strip()
        if not title or not artist:
            continue
        category = normalize_category(str(cell(row, "category")))
        if category is None:
            skipped += 1
            continue
        tempo = _parse_tempo(cell(row, "tempo", None))
        raw_year = cell(row, "year", None)
        try:
            year = int(float(raw_year)) if raw_year not in (None, "") else None
        except (ValueError, TypeError):
            year = None
        if year is None:
            year = _CAT_ERA.get(category, 2010)

        raw_tier = cell(row, "artist_tier", None)
        if raw_tier not in (None, ""):
            artist_tier = ArtistTier.parse(str(raw_tier))
        else:
            # Infer tier from rotation category when not in the spreadsheet
            artist_tier = (ArtistTier.CORE if category in ("PC", "PR")
                           else ArtistTier.SECONDARY)

        songs.append(Song(
            song_id=str(cell(row, "song_id", f"S{n:04d}")).strip() or f"S{n:04d}",
            title=title,
            artist=artist,
            category=category,
            tempo=tempo,
            sound=Sound.parse(str(cell(row, "sound"))),
            mood=Mood.parse(str(cell(row, "mood"))),
            year=year,
            artist_tier=artist_tier,
            length_seconds=_parse_length(cell(row, "length")),
        ))
    if not songs:
        raise ValueError(f"{path}: no schedulable songs found "
                         f"({skipped} rows had unrecognized categories)")
    return songs
