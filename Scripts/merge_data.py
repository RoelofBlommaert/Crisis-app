"""
Merge the four data sources into one static JSON file the frontend reads
directly, with no backend: App/data/dataset.json.

Reads (latest file per pattern, by filename date):
  Data/GDELT/gdelt_tension_history_*.csv   (falls back to gdelt_tension_*.csv)
  Data/Reliefweb and GDACS/gdacs_events_matched_*.csv
  Data/Travel and flights/cbs_travel_*.csv

Per tracked country (Scripts/countries.py), produces one record with:
  - tension_series: the GDELT hourly volume/tone/conflict/disaster timeline
  - events: matched GDACS events (empty list where there's genuinely no
    confirmed-event coverage -- notably the conflict-driven countries;
    see Documentation/Relevance and function.txt for why)
  - travel_baseline: CBS series + its granularity flag (country vs region),
    preserved as-is so the frontend can show the right caveat rather than
    presenting region data as if it were country-specific
  - conflict_signal / disaster_signal: two illustrative 0-100 gauges (see
    scoring section below) and an overall alert_level derived from them

This is a one-time snapshot generator, not a live pipeline: run it once
after refreshing the source CSVs, then commit App/data/dataset.json.

## Scoring: conflict_signal / disaster_signal (illustrative, not a forecast)

These are NOT a statistical probability of conflict or disaster -- there
is no calibrated base rate or validated model behind them, and the app
says so explicitly. They're a transparent, inspectable heuristic meant to
replace the earlier (buggy) approach of color-coding countries by their
flat 7-day-average GDELT tone: that stayed "Green" for Israel/Lebanon
even during heavy negative coverage, because a week-long average dilutes
acute events with routine reporting (Lebanon's week-average tone was
only -2.9, nowhere near the old -4 threshold).

Instead, for each country we split the 7-day hourly series into the most
recent 24h ("recent") vs. the preceding ~6 days ("baseline"), and score:

  conflict_signal = clamp(
      recent_conflict_theme_share * 70          # up to 55, share of recent
    + max(0, -recent_avg_tone) * 5              # up to 25, tone severity
    + max(0, volume_ratio - 1) * 15,            # up to 20, recent vs baseline spike
    0, 100)

  disaster_signal = clamp(
      gdacs_alertscore * 25                     # up to 75, confirmed GDACS event wins
    + recent_disaster_theme_share * 100,        # up to 25, disaster-theme article share
    0, 100)

alert_level (Green/Orange/Red) = whichever band max(conflict_signal,
disaster_signal) falls in (>=60 Red, >=30 Orange, else Green) -- so a
confirmed Red GDACS event or a strong conflict-theme spike both surface
the same way, and the frontend shows which signal is driving it.
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
                    "conflict_article_count": int(row.get("conflict_article_count") or 0),
                    "disaster_article_count": int(row.get("disaster_article_count") or 0),
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


RECENT_WINDOW_HOURS = 24


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _window_stats(points: list) -> dict:
    total_volume = sum(p["volume_article_count"] for p in points)
    tones = [p["avg_tone"] for p in points if p["avg_tone"] is not None]
    return {
        "avg_volume": total_volume / len(points) if points else 0.0,
        "avg_tone": sum(tones) / len(tones) if tones else None,
        "conflict_share": (sum(p["conflict_article_count"] for p in points) / total_volume) if total_volume else 0.0,
        "disaster_share": (sum(p["disaster_article_count"] for p in points) / total_volume) if total_volume else 0.0,
    }


def score_country(events: list, tension_series: list) -> dict:
    """Returns {conflict_signal, disaster_signal, alert_level, driver}.
    Illustrative heuristic, not a statistical forecast -- see the module
    docstring "Scoring" section for the formula and why it replaced the
    earlier flat-average-tone approach."""
    series = sorted(tension_series, key=lambda p: p["timestamp_utc"])
    recent = _window_stats(series[-RECENT_WINDOW_HOURS:])
    baseline = _window_stats(series[:-RECENT_WINDOW_HOURS]) if len(series) > RECENT_WINDOW_HOURS else recent

    volume_ratio = (recent["avg_volume"] / baseline["avg_volume"]) if baseline["avg_volume"] else 1.0
    recent_tone = recent["avg_tone"] if recent["avg_tone"] is not None else 0.0

    conflict_signal = round(
        _clamp(
            recent["conflict_share"] * 70
            + max(0.0, -recent_tone) * 5
            + max(0.0, volume_ratio - 1) * 15,
            0,
            100,
        )
    )

    order = {"Green": 1, "Orange": 2, "Red": 3}
    gdacs_alertscore = max((e["alertscore"] for e in events if e["alertlevel"] in order), default=0)
    disaster_signal = round(_clamp(gdacs_alertscore * 25 + recent["disaster_share"] * 100, 0, 100))

    top_signal = max(conflict_signal, disaster_signal)
    if top_signal >= 60:
        alert_level = "Red"
    elif top_signal >= 30:
        alert_level = "Orange"
    else:
        alert_level = "Green"

    return {
        "conflict_signal": conflict_signal,
        "disaster_signal": disaster_signal,
        "alert_level": alert_level,
        "driver": "conflict" if conflict_signal >= disaster_signal else "disaster",
    }


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
        scores = score_country(events, tension_series)
        countries_out.append(
            {
                "name": name,
                "iso2": c["iso2"],
                "iso3": c["iso3"],
                "coords": COUNTRY_COORDS.get(name),
                **scores,
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
        "note": (
            "One-time static snapshot, not a live-refreshing feed. "
            "conflict_signal/disaster_signal are an illustrative 0-100 heuristic, "
            "not a statistical forecast or probability -- see Documentation/ and Scripts/merge_data.py."
        ),
        "countries": countries_out,
    }
    OUT_PATH.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"\nSaved {len(countries_out)} countries to {OUT_PATH}")


if __name__ == "__main__":
    main()
