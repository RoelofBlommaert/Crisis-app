"""
Merge the three data sources into one static JSON file the frontend reads
directly, with no backend: App/data/dataset.json.

Reads (latest file per pattern, by filename date):
  Data/GDELT/gdelt_tension_history_*.csv   (falls back to gdelt_tension_*.csv)
  Data/GDACS/gdacs_events_matched_*.csv
  Data/ACLED/acled_monthly_*.csv

Per tracked country (Scripts/countries.py), produces one record with:
  - tension_series: the GDELT hourly volume/tone/conflict/disaster timeline
  - events: matched GDACS events (empty list where there's genuinely no
    confirmed-event coverage -- notably the conflict-driven countries;
    see Documentation/Relevance and function.txt for why)
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
      acled_component                               # up to 90, real ACLED severity + escalation (see below)
    + day_conflict_theme_share * 8 * confidence      # up to 8, GDELT corroboration
    + max(0, -day_avg_tone) * 1.5,                   # up to ~2, tone severity that day
    0, 100)

  disaster_signal = clamp(
      active_gdacs_alertscore * 25             # up to 75, only events active ON THAT DAY
    + day_disaster_theme_share * 40 * confidence,  # up to 40, was *100 w/ no dampening
    0, 100)

alert_level bands: Red >= 65, Orange >= 35, else Green.

**ACLED integration (ground-truth conflict severity, not a media proxy).**
`acled_component` is conflict_signal's dominant term (up to 90 of 100
points), mirroring how `active_gdacs_alertscore` dominates disaster_signal,
but is now a **continuous, baseline-relative** measure rather than a
4-tier band -- see "Baseline vs. escalation" below for why that changed.
Without real confirmed political violence, GDELT alone caps conflict_signal
at ~10, same principle as disaster_signal: pure media-mention noise
shouldn't be able to call something "High" on its own.

**Baseline vs. escalation (why this isn't just "this month's fatality
count").** An earlier version banded conflict_signal directly off that
month's ACLED fatalities (0 / 1-24 / 25-99 / 100+ -> 0/1/2/3, *25 each).
Checked against live data before shipping this replacement: Ukraine
(4008 fatalities that month), Sudan (876), and Haiti (103) all landed in
the same top tier and clipped conflict_signal at 100 -- indistinguishable,
despite being different by an order of magnitude, and despite two of
them (Sudan, Ukraine) actually running *below* their own recent average
that month (ratio 0.75-0.77 vs. their own trailing-12-month baseline) --
a stable, chronic war, not a fresh spike. Meanwhile Egypt, at only 10
fatalities, was invisible next to them despite being 3.3x its own
(near-zero) baseline -- a real, if small-scale, emerging signal that a
flat absolute count buried completely. For a "risk of imminent crisis"
lens this is backwards: absolute severity alone conflates "this has
always been terrible here" with "something new is happening here," and
loses the country that's actually changing.

Fixed by splitting into two explicit components, both derived from the
same monthly ACLED fatality series:
  baseline_fatalities = average fatalities/month over the 12 months
    before the scoring month (the country's own recent normal)
  escalation_ratio = scoring_fatalities / max(baseline_fatalities, 3)
    (floor of 3 avoids ratio blowups when a country's baseline is
    near zero)
  severity = clamp(75 * log10(scoring_fatalities + 1) / log10(5001), 0, 75)
    -- log-scaled against a fixed reference of 5000 fatalities/month
    (roughly the scale of the world's most severe active conflicts in
    recent years -- a fixed external anchor, deliberately NOT derived
    from our own 8-country sample, so it doesn't shift if countries are
    added/removed)
  escalation_bonus = clamp((escalation_ratio - 1) * 10, 0, 15)
    -- only rewards being ABOVE one's own baseline; below-baseline
    countries get zero bonus, not a penalty
  acled_component = severity + escalation_bonus   (0-90)
`severity` differentiates chronic-severity countries properly instead of
saturating (verified: Ukraine ~73, Sudan ~60, Haiti ~41, Lebanon ~29,
Egypt ~21 -- ordered by real scale, not clipped together). The
`escalation_bonus` is what actually flags "something newly happening" --
it's what pushes Egypt (severity 21 + bonus 15 = 36) into the same
territory as far-larger-but-stable conflicts, which is the "imminent"
signal this app is meant to surface, per the user's explicit ask that
scores reflect risk of imminent crisis rather than pure violence scale.
`baseline_fatalities`, `escalation_ratio`, and a qualitative trend label
("Escalating" / "Stable" / "Below baseline") are exposed in the output
alongside the score, not hidden inside it -- the point is to show the
data, not just compress it away (per STRATEGY.md).

Both components come from `Scripts/fetch_acled_hdx.py`'s monthly
political-violence series, using the most recent *complete* month (see
`acled_severity()` for why the latest available month is skipped --
ACLED/HDX's newest month is consistently far below trend across nearly
every tracked country, reporting/verification lag, not a real
across-the-board de-escalation). This one monthly value is applied to
every day in the current 7-8 day GDELT window (ACLED updates monthly,
GDELT daily) -- a deliberate, documented resolution mismatch: the
confirmed-severity floor holds steady within a month while GDELT's
day-to-day term still moves the score around it.

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
import math
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
    d = DATA_DIR / "GDACS"
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


def _months_ago(n: int) -> tuple:
    """(year, month_num) cutoff n months before today, for trimming the
    ACLED series to a recent window in the output."""
    now = datetime.now(timezone.utc)
    total = now.year * 12 + (now.month - 1) - n
    return (total // 12, total % 12 + 1)


def load_acled_monthly() -> dict:
    d = DATA_DIR / "ACLED"
    path = latest_file(d, "acled_monthly_*.csv")
    records = defaultdict(list)
    if not path:
        print("  ! no ACLED/HDX file found (run fetch_acled_hdx.py)")
        return records
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records[row["country"]].append(
                {
                    "year": int(row["year"]),
                    "month": row["month"],
                    "month_num": int(row["month_num"]),
                    "category": row["category"],
                    "events": int(row["events"]),
                    "fatalities": int(row["fatalities"]) if row["fatalities"] != "" else None,
                }
            )
    for name in records:
        records[name].sort(key=lambda r: (r["year"], r["month_num"]))
    print(f"  loaded ACLED/HDX data from {path.name} ({sum(len(v) for v in records.values())} rows)")
    return records


REFERENCE_MAX_FATALITIES = 5000  # fixed external anchor (severe active-conflict scale), not derived from our 8-country sample
BASELINE_MONTHS = 12


def _trend_label(ratio: float) -> str:
    if ratio >= 1.5:
        return "Escalating"
    if ratio <= 0.67:
        return "Below baseline"
    return "Stable"


def _category_scoring_month(records: list, category: str, scoring_period: str) -> dict:
    for r in records:
        if r["category"] == category and f"{r['year']}-{r['month']}" == scoring_period:
            return {"events": r["events"], "fatalities": r["fatalities"]}
    return {"events": 0, "fatalities": None if category == "demonstrations" else 0}


def acled_severity(records: list) -> dict:
    """Baseline-vs-escalation conflict severity from real ACLED
    political-violence fatalities -- see module docstring "Baseline vs.
    escalation" for why this replaced a flat fatality-count band, and
    why the latest available month is excluded (reporting lag, not real
    de-escalation)."""
    pv = [r for r in records if r["category"] == "political_violence"]
    if not pv:
        return {
            "acled_component": 0.0,
            "severity": 0.0,
            "escalation_bonus": 0.0,
            "escalation_ratio": 0.0,
            "trend": "Unknown",
            "baseline_fatalities": 0.0,
            "scoring_period": None,
            "scoring_fatalities": 0,
            "scoring_events": 0,
            "latest_period": None,
            "latest_is_provisional": False,
            "civilian_targeting": {"events": 0, "fatalities": 0},
            "demonstrations": {"events": 0, "fatalities": None},
        }

    scoring = pv[-2] if len(pv) >= 2 else pv[-1]
    latest = pv[-1]
    scoring_fatalities = scoring["fatalities"] or 0

    scoring_index = pv.index(scoring)
    baseline_window = pv[max(0, scoring_index - BASELINE_MONTHS):scoring_index]
    baseline_fatalities = (
        sum((r["fatalities"] or 0) for r in baseline_window) / len(baseline_window) if baseline_window else 0.0
    )

    escalation_ratio = scoring_fatalities / max(baseline_fatalities, 3)
    severity = _clamp(75 * math.log10(scoring_fatalities + 1) / math.log10(REFERENCE_MAX_FATALITIES + 1), 0, 75)
    escalation_bonus = _clamp((escalation_ratio - 1) * 10, 0, 15)

    scoring_period = f"{scoring['year']}-{scoring['month']}"
    return {
        "acled_component": severity + escalation_bonus,
        "severity": round(severity, 1),
        "escalation_bonus": round(escalation_bonus, 1),
        "escalation_ratio": round(escalation_ratio, 2),
        "trend": _trend_label(escalation_ratio),
        "baseline_fatalities": round(baseline_fatalities, 1),
        "scoring_period": scoring_period,
        "scoring_fatalities": scoring_fatalities,
        "scoring_events": scoring["events"],
        "latest_period": f"{latest['year']}-{latest['month']}",
        "latest_is_provisional": latest is not scoring,
        "civilian_targeting": _category_scoring_month(records, "civilian_targeting", scoring_period),
        "demonstrations": _category_scoring_month(records, "demonstrations", scoring_period),
    }


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


def score_country(events: list, tension_series: list, acled_component: float = 0.0) -> dict:
    """Returns {conflict_signal, disaster_signal, alert_level, driver,
    daily_scores}. Illustrative heuristic, not a statistical forecast --
    see the module docstring "Scoring" section for the formula and why
    each day is scored against events actually active that day rather
    than one flat weekly number. `acled_component` (0-90, real ACLED
    severity + escalation, see "Baseline vs. escalation" above) is the
    same value for every day in the window -- ACLED updates monthly,
    GDELT daily."""
    series = sorted(tension_series, key=lambda p: p["timestamp_utc"])

    by_day = defaultdict(list)
    for p in series:
        by_day[p["timestamp_utc"][:10]].append(p)

    daily_scores = []
    for day_str in sorted(by_day):
        day_points = by_day[day_str]
        day = datetime.fromisoformat(day_str).date()
        day_stats = _window_stats(day_points)
        day_tone = day_stats["avg_tone"] if day_stats["avg_tone"] is not None else 0.0
        confidence = min(1.0, day_stats["total_volume"] / MIN_CONFIDENT_VOLUME)

        conflict_signal = round(
            _clamp(
                acled_component
                + day_stats["conflict_share"] * 8 * confidence
                + max(0.0, -day_tone) * 1.5,
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
    theme_breakdown = load_theme_breakdown()
    acled = load_acled_monthly()

    countries_out = []
    for c in COUNTRIES:
        name = c["name"]
        tension_series = gdelt.get(name, [])
        events = gdacs.get(name, [])
        acled_records = acled.get(name, [])
        severity = acled_severity(acled_records)
        scores = score_country(events, tension_series, severity["acled_component"])

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
                "acled": {
                    "severity": severity,
                    # last 24 months per category, for the real multi-year chart
                    "monthly": [r for r in acled_records if (r["year"], r["month_num"]) >= _months_ago(24)],
                },
            }
        )

    # Per-source freshness/vintage -- surfaces the "near-real-time
    # engineering" track's honesty requirement without building live
    # infrastructure: show exactly how current each source actually is.
    all_timestamps = [p["timestamp_utc"] for series in gdelt.values() for p in series]
    gdacs_path = latest_file(DATA_DIR / "GDACS", "gdacs_events_matched_*.csv")
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
        "acled": {
            "kind": "real",
            "attribution": "Data from ACLED (acleddata.com), via HDX aggregated country files -- no login required. "
            "ACLED must be clearly credited wherever this data or a derivative is shown.",
            "note": "Monthly resolution only; the single most recent available month is excluded from scoring "
            "as provisional (reporting/verification lag consistently understates it) -- see Scripts/README.md.",
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
