"""
Pull real ACLED (Armed Conflict Location & Event Data Project) conflict
data per tracked country -- ground-truth political-violence/fatality
counts, not a media-mention proxy like GDELT.

Why via HDX, not ACLED's own API: ACLED's API requires registering a
myACLED account and generating an API key (see acleddata.com/register) --
we're avoiding new registrations this round. ACLED itself publishes
pre-aggregated, no-registration, freely downloadable country files
through the Humanitarian Data Exchange (data.humdata.org/organization/acled),
updated weekly. Confirmed by querying HDX's public CKAN API directly:
every one of our 8 tracked countries has a "<country>-acled-conflict-data"
dataset with three monthly XLSX resources:
  - political_violence_events_and_fatalities_by_month-year
  - civilian_targeting_events_and_fatalities_by_month-year
  - demonstration_events_by_month-year (events only, no fatalities)
Monthly resolution only (not daily) -- this is the real tradeoff for
avoiding registration; ACLED's own API/export tool would give
event-level daily data with an account.

ACLED's Terms of Use require ACLED to be "clearly and prominently
acknowledged" wherever this data (or anything derived from it) is
shown -- see Scripts/README.md and the app's About panel/attribution.
Never redistribute the raw per-row data directly (their ToU prohibits
"direct access to any of ACLED's original/raw data" by other users) --
this app only ever shows aggregated/visualized derivatives.

Two different HDX file layouts exist depending on the country: Ukraine,
Sudan, and Haiti (all current Humanitarian Response Plan countries) get
an "_HRP_" variant broken down by Admin1/Admin2 sub-region -- one row
per region per month, not one national total -- while the rest (Turkey,
Lebanon, Israel, Egypt, Thailand) get a single national row per month.
We always aggregate to one national total per (country, year, month,
category) regardless of which layout we got, since that's what the
per-country app model needs.

Output: Data/ACLED/acled_monthly_<date>.csv
Columns: country, year, month, month_num, category, events, fatalities
  category is one of: political_violence, civilian_targeting, demonstrations
  fatalities is blank for demonstrations (HDX doesn't provide it)
"""

import csv
import io
from datetime import date
from pathlib import Path

import openpyxl
import requests

from countries import COUNTRIES

CKAN_PACKAGE_SHOW = "https://data.humdata.org/api/3/action/package_show"
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "ACLED"

MONTH_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

CATEGORY_MATCH = {
    "political_violence": "political_violence",
    "civilian_targeting": "civilian_targeting",
    "demonstration": "demonstrations",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (crisis-connectivity-monitor course demo)"}


def hdx_slug(country_name: str) -> str:
    return f"{country_name.lower().replace(' ', '-')}-acled-conflict-data"


def fetch_package_resources(slug: str) -> list:
    resp = requests.get(CKAN_PACKAGE_SHOW, params={"id": slug}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        return []
    return data["result"]["resources"]


def parse_xlsx_data_sheet(content: bytes) -> list:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb["Data"]
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    header = [str(h).strip() if h else "" for h in rows[0]]
    return [dict(zip(header, row)) for row in rows[1:] if row and row[0]]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for c in COUNTRIES:
        name = c["name"]
        slug = hdx_slug(name)
        print(f"Fetching HDX/ACLED package for {name} ({slug})...")
        try:
            resources = fetch_package_resources(slug)
        except requests.exceptions.RequestException as exc:
            print(f"  ! request failed: {exc}")
            continue
        if not resources:
            print("  ! package not found on HDX")
            continue

        for res in resources:
            res_name = res.get("name", "")
            category = next((v for k, v in CATEGORY_MATCH.items() if k in res_name), None)
            if category is None:
                continue
            try:
                file_resp = requests.get(res["url"], headers=HEADERS, timeout=60, allow_redirects=True)
                file_resp.raise_for_status()
                records = parse_xlsx_data_sheet(file_resp.content)
            except Exception as exc:  # noqa: BLE001 -- best-effort per resource
                print(f"  ! failed to fetch/parse {res_name}: {exc}")
                continue

            # Aggregate to one national total per (year, month) -- the HRP
            # variant has one row per Admin1/Admin2 sub-region per month,
            # not a single national row (see module docstring).
            has_fatalities = any("Fatalities" in r for r in records)
            monthly = {}
            for r in records:
                month_name = str(r.get("Month", "")).strip()
                year = int(r.get("Year"))
                key = (year, month_name)
                agg = monthly.setdefault(key, {"events": 0, "fatalities": 0})
                agg["events"] += int(r.get("Events") or 0)
                if has_fatalities:
                    agg["fatalities"] += int(r.get("Fatalities") or 0)

            for (year, month_name), agg in monthly.items():
                all_rows.append(
                    {
                        "country": name,
                        "year": year,
                        "month": month_name,
                        "month_num": MONTH_NUM.get(month_name, 0),
                        "category": category,
                        "events": agg["events"],
                        "fatalities": agg["fatalities"] if has_fatalities else "",
                    }
                )
            print(f"  {category}: {len(monthly)} months ({len(records)} source rows)")

    if not all_rows:
        print("No ACLED/HDX data retrieved.")
        return

    all_rows.sort(key=lambda r: (r["country"], r["category"], r["year"], r["month_num"]))
    out_path = OUT_DIR / f"acled_monthly_{date.today().isoformat()}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["country", "year", "month", "month_num", "category", "events", "fatalities"]
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nSaved {len(all_rows)} rows to {out_path}")
    print("Reminder: ACLED must be clearly attributed wherever this data (or a derivative) is shown.")


if __name__ == "__main__":
    main()
