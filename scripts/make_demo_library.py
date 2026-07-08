"""Generate data/demo_library.csv — a synthetic country library sized
like a real active library so the app runs end-to-end without the
station's spreadsheet. Replace with 'KQBL Active Library July 6 2026.xlsx'
for production use."""

import csv
import random
from pathlib import Path

rng = random.Random(20260707)

FIRST = ["Wade", "Colt", "Sadie", "Lainey", "Boone", "Merle", "Dolly Jo",
         "Tucker", "Rhett", "Casey", "June", "Hank Lee", "Shelby", "Dutch",
         "Reba Mae", "Cash", "Willa", "Sterling", "Maren Kate", "Jethro"]
LAST = ["Callahan", "Whitfield", "Monroe", "Prescott", "Delaney", "Hart",
        "Boggs", "Ryder", "Lawson", "McCrae", "Stapleton Jr.", "Vann",
        "Ellison", "Krause", "Redding", "Sloane", "Tatum", "Underhill"]
WORDS = ["Dirt Road", "Neon", "Tailgate", "Whiskey", "Sundown", "Bonfire",
         "Heartland", "Blue Jeans", "Backroads", "Honky Tonk", "Midnight",
         "River", "Small Town", "Front Porch", "Gravel", "Amen", "Dixie",
         "Firefly", "Rodeo", "Silver Dollar", "Homegrown", "Wildflower",
         "Cold Beer", "Church Bells", "Two-Lane", "Moonshine", "Tin Roof",
         "Dashboard", "Barefoot", "Long Gone"]

# (category, count, year range)
PLAN = [
    ("Power Current", 8, (2025, 2026)),
    ("Power Recurrent", 10, (2023, 2025)),
    ("Power 20-Teens", 18, (2010, 2019)),
    ("Secondary Teens", 18, (2010, 2019)),
    ("Power 2000s", 12, (2000, 2009)),
    ("Secondary 2000s", 12, (2000, 2009)),
    ("Power 90s", 8, (1990, 1999)),
    ("Secondary 90s", 10, (1990, 1999)),
    ("Throwback", 20, (1985, 2005)),
    ("Affiliate Fill", 12, (2005, 2020)),
]

MOODS = ["Happy", "Happy", "Neutral", "Neutral", "Neutral", "Sad/Angry"]
SOUNDS = ["Mainstream", "Mainstream", "Mainstream", "Pop"]

artists = [f"{f} {l}" for f in FIRST for l in LAST]
rng.shuffle(artists)
artist_pool = iter(artists)
artist_of = {}

rows = []
n = 0
used_titles = set()
for category, count, (y0, y1) in PLAN:
    for _ in range(count):
        n += 1
        while True:
            title = " ".join(rng.sample(WORDS, rng.choice([1, 2])))
            if title not in used_titles:
                used_titles.add(title)
                break
        # Reuse some artists across categories so separation rules bite.
        if rng.random() < 0.35 and artist_of:
            artist = rng.choice(list(artist_of))
        else:
            artist = next(artist_pool)
        artist_of.setdefault(artist, None)
        tier = "Core" if rng.random() < 0.45 else "Secondary"
        length = rng.randint(170, 250)
        rows.append({
            "Song ID": f"KQ{n:04d}",
            "Title": title,
            "Artist": artist,
            "Category": category,
            "Tempo": rng.choice([1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5]),
            "Sound": rng.choice(SOUNDS),
            "Mood": rng.choice(MOODS),
            "Year": rng.randint(y0, y1),
            "Artist Tier": tier,
            "Length": f"{length // 60}:{length % 60:02d}",
        })

out = Path(__file__).resolve().parent.parent / "data" / "demo_library.csv"
out.parent.mkdir(exist_ok=True)
with open(out, "w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(f"Wrote {len(rows)} songs -> {out}")
