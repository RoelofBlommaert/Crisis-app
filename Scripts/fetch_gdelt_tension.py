"""
Pull a GDELT-based "tension score" (article volume + average tone) per
country, from GDELT's raw bulk export files rather than the DOC 2.0
query API.

Why not the DOC 2.0 API: it enforces "one request every 5 seconds," but
in practice it can hard-block a shared/cloud IP for an extended period
regardless of backoff (see Scripts/README.md for what we hit and what
GDELT's own blog says about it). It's meant for occasional interactive
lookups, not repeated/scripted polling.

Data source instead: GDELT 2.0 Global Knowledge Graph (GKG) bulk files,
published every 15 minutes, no key, no rate limit (plain files on GCS):
  https://data.gdeltproject.org/gdeltv2/lastupdate.txt          -> latest 3 filenames
  https://data.gdeltproject.org/gdeltv2/<timestamp>.gkg.csv.zip -> that 15-min batch

Each row is one article; V2Locations lists (type#name#countrycode#...)
per place mentioned (FIPS 10-4 country codes); V2Tone's first value is
that article's average tone (-100..+100); V2Themes lists GKG theme tags
(code,offset;code,offset;...). We match articles whose V2Locations
includes one of our target countries' FIPS code, and aggregate per
country per 15-minute file: article count, mean tone, and how many of
those articles carry a conflict-related or natural-disaster-related
theme tag (CONFLICT_THEMES / DISASTER_THEME_PREFIX below) -- this is
what lets the app separate "political/conflict signal" from "natural
disaster signal" instead of relying on tone alone. Codes were picked by
downloading a live GKG file and checking which ones actually appear
(not from documentation alone) -- see Scripts/README.md.

This trades DOC 2.0's ~3-month daily timeline for a short, high-resolution
(15-min) recent window -- see LOOKBACK_FILES below. Run this on a
schedule (hourly/daily cron, cloud scheduler, etc.) and append the output
to build up real history over time; see Scripts/README.md for the general
"how do I poll GDELT hourly" guidance this implies.

Backfill mode (--backfill): instead of only grabbing the most recent
LOOKBACK_FILES, walks back BACKFILL_DAYS days and downloads one GKG file
per hour (the top-of-hour :00 file), computing each historical filename
directly rather than following lastupdate.txt. Same bulk-file mechanism,
no key, no observed rate limit either way -- this just reaches further
back in time. Used once to seed a real multi-day trend for the app since
this project isn't running a recurring scheduled pull.

Also writes a small summary, `gdelt_theme_breakdown_<date>.csv`
(country, theme_code, category, article_count): a per-theme-code tally
across the whole run, so the app can show *what* is happening (e.g.
"ARMEDCONFLICT: 312 articles, PROTEST: 89, TERROR: 45") instead of just
a compressed share number. One summary for the whole run, not one row
per 15-min file.

Output: Data/GDELT/gdelt_tension_<date>.csv (normal mode)
        Data/GDELT/gdelt_tension_history_<date>.csv (--backfill mode)
        Data/GDELT/gdelt_theme_breakdown_<date>.csv (both modes)
Columns: country, timestamp_utc, date, volume_article_count, avg_tone,
         conflict_article_count, disaster_article_count
"""

import argparse
import csv
import io
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from countries import COUNTRIES

LASTUPDATE_URL = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
FILE_URL_TEMPLATE = "https://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip"
LOOKBACK_FILES = 8  # 8 x 15min = last ~2 hours; raise for a longer window
BACKFILL_DAYS = 7  # --backfill: how many days back to pull, at hourly resolution
BACKFILL_DELAY_SECONDS = 0.5  # politeness delay between backfill downloads

# GKG uses FIPS 10-4 country codes, which differ from ISO for several
# of our countries (e.g. Turkey is TU in FIPS, TR in ISO).
FIPS_BY_COUNTRY = {
    "Turkey": "TU",
    "Ukraine": "UP",
    "Lebanon": "LE",
    "Israel": "IS",
    "Egypt": "EG",
    "Sudan": "SU",
    "Haiti": "HA",
    "Thailand": "TH",
}

V2THEMES_COL = 8
V2LOCATIONS_COL = 10
V2TONE_COL = 15
DATE_COL = 1

# Verified against a live GKG file (2026-09-14) rather than assumed from
# docs -- see Scripts/README.md "Conflict/disaster theme tagging".
CONFLICT_THEMES = {
    "ARMEDCONFLICT",
    "PROTEST",
    "TERROR",
    "UNREST_BELLIGERENT",
    "WB_739_POLITICAL_VIOLENCE_AND_CIVIL_WAR",
    "WB_2432_FRAGILITY_CONFLICT_AND_VIOLENCE",
    "WB_2433_CONFLICT_AND_VIOLENCE",
    "WB_2462_POLITICAL_VIOLENCE_AND_WAR",
    "WB_2467_TERRORISM",
    "WB_2468_CONVENTIONAL_WAR",
    "WB_2492_COUNTER_TERRORISM",
    "WB_2510_WAR_CRIMES",
}
DISASTER_THEME_PREFIX = "NATURAL_DISASTER_"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "GDELT"


def latest_gkg_timestamp() -> str:
    resp = requests.get(LASTUPDATE_URL, timeout=30)
    resp.raise_for_status()
    for line in resp.text.splitlines():
        if line.strip().endswith(".gkg.csv.zip"):
            url = line.split()[-1]
            return url.rsplit("/", 1)[-1].split(".")[0]
    raise RuntimeError("Could not find a .gkg.csv.zip entry in lastupdate.txt")


def timestamps_going_back(latest_ts: str, n: int) -> list:
    latest_dt = datetime.strptime(latest_ts, "%Y%m%d%H%M%S")
    return [(latest_dt - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(n)]


def hourly_timestamps_going_back(days: int) -> list:
    """Top-of-hour GKG filenames for the past `days` days, newest first."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [(now - timedelta(hours=i)).strftime("%Y%m%d%H%M%S") for i in range(days * 24)]


def _article_theme_codes(themes_field: str) -> tuple:
    """Returns (conflict_codes, disaster_codes) sets of matched theme codes
    for one article's V2Themes field (not just booleans) -- so callers can
    tally *which* themes are driving the signal, not only whether one matched."""
    conflict_codes = set()
    disaster_codes = set()
    for entry in themes_field.split(";"):
        code = entry.split(",")[0]
        if not code:
            continue
        if code in CONFLICT_THEMES:
            conflict_codes.add(code)
        elif code.startswith(DISASTER_THEME_PREFIX):
            disaster_codes.add(code)
    return conflict_codes, disaster_codes


def fetch_and_aggregate(ts: str, fips_to_country: dict, theme_totals: dict) -> dict:
    """Returns {country_name: (article_count, tone_sum, conflict_count, disaster_count)}
    for one 15-min file. Mutates `theme_totals[country][theme_code]` in
    place with per-article theme-code counts across the whole run."""
    url = FILE_URL_TEMPLATE.format(ts=ts)
    resp = requests.get(url, timeout=60)
    if resp.status_code == 404:
        print(f"  {ts}: not found (skipping)")
        return {}
    resp.raise_for_status()

    counts = {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as f:
            for raw_line in f:
                try:
                    line = raw_line.decode("utf-8", errors="replace")
                    fields = line.rstrip("\n").split("\t")
                    locations = fields[V2LOCATIONS_COL]
                    tone = float(fields[V2TONE_COL].split(",")[0])
                    themes = fields[V2THEMES_COL]
                except (IndexError, ValueError):
                    continue

                matched_countries = set()
                for entry in locations.split(";"):
                    parts = entry.split("#")
                    if len(parts) < 3:
                        continue
                    fips = parts[2]
                    country_name = fips_to_country.get(fips)
                    if country_name:
                        matched_countries.add(country_name)

                if not matched_countries:
                    continue
                conflict_codes, disaster_codes = _article_theme_codes(themes)

                for country_name in matched_countries:
                    n, total, n_conflict, n_disaster = counts.get(country_name, (0, 0.0, 0, 0))
                    counts[country_name] = (
                        n + 1,
                        total + tone,
                        n_conflict + (1 if conflict_codes else 0),
                        n_disaster + (1 if disaster_codes else 0),
                    )
                    country_totals = theme_totals.setdefault(country_name, {})
                    for code in conflict_codes | disaster_codes:
                        country_totals[code] = country_totals.get(code, 0) + 1

    print(f"  {ts}: processed, {sum(c[0] for c in counts.values())} matching articles")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=f"Pull {BACKFILL_DAYS} days of history at hourly resolution instead of the last {LOOKBACK_FILES} 15-min files.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fips_to_country = {v: k for k, v in FIPS_BY_COUNTRY.items()}

    if args.backfill:
        ts_list = hourly_timestamps_going_back(BACKFILL_DAYS)
        print(f"Backfilling {len(ts_list)} hourly files (~{BACKFILL_DAYS} days), newest first: {ts_list[0]}")
    else:
        print("Looking up latest GDELT GKG bulk file...")
        latest_ts = latest_gkg_timestamp()
        ts_list = timestamps_going_back(latest_ts, LOOKBACK_FILES)
        print(f"Pulling last {len(ts_list)} files (~{15 * len(ts_list)} min window), newest first: {ts_list[0]}")

    rows = []
    theme_totals = {}
    missing = 0
    for i, ts in enumerate(ts_list):
        print(f"[{i + 1}/{len(ts_list)}] {ts}")
        try:
            counts = fetch_and_aggregate(ts, fips_to_country, theme_totals)
        except requests.exceptions.RequestException as exc:
            print(f"  ! request failed: {exc}")
            missing += 1
            continue

        ts_dt = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        for country in COUNTRIES:
            name = country["name"]
            n, total, n_conflict, n_disaster = counts.get(name, (0, 0.0, 0, 0))
            rows.append(
                {
                    "country": name,
                    "timestamp_utc": ts_dt.isoformat(),
                    "date": ts_dt.date().isoformat(),
                    "volume_article_count": n,
                    "avg_tone": round(total / n, 4) if n else "",
                    "conflict_article_count": n_conflict,
                    "disaster_article_count": n_disaster,
                }
            )

        if args.backfill:
            time.sleep(BACKFILL_DELAY_SECONDS)

    if not rows:
        print("No GDELT data retrieved.", file=sys.stderr)
        sys.exit(1)

    if args.backfill:
        print(f"\n{missing}/{len(ts_list)} hourly files were missing/failed (best-effort skip).")

    filename = f"gdelt_tension_history_{date.today().isoformat()}.csv" if args.backfill else f"gdelt_tension_{date.today().isoformat()}.csv"
    out_path = OUT_DIR / filename
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "country",
                "timestamp_utc",
                "date",
                "volume_article_count",
                "avg_tone",
                "conflict_article_count",
                "disaster_article_count",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} rows to {out_path}")

    theme_path = OUT_DIR / f"gdelt_theme_breakdown_{date.today().isoformat()}.csv"
    theme_rows = [
        {
            "country": country_name,
            "theme_code": code,
            "category": "conflict" if code in CONFLICT_THEMES else "disaster",
            "article_count": count,
        }
        for country_name, codes in theme_totals.items()
        for code, count in codes.items()
    ]
    theme_rows.sort(key=lambda r: (r["country"], -r["article_count"]))
    with theme_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["country", "theme_code", "category", "article_count"])
        writer.writeheader()
        writer.writerows(theme_rows)
    print(f"Saved {len(theme_rows)} theme-breakdown rows to {theme_path}")


if __name__ == "__main__":
    main()
