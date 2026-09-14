"""
Merge the four data sources into one static JSON file the frontend reads
directly, with no backend: App/data/dataset.json.

Reads (latest file per pattern, by filename date):
  Data/GDELT/gdelt_tension_history_*.csv   (falls back to gdelt_tension_*.csv)
  Data/Reliefweb and GDACS/gdacs_events_matched_*.csv
  Data/Travel and flights/cbs_travel_*.csv

Per tracked country (Scripts/countries.py), produces one record with:
  - tension_series: the GDELT hourly volume/tone timeline
  - events: matched GDACS events (empty list where there's genuinely no
    confirmed-event coverage -- notably the conflict-driven countries;
    see Documentation/Relevance and function.txt for why)
  - travel_baseline: CBS series + its granularity flag (country vs region),
    preserved as-is so the frontend can show the right caveat rather than
    presenting region data as if it were country-specific
  - a simple illustrative alert_level (see LEVEL note below)

This is a one-time snapshot generator, not a live pipeline: run it once
after refreshing the source CSVs, then commit App/data/dataset.json.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from countries import COUNTRIES

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "Data"
OUT_PATH = REPO_ROOT / "App" / "data" / "dataset.json"

# Approximate marker coordinates for the map view (capital or centroid).
# GDELT/GDACS/CBS carry no coordinates of their own.
COUNTRY_COORDS = {
    "Turkey": [39.0, 35.0],
    "Ukraine": [49.0, 31.5],
    "Lebanon": [33.85, 35.85],
    "Israel": [31.5, 34.8],
    "Egypt": [26.8, 30.8],
    "Sudan": [15.5, 30.5],
    "Haiti": [18.95, -72.3],
    "Thailand": [15.0, 101.0],
}


def latest_file(directory: Path, pattern: str) -> Path | None:
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def load_gdelt_history() -> dict:
    d = DATA_DIR / "GDELT"
    path = latest_file(d, "gdelt_tension_history_*.csv") or latest_file(d, "gdelt_tension_*.csv")
    series = defaultdict(list)
    if not path:
        print("  ! no GDELT file found")
        return series
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            series[row["country"]].append(
                {
                    "timestamp_utc": row["timestamp_utc"],
                    "volume_article_count": int(row["volume_article_count"]),
                    "avg_tone": float(row["avg_tone"]) if row["avg_tone"] != "" else None,
                }
            )
    for name in series:
        series[name].sort(key=lambda r: r["timestamp_utc"])
    print(f"  loaded GDELT history from {path.name} ({sum(len(v) for v in series.values())} rows)")
    return series


def load_gdacs_events() -> dict:
    d = DATA_DIR / "Reliefweb and GDACS"
    path = latest_file(d, "gdacs_events_matched_*.csv")
    events = defaultdict(list)
    if not path:
        print("  ! no GDACS matched file found")
        return events
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for name in row["matched_countries"].split(";"):
                events[name].append(
                    {
                        "eventtype": row["eventtype"],
                        "eventname": row["eventname"],
                        "alertlevel": row["alertlevel"],
                        "alertscore": int(row["alertscore"]) if row["alertscore"] else 0,
                        "fromdate": row["fromdate"],
                        "todate": row["todate"],
                        "description": row["description"],
                    }
                )
    print(f"  loaded GDACS events from {path.name} ({sum(len(v) for v in events.values())} matched rows)")
    return events


def load_cbs_travel() -> dict:
    d = DATA_DIR / "Travel and flights"
    path = latest_file(d, "cbs_travel_*.csv")
    baseline = {}
    if not path:
        print("  ! no CBS travel file found")
        return baseline
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["crisis_country"]
            baseline.setdefault(
                name,
                {"granularity": row["cbs_granularity"], "area_label": row["cbs_area_label"], "series": []},
            )
            baseline[name]["series"].append(
                {
                    "year": row["year"],
                    "dutch_travellers_x1000": row["dutch_travellers_x1000"],
                    "total_trips_x1000": row["total_trips_x1000"],
                    "total_overnight_stays_x1000000": row["total_overnight_stays_x1000000"],
                    "total_spend_eur_million": row["total_spend_eur_million"],
                }
            )
    for name in baseline:
        baseline[name]["series"].sort(key=lambda r: r["year"])
    print(f"  loaded CBS travel from {path.name} ({len(baseline)} countries)")
    return baseline


def alert_level_for(events: list, tension_series: list) -> str:
    """Illustrative only -- see Documentation known limitations. Confirmed
    GDACS alert level wins; otherwise a rough tone-based fallback so
    conflict countries (no GDACS coverage) still get a signal."""
    order = {"Green": 1, "Orange": 2, "Red": 3}
    confirmed = [e["alertlevel"] for e in events if e["alertlevel"] in order]
    if confirmed:
        return max(confirmed, key=lambda level: order[level])

    tones = [p["avg_tone"] for p in tension_series if p["avg_tone"] is not None]
    if not tones:
        return "unknown"
    avg = sum(tones) / len(tones)
    if avg <= -8:
        return "Red"
    if avg <= -4:
        return "Orange"
    return "Green"


def main() -> None:
    print("Loading source data...")
    gdelt = load_gdelt_history()
    gdacs = load_gdacs_events()
    cbs = load_cbs_travel()

    countries_out = []
    for c in COUNTRIES:
        name = c["name"]
        tension_series = gdelt.get(name, [])
        events = gdacs.get(name, [])
        countries_out.append(
            {
                "name": name,
                "iso2": c["iso2"],
                "iso3": c["iso3"],
                "coords": COUNTRY_COORDS.get(name),
                "alert_level": alert_level_for(events, tension_series),
                "tension_series": tension_series,
                "events": events,
                "travel_baseline": cbs.get(
                    name, {"granularity": "none", "area_label": "", "series": []}
                ),
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "One-time static snapshot, not a live-refreshing feed. See Documentation/ for data source caveats.",
        "countries": countries_out,
    }
    OUT_PATH.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"\nSaved {len(countries_out)} countries to {OUT_PATH}")


if __name__ == "__main__":
    main()
