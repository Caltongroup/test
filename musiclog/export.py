"""Write DayLog objects out as .LOG text files and a human summary."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import CATEGORIES, DayLog

DAY_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
             "FRIDAY", "SATURDAY", "SUNDAY"]


def log_filename(log: DayLog, station: str = "KQBL") -> str:
    d = date.fromisoformat(log.date_iso)
    return f"{station} {DAY_NAMES[log.weekday]} {d:%m%d%y}.LOG"


def render_log(log: DayLog, station: str = "KQBL") -> str:
    d = date.fromisoformat(log.date_iso)
    lines = [
        f"{station} MUSIC LOG  {DAY_NAMES[log.weekday]}  {d:%m/%d/%Y}",
        "=" * 78,
    ]
    current_hour = None
    for slot in log.slots:
        if slot.hour != current_hour:
            current_hour = slot.hour
            lines.append("")
            lines.append(f"--- {slot.hour:02d}:00 HOUR ---")
        s = slot.song
        m, sec = divmod(s.length_seconds, 60)
        lines.append(
            f"{slot.time_str}  {s.song_id:<8} {s.title[:30]:<30} "
            f"{s.artist[:24]:<24} {m}:{sec:02d}  {s.category}")
    lines.append("")
    return "\n".join(lines)


def render_summary(log: DayLog) -> str:
    counts: dict[str, int] = {}
    for slot in log.slots:
        counts[slot.song.category] = counts.get(slot.song.category, 0) + 1
    parts = [f"{code}({CATEGORIES[code].name}): {n}"
             for code, n in sorted(counts.items())]
    return f"{log.date_iso} [{DAY_NAMES[log.weekday]}] " \
           f"{len(log.slots)} songs — " + ", ".join(parts)


def write_logs(logs: list[DayLog], out_dir: str | Path,
               station: str = "KQBL") -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for log in logs:
        path = out_dir / log_filename(log, station)
        path.write_text(render_log(log, station))
        paths.append(path)
    return paths
