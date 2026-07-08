"""Command-line interface.

  python -m musiclog analyze  --library data/library.xlsx \
                              --samples data/samples --clock data/clock.json

  python -m musiclog generate --library data/library.xlsx \
                              --start 2026-07-13 --days 7 --out logs \
                              [--clock data/clock.json] \
                              [--history state/history.json]

  python -m musiclog validate --library data/library.xlsx \
                              --start 2026-07-13 --days 7
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .export import render_summary, write_logs
from .history import HistoryStore
from .library import load_library
from .log_analyzer import build_clock, load_clock
from .scheduler import Scheduler
from .validate import validate_logs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="musiclog",
                                     description="Daily music log automation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_an = sub.add_parser("analyze",
                          help="learn the hour clock from sample .LOG files")
    p_an.add_argument("--library", required=True)
    p_an.add_argument("--samples", required=True,
                      help="directory containing sample .LOG files")
    p_an.add_argument("--clock", default="data/clock.json",
                      help="where to save the learned clock JSON")

    p_gen = sub.add_parser("generate", help="generate daily logs")
    p_gen.add_argument("--library", required=True)
    p_gen.add_argument("--start", default=date.today().isoformat(),
                       help="first day to schedule (YYYY-MM-DD)")
    p_gen.add_argument("--days", type=int, default=7)
    p_gen.add_argument("--out", default="logs")
    p_gen.add_argument("--clock", default=None,
                       help="clock JSON learned by 'analyze' (optional)")
    p_gen.add_argument("--history", default=None,
                       help="JSON file persisting 7-day rotation state")
    p_gen.add_argument("--station", default="KQBL")
    p_gen.add_argument("--seed", type=int, default=None)

    p_val = sub.add_parser("validate",
                           help="generate logs in-memory and audit the rules")
    p_val.add_argument("--library", required=True)
    p_val.add_argument("--start", default=date.today().isoformat())
    p_val.add_argument("--days", type=int, default=7)
    p_val.add_argument("--seed", type=int, default=None)

    args = parser.parse_args(argv)
    songs = load_library(args.library)
    print(f"Loaded {len(songs)} songs from {args.library}")

    if args.command == "analyze":
        clock = build_clock(args.samples, songs, args.clock)
        if not clock:
            print("No usable sample logs found (or no library matches).",
                  file=sys.stderr)
            return 1
        print(f"Learned clock for weekdays {sorted(clock)} -> {args.clock}")
        return 0

    start = date.fromisoformat(args.start)
    clock = load_clock(args.clock) if getattr(args, "clock", None) else None
    history = HistoryStore(getattr(args, "history", None))
    scheduler = Scheduler(songs, history, clock=clock,
                          seed=getattr(args, "seed", None))
    logs = scheduler.schedule_days(start, args.days)

    if args.command == "generate":
        paths = write_logs(logs, args.out, args.station)
        for log, path in zip(logs, paths):
            print(render_summary(log))
            print(f"  -> {path}")
        return 0

    # validate
    problems = validate_logs(logs, songs)
    for log in logs:
        print(render_summary(log))
    if problems:
        print(f"\n{len(problems)} rule issue(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nAll rules validated clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
