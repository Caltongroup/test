"""Audit generated logs against the programming rules.

Used by `python -m musiclog validate` and by the test suite.
"""

from __future__ import annotations

from collections import defaultdict

from .models import CATEGORIES, DayLog, Song
from .rules import SAME_SONG_SEP_MIN, _artist_sep_minutes


def validate_logs(logs: list[DayLog], songs: list[Song]) -> list[str]:
    problems: list[str] = []
    for log in logs:
        problems += _validate_day(log)
    problems += _validate_stacking(logs)
    problems += _validate_category_counts(logs)
    return problems


def _validate_day(log: DayLog) -> list[str]:
    problems = []
    prev = None
    prev2 = None
    last_artist_minute: dict[str, int] = {}
    last_song_minute: dict[str, int] = {}
    for slot in log.slots:
        s = slot.song
        minute = slot.hour * 60 + slot.start_seconds // 60
        where = f"{log.date_iso} {slot.time_str}"

        if prev is not None:
            if s.is_slow and prev.song.is_slow:
                problems.append(f"{where}: two slow songs in a row "
                                f"({prev.song.title} -> {s.title})")
            if (s.is_fast and prev.song.is_fast
                    and prev2 is not None and prev2.song.is_fast):
                problems.append(f"{where}: three fast songs in a row")
            if not s.mood.compatible_next_to(prev.song.mood):
                problems.append(f"{where}: happy next to sad/angry "
                                f"({prev.song.title} -> {s.title})")

        if s.artist in last_artist_minute:
            gap = minute - last_artist_minute[s.artist]
            if gap < _artist_sep_minutes(s):
                problems.append(f"{where}: artist separation broken for "
                                f"{s.artist} ({gap} min)")
        last_artist_minute[s.artist] = minute

        if s.song_id in last_song_minute:
            gap = minute - last_song_minute[s.song_id]
            if gap < SAME_SONG_SEP_MIN:
                problems.append(f"{where}: {s.title} repeated after only "
                                f"{gap} min")
        last_song_minute[s.song_id] = minute

        prev2, prev = prev, slot

    # Affiliate fill must never sit above the last song(s) of an hour.
    for hour in sorted({sl.hour for sl in log.slots}):
        hour_slots = log.hour_slots(hour)
        seen_fill = False
        for sl in hour_slots:
            if sl.song.category == "AF":
                seen_fill = True
            elif seen_fill:
                problems.append(f"{log.date_iso} {hour:02d}:00: affiliate "
                                f"fill scheduled above {sl.song.title}")
    return problems


def _validate_stacking(logs: list[DayLog]) -> list[str]:
    """No song may sit in the same hour on consecutive days."""
    problems = []
    by_date: dict[str, dict[str, set[int]]] = defaultdict(
        lambda: defaultdict(set))
    for log in logs:
        for slot in log.slots:
            by_date[log.date_iso][slot.song.song_id].add(slot.hour)
    dates = sorted(by_date)
    for a, b in zip(dates, dates[1:]):
        for song_id, hours_b in by_date[b].items():
            same_hour = by_date[a].get(song_id, set()) & hours_b
            if same_hour:
                problems.append(f"{b}: song {song_id} stacked in hour(s) "
                                f"{sorted(same_hour)} vs {a}")
    return problems


def _validate_category_counts(logs: list[DayLog]) -> list[str]:
    """Per-song daily spins must stay within the category's range
    (allowing one under, since fallbacks may borrow slots)."""
    problems = []
    for log in logs:
        song_plays: dict[str, int] = defaultdict(int)
        cat_of: dict[str, str] = {}
        for slot in log.slots:
            song_plays[slot.song.song_id] += 1
            cat_of[slot.song.song_id] = slot.song.category
        for song_id, n in song_plays.items():
            rule = CATEGORIES[cat_of[song_id]]
            if rule.fill_only or rule.code == "TB":
                continue
            if n > rule.max_plays_per_day + 1:
                problems.append(
                    f"{log.date_iso}: song {song_id} ({rule.code}) played "
                    f"{n}x, above the {rule.max_plays_per_day}/day target")
    return problems
