"""Daily log generator.

Rotation model: the plays-per-day targets in models.CATEGORIES are
per-SONG spin counts (standard radio rotation — a Power Current spins
5-6x/day, a Secondary 90s title about once a day). The generator works
in two layers:

1. Day plan — for each song, decide how many spins it gets today and in
   which hours, spreading spins evenly across the broadcast day with a
   sliding day offset so power titles walk across every hour and daypart
   over the week. Weekend Throwback rules (2/hour Sat-Sun) and Affiliate
   Fill (always the last song of the hour) are applied here. If a clock
   learned from the station's sample logs exists (see log_analyzer), its
   per-hour category flow overrides the built-in load.

2. Song selection — each hour's category slots are filled with concrete
   songs by rest order + the rule engine (tempo/mood/sound flow, artist
   and same-song separation, anti-stacking vs yesterday). Hard rules are
   never relaxed; a slot is re-cast to a fallback category or dropped
   before a hard rule is broken.
"""

from __future__ import annotations

import random
import zlib
from collections import defaultdict
from datetime import date

from .history import HistoryStore
from .models import CATEGORIES, DayLog, Slot, Song
from .rules import ScheduleContext, soft_penalty, violates_hard_rules

BROADCAST_HOURS = list(range(6, 24))   # 6am through 11pm
SLOTS_PER_HOUR = 12                    # music slots before the fill
FILL_SLOTS = 1                         # affiliate fill at the end of hour

# Stride (coprime with a 7-day week and the 18-hour day) so sliding
# rotations walk across every hour/daypart over the cycle.
SLIDE_STRIDE = 5


def _stable_hash(text: str) -> int:
    """Deterministic across processes (unlike built-in hash())."""
    return zlib.crc32(text.encode())


class Scheduler:
    def __init__(self, songs: list[Song], history: HistoryStore,
                 clock: dict | None = None, seed: int | None = None):
        self.songs = songs
        self.history = history
        self.clock = clock or {}
        self.rng = random.Random(seed)
        self.by_category: dict[str, list[Song]] = defaultdict(list)
        for s in songs:
            self.by_category[s.category].append(s)

    # ------------------------------------------------------------------
    # Layer 1: how many of each category in each hour
    # ------------------------------------------------------------------

    def _spins_today(self, song: Song, day: date) -> int:
        rule = CATEGORIES[song.category]
        weekday = day.weekday()
        if song.category == "TB":
            return 0  # throwbacks are planned per-hour, not per-song
        if rule.fill_only:
            return 0
        lo, hi = rule.min_plays_per_day, rule.max_plays_per_day
        # Alternate low/high by day and song so weekly totals average out
        # and "about once per day" songs skip some days.
        wobble = (day.toordinal() + _stable_hash(song.song_id)) % 2
        return hi if wobble else lo

    def _day_category_plan(self, day: date) -> dict[int, list[str]]:
        """Return {hour: [category codes]} for the day's music slots."""
        weekday = day.weekday()
        learned = self.clock.get(str(weekday))
        if learned:
            plan = {}
            for hour in BROADCAST_HOURS:
                cats = [c for c in learned.get(str(hour), [])
                        if c in CATEGORIES and self.by_category.get(c)]
                plan[hour] = cats
            if any(plan.values()):
                return plan

        hours = BROADCAST_HOURS
        n_hours = len(hours)
        weekend = weekday >= 5
        day_index = day.toordinal()
        demand: dict[int, list[str]] = {h: [] for h in hours}

        # Per-song spins aggregated into per-hour category demand, with a
        # per-song sliding offset so each title walks the clock.
        for code, songs in self.by_category.items():
            rule = CATEGORIES[code]
            if rule.fill_only or code == "TB":
                continue
            for j, song in enumerate(songs):
                spins = self._spins_today(song, day)
                if spins <= 0:
                    continue
                stride = SLIDE_STRIDE if rule.slides else 3
                offset = (day_index * stride + j * 7
                          + _stable_hash(song.song_id)) % n_hours
                for i in range(spins):
                    h = hours[(offset + round(i * n_hours / spins)) % n_hours]
                    demand[h].append(code)

        # Throwbacks: 2 per hour on the weekend, sparingly (2/day) weekdays.
        if self.by_category.get("TB"):
            if weekend:
                for h in hours:
                    demand[h] += ["TB"] * CATEGORIES["TB"].weekend_per_hour
            else:
                for i in range(2):
                    h = hours[(day_index * SLIDE_STRIDE + i * n_hours // 2)
                              % n_hours]
                    demand[h].append("TB")

        # Balance each hour to SLOTS_PER_HOUR: trim overloaded hours into
        # lighter ones (preserving power categories first), pad shortfalls.
        self._rebalance(demand, hours)
        return demand

    def _rebalance(self, demand: dict[int, list[str]],
                   hours: list[int]) -> None:
        keep_priority = ["TB", "PC", "PR", "PT", "P2K", "P90", "ST",
                         "S2K", "S90"]

        def overflow_hours():
            return [h for h in hours if len(demand[h]) > SLOTS_PER_HOUR]

        def light_hours():
            return sorted(hours, key=lambda h: len(demand[h]))

        for h in overflow_hours():
            demand[h].sort(key=lambda c: keep_priority.index(c)
                           if c in keep_priority else 99)
            extra = demand[h][SLOTS_PER_HOUR:]
            demand[h] = demand[h][:SLOTS_PER_HOUR]
            for code in extra:
                for target in light_hours():
                    if len(demand[target]) < SLOTS_PER_HOUR:
                        demand[target].append(code)
                        break

        pad_cycle = [c for c in ("ST", "S2K", "S90", "PT", "P2K", "P90")
                     if self.by_category.get(c)]
        if pad_cycle:
            for h in hours:
                i = 0
                while len(demand[h]) < SLOTS_PER_HOUR:
                    demand[h].append(pad_cycle[(h + i) % len(pad_cycle)])
                    i += 1

    # ------------------------------------------------------------------
    # Layer 2: pick concrete songs
    # ------------------------------------------------------------------

    def _pick(self, category: str, ctx: ScheduleContext,
              plays_today: dict[str, int], day: date) -> Song | None:
        rule = CATEGORIES[category]
        candidates = [s for s in self.by_category.get(category, [])
                      if rule.fill_only
                      or plays_today.get(s.song_id, 0) < rule.max_plays_per_day]
        legal = [s for s in candidates
                 if violates_hard_rules(s, ctx, self.history) is None]
        if not legal:
            return None

        def score(s: Song) -> float:
            p = soft_penalty(s, ctx, self.history)
            # Pull hard toward songs still under today's spin target;
            # strongly avoid exceeding it.
            target = self._spins_today(s, day) if s.category != "TB" else 1
            done = plays_today.get(s.song_id, 0)
            if done >= max(1, target):
                p += 200
            else:
                p -= 25 * (target - done)
            return p + self.rng.random()

        return min(legal, key=score)

    def _fallback_categories(self, category: str) -> list[str]:
        chart = {
            "PC": ["PR", "PT"], "PR": ["PC", "PT"],
            "PT": ["ST", "PR"], "ST": ["PT", "S2K"],
            "P2K": ["S2K", "PT"], "S2K": ["P2K", "ST"],
            "P90": ["S90", "P2K"], "S90": ["P90", "S2K"],
            "TB": ["S90", "S2K"], "AF": [],
        }
        return [c for c in chart.get(category, [])
                if self.by_category.get(c)]

    def schedule_day(self, day: date) -> DayLog:
        log = DayLog(date_iso=day.isoformat(), weekday=day.weekday())
        plan = self._day_category_plan(day)
        plays_today: dict[str, int] = defaultdict(int)
        prev_songs: list[Song] = []
        prev_minutes: list[int] = []

        for hour in BROADCAST_HOURS:
            hour_cats = list(plan.get(hour, []))[:SLOTS_PER_HOUR]
            self.rng.shuffle(hour_cats)
            if self.by_category.get("AF"):
                hour_cats += ["AF"] * FILL_SLOTS  # pinned to end of hour

            elapsed = 0
            hour_songs: list[Song] = []
            for position, category in enumerate(hour_cats):
                ctx = ScheduleContext(
                    date_iso=log.date_iso, hour=hour,
                    minute_of_day=hour * 60 + elapsed // 60,
                    prev_songs=prev_songs, prev_minutes=prev_minutes,
                    hour_songs=hour_songs)
                song = self._pick(category, ctx, plays_today, day)
                if song is None:
                    for alt in self._fallback_categories(category):
                        song = self._pick(alt, ctx, plays_today, day)
                        if song:
                            break
                if song is None and category != "AF":
                    # Last resort: any non-fill category rather than a
                    # hole in the hour. Hard rules still fully apply.
                    for alt in self.by_category:
                        if CATEGORIES[alt].fill_only or alt == category:
                            continue
                        song = self._pick(alt, ctx, plays_today, day)
                        if song:
                            break
                if song is None:
                    continue  # drop the slot rather than break a hard rule
                log.slots.append(Slot(hour=hour, position=position,
                                      song=song, start_seconds=elapsed))
                hour_songs.append(song)
                prev_songs.append(song)
                prev_minutes.append(hour * 60 + elapsed // 60)
                plays_today[song.song_id] += 1
                elapsed += song.length_seconds

        return log

    def schedule_days(self, start: date, days: int) -> list[DayLog]:
        logs = []
        for offset in range(days):
            day = date.fromordinal(start.toordinal() + offset)
            log = self.schedule_day(day)
            self.history.record_day(log)
            logs.append(log)
        self.history.save()
        return logs
