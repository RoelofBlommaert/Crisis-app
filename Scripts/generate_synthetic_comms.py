"""
Generate a FICTIONAL "incoming communication volume" layer (e.g. consular
calls/signals) per tracked country, per day.

Why this exists: STRATEGY.md names combining the tension signal with the
volume of incoming communication as core to the primary user's (crisis
coordinator) actual workflow, and explicitly allows synthetic/fictional
data for sources whose real access isn't confirmed yet (calls, RNI,
CBS-flights). This is NOT connected to any real NWW/consular system --
it exists purely to demonstrate what combining such a layer with the
other (real) signals could look like.

Deterministic, not random-per-run: seeded per country+date so re-running
this script produces the same numbers, rather than different fake data
every time. Loosely scaled with that day's real GDELT article volume (so
the demo isn't arbitrary) plus a small seeded jitter, on top of a fixed
per-country baseline (a consulate gets *some* calls on a calm day too).

Output: Data/Synthetic/comms_volume_<date>.csv
Columns: country, date, synthetic_incoming_signals
"""

import csv
import random
from datetime import date
from pathlib import Path

from countries import COUNTRIES

REPO_ROOT = Path(__file__).resolve().parent.parent
GDELT_DIR = REPO_ROOT / "Data" / "GDELT"
OUT_DIR = REPO_ROOT / "Data" / "Synthetic"

BASE_SIGNALS = 8  # a consulate/desk gets some baseline volume even on a calm day
VOLUME_SCALE = 0.25  # how strongly real article volume nudges the fictional count
JITTER_FRACTION = 0.25  # +/- 25% seeded jitter


def latest_file(directory: Path, pattern: str):
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def load_daily_volume() -> dict:
    """{country: {date_str: total_article_volume}} from the GDELT history."""
    path = latest_file(GDELT_DIR, "gdelt_tension_history_*.csv") or latest_file(GDELT_DIR, "gdelt_tension_*.csv")
    daily = {}
    if not path:
        print("  ! no GDELT file found -- synthetic layer will use baseline only")
        return daily
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            country = row["country"]
            day = row["timestamp_utc"][:10]
            daily.setdefault(country, {})
            daily[country][day] = daily[country].get(day, 0) + int(row["volume_article_count"])
    return daily


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_volume = load_daily_volume()

    rows = []
    for c in COUNTRIES:
        name = c["name"]
        days = daily_volume.get(name, {})
        for day_str in sorted(days):
            rng = random.Random(f"{name}-{day_str}")  # deterministic per country+day
            jitter = 1 + rng.uniform(-JITTER_FRACTION, JITTER_FRACTION)
            signals = round((BASE_SIGNALS + VOLUME_SCALE * days[day_str]) * jitter)
            rows.append({"country": name, "date": day_str, "synthetic_incoming_signals": max(0, signals)})

    out_path = OUT_DIR / f"comms_volume_{date.today().isoformat()}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["country", "date", "synthetic_incoming_signals"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} FICTIONAL comms-volume rows to {out_path}")
    print("Reminder: this data is synthetic and not connected to any real NWW/consular system.")


if __name__ == "__main__":
    main()
