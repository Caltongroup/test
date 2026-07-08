# musiclog — Daily Music Log Automation

End-to-end scheduler that produces daily music logs for a commercial
radio station (built for KQBL, a country FM). It reads the active
library spreadsheet, learns the station's hour clock from sample
`.LOG` files, and generates rule-clean daily logs with a rolling
7-day rotation memory.

## Quick start (demo data included)

```bash
pip install -r requirements.txt

# Generate a week of logs with the bundled demo library
python -m musiclog generate --library data/demo_library.csv \
    --start 2026-07-13 --days 7 --out logs --history state/history.json

# Audit a generated week against every programming rule
python -m musiclog validate --library data/demo_library.csv \
    --start 2026-07-13 --days 7
```

## Using the real KQBL data

Copy the station files (they live on the studio share
`\\10.18.50.98\Jock_Folders\James\`) into `data/`:

```
data/KQBL Active Library July 6 2026.xlsx
data/samples/KQBL MONDAY SAMPLE LOG.LOG
data/samples/... (one per weekday)
```

Then:

```bash
# 1. Learn the hour clock (slots per hour + category flow) from the
#    sample logs, cross-referenced against the library
python -m musiclog analyze --library "data/KQBL Active Library July 6 2026.xlsx" \
    --samples data/samples --clock data/clock.json

# 2. Generate logs that follow the learned clock
python -m musiclog generate --library "data/KQBL Active Library July 6 2026.xlsx" \
    --clock data/clock.json --start 2026-07-13 --days 7 \
    --out logs --history state/history.json
```

The library loader matches headers fuzzily (Title/Song Title,
Category/Rotation, Tempo/Tempo Code, …) and normalizes category labels
("Power Current", "90's Power", "Throwbacks", …) — see
`musiclog/library.py` if your column names differ.

## Programming rules enforced

**Hard rules — never broken** (a slot is re-cast or dropped first):

- **Tempo**: never two slow songs (tempo 1-2) back to back; two fast
  songs (tempo 4-5) together is fine, three is not.
- **Mood**: happy songs never sit next to sad/angry songs; neutral
  bridges both.
- **Artist separation**: 35 min for core artists, 45 min for secondary.
- **Same-song separation**: 150 min minimum between spins of a title.
- **Anti-stacking**: a song never plays in the same hour as the day
  before (habitual listeners hear variety at their usual time).
- **Affiliate Fill**: always the last song of the hour, never higher.

**Soft rules — minimized by scoring**:

- Pop-leaning songs rarely adjacent (Mainstream is the core sound).
- Eras spaced: new next to old, penalty for same-era pairs.
- Mood balance within each hour; no dreary sad runs.
- Daypart-level anti-stacking day over day (strong for low-rotation
  songs, mild for powers that must revisit dayparts).
- Rest order: least-recently-played songs first.

**Rotation targets (spins per song per day)**:

| Category | Spins/day | Notes |
|---|---|---|
| Power Current | 5-6 | sliding day offset across hours |
| Power Recurrent | 3-4 | slides across dayparts over 7 days |
| Power 20-Teens | 2-3 | |
| Secondary Teens | 1-2 | |
| Power 2000s | 1-2 | |
| Secondary 2000s | ~1 | |
| Power 90s | 1-2 | |
| Secondary 90s | ~1 | |
| Throwback | sparingly weekdays; **2 per hour Sat-Sun** | |
| Affiliate Fill | end of every hour | |

The `--history` file persists a rolling 7-day play history so
consecutive daily runs keep artist separation, anti-stacking, and the
sliding rotations honest across the week. Run with the same history
file every day.

## Layout

```
musiclog/
  models.py        # Song / category / slot data model, rotation targets
  library.py       # xlsx/csv library loader with fuzzy headers
  log_analyzer.py  # learns the hour clock from sample .LOG files
  rules.py         # hard-rule checks + soft-penalty scoring
  scheduler.py     # day planner + song selection engine
  history.py       # rolling 7-day play history (JSON)
  validate.py      # full-week rule audit
  export.py        # .LOG file writer
  cli.py           # analyze / generate / validate commands
scripts/make_demo_library.py   # regenerates data/demo_library.csv
tests/             # end-to-end rule tests (pytest)
```
