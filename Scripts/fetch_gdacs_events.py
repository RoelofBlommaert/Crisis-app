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
  Data/GDACS/gdacs_events_<date>.json   (raw API response)
  Data/GDACS/gdacs_events_<date>.csv     (all current events, flattened)
  Data/GDACS/gdacs_events_matched_<date>.csv (events matching our country list)
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
OUT_DIR = REPO_ROOT / "Data" / "GDACS"

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

MATCHED_FIELDS = FIELDS + ["matched_countries"]

# GDACS's "country" field is a plain comma-separated name list; matching by
# substring (e.g. "sudan" in "south sudan") produces false positives, so we
# match whole comma-separated tokens instead. A couple of GDACS's own names
# don't match our country list verbatim.
NAME_ALIASES = {
    "turkiye": "turkey",
}


def _normalize(name: str) -> str:
    name = name.strip().lower()
    # strip diacritics GDACS uses (e.g. "Türkiye") so alias lookups match
    name = name.replace("ü", "u").replace("ç", "c").replace("ö", "o")
    return NAME_ALIASES.get(name, name)


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

    iso3_to_name = {c["iso3"]: c["name"] for c in COUNTRIES}
    name_to_target = {_normalize(c["name"]): c["name"] for c in COUNTRIES}

    matched_rows = []
    for row in all_rows:
        matched = set()
        # iso3 identifies the event's primary/first-listed country only --
        # trustworthy on its own for single-country events.
        if row["iso3"] in iso3_to_name:
            matched.add(iso3_to_name[row["iso3"]])
        # For multi-country events, check each comma-separated name token
        # against our list (whole-token match, not substring).
        for token in row["country"].split(","):
            token_norm = _normalize(token)
            if token_norm in name_to_target:
                matched.add(name_to_target[token_norm])
        if matched:
            row = dict(row)
            row["matched_countries"] = ";".join(sorted(matched))
            matched_rows.append(row)

    matched_path = OUT_DIR / f"gdacs_events_matched_{today}.csv"
    with matched_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MATCHED_FIELDS)
        writer.writeheader()
        writer.writerows(matched_rows)

    print(f"Saved {len(all_rows)} events to {all_path}")
    print(f"Saved {len(matched_rows)} matched events to {matched_path}")
    print(f"Saved raw response to {raw_path}")

    if not features:
        sys.exit(1)


if __name__ == "__main__":
    main()
