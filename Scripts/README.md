# Data-gathering scripts

Pulls the raw data for the Crisis & Connectivity Monitor described in
`Documentation/Relevance and function.txt`. Each script is standalone and
writes into the matching `Data/` subfolder; `run_all.py` runs all of them
in sequence.

## Setup

```
pip install -r requirements.txt
```

Python 3.9+.

## Scripts

| Script | Source | Needs a key? | Output |
|---|---|---|---|
| `fetch_gdelt_tension.py` | GDELT 2.0 GKG bulk files | No | `Data/GDELT/gdelt_tension_<date>.csv` |
| `fetch_gdacs_events.py` | GDACS event list | No | `Data/Reliefweb and GDACS/gdacs_events_<date>.{json,csv}` |
| `fetch_reliefweb_events.py` | ReliefWeb API v2 | **Yes, see below** | `Data/Reliefweb and GDACS/reliefweb_disasters_<date>.csv` |
| `fetch_cbs_travel.py` | CBS StatLine table 84365NED | No | `Data/Travel and flights/cbs_travel_<date>.csv` |
| `fetch_opensky_snapshot.py` | OpenSky Network (live only) | No | `Data/Travel and flights/opensky_snapshot_<timestamp>.csv` |

Run everything: `python run_all.py`

## Country list

All scripts pull from the shared list in `countries.py`: Turkey, Ukraine,
Lebanon, Israel, Egypt, Sudan, Haiti, Thailand. Edit that file to change
which countries are tracked.

## Known limitations (read before treating outputs as ground truth)

- **ReliefWeb now requires a pre-approved appname** (changed 1 Nov 2025,
  after the original Documentation was written). Free registration, but
  it's a review process, not instant -- see
  `apidoc.reliefweb.int/parameters#appname`. Until you have one, set
  `RELIEFWEB_APPNAME` as an env var; without it, the script writes a
  status note instead of failing the rest of the pipeline. Since GDACS
  already covers natural disasters with no key needed, ReliefWeb mainly
  adds conflict/displacement reporting GDACS doesn't have.
- **CBS travel data is only country-specific for ~15 "most visited"
  destinations** (mostly Western Europe, plus US/Turkey). For the other
  crisis countries in our list, CBS only reports continent/region totals
  (e.g. all of "Africa" lumped together), so `cbs_travel_*.csv` marks
  each row's `cbs_granularity` as `country` or `region` -- treat `region`
  rows as rough context, not a per-country baseline.
- **GDELT** volume/tone is a media-attention proxy, not ground-truth
  instability. We pull it from the raw GKG bulk files (updated every 15
  min), not the DOC 2.0 query API — see "Avoiding the GDELT rate limit"
  below for why, and for how to query GDELT for ongoing/hourly
  collection.
- **OpenSky** is live-snapshot only under anonymous access; it cannot
  answer "how has flight volume out of country X changed" (see
  `Documentation/Data ideation.txt`). It's wired in only as an optional
  "right now" layer.
- **GDACS** covers natural disasters (earthquakes, floods, storms,
  droughts, volcanic activity) — it does not cover conflict, political
  unrest, or civil war, which matters for a couple of the countries on
  the list.

## Avoiding the GDELT rate limit (and how to query GDELT hourly, in general)

The GDELT 2.0 **DOC API** (`api.gdeltproject.org/api/v2/doc/doc`, the
`mode=timelinevol` / `mode=timelinetone` endpoints we first tried) states
a "one request every 5 seconds" limit, but in practice a handful of
requests from a shared/cloud IP can trigger a 429 block that no amount of
client-side backoff clears quickly — other users hitting this from CI or
cloud environments report the same thing. It's built for occasional
interactive lookups (a human typing a query), **not for scripted or
recurring polling** — GDELT's own blog explicitly tells high-volume users
to stop using it and switch to something else.

The fix `fetch_gdelt_tension.py` uses: skip the DOC API and pull straight
from GDELT's **raw bulk export files** instead, which is what GDELT
actually intends for programmatic/recurring consumption:

- `https://data.gdeltproject.org/gdeltv2/lastupdate.txt` — always lists
  the 3 most recently published files (event, mentions, and GKG).
- New files land every 15 minutes, at :00/:15/:30/:45 past the hour, at
  `https://data.gdeltproject.org/gdeltv2/<YYYYMMDDHHMMSS>.gkg.csv.zip`
  (and `.export.CSV.zip`, `.mentions.CSV.zip`).
- These are plain static files on Google Cloud Storage — no API key, no
  observed rate limit, and they're the same data the DOC API summarizes.

**If you (or a colleague) want to collect GDELT data on an hourly
cadence going forward, this is the pattern to use in general:**

1. Don't call the DOC/Context query APIs on a schedule — they're
   explicitly not meant for that and will eventually get you blocked.
2. On your schedule (hourly is easy — files land every 15 min, so an
   hourly job can just grab the 4 files since its last run), fetch
   `lastupdate.txt`, then download the new `.gkg.csv.zip` (and/or
   `.export.CSV.zip` for structured event records with actor/location/
   Goldstein-scale fields, if you want events rather than free-text
   tone) files you haven't already processed.
3. Parse and aggregate locally (this script filters `V2Locations` by
   FIPS 10-4 country code and averages `V2Tone`) and **append** to your
   own store — GDELT doesn't keep a queryable history for you beyond the
   DOC API's ~3-month rolling window, so your own accumulated file *is*
   your history.
4. For heavy historical backfill (not just going-forward polling),
   GDELT's full event/GKG archive is also queryable via Google BigQuery
   (`gdelt-bq` public datasets) without hitting either rate limit — worth
   it only if you need bulk historical analysis rather than ongoing
   collection.

This script currently pulls the last `LOOKBACK_FILES` (8, i.e. ~2 hours)
of GKG files as a recent snapshot rather than backfilling months of
history in one run — bump that constant, or run the script on a
schedule and concatenate its output over time, to build up a longer
series.
