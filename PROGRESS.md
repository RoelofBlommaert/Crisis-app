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

Published: committed, pushed, and deployed to GitHub Pages via a
GitHub Actions workflow (`.github/workflows/deploy-pages.yml`) scoped to
`App/` only — Data/Scripts/Documentation stay out of the live site. The
first auto-triggered run failed at `configure-pages` because Pages
wasn't enabled yet at push time; fixed by enabling Settings → Pages →
Source: GitHub Actions and re-running the workflow manually.

## 2026-09-14 (continued 2) — conflict/disaster signal scoring + frontend pass

User feedback after seeing the deployed app: Israel/Lebanon showed high
article volume and strongly negative tone (real ongoing Levant crisis)
but still rendered "Green" — the alert-level heuristic was broken. Root
cause: it used the whole 7-day *average* tone against fixed thresholds
(-4/-8), which a week-long average essentially never reaches even during
real crises (Lebanon's week-average tone was only -2.9) because routine
coverage dilutes acute events.

Fix, plus the requested "chances of conflict" feature: explicitly framed
this as an illustrative 0-100 heuristic, not a real statistical
probability — there's no calibrated base rate or validated model behind
it, consistent with this app's existing "not operational, not validated"
framing.
- Downloaded a live GDELT GKG file and inspected real `V2Themes` tags for
  our tracked countries (rather than trusting docs alone) to find actual
  in-use codes: `NATURAL_DISASTER_*` prefix for disaster articles;
  `ARMEDCONFLICT`, `PROTEST`, `TERROR`, `UNREST_BELLIGERENT`, and several
  World Bank taxonomy codes for conflict articles.
- Extended `fetch_gdelt_tension.py` to tally `conflict_article_count` /
  `disaster_article_count` per country per file, re-ran the 7-day
  hourly backfill.
- Rewrote `merge_data.py`'s scoring: `conflict_signal` and
  `disaster_signal` (0-100 each), combining recent (last-24h) theme
  share, tone severity, a volume-spike bonus, and confirmed GDACS
  alert level — replacing the flat-average-tone `alert_level_for`.
  Verified against real recomputed data before settling on constants
  (Israel/Lebanon now correctly land "Red, conflict-driven"; Sudan's
  civil war also correctly surfaces as high-conflict; Egypt/Turkey come
  out moderately elevated too, which is real but partly an artifact of
  GDELT tagging bordering/mediating countries mentioned in Gaza-related
  coverage — documented as a known limitation, not hidden).
- Frontend pass: header stat strip (count of Red/Orange/Green), country
  list sorted by risk with dual conflict/disaster mini-bars, per-country
  gauge bars with an explicit "not a forecast" disclaimer, a second
  chart showing conflict-vs-disaster theme share over time, map markers
  sized by recent volume, general visual polish. About panel and
  `Documentation/` updated with the new methodology and its limitations.
- Re-tested end-to-end in a browser: bug confirmed fixed, no console
  errors, gauges/charts/list all render correctly.

## 2026-09-14 (continued 3) — fixed year-old events leaking into "current" score + visual overhaul

User caught a second, related bug: GDACS's "matched events" list includes
events that GDACS keeps listed for a while after they're actually over
(Haiti's cyclone from Oct 2025, Turkey's earthquake, Thailand's floods —
all 7-11 months old relative to the current snapshot date), and the
previous scoring counted *any* matched event toward `disaster_signal`
regardless of how old it was — silently mixing a year of stale event data
into what was supposed to be a "last week" score.

Fix: `score_country` in `merge_data.py` now scores **one calendar day at
a time** instead of one flat number, and a GDACS event only counts toward
a given day's `disaster_signal` if that day actually falls within the
event's own `fromdate`/`todate` range (`event_active_on`). Concretely:
Haiti/Turkey/Thailand's old events no longer inflate today's score (Turkey
dropped from disaster_signal 57 to 10; Thailand dropped from Red to Green
entirely), while still showing up in the country's event list tagged
`is_current: false` / "Historical" rather than being hidden. Each
country's full `daily_scores` array (conflict/disaster/alert_level per
day) is now in the dataset, and the top-level fields are simply the most
recent day's entry — so "today's" gauge and the new 7-8 day history strip
are guaranteed to agree.

Also did the requested visual overhaul of `App/` (was "very barebones"):
Inter font, gradient header band with stat chips, redesigned country list
(risk number + dual mini-bars, sorted by risk), circular CSS
conic-gradient gauges with a day-by-day color strip underneath each,
card-based layout with shadows/spacing throughout, active-vs-historical
event styling, and (after CartoDB's basemap tiles turned out to now
require a key -- showed a watermark instead of a map) a dark-mode map
via a CSS filter on the OSM tile layer rather than a paid/keyed tile
provider. Re-verified end-to-end in-browser: no console errors, Turkey's
old earthquake correctly shows "Historical," gauges/strips/charts render.

## 2026-09-14 (continued 4) — realigned with STRATEGY.md

User found `C:\Users\roelo\Downloads\STRATEGY.md` (the actual strategy doc
for this PoC -- crisis classification support for NWW/MFA) and asked for
a from-scratch comparison against what had actually been built. Found
real misalignment, not just polish:
- STRATEGY.md explicitly says no crisis prediction and no automatic
  classification are required yet at this PoC stage, but the app had
  quietly become exactly that: an automatic 0-100 score classifying every
  country with no human step.
- STRATEGY.md's primary user (crisis coordinator) and its named tracks
  (near-real-time engineering, data integration, classification
  groundwork, flexibiliteit/hybride sturing) had no clear representation
  in the app -- it instead starred a travel/tourism narrative and had no
  comms-volume layer at all, despite the strategy naming that as core to
  the primary workflow and explicitly allowing synthetic data for it.

Decisions (via clarifying questions): keep the automatic scoring
mechanism but recalibrate it, explain the data instead of only scoring
it, add a synthetic comms-volume layer, reframe CBS as context (not a
trend narrative), keep the static snapshot but surface freshness, and
leave the "hybride sturing" manual-override track as a deliberately
deferred gap this round (not built).

Work done:
- **Recalibrated scoring** (`Scripts/merge_data.py`): live data showed
  6-8 of 8 countries at Orange-or-above almost every day. Root cause:
  `conflict_share * 70` crosses the old Orange cutoff at ~43% share, and
  GDELT tags articles with every country they *mention* (so Egypt/Turkey
  pick up conflict share from Gaza-adjacent coverage without being
  combatants); `disaster_share * 100` let single-article low-volume days
  swing the score by up to 100 points of noise. Fixed with lower weights,
  a `confidence = min(1, day_volume/15)` dampener, and raised bands
  (Red>=65, Orange>=35, was 60/30). Result: 0 Red / 5 Orange / 3 Green
  today, a believable spread.
- **Added a real "what's happening" explanation**: extended
  `fetch_gdelt_tension.py` to tally which *specific* theme codes matched
  (not just a conflict/disaster boolean) into a new
  `gdelt_theme_breakdown_<date>.csv`; `merge_data.py` exposes
  `top_conflict_themes`/`top_disaster_themes` per country with a
  human-readable label and each theme's **share of that week's total
  articles** (added after noticing a bare count like "Famine: 96
  articles" reads as a real signal without that context, when it's
  <2% of a high-volume country's week).
- **Added the synthetic comms-volume layer**: new
  `Scripts/generate_synthetic_comms.py`, deterministic per country+day,
  loosely scaled off real GDELT volume, labelled SYNTHETIC everywhere in
  the UI and docs -- per STRATEGY.md's explicit allowance for
  unconfirmed sources.
- **Restructured the frontend**: "What's happening this week" leads
  (real theme breakdown before any chart), GDACS events split into
  active-this-week (expanded) vs. historical (collapsed `<details>`,
  fixing the earlier complaint that old 2025 events dominated the
  picture), CBS travel reframed as a one-line context stat with the
  5-year table collapsed, decoded GDACS event-type badges
  (EQ→Earthquake etc.), and a new "Data sources & freshness" section in
  the About panel listing each source's real vintage.
- **Realigned Documentation** (`Documentation/Relevance and function.txt`):
  crisis-coordinator framing (not general travel-advisory framing),
  explicit note that the "hybride sturing" override track is a
  deliberately deferred gap, and the recalibration/synthetic-data
  rationale.
- Re-tested end-to-end in-browser: no console errors, score distribution
  now spans Green/Orange/Red sensibly, historical events collapse
  correctly, synthetic layer clearly labelled throughout.

### Next up
- [ ] Build the "hybride sturing" manual-override control (coordinator
      confirms/corrects a suggested classification) -- deliberately
      deferred this round, not an oversight
- [ ] Re-run `fetch_gdelt_tension.py --backfill` + `generate_synthetic_comms.py`
      + `merge_data.py` periodically if the signals should stay current
      (still a one-time snapshot by design — see Documentation)
- [ ] If this ever needs to become a live-refreshing dashboard rather
      than a one-time snapshot, revisit the GitHub Actions cron option
      that was consciously deferred this round
- [ ] Register a ReliefWeb appname if conflict/displacement reporting
      (vs. GDACS's natural-disasters-only coverage) is worth adding later
- [ ] Commit and push this round's changes, confirm the Pages deploy
