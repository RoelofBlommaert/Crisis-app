"""
Pull confirmed crisis/disaster reports from ReliefWeb, for our country list.

Data source: ReliefWeb API v2 (https://api.reliefweb.int/v2/disasters)

IMPORTANT CHANGE vs. the original plan in Documentation/Data ideation.txt:
as of 1 November 2025, ReliefWeb requires a *pre-approved* appname -- you
can no longer just make one up. Request one here (takes a review cycle,
not instant): https://apidoc.reliefweb.int/parameters#appname

Until you have one, set it as an environment variable before running:
  Windows (PowerShell):  $env:RELIEFWEB_APPNAME = "your-approved-appname"
  bash:                  export RELIEFWEB_APPNAME="your-approved-appname"

If the env var isn't set, this script does NOT fail the whole pipeline --
it writes a short status note explaining why no file was produced, so
run_all.py can still complete the other pulls.

Output (once you have an appname):
  Data/Reliefweb and GDACS/reliefweb_disasters_<date>.csv
"""

import csv
import os
from datetime import date
from pathlib import Path

import requests

from countries import COUNTRIES

API_URL = "https://api.reliefweb.int/v2/disasters"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "Reliefweb and GDACS"

FIELDS = ["id", "name", "status", "date_created", "country", "type"]


def write_status_note(message: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    note_path = OUT_DIR / "reliefweb_STATUS.txt"
    note_path.write_text(message, encoding="utf-8")
    print(message)


def main() -> None:
    appname = os.environ.get("RELIEFWEB_APPNAME")
    if not appname:
        write_status_note(
            "ReliefWeb pull skipped: no RELIEFWEB_APPNAME environment variable set.\n"
            "ReliefWeb now requires a pre-approved appname (since 1 Nov 2025).\n"
            "Request one at https://apidoc.reliefweb.int/parameters#appname, then set:\n"
            "  $env:RELIEFWEB_APPNAME = \"your-approved-appname\"   (PowerShell)\n"
            "and re-run this script. GDACS already covers natural-disaster events\n"
            "without needing a key -- see fetch_gdacs_events.py.\n"
        )
        return

    country_names = [c["name"] for c in COUNTRIES]
    payload = {
        "appname": appname,
        "limit": 100,
        "filter": {
            "field": "country",
            "value": country_names,
            "operator": "OR",
        },
        "fields": {"include": ["name", "status", "date.created", "country.name", "type.name"]},
        "sort": ["date.created:desc"],
    }

    print(f"Fetching ReliefWeb disasters for: {', '.join(country_names)}")
    resp = requests.post(API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for item in data.get("data", []):
        fields = item.get("fields", {})
        countries = fields.get("country", [])
        types = fields.get("type", [])
        rows.append(
            {
                "id": item.get("id", ""),
                "name": fields.get("name", ""),
                "status": fields.get("status", ""),
                "date_created": fields.get("date", {}).get("created", ""),
                "country": ", ".join(c.get("name", "") for c in countries),
                "type": ", ".join(t.get("name", "") for t in types),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"reliefweb_disasters_{date.today().isoformat()}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} disasters to {out_path}")


if __name__ == "__main__":
    main()
