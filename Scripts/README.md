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
| `fetch_acled_hdx.py` | ACLED, via HDX aggregated country files | No | `Data/ACLED/acled_monthly_<date>.csv` |
| `fetch_gdelt_tension.py` | GDELT 2.0 GKG bulk files | No | `Data/GDELT/gdelt_tension_<date>.csv` (or `gdelt_tension_history_<date>.csv` with `--backfill`) |
| `fetch_gdacs_events.py` | GDACS event list | No | `Data/GDACS/gdacs_events_<date>.{json,csv}` |
| `merge_data.py` | combines all of the above | No | `App/data/dataset.json` (what the frontend reads) |

Run everything: `python run_all.py`, then `python merge_data.py` to
produce the merged JSON the app reads. `run_all.py` does not pass
`--backfill` to `fetch_gdelt_tension.py` (a normal run only takes a few
seconds; the backfill takes several minutes) — run that one separately
when you want to (re)seed the trend history:

```
python fetch_gdelt_tension.py --backfill
python fetch_acled_hdx.py
python merge_data.py
```

`fetch_acled_hdx.py` has no dependency on the other scripts and can run
any time before `merge_data.py`.

## Sources dropped after review (2026-09-15)

Trimmed to the three sources that actually drive the conflict/disaster
signals, after checking what each one contributed to the merged dataset:

- **ReliefWeb** (`fetch_reliefweb_events.py`) — never actually produced
  data: ReliefWeb has required a pre-approved `appname` since 1 Nov 2025,
  the fetch was never wired into `merge_data.py` in the first place, and
  it would only have added displacement/humanitarian-response reporting
  that GDACS (disasters) and ACLED (conflict) already cover for this PoC's
  purpose (spotting rising tension, not humanitarian-response detail).
  Removed as dead weight; worth reconsidering only if a registered
  appname becomes available AND humanitarian-response detail becomes a
  stated requirement.
- **CBS travel** (`fetch_cbs_travel.py`) — Dutch traveler/spend counts per
  country. Context ("how many Dutch citizens are plausibly there"), not a
  tension/escalation signal, and stale by nature (annual, published with
  a lag; several tracked countries were region- not country-level to
  begin with). Removed to keep the dataset focused on signals that move
  when a situation is actually escalating.
- **OpenSky** (`fetch_opensky_snapshot.py`) — live flight snapshot only
  (no history under anonymous access, see former "Known limitations"
  notes) and was never actually merged into `App/data/dataset.json` or
  rendered anywhere in the app — pure dead data collection. Removed.
- **Synthetic comms volume** (`generate_synthetic_comms.py`) — entirely
  fictional demo data (see former "Synthetic data" section below),
  never connected to a real NWW/consular system. Removed rather than kept
  as a placeholder, per the decision to minimize the dataset to real
  signals only.

What stays, and why each earns its place:
- **ACLED** — the only ground-truth conflict-severity source (real
  fatality/event counts); dominant driver of `conflict_signal`.
- **GDACS** — the only ground-truth disaster-event source; dominant
  driver of `disaster_signal`. Nothing else in this pipeline covers
  natural disasters at all.
- **GDELT** — the only source that updates faster than monthly. It can't
  carry a score on its own (capped near ~10/100 without ACLED
  corroboration — see `merge_data.py`), but it's what lets the app show
  day-to-day movement and *which* themes (protests, armed conflict,
  terrorism, ...) are driving attention between ACLED's monthly updates —
  directly serving the "is this rising toward a crisis" question, not
  just "how bad is it right now."

## Country list

All scripts pull from the shared list in `countries.py`: Turkey, Ukraine,
Lebanon, Israel, Egypt, Sudan, Haiti, Thailand. Edit that file to change
which countries are tracked.

## Known limitations (read before treating outputs as ground truth)

- **GDELT** volume/tone is a media-attention proxy, not ground-truth
  instability. We pull it from the raw GKG bulk files (updated every 15
  min), not the DOC 2.0 query API — see "Avoiding the GDELT rate limit"
  below for why, and for how to query GDELT for ongoing/hourly
  collection.
- **Whole-week average tone is a poor crisis signal on its own.** We
  originally color-coded countries by their 7-day average GDELT tone
  against fixed thresholds (-4/-8). In practice this stayed "Green" for
  Israel/Lebanon even during heavy, clearly negative coverage, because
  a week-long average is diluted by routine reporting -- Lebanon's
  7-day average tone was only -2.9, never close to -4. Fixed by also
  tagging each article's GKG themes (see below) and using conflict-theme
  *share* + a recent-vs-baseline trend instead of a flat weekly average;
  see `merge_data.py`.
- **Then the fix over-corrected: almost every country landed
  Orange-or-above almost every day.** `conflict_share * 70` alone crosses
  the Orange cutoff (30) once ~43% of a country's articles carry a
  conflict theme tag, and GDELT tags an article with *every* country it
  mentions -- so regional spillover coverage (Egypt/Turkey appearing in
  Gaza-adjacent stories) clears that easily without those countries being
  combatants. Separately, `disaster_share * 100` let a single article on
  a low-volume day swing the score by up to 100 points of pure sampling
  noise (Haiti, at 1-10 articles/day, ranged 10-69 across a week with no
  active disaster event behind any of it). Recalibrated in `merge_data.py`:
  lower weights, a `confidence = min(1, day_volume/15)` dampener on the
  share-based terms, and raised bands (Red>=65, Orange>=35, was 60/30).
- **Per STRATEGY.md, this project isn't meant to auto-classify crises yet**
  ("classificatie hoeft in de PoC nog niet automatisch te werken -- puur
  laten zien wat er aan data is"). The 0-100 gauges stay (per-round
  decision to keep the mechanism, just recalibrated) but are now paired
  with `top_conflict_themes` / `top_disaster_themes` (see below) so the
  app explains *what* is driving a score, not just the compressed number.
  A manual-override control ("hybride sturing" in the strategy doc) is a
  known, deliberately deferred gap -- not built this round.
- **GDACS** covers natural disasters (earthquakes, floods, storms,
  droughts, volcanic activity) — it does not cover conflict, political
  unrest, or civil war, which matters for a couple of the countries on
  the list.
- **Fixed: GDACS country matching had a substring bug.** The event
  list's `country` field is a plain comma-separated name string (e.g.
  "Jamaica, Cuba, Bahamas, ... Haiti, Canada"), and the original matching
  checked `name in row["country"].lower()` — a substring test, so
  "sudan" matched inside "south sudan" and incorrectly attributed a
  South Sudan flood event to our tracked "Sudan". Fixed to match whole
  comma-separated tokens instead (with a small alias table for name
  mismatches like GDACS's "Türkiye" vs. our "Turkey"). The matched CSV
  now also carries a `matched_countries` column listing exactly which
  tracked country/countries triggered each row, since a single
  multi-country event's `iso3` field only ever names one (usually the
  first-listed) country — not reliable for per-country attribution on
  its own.

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

## Conflict/disaster theme tagging

`fetch_gdelt_tension.py` also parses each article's `V2Themes` field
(GKG's per-article topic tags) and counts, per country per file, how
many matching articles carry a conflict-related theme vs. a
natural-disaster-related theme -- `conflict_article_count` /
`disaster_article_count` columns. This is what lets the app show a
"conflict signal" separate from a "disaster signal" instead of lumping
everything into one tone number.

The theme codes used (`CONFLICT_THEMES` set, `NATURAL_DISASTER_` prefix
in the script) were picked by **downloading a live GKG file and checking
which codes actually appear** for our tracked countries, not copied
blind from GDELT's documentation (theme taxonomies drift and the docs
aren't fully authoritative). `NATURAL_DISASTER_*` reliably prefixes every
disaster-specific tag observed (flooding, hurricane, wildfire, landslide,
avalanche, monsoon, ...). Conflict signal is a fixed set of codes that
showed up on real conflict-country articles: `ARMEDCONFLICT`, `PROTEST`,
`TERROR`, `UNREST_BELLIGERENT`, and several World Bank taxonomy codes
(`WB_2462_POLITICAL_VIOLENCE_AND_WAR`, `WB_2467_TERRORISM`,
`WB_739_POLITICAL_VIOLENCE_AND_CIVIL_WAR`, etc). Deliberately excluded
broader/noisier codes like generic `MILITARY` or `TAX_MILITARY_TITLE_*`
(military titles/spending stories aren't necessarily about actual
conflict) and `CRISISLEX_CRISISLEXREC` (fires on both conflict and
disaster stories, not a clean signal either way).

`fetch_gdelt_tension.py` also now tallies *which specific* theme codes
matched (not just the conflict/disaster booleans), across the whole run,
into `Data/GDELT/gdelt_theme_breakdown_<date>.csv`
(`country, theme_code, category, article_count`). `merge_data.py` turns
this into `top_conflict_themes` / `top_disaster_themes` per country (top
5 by count, with a human-readable label from `THEME_LABELS`) -- this is
the concrete "what is happening" answer (e.g. "Armed conflict: 312
articles, Protests: 89, Terrorism-related coverage: 45") rather than
just a compressed score, per STRATEGY.md's ask to show the underlying
data, not only an automated verdict.

## ACLED conflict data, without registering an account

ACLED (Armed Conflict Location & Event Data Project) is the standard
real-time armed-conflict event database -- precise event-level data with
actor/fatality/location detail. Its own API requires registering a
myACLED account and generating a key (see acleddata.com/register); we
avoided that (this project's "no new registrations" constraint) by using
ACLED's own **pre-aggregated country files published through the
Humanitarian Data Exchange** (`data.humdata.org/organization/acled`),
confirmed via HDX's public CKAN API (`/api/3/action/package_show`) to
need no login, cover all 8 tracked countries, and update weekly.

**Two different file layouts, found by inspecting the actual files, not
assumed:**
- Turkey, Lebanon, Israel, Egypt, Thailand: one national row per month.
- Ukraine, Sudan, Haiti (current Humanitarian Response Plan countries):
  one row **per Admin1/Admin2 sub-region per month** -- naively treating
  each row as a national total inflated these three countries' row
  counts by 100-500x on the first attempt (e.g. "14595 months" for
  Ukraine). `fetch_acled_hdx.py` always aggregates to one national
  total per (country, year, month, category) regardless of layout.

**Scoring leads with unrest (event count), not fatalities -- fatalities
are a secondary accelerant.** Two earlier versions both scored primarily
off fatalities: first a flat band (0/1-24/25-99/100+ -> 0/1/2/3, *25
each), then a log-scaled fatality severity + fatality-baseline escalation
bonus. Changed again per an explicit steering decision: this app exists
to spot rising unrest early, so *how much political violence is
happening* (event count) should drive the score, with fatalities kept as
a secondary signal that accelerates the score once people are actually
dying rather than the thing driving it in the first place. Now three
explicit numbers: a log-scaled unrest-severity score (0-55, against a
fixed 10,000-events/month reference -- not derived from our own
8-country sample, so it doesn't shift if countries are added), an
unrest-escalation bonus (0-15) that only activates when the current
month's event count exceeds the country's own trailing 12-month average,
and a fatality accelerant (0-20, log-scaled against a much lower
500-fatalities/month reference so it climbs fast at low death tolls --
e.g. Sudan's real 876 fatalities that month already maxes this term out).
All three are exposed in the output and shown in the UI (baseline
events/month, event ratio, trend label, plus the raw fatality count), not
just the combined score. See `merge_data.py`'s "Unrest-primary,
fatalities as an urgency accelerant" docstring section for the exact
formula and the full before/after numbers, verified against live data
(Ukraine unrest ~54, Sudan ~33, Lebanon ~38, Haiti ~25, ordered by real
event-count scale; Turkey's small absolute count but 3x-baseline surge
still earns the full +15 escalation bonus; Sudan's and Haiti's high
fatality counts each max the +20 accelerant even though their event
counts alone wouldn't justify that).

**The most recent available month is always excluded from scoring** --
checked across all 8 countries before deciding this, not assumed from
one case: the newest month is consistently far below the surrounding
trend for nearly every country simultaneously (Sudan 876 -> 70
fatalities, Ukraine 4008 -> 1010, Haiti 103 -> 8, month over month),
which is reporting/verification lag, not a real synchronized
de-escalation across unrelated conflicts. The previous complete month is
used for scoring instead; the provisional month is still fetched and
shown in the chart (visible as a sudden drop at the right edge) with an
explanatory note, not hidden.

**Attribution is a hard requirement, not a courtesy**: ACLED's Terms of
Use (acleddata.com/terms-of-use) require ACLED to be "clearly and
prominently acknowledged" wherever their data or a derivative is shown,
and prohibit redistributing their raw/original data directly to other
users. This app only ever shows aggregated monthly totals and
visualizations (never a raw per-row dump) and credits ACLED with a link
under every ACLED chart and in the About panel.

Needs `openpyxl` (added to `requirements.txt`) to read the `.xlsx` files
HDX serves.
