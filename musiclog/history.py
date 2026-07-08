"""Rolling 7-day play history.

Persisted as JSON so consecutive daily runs keep artist separation,
anti-stacking, and sliding rotation state across days.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .models import DayLog


@dataclass
class PlayRecord:
    date_iso: str
    hour: int
    position: int
    minute_of_day: int
    song_id: str
    artist: str
    category: str


class HistoryStore:
    KEEP_DAYS = 8

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.plays: list[PlayRecord] = []
        if self.path and self.path.exists():
            for row in json.loads(self.path.read_text()):
                self.plays.append(PlayRecord(**row))

    def record_day(self, log: DayLog) -> None:
        for slot in log.slots:
            self.plays.append(PlayRecord(
                date_iso=log.date_iso,
                hour=slot.hour,
                position=slot.position,
                minute_of_day=slot.hour * 60 + slot.start_seconds // 60,
                song_id=slot.song.song_id,
                artist=slot.song.artist,
                category=slot.song.category,
            ))
        self._prune(log.date_iso)

    def _prune(self, latest_iso: str) -> None:
        cutoff = (date.fromisoformat(latest_iso)
                  - timedelta(days=self.KEEP_DAYS)).isoformat()
        self.plays = [p for p in self.plays if p.date_iso >= cutoff]

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            [vars(p) for p in self.plays], indent=1))

    # -- queries used by the rule engine ---------------------------------

    def plays_on(self, date_iso: str) -> list[PlayRecord]:
        return [p for p in self.plays if p.date_iso == date_iso]

    def song_hours_on(self, date_iso: str, song_id: str) -> set[int]:
        return {p.hour for p in self.plays
                if p.date_iso == date_iso and p.song_id == song_id}

    def last_play_index(self, song_id: str) -> int:
        """Higher = more recent. -1 if never played in the window."""
        for i in range(len(self.plays) - 1, -1, -1):
            if self.plays[i].song_id == song_id:
                return i
        return -1
