"""End-to-end tests: generate a full week and audit every rule."""

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from musiclog.export import log_filename, render_log, write_logs  # noqa: E402
from musiclog.history import HistoryStore  # noqa: E402
from musiclog.library import load_library  # noqa: E402
from musiclog.models import CATEGORIES, Mood  # noqa: E402
from musiclog.scheduler import BROADCAST_HOURS, Scheduler  # noqa: E402
from musiclog.validate import validate_logs  # noqa: E402

LIBRARY = REPO / "data" / "demo_library.csv"
START = date(2026, 7, 13)  # a Monday


@pytest.fixture(scope="module")
def songs():
    return load_library(LIBRARY)


@pytest.fixture(scope="module")
def week(songs):
    scheduler = Scheduler(songs, HistoryStore(), seed=7)
    return scheduler.schedule_days(START, 7)


def test_library_loads(songs):
    assert len(songs) > 100
    assert {s.category for s in songs} == set(CATEGORIES)


def test_week_passes_all_rules(week, songs):
    problems = validate_logs(week, songs)
    assert problems == []


def test_every_hour_is_filled(week):
    for log in week:
        for hour in BROADCAST_HOURS:
            n = len(log.hour_slots(hour))
            assert n >= 10, f"{log.date_iso} {hour}:00 only {n} songs"


def test_affiliate_fill_ends_every_hour(week):
    for log in week:
        for hour in BROADCAST_HOURS:
            slots = log.hour_slots(hour)
            assert slots[-1].song.category == "AF", \
                f"{log.date_iso} {hour}:00 does not end with fill"


def test_weekend_throwbacks_two_per_hour(week):
    for log in week:
        for hour in BROADCAST_HOURS:
            tb = sum(1 for s in log.hour_slots(hour)
                     if s.song.category == "TB")
            if log.weekday >= 5:
                assert tb == 2, (f"{log.date_iso} {hour}:00 has {tb} "
                                 f"throwbacks, expected 2")
            else:
                assert tb <= 1


def test_weekday_throwbacks_sparingly(week):
    for log in week:
        if log.weekday < 5:
            tb = sum(1 for s in log.slots if s.song.category == "TB")
            assert tb <= 3


def test_power_current_daily_spins(week):
    for log in week:
        plays = {}
        for slot in log.slots:
            if slot.song.category == "PC":
                plays[slot.song.song_id] = plays.get(slot.song.song_id, 0) + 1
        assert plays, f"{log.date_iso}: no Power Currents scheduled"
        for song_id, n in plays.items():
            assert 3 <= n <= 6, f"{log.date_iso}: PC {song_id} played {n}x"


def test_no_happy_next_to_sad(week):
    for log in week:
        for a, b in zip(log.slots, log.slots[1:]):
            assert {a.song.mood, b.song.mood} != {Mood.HAPPY, Mood.SAD}


def test_no_consecutive_slow_songs(week):
    for log in week:
        for a, b in zip(log.slots, log.slots[1:]):
            assert not (a.song.is_slow and b.song.is_slow)


def test_sliding_rotation_across_week(week):
    """A Power Current's play-hours should not repeat day over day."""
    hours_by_day = []
    pc_id = next(s.song.song_id for s in week[0].slots
                 if s.song.category == "PC")
    for log in week:
        hours_by_day.append({s.hour for s in log.slots
                             if s.song.song_id == pc_id})
    for a, b in zip(hours_by_day, hours_by_day[1:]):
        assert not (a & b), "power current stacked in the same hour"


def test_export_roundtrip(week, tmp_path):
    paths = write_logs(week[:1], tmp_path)
    assert paths[0].name == log_filename(week[0])
    text = render_log(week[0])
    assert "06:00:00" in text and "MONDAY" in text


def test_cli_validate_exit_code():
    result = subprocess.run(
        [sys.executable, "-m", "musiclog", "validate",
         "--library", str(LIBRARY), "--start", "2026-07-13",
         "--days", "3", "--seed", "11"],
        cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
