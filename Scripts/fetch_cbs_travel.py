"""
Pull Dutch outbound-travel baseline stats from CBS StatLine.

Data source: CBS OData v3 table 84365NED
"Vakanties van Nederlanders; buitenland, vakantiekenmerken"
(foreign holidays of Dutch residents, by destination), annual, 2021-2025.
Public, no API key required.

IMPORTANT LIMITATION (see Documentation for the tweak this implies):
this table only breaks out ~15 individually-named "most visited"
destinations (mostly Western Europe + US/Turkey). Countries outside that
top list -- Lebanon, Israel, Egypt, Sudan, Haiti, Ukraine, Thailand in
our crisis list -- are only available at continent/region level
(e.g. all of "Africa" or "Asia" lumped together). Scripts/countries.py
records, per country, whether we get country-level or only region-level
CBS data via the `cbs_granularity` field.

Output: Data/Travel and flights/cbs_travel_<date>.csv
Columns: crisis_country, cbs_granularity, cbs_area_label, year,
         dutch_travellers_x1000, pct_of_dutch_population,
         total_trips_x1000, total_overnight_stays_x1000000,
         total_spend_eur_million
"""

import csv
from datetime import date
from pathlib import Path

import requests

from countries import COUNTRIES

TABLE_ID = "84365NED"
BASE_URL = f"https://opendata.cbs.nl/ODataApi/odata/{TABLE_ID}/TypedDataSet"
TOTAL_CHARACTERISTIC = "T001460"  # Vakantiekenmerken: "Totaal vakanties"
POINT_ESTIMATE_MARGIN = "MW00000"  # Marges: "Waarde" (not a confidence bound)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "Travel and flights"

MEASURES = {
    "TotaalNederlanders_1": "dutch_travellers_x1000",
    "PercentageNederlanders_2": "pct_of_dutch_population",
    "TotaalVakanties_3": "total_trips_x1000",
    "TotaalOvernachtingen_8": "total_overnight_stays_x1000000",
    "TotaalVakantieUitgaven_11": "total_spend_eur_million",
}


def period_to_year(period: str) -> str:
    return period[:4]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cbs_keys = sorted({c["cbs_key"] for c in COUNTRIES})
    key_to_countries = {}
    for c in COUNTRIES:
        key_to_countries.setdefault(c["cbs_key"], []).append(c)

    dest_filter = " or ".join(f"Bestemmingen eq '{k}'" for k in cbs_keys)
    filt = f"({dest_filter}) and Vakantiekenmerken eq '{TOTAL_CHARACTERISTIC}' and Marges eq '{POINT_ESTIMATE_MARGIN}'"
    select = "Bestemmingen,Perioden," + ",".join(MEASURES.keys())

    print(f"Fetching CBS table {TABLE_ID} for {len(cbs_keys)} destination area(s)...")
    resp = requests.get(BASE_URL, params={"$filter": filt, "$select": select, "$format": "json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    records = data.get("value", [])
    print(f"  {len(records)} records returned")

    fieldnames = [
        "crisis_country",
        "cbs_granularity",
        "cbs_area_label",
        "year",
        *MEASURES.values(),
    ]
    rows = []
    for rec in records:
        cbs_key = rec["Bestemmingen"]
        for country in key_to_countries.get(cbs_key, []):
            row = {
                "crisis_country": country["name"],
                "cbs_granularity": country["cbs_granularity"],
                "cbs_area_label": country["cbs_label"],
                "year": period_to_year(rec["Perioden"]),
            }
            for cbs_field, out_field in MEASURES.items():
                row[out_field] = rec.get(cbs_field, "")
            rows.append(row)

    rows.sort(key=lambda r: (r["crisis_country"], r["year"]))

    out_path = OUT_DIR / f"cbs_travel_{date.today().isoformat()}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
