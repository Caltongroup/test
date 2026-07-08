"""Analyze sample .LOG files to learn the station's hour clock.

Sample logs (e.g. "KQBL MONDAY SAMPLE LOG.LOG") are cross-referenced
against the library by title/artist so each logged song can be assigned
a category. From that we derive, per weekday and per hour:

  * how many music slots the hour carries, and
  * the category flow (which categories appear at which positions).

The result is saved as a JSON "clock" file the scheduler consumes. If no
sample logs are available, the scheduler falls back to a built-in clock
derived from the category rotation targets.

Sample logs are plain text; each music line is expected to carry a
scheduled time (H:MM or HH:MM:SS) followed by title/artist fields.
Non-music lines (spots, jingles, top-of-hour IDs) simply won't match the
library and are ignored.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .models import Song

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\b")

WEEKDAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                 "FRIDAY", "SATURDAY", "SUNDAY"]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def weekday_from_filename(path: Path) -> int | None:
    upper = path.name.upper()
    for i, name in enumerate(WEEKDAY_NAMES):
        if name in upper:
            return i
    return None


def analyze_log(path: Path, songs: list[Song]) -> dict[int, list[str]]:
    """Return {hour: [category, ...]} for one sample log."""
    by_title = {_norm(s.title): s for s in songs}
    hours: dict[int, list[str]] = defaultdict(list)
    for line in path.read_text(errors="replace").splitlines():
        m = TIME_RE.search(line)
        if not m:
            continue
        hour = int(m.group(1)) % 24
        rest = _norm(line[m.end():])
        for key, song in by_title.items():
            if key and key in rest:
                hours[hour].append(song.category)
                break
    return dict(hours)


def build_clock(sample_dir: str | Path, songs: list[Song],
                out_path: str | Path | None = None) -> dict:
    """Analyze every .LOG under sample_dir into a weekday->hour clock."""
    sample_dir = Path(sample_dir)
    clock: dict[str, dict[str, list[str]]] = {}
    for log_file in sorted(sample_dir.glob("*.LOG")) + \
            sorted(sample_dir.glob("*.log")):
        weekday = weekday_from_filename(log_file)
        if weekday is None:
            continue
        hours = analyze_log(log_file, songs)
        if hours:
            clock[str(weekday)] = {str(h): cats for h, cats in
                                   sorted(hours.items())}
    if out_path and clock:
        Path(out_path).write_text(json.dumps(clock, indent=2))
    return clock


def load_clock(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())
