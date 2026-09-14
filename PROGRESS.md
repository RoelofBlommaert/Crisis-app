# Progress Log — Crisis & Connectivity Monitor

Running log of what's been done on this project and what's next.
See `Documentation/Relevance and function.txt` for the app concept and
`Documentation/Data ideation.txt` for the data source decisions.

## 2026-09-14

- Repo scaffolding created: `App/`, `Data/` (with `CBS flight patterns/`,
  `GDELT/`, `Reliefweb and GDACS/` subfolders), `Documentation/`.
- Wrote up the concept and data-source rationale in `Documentation/`.
- Decided against OpenSky historical flight data (anonymous tier is
  live-only); using Eurostat/CBS seasonal travel stats as the travel
  trend layer instead. OpenSky may still be used for an optional
  live-snapshot map view.
- All folders currently empty except docs — no data pulled and no app
  code written yet.
- Added this progress file and confirmed the repo is connected to
  GitHub (`origin` → RoelofBlommaert/Crisis-app), working tree clean.

- Built data-gathering scripts in `Scripts/` for all four sources and ran
  them, saving output into `Data/`:
  - `fetch_gdelt_tension.py` — article volume + avg tone per country.
  - `fetch_gdacs_events.py` — current disaster events (99 pulled, 8
    matching our country list).
  - `fetch_reliefweb_events.py` — wired up but skipped: ReliefWeb now
    requires a pre-approved appname (changed 1 Nov 2025, after the
    original docs were written); writes a status note explaining how to
    get one instead of failing the run.
  - `fetch_cbs_travel.py` — outbound travel stats from CBS table
    84365NED, 2021–2025.
  - `fetch_opensky_snapshot.py` — bonus optional live aircraft snapshot
    (documented as live-only, not a trend source).
- Picked a working 8-country tracking list (`Scripts/countries.py`):
  Turkey, Ukraine, Lebanon, Israel, Egypt, Sudan, Haiti, Thailand.
- Found and documented two source-quality issues not known when the
  original docs were written (see `Scripts/README.md`):
  - CBS's outbound-travel table only breaks out ~15 individually-named
    "most visited" destinations; everything else (most of our crisis
    countries) is only available at continent/region level. Rows are
    tagged `country` vs `region` granularity accordingly.
  - GDACS only covers natural disasters, not conflict/political crises —
    a real gap for e.g. Lebanon/Israel/Ukraine/Sudan.
- Renamed `Data/CBS flight patterns/` → `Data/Travel and flights/` since
  it now holds both the CBS travel baseline and the optional OpenSky
  snapshot.
- Hit the GDELT DOC 2.0 API's rate limit hard: even with retry/backoff,
  a shared/cloud IP got blocked for an extended period (confirmed via
  web search — this is a known issue for others polling it from
  CI/cloud environments, not just us). Fixed by switching
  `fetch_gdelt_tension.py` to GDELT's raw GKG bulk files
  (`data.gdeltproject.org/gdeltv2/`, updated every 15 min, no key, not
  rate-limited) instead of the query API. This also changed the shape of
  the GDELT output: instead of a ~3-month daily timeline, it's now a
  short high-resolution (15-min) recent snapshot — run it on a schedule
  and append to build real history. Full writeup, including the general
  pattern for polling GDELT hourly, is in `Scripts/README.md` under
  "Avoiding the GDELT rate limit."

## 2026-09-14 (continued) — data buildout + first app version

Reviewed the actual pulled data against the Documentation and found it
was too thin to build a real dashboard from (GDELT: ~2 hours of history;
GDACS: natural-disasters-only, 4 of 8 tracked countries are
conflict-driven with zero coverage; CBS: region-level for 7 of 8
countries). Decisions made with the user:
- No new account/registration signups — rules out a ReliefWeb appname
  and a BigQuery-based GDELT backfill.
- **Ship without ReliefWeb.** GDACS (disasters) + GDELT (media tone) are
  the permanent confirmed-event/signal layers; conflict-driven countries
  will only ever show a tone signal, not a confirmed-event marker. Noted
  in `Documentation/Relevance and function.txt`.
- **Publish as a one-time static snapshot** on GitHub Pages — no
  GitHub Actions cron, no recurring refresh.
- To get more data without any signup: **backfilled GDELT 7 days back at
  hourly resolution** (168 static bulk-file downloads — same
  no-key/no-rate-limit mechanism as before, just walking further back in
  time) instead of only the latest 8 files.

Work done:
- Checked Eurostat's `tour_dem_ttw` (trips by destination) as a possible
  fix for CBS's region-only gap. It does have per-country codes for
  Turkey and Ukraine, but querying the live API confirmed the
  Netherlands reports **zero data for Ukraine** in it, across every
  combination — so it adds nothing over CBS. Documented and dropped
  rather than built; see `Scripts/README.md`.
- Added `--backfill` mode to `fetch_gdelt_tension.py`: computes and
  downloads the top-of-hour GKG file for each of the past 7×24 hours
  directly (rather than following `lastupdate.txt`), producing
  `Data/GDELT/gdelt_tension_history_<date>.csv`.
- **Found and fixed a real bug** in `fetch_gdacs_events.py`'s country
  matching: it matched country names as a substring
  (`"sudan" in "south sudan"`), so a South Sudan flood event was being
  incorrectly attributed to our tracked "Sudan". Fixed to match whole
  comma-separated name tokens, added a `matched_countries` column to the
  matched-events CSV (the row's own `iso3` only ever names one country
  in a multi-country event, so it isn't reliable for per-country
  attribution on its own).
- Built `Scripts/merge_data.py`: combines GDELT history, matched GDACS
  events, and CBS travel data into one static `App/data/dataset.json`
  per country (tension series, events list — genuinely empty where
  there's no confirmed-event coverage, travel baseline with its
  granularity flag preserved).
- Built the first version of the app in `App/` (`index.html`,
  `styles.css`, `app.js`): a Leaflet marker map + country list
  color-coded by an illustrative alert level, with a per-country detail
  view (Chart.js tension trend, matched GDACS events, CBS travel table
  with a country/region badge) and an About panel stating the data
  caveats. Plain static site, CDN libraries only, reads
  `data/dataset.json` via a relative path — works unmodified on GitHub
  Pages.

### Next up
- [ ] Run `fetch_gdelt_tension.py --backfill` + `merge_data.py`, and
      smoke-test the app locally (`python -m http.server` from `App/`)
- [ ] Publish: repo Settings → Pages → Deploy from branch → `main` →
      folder `/App` (manual step, not something automatable from here)
- [ ] If this ever needs to become a live-refreshing dashboard rather
      than a one-time snapshot, revisit the GitHub Actions cron option
      that was consciously deferred this round
- [ ] Register a ReliefWeb appname if conflict/displacement reporting
      (vs. GDACS's natural-disasters-only coverage) is worth adding later
