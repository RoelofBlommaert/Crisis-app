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

We score **one day at a time** rather than one flat weekly number, so a
week-old GDACS event can't quietly keep contributing to "today's" score
forever. For each calendar day present in the 7-day GDELT history:

  conflict_signal = clamp(
      day_conflict_theme_share * 70            # up to 70, share of that day's articles
    + max(0, -day_avg_tone) * 5                # up to 25, tone severity that day
    + max(0, day_volume / week_avg_volume - 1) * 15,  # up to 20, spike vs the week's own average
    0, 100)

  disaster_signal = clamp(
      active_gdacs_alertscore * 25             # up to 75, only events active ON THAT DAY
    + day_disaster_theme_share * 100,          # up to 25, disaster-theme article share that day
    0, 100)

A GDACS event only counts toward a given day's disaster_signal if that
day falls within the event's own fromdate/todate range (`event_active_on`
below) -- this is what fixes the original bug: Haiti's October-2025
cyclone and Turkey's October-2025 earthquake are still in the "matched
events" list (GDACS keeps recently-modified events listed for a while
after they end) but are correctly no longer active in the current 7-day
window, so they show up as *historical* events in the app rather than
inflating today's score.

`daily_scores` (7 entries, oldest first) carries this per-day breakdown;
the top-level conflict_signal/disaster_signal/alert_level/driver fields
are simply the most recent day's entry, so "today's" gauge and the
history strip are always the same underlying numbers.

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


ALERT_ORDER = {"Green": 1, "Orange": 2, "Red": 3}


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


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def event_active_on(event: dict, day) -> bool:
    """Whether a GDACS event's own fromdate/todate range covers `day`.
    This is what stops a months-old, still-listed event (GDACS keeps
    recently-modified events around after they're over) from inflating
    every subsequent day's disaster_signal forever."""
    start = _parse_date(event.get("fromdate"))
    end = _parse_date(event.get("todate")) or start
    if start is None:
        return False
    return start <= day <= end


def _alert_band(score: float) -> str:
    if score >= 60:
        return "Red"
    if score >= 30:
        return "Orange"
    return "Green"


def score_country(events: list, tension_series: list) -> dict:
    """Returns {conflict_signal, disaster_signal, alert_level, driver,
    daily_scores}. Illustrative heuristic, not a statistical forecast --
    see the module docstring "Scoring" section for the formula and why
    each day is scored against events actually active that day rather
    than one flat weekly number."""
    series = sorted(tension_series, key=lambda p: p["timestamp_utc"])
    week_stats = _window_stats(series)
    week_avg_volume = week_stats["avg_volume"] or 1.0

    by_day = defaultdict(list)
    for p in series:
        by_day[p["timestamp_utc"][:10]].append(p)

    daily_scores = []
    for day_str in sorted(by_day):
        day_points = by_day[day_str]
        day = datetime.fromisoformat(day_str).date()
        day_stats = _window_stats(day_points)
        day_tone = day_stats["avg_tone"] if day_stats["avg_tone"] is not None else 0.0
        volume_ratio = day_stats["avg_volume"] / week_avg_volume

        conflict_signal = round(
            _clamp(
                day_stats["conflict_share"] * 70 + max(0.0, -day_tone) * 5 + max(0.0, volume_ratio - 1) * 15,
                0,
                100,
            )
        )

        active_events = [e for e in events if e["alertlevel"] in ALERT_ORDER and event_active_on(e, day)]
        gdacs_alertscore = max((e["alertscore"] for e in active_events), default=0)
        disaster_signal = round(_clamp(gdacs_alertscore * 25 + day_stats["disaster_share"] * 100, 0, 100))

        daily_scores.append(
            {
                "date": day_str,
                "conflict_signal": conflict_signal,
                "disaster_signal": disaster_signal,
                "alert_level": _alert_band(max(conflict_signal, disaster_signal)),
                "driver": "conflict" if conflict_signal >= disaster_signal else "disaster",
            }
        )

    current = daily_scores[-1] if daily_scores else {
        "conflict_signal": 0,
        "disaster_signal": 0,
        "alert_level": "unknown",
        "driver": "conflict",
    }

    return {
        "conflict_signal": current["conflict_signal"],
        "disaster_signal": current["disaster_signal"],
        "alert_level": current["alert_level"],
        "driver": current["driver"],
        "daily_scores": daily_scores,
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

        latest_day = scores["daily_scores"][-1]["date"] if scores["daily_scores"] else None
        latest_day_parsed = datetime.fromisoformat(latest_day).date() if latest_day else None
        for e in events:
            e["is_current"] = bool(latest_day_parsed and event_active_on(e, latest_day_parsed))
        events.sort(key=lambda e: e["fromdate"], reverse=True)

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
