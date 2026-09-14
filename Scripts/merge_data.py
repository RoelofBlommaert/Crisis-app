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
says so explicitly. Per STRATEGY.md, automatic classification isn't even
required to work at this PoC stage -- this stays a transparent, inspectable
heuristic whose job is to illustrate how the raw signals *could* combine,
alongside showing the raw signals themselves (see `top_conflict_themes` /
`top_disaster_themes` below), not to be the definitive answer.

We score **one day at a time** rather than one flat weekly number, so a
week-old GDACS event can't quietly keep contributing to "today's" score
forever. For each calendar day present in the 7-day GDELT history:

  confidence = min(1, day_volume / MIN_CONFIDENT_VOLUME)   # dampens thin days

  conflict_signal = clamp(
      day_conflict_theme_share * 50 * confidence   # up to 50, was 70 w/ no dampening
    + max(0, -day_avg_tone) * 6                    # up to ~30, tone severity that day
    + max(0, day_volume / week_avg_volume - 1) * 15,  # up to 20, spike vs the week's own average
    0, 100)

  disaster_signal = clamp(
      active_gdacs_alertscore * 25             # up to 75, only events active ON THAT DAY
    + day_disaster_theme_share * 40 * confidence,  # up to 40, was *100 w/ no dampening
    0, 100)

alert_level bands: Red >= 65, Orange >= 35, else Green (raised from
60/30 -- see below).

**Recalibration history:** the original 70/100-weighted, undampened
version put almost every tracked country at Orange-or-above nearly every
day. Root cause, found by inspecting the live dataset: (a)
`conflict_share * 70` alone crosses the old Orange cutoff (30) once
~43% of a country's articles carry a conflict theme tag, and GDELT tags
an article with *every* country it mentions, so regional spillover
coverage (Egypt/Turkey appearing in Gaza-adjacent stories) clears that
easily without those countries being combatants; (b) `disaster_share *
100` with no confidence dampening let a single article on a low-volume
day swing the score by up to 100 points of pure sampling noise (Haiti,
at 1-10 articles/day, saw disaster_signal range 10-69 across a week with
**no active disaster event** driving any of it). The `confidence` factor
and lower weights above fix both.

A GDACS event only counts toward a given day's disaster_signal if that
day falls within the event's own fromdate/todate range (`event_active_on`
below) -- this is what fixes a separate, earlier bug: Haiti's October-2025
cyclone and Turkey's October-2025 earthquake are still in the "matched
events" list (GDACS keeps recently-modified events listed for a while
after they end) but are correctly no longer active in the current 7-day
window, so they show up as *historical* events in the app rather than
inflating today's score.

`daily_scores` (7-8 entries, oldest first) carries this per-day breakdown;
the top-level conflict_signal/disaster_signal/alert_level/driver fields
are simply the most recent day's entry, so "today's" gauge and the
history strip are always the same underlying numbers.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from countries import COUNTRIES

# Human-readable labels for the theme codes we tally (see
# fetch_gdelt_tension.py's CONFLICT_THEMES / DISASTER_THEME_PREFIX).
THEME_LABELS = {
    "ARMEDCONFLICT": "Armed conflict",
    "PROTEST": "Protests",
    "TERROR": "Terrorism-related coverage",
    "UNREST_BELLIGERENT": "Civil unrest",
    "WB_739_POLITICAL_VIOLENCE_AND_CIVIL_WAR": "Political violence & civil war",
    "WB_2432_FRAGILITY_CONFLICT_AND_VIOLENCE": "Fragility & conflict",
    "WB_2433_CONFLICT_AND_VIOLENCE": "Conflict & violence",
    "WB_2462_POLITICAL_VIOLENCE_AND_WAR": "Political violence & war",
    "WB_2467_TERRORISM": "Terrorism",
    "WB_2468_CONVENTIONAL_WAR": "Conventional war",
    "WB_2492_COUNTER_TERRORISM": "Counter-terrorism",
    "WB_2510_WAR_CRIMES": "War crimes",
}
DISASTER_THEME_PREFIX = "NATURAL_DISASTER_"


def theme_label(code: str) -> str:
    if code in THEME_LABELS:
        return THEME_LABELS[code]
    if code.startswith(DISASTER_THEME_PREFIX):
        suffix = code[len(DISASTER_THEME_PREFIX):]
        return re.sub(r"_", " ", suffix).title()
    return code

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


def load_theme_breakdown() -> dict:
    d = DATA_DIR / "GDELT"
    path = latest_file(d, "gdelt_theme_breakdown_*.csv")
    breakdown = defaultdict(list)
    if not path:
        print("  ! no GDELT theme-breakdown file found")
        return breakdown
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            breakdown[row["country"]].append(
                {
                    "code": row["theme_code"],
                    "label": theme_label(row["theme_code"]),
                    "category": row["category"],
                    "count": int(row["article_count"]),
                }
            )
    print(f"  loaded theme breakdown from {path.name} ({sum(len(v) for v in breakdown.values())} rows)")
    return breakdown


def load_synthetic_comms() -> dict:
    d = DATA_DIR / "Synthetic"
    path = latest_file(d, "comms_volume_*.csv")
    comms = defaultdict(list)
    if not path:
        print("  ! no synthetic comms-volume file found (run generate_synthetic_comms.py)")
        return comms
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            comms[row["country"]].append(
                {"date": row["date"], "synthetic_incoming_signals": int(row["synthetic_incoming_signals"])}
            )
    for name in comms:
        comms[name].sort(key=lambda r: r["date"])
    print(f"  loaded FICTIONAL comms volume from {path.name} ({sum(len(v) for v in comms.values())} rows)")
    return comms


ALERT_ORDER = {"Green": 1, "Orange": 2, "Red": 3}
MIN_CONFIDENT_VOLUME = 15


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _window_stats(points: list) -> dict:
    total_volume = sum(p["volume_article_count"] for p in points)
    tones = [p["avg_tone"] for p in points if p["avg_tone"] is not None]
    return {
        "total_volume": total_volume,
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
    if score >= 65:
        return "Red"
    if score >= 35:
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
        confidence = min(1.0, day_stats["total_volume"] / MIN_CONFIDENT_VOLUME)

        conflict_signal = round(
            _clamp(
                day_stats["conflict_share"] * 50 * confidence
                + max(0.0, -day_tone) * 6
                + max(0.0, volume_ratio - 1) * 15,
                0,
                100,
            )
        )

        active_events = [e for e in events if e["alertlevel"] in ALERT_ORDER and event_active_on(e, day)]
        gdacs_alertscore = max((e["alertscore"] for e in active_events), default=0)
        disaster_signal = round(
            _clamp(gdacs_alertscore * 25 + day_stats["disaster_share"] * 40 * confidence, 0, 100)
        )

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


def top_themes(theme_rows: list, category: str, total_volume: int, limit: int = 5) -> list:
    """Top theme codes by count, each annotated with its share of the
    country's total weekly article volume -- without that, a small
    absolute count (e.g. "Famine: 96 articles") reads as a real signal
    out of context, when it might be <2% of a high-volume country's week."""
    matching = [r for r in theme_rows if r["category"] == category]
    matching.sort(key=lambda r: -r["count"])
    for r in matching:
        r["share_of_week"] = round(r["count"] / total_volume, 4) if total_volume else 0.0
    return matching[:limit]


def main() -> None:
    print("Loading source data...")
    gdelt = load_gdelt_history()
    gdacs = load_gdacs_events()
    cbs = load_cbs_travel()
    theme_breakdown = load_theme_breakdown()
    synthetic_comms = load_synthetic_comms()

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

        country_themes = theme_breakdown.get(name, [])
        week_total_volume = sum(p["volume_article_count"] for p in tension_series)

        countries_out.append(
            {
                "name": name,
                "iso2": c["iso2"],
                "iso3": c["iso3"],
                "coords": COUNTRY_COORDS.get(name),
                **scores,
                "tension_series": tension_series,
                "top_conflict_themes": top_themes(country_themes, "conflict", week_total_volume),
                "top_disaster_themes": top_themes(country_themes, "disaster", week_total_volume),
                "events": events,
                "travel_baseline": cbs.get(
                    name, {"granularity": "none", "area_label": "", "series": []}
                ),
                "comms_volume": synthetic_comms.get(name, []),
            }
        )

    # Per-source freshness/vintage -- surfaces the "near-real-time
    # engineering" track's honesty requirement without building live
    # infrastructure: show exactly how current each source actually is.
    all_timestamps = [p["timestamp_utc"] for series in gdelt.values() for p in series]
    gdacs_path = latest_file(DATA_DIR / "Reliefweb and GDACS", "gdacs_events_matched_*.csv")
    cbs_path = latest_file(DATA_DIR / "Travel and flights", "cbs_travel_*.csv")
    all_cbs_years = [row["year"] for rows in cbs.values() for row in rows["series"]]
    data_sources = {
        "gdelt": {
            "kind": "real",
            "latest_timestamp_utc": max(all_timestamps) if all_timestamps else None,
            "earliest_timestamp_utc": min(all_timestamps) if all_timestamps else None,
        },
        "gdacs": {
            "kind": "real",
            "fetched_on": gdacs_path.stem.rsplit("_", 1)[-1] if gdacs_path else None,
        },
        "cbs_travel": {
            "kind": "real",
            "fetched_on": cbs_path.stem.rsplit("_", 1)[-1] if cbs_path else None,
            "latest_year": max(all_cbs_years) if all_cbs_years else None,
        },
        "comms_volume": {
            "kind": "synthetic",
            "note": "Fictional data generated for this demo -- not connected to any real NWW/consular system.",
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "One-time static snapshot, not a live-refreshing feed. "
            "conflict_signal/disaster_signal are an illustrative 0-100 heuristic, "
            "not a statistical forecast or probability -- see Documentation/ and Scripts/merge_data.py."
        ),
        "data_sources": data_sources,
        "countries": countries_out,
    }
    OUT_PATH.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    print(f"\nSaved {len(countries_out)} countries to {OUT_PATH}")


if __name__ == "__main__":
    main()
