"""Data model for songs, categories, and schedule slots."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Sound(enum.Enum):
    MAINSTREAM = "Mainstream"
    POP = "Pop"

    @classmethod
    def parse(cls, raw: str) -> "Sound":
        raw = (raw or "").strip().lower()
        if raw.startswith("pop"):
            return cls.POP
        return cls.MAINSTREAM


class Mood(enum.Enum):
    HAPPY = "Happy"
    NEUTRAL = "Neutral"
    SAD = "Sad/Angry"

    @classmethod
    def parse(cls, raw: str) -> "Mood":
        raw = (raw or "").strip().lower()
        if raw.startswith("happy") or raw.startswith("up"):
            return cls.HAPPY
        if raw.startswith("sad") or raw.startswith("ang") or raw.startswith("dark"):
            return cls.SAD
        return cls.NEUTRAL

    def compatible_next_to(self, other: "Mood") -> bool:
        """Happy may not sit next to Sad/Angry; Neutral bridges both."""
        if {self, other} == {Mood.HAPPY, Mood.SAD}:
            return False
        return True


class ArtistTier(enum.Enum):
    CORE = "Core"
    SECONDARY = "Secondary"

    @classmethod
    def parse(cls, raw: str) -> "ArtistTier":
        raw = (raw or "").strip().lower()
        if raw.startswith("core") or raw.startswith("a"):
            return cls.CORE
        return cls.SECONDARY


@dataclass(frozen=True)
class CategoryRule:
    """Rotation policy for one library category."""

    code: str
    name: str
    min_plays_per_day: int
    max_plays_per_day: int
    slides: bool = False          # sliding day-offset across hours/dayparts
    weekend_per_hour: int = 0     # forced plays per hour on Sat/Sun (Throwbacks)
    weekday_sparingly: bool = False
    fill_only: bool = False       # only ever the last song(s) of an hour


# Category codes are normalized from whatever labels appear in the library
# spreadsheet (see library.CATEGORY_ALIASES).
CATEGORIES: dict[str, CategoryRule] = {
    "PC": CategoryRule("PC", "Power Current", 5, 6, slides=True),
    "PR": CategoryRule("PR", "Power Recurrent", 3, 4, slides=True),
    "PT": CategoryRule("PT", "Power 20-Teens", 2, 3),
    "ST": CategoryRule("ST", "Secondary Teens", 1, 2),
    "P2K": CategoryRule("P2K", "Power 2000s", 1, 2),
    "S2K": CategoryRule("S2K", "Secondary 2000s", 1, 1),
    "P90": CategoryRule("P90", "Power 90s", 1, 2),
    "S90": CategoryRule("S90", "Secondary 90s", 1, 1),
    "TB": CategoryRule("TB", "Throwback", 0, 2, weekend_per_hour=2,
                       weekday_sparingly=True),
    "AF": CategoryRule("AF", "Affiliate Fill", 0, 99, fill_only=True),
}


@dataclass
class Song:
    song_id: str
    title: str
    artist: str
    category: str                 # key into CATEGORIES
    tempo: int                    # 1 (slowest) .. 5 (fastest)
    sound: Sound
    mood: Mood
    year: int
    artist_tier: ArtistTier
    length_seconds: int = 210

    @property
    def is_fast(self) -> bool:
        return self.tempo >= 4

    @property
    def is_slow(self) -> bool:
        return self.tempo <= 2

    @property
    def era(self) -> str:
        if self.year >= 2020:
            return "current"
        if self.year >= 2010:
            return "teens"
        if self.year >= 2000:
            return "2000s"
        return "90s"


@dataclass
class Slot:
    """One scheduled song within a daily log."""

    hour: int
    position: int                 # 0-based position within the hour
    song: Song
    start_seconds: int = 0        # offset from top of hour

    @property
    def time_str(self) -> str:
        m, s = divmod(self.start_seconds, 60)
        return f"{self.hour:02d}:{m:02d}:{s:02d}"


@dataclass
class DayLog:
    date_iso: str
    weekday: int                  # 0=Monday
    slots: list[Slot] = field(default_factory=list)

    def hour_slots(self, hour: int) -> list[Slot]:
        return [s for s in self.slots if s.hour == hour]
