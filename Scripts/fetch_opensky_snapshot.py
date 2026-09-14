"""
Pull a single live snapshot of aircraft state vectors from OpenSky.

Data source: OpenSky Network REST API (https://opensky-network.org/api/states/all)
Public, anonymous, free -- but ONLY gives a live "right now" snapshot.
As flagged in Documentation/Data ideation.txt, the anonymous tier cannot
retrieve historical flight volume, so this is NOT a trend/baseline data
source. It's included as the optional "live map" layer the documentation
mentions, nothing more -- don't build core insight logic on it.

`origin_country` in the OpenSky response is derived from the aircraft's
ICAO24 address allocation (i.e. country of registration), not its current
position, so this filters "aircraft currently registered to / airborne
from our crisis countries" rather than "aircraft currently over them."

Output: Data/Travel and flights/opensky_snapshot_<timestamp>.csv
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

import requests

from countries import COUNTRIES

API_URL = "https://opensky-network.org/api/states/all"

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "Data" / "Travel and flights"

COLUMNS = [
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching live OpenSky state vector snapshot...")
    resp = requests.get(API_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    states = data.get("states") or []
    print(f"  {len(states)} aircraft in global snapshot")

    target_names = {c["name"].lower() for c in COUNTRIES}
    rows = []
    for s in states:
        origin_country = (s[2] or "").strip()
        if origin_country.lower() in target_names:
            rows.append(
                {
                    "icao24": s[0],
                    "callsign": (s[1] or "").strip(),
                    "origin_country": origin_country,
                    "time_position": s[3],
                    "longitude": s[5],
                    "latitude": s[6],
                    "baro_altitude": s[7],
                    "on_ground": s[8],
                    "velocity": s[9],
                }
            )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"opensky_snapshot_{ts}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} aircraft (matching our country list) to {out_path}")


if __name__ == "__main__":
    main()
