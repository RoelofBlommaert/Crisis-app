"""
Pull currently active/recent disaster events from GDACS.

Data source: GDACS Event List API
(https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH)
Public, no API key required. Returns a GeoJSON FeatureCollection of
current disaster events worldwide (earthquakes, floods, cyclones,
droughts, volcanic activity, etc.) with an alert level (Green/Orange/Red).

This is the "confirmed event" layer described in the documentation. Note
that GDACS covers natural disasters only, not conflict/political crises
-- that gap is discussed in Documentation/Relevance and function.txt.

Output:
  Data/Reliefweb and GDACS/gdacs_events_<date>.json   (raw API response)
  Data/Reliefweb and GDACS/gdacs_events_<date>.csv     (all current events, flattened)
  Data/Reliefweb and GDACS/gdacs_events_matched_<date>.csv (events matching our country list)
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path

import requests

from countries import COUNTRIES

API_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "Reliefweb and GDACS"

FIELDS = [
    "eventtype",
    "eventname",
    "country",
    "iso3",
    "alertlevel",
    "alertscore",
    "fromdate",
    "todate",
    "datemodified",
    "description",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching GDACS current event list...")
    resp = requests.get(API_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    print(f"  {len(features)} active/recent events returned")

    today = date.today().isoformat()

    raw_path = OUT_DIR / f"gdacs_events_{today}.json"
    raw_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    all_rows = []
    for feat in features:
        p = feat.get("properties", {})
        all_rows.append({k: p.get(k, "") for k in FIELDS})

    all_path = OUT_DIR / f"gdacs_events_{today}.csv"
    with all_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    target_iso3 = {c["iso3"] for c in COUNTRIES}
    target_names = {c["name"].lower() for c in COUNTRIES}
    matched_rows = [
        row
        for row in all_rows
        if row["iso3"] in target_iso3
        or any(name in row["country"].lower() for name in target_names)
    ]

    matched_path = OUT_DIR / f"gdacs_events_matched_{today}.csv"
    with matched_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(matched_rows)

    print(f"Saved {len(all_rows)} events to {all_path}")
    print(f"Saved {len(matched_rows)} matched events to {matched_path}")
    print(f"Saved raw response to {raw_path}")

    if not features:
        sys.exit(1)


if __name__ == "__main__":
    main()
