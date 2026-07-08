"""Rule engine: hard constraints and soft scoring for candidate songs.

Hard rules reject a candidate outright; soft rules add penalty points.
The scheduler picks the legal candidate with the lowest penalty, and
relaxes soft rules (never hard ones like artist separation) if an hour
would otherwise go unfilled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .history import HistoryStore
from .models import CATEGORIES, ArtistTier, Mood, Song, Sound

CORE_ARTIST_SEP_MIN = 35
SECONDARY_ARTIST_SEP_MIN = 45
SAME_SONG_SEP_MIN = 150  # a song spinning 5-6x/day still rests ~2.5h+

# Dayparts used for anti-stacking (radio listeners are habitual).
DAYPARTS = {  # hour -> daypart name
    **{h: "overnight" for h in range(0, 6)},
    **{h: "morning" for h in range(6, 10)},
    **{h: "midday" for h in range(10, 15)},
    **{h: "afternoon" for h in range(15, 19)},
    **{h: "evening" for h in range(19, 24)},
}


@dataclass
class ScheduleContext:
    """Everything the rules need to judge a candidate for the next slot."""

    date_iso: str
    hour: int
    minute_of_day: int
    prev_songs: list[Song] = field(default_factory=list)  # today, in order
    prev_minutes: list[int] = field(default_factory=list)
    hour_songs: list[Song] = field(default_factory=list)  # this hour so far

    @property
    def prev(self) -> Song | None:
        return self.prev_songs[-1] if self.prev_songs else None

    @property
    def prev2(self) -> Song | None:
        return self.prev_songs[-2] if len(self.prev_songs) >= 2 else None


def _artist_sep_minutes(song: Song) -> int:
    return (CORE_ARTIST_SEP_MIN if song.artist_tier is ArtistTier.CORE
            else SECONDARY_ARTIST_SEP_MIN)


def violates_hard_rules(song: Song, ctx: ScheduleContext,
                        history: HistoryStore) -> str | None:
    """Return a reason string if the song is illegal here, else None."""

    # Tempo: never two slow songs back to back.
    if ctx.prev is not None and song.is_slow and ctx.prev.is_slow:
        return "two slow songs in a row"

    # Tempo: two fast in a row is fine, three is not.
    if (song.is_fast and ctx.prev is not None and ctx.prev.is_fast
            and ctx.prev2 is not None and ctx.prev2.is_fast):
        return "three fast songs in a row"

    # Mood: happy never touches sad/angry.
    if ctx.prev is not None and not song.mood.compatible_next_to(ctx.prev.mood):
        return "mood clash with previous song"

    # Artist and same-song separation within today.
    sep = _artist_sep_minutes(song)
    for other, minute in zip(ctx.prev_songs, ctx.prev_minutes):
        gap = ctx.minute_of_day - minute
        if other.song_id == song.song_id and gap < SAME_SONG_SEP_MIN:
            return f"same song within {SAME_SONG_SEP_MIN} min"
        if other.artist == song.artist and gap < sep:
            return f"artist separation ({sep} min)"

    # Anti-stacking: never the same hour as yesterday. (Same daypart as
    # yesterday is a soft penalty — a 6x/day power song necessarily
    # revisits dayparts, but low-rotation songs should slide.)
    yesterday = (date.fromisoformat(ctx.date_iso)
                 - timedelta(days=1)).isoformat()
    if ctx.hour in history.song_hours_on(yesterday, song.song_id):
        return "played this hour yesterday (stacking)"

    return None


def soft_penalty(song: Song, ctx: ScheduleContext,
                 history: HistoryStore) -> float:
    """Lower is better."""
    penalty = 0.0
    prev = ctx.prev

    if prev is not None:
        # Pop-leaning songs shouldn't sit together very often.
        if song.sound is Sound.POP and prev.sound is Sound.POP:
            penalty += 25
        # Era balance: space newer songs with older ones.
        if song.era == prev.era:
            penalty += 8
        # Two fast together is allowed but shouldn't be the norm.
        if song.is_fast and prev.is_fast:
            penalty += 4
        # Identical tempo twice in a row flattens the flow.
        if song.tempo == prev.tempo:
            penalty += 3

    # Mood balance within the hour: penalize a mood already dominating.
    same_mood = sum(1 for s in ctx.hour_songs if s.mood is song.mood)
    if same_mood >= 3:
        penalty += 10 * (same_mood - 2)

    # Sad/angry runs get dreary even with neutral bridges.
    if song.mood is Mood.SAD:
        recent_sad = sum(1 for s in ctx.prev_songs[-4:] if s.mood is Mood.SAD)
        penalty += 6 * recent_sad

    # Rest: prefer the least-recently-played song in the category.
    last_idx = history.last_play_index(song.song_id)
    if last_idx >= 0:
        recency = last_idx / max(1, len(history.plays))
        penalty += 20 * recency
    else:
        penalty -= 5  # fresh songs get a small boost

    # Same-artist elsewhere today (beyond the hard separation window)
    # still costs a little, encouraging variety.
    penalty += 2 * sum(1 for s in ctx.prev_songs if s.artist == song.artist)

    # Daypart anti-stacking vs yesterday: habitual listeners should hear
    # different songs at the same time of day. Heavy penalty for
    # low-rotation songs, mild for power songs that spin 4-6x/day.
    yesterday = (date.fromisoformat(ctx.date_iso)
                 - timedelta(days=1)).isoformat()
    y_hours = history.song_hours_on(yesterday, song.song_id)
    if any(DAYPARTS[h] == DAYPARTS[ctx.hour] for h in y_hours):
        max_spins = CATEGORIES[song.category].max_plays_per_day
        penalty += 8 if max_spins >= 4 else 40

    return penalty
