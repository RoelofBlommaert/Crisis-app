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

## 2026-09-14 (continued 5) — added ACLED as the primary conflict data source

User asked what data was actually used and specifically whether ACLED
(Armed Conflict Location & Event Data Project) was in the mix. It wasn't
-- confirmed by grep. User's follow-up: add it, since it's real
ground-truth conflict data (event-level fatalities/actors) vs. GDELT's
media-mention proxy, and called it possibly "the most important" source.

This reverses the earlier "no new registrations" decision in spirit, so
researched ACLED's actual access model before proposing anything:
ACLED's own API needs a registered myACLED account + generated key. But
ACLED itself publishes pre-aggregated country files through the
Humanitarian Data Exchange (data.humdata.org) with **no registration**
-- confirmed by querying HDX's public CKAN API directly (not assumed),
covering all 8 tracked countries, updated weekly. Tradeoff: monthly
resolution (event+fatality counts), not daily/event-level like ACLED's
own API would give with an account.

Work done:
- New `Scripts/fetch_acled_hdx.py`: pulls political-violence,
  civilian-targeting, and demonstration-event monthly counts per
  country from HDX. Found and fixed a real bug on the first run: three
  countries (Ukraine, Sudan, Haiti -- current Humanitarian Response
  Plan countries) use a different HDX file layout with one row per
  Admin1/Admin2 sub-region per month, not one national row -- this
  inflated their row counts by 100-500x before the fix aggregated
  properly to national totals.
- Redesigned `merge_data.py`'s conflict_signal to make ACLED's fatality
  count the **dominant, ground-truth term** -- structurally mirroring
  how GDACS already dominates disaster_signal (both are now: confirmed-
  source severity score, weight 25/tier up to 75, plus GDELT as
  secondary corroboration). Verified real severity bands against live
  data before picking them (0 fatalities->0, 1-24->1, 25-99->2, 100+->3
  -- log-scaled, not linear, since real counts span 0 to 4000+ across
  our 8 countries).
- Found and handled a second real pattern in the live data before
  trusting it: the single most recent available ACLED/HDX month is
  consistently far below the surrounding trend for nearly every country
  simultaneously (Sudan 876->70, Ukraine 4008->1010 fatalities, month
  over month) -- reporting/verification lag, not synchronized
  de-escalation across unrelated wars. Scoring uses the previous
  complete month instead; the provisional month is still shown in the
  chart (visible as a sudden drop at the right edge) with an
  explanatory note, not hidden.
- Recalibrated with real data before finalizing: new distribution is
  4 Red (Ukraine, Sudan, Haiti, Lebanon), 3 Orange (Turkey, Egypt,
  Israel), 1 Green (Thailand) -- a believable, ground-truth-anchored
  spread, matching real severity far better than the GDELT-only version.
- Added a real 24-month ACLED chart (fatalities + events) per country to
  the frontend, with required ACLED attribution (their Terms of Use
  mandate clear acknowledgement wherever their data or a derivative is
  shown, and prohibit redistributing raw data -- this app only shows
  aggregated/visualized derivatives, never a raw dump) and a
  "GROUND TRUTH" tag distinguishing it from the media-proxy signals.
- Updated Documentation, Scripts/README.md, and the About panel's
  "Data sources & freshness" list accordingly.
- Re-tested end-to-end in-browser: no console errors, scores match hand
  calculation, provisional-month drop-off visible and explained in the
  chart itself.

## 2026-09-14 (continued 6) — replaced flat ACLED fatality score with baseline vs. escalation

User asked why scores jumped so much, and separately pushed back on the
result: "many countries are at about 100 for conflict" with no
differentiation, and asked for scores that reflect risk of *imminent*
crisis rather than raw violence scale. They also asked for ACLED to be
the main driver, for a unified "what's happening" view (event counts,
types, article volume/tone), and for Dutch-citizen exposure to connect
to that picture.

Root cause of the saturation, confirmed against live data before
redesigning: the previous banding (0/1-24/25-99/100+ fatalities ->
0/1/2/3, *25 each) put Ukraine (4008 fatalities), Sudan (876), and Haiti
(103) all in the same top tier, clipping conflict_signal at 100 for all
three -- and worse, two of them (Sudan, Ukraine: ratio 0.75-0.77) were
actually running *below* their own 12-month average that month, i.e. a
stable chronic war, not a fresh spike, while Egypt's real 3.3x jump
above its own near-zero baseline was completely invisible next to them.
Absolute severity alone conflates "always been terrible here" with
"something new is happening here" -- backwards for an imminent-risk lens.

Redesigned `merge_data.py`'s conflict_signal into two explicit,
separately-shown components instead of one flat band:
- **severity** (0-75): log-scaled off that month's real ACLED fatalities
  against a fixed external reference (5000 fatalities/month, roughly
  the scale of the world's most severe active conflicts -- deliberately
  not derived from our own 8-country sample, so it won't shift if
  countries are added/removed). Differentiates Ukraine(73)/Sudan(60)/
  Haiti(41)/Lebanon(29)/Egypt(21) by real scale instead of saturating.
- **escalation_bonus** (0-15): only activates when the current month
  exceeds that country's own trailing-12-month average -- a below-
  baseline month gets zero bonus, never a penalty. This is what
  actually flags "something newly happening" (Egypt: ratio 3.33x ->
  full +15 bonus, correctly surfacing an emerging signal despite tiny
  absolute numbers).
GDELT's role shrank to a small corroborating nudge (was up to 45 points,
now up to ~10) since ACLED is now explicitly "the main driver."

New distribution (verified against real numbers, not assumed): Ukraine
83, Sudan 69 (2 Red); Haiti 43, Egypt 43, Lebanon 38 (3 Orange); Thailand
17, Israel 11, Turkey 11 (3 Green) -- well-differentiated, no more
identical scores at the ceiling.

Frontend changes to match:
- Reordered the detail panel so the ACLED "Baseline & escalation" box
  comes immediately after the gauges (the dominant driver, explained
  first), with GDELT's theme breakdown relabelled "Media attention this
  week (corroborating, not the driver)" and moved below it.
- The ACLED box now states both numbers explicitly in one sentence
  ("this month runs at 3.33x that baseline") plus a directional trend
  badge (↑ Escalating / → Stable / ↓ Below baseline) with its own arrow
  glyphs so it can't be mistaken for the absolute-severity badge, and
  folds in that month's civilian-targeting and demonstration counts
  (previously fetched but not shown) -- the unified "how many things,
  what type" view the user asked for.
- CBS renamed "Dutch citizen exposure" with a sentence explicitly
  connecting it to the risk picture ("a coordinator combines... "),
  without fabricating a fake composite risk×exposure number -- shown
  separately by design, consistent with this project's "explain the
  data, don't just compress it" approach throughout.
- Updated the About panel and Documentation with the full before/after
  reasoning (not just the new formula) so a reader can see why it
  changed, not only what it is now.
- Re-tested in-browser: no console errors, Egypt's escalation renders
  distinctly from Ukraine/Sudan's chronic-but-stable severity.

### Next up
- [ ] Build the "hybride sturing" manual-override control (coordinator
      confirms/corrects a suggested classification) -- deliberately
      deferred this round, not an oversight
- [ ] Re-run `fetch_gdelt_tension.py --backfill` + `generate_synthetic_comms.py`
      + `fetch_acled_hdx.py` + `merge_data.py` periodically if the signals
      should stay current (still a one-time snapshot by design — see
      Documentation)
- [ ] If this ever needs to become a live-refreshing dashboard rather
      than a one-time snapshot, revisit the GitHub Actions cron option
      that was consciously deferred this round
- [ ] Register a ReliefWeb appname if disaster/displacement reporting
      beyond GDACS is worth adding later (ACLED now covers the
      conflict-confirmed-event gap that ReliefWeb would have)
- [ ] Commit and push this round's changes, confirm the Pages deploy

## 2026-09-15: Data minimization pass

Trimmed the pipeline to the three sources that actually drive the
conflict/disaster signals, per an explicit ask to minimize the dataset
to what serves "is tension in a country rising toward a crisis":

- **Removed OpenSky** (`fetch_opensky_snapshot.py` + its Data files) —
  it was never wired into `merge_data.py` or rendered anywhere in the
  app; pure dead data collection since the "optional right-now layer"
  mentioned earlier in this log was never actually built.
- **Removed CBS travel** (`fetch_cbs_travel.py`, `travel_baseline`,
  the "Dutch citizen exposure" panel) — annual, lagging traveler/spend
  counts are exposure context, not a tension signal, and several
  tracked countries were region- not country-level anyway. Cut from
  the app entirely rather than just hidden.
- **Removed ReliefWeb** (`fetch_reliefweb_events.py`, the status-file
  workaround) — never produced data in the first place (appname
  requirement since 1 Nov 2025, never actually merged), and GDACS +
  ACLED already cover the disaster/conflict ground it would add.
- **Removed the synthetic comms-volume layer**
  (`generate_synthetic_comms.py`, `comms_volume`, the "Incoming
  communication volume" chart) — fictional demo data, never connected
  to a real NWW/consular system; removed rather than kept as a
  placeholder.
- **Renamed** `Data/Reliefweb and GDACS/` to `Data/GDACS/` now that
  ReliefWeb is gone; `merge_data.py` and `fetch_gdacs_events.py`
  updated to match.
- **Kept GDELT, GDACS, ACLED** — see `Scripts/README.md`'s new
  "Sources dropped after review" section for why each of these three
  earns its place (ACLED = ground-truth conflict severity, GDACS =
  ground-truth disaster events, GDELT = the only sub-monthly signal,
  showing day-to-day movement and *which* themes are driving attention
  between ACLED's monthly updates).
- Regenerated `App/data/dataset.json` after the change; verified the
  removed fields (`travel_baseline`, `comms_volume`) are gone from its
  output and the app still renders with the trimmed dataset.

## 2026-09-15: ACLED scoring switched to unrest-primary, fatalities as an accelerant

Explicit steering ask: score mostly on unrest (ACLED event count), with
fatalities as a secondary signal that pushes the score up faster once
people are dying, "because we have to act even more swiftly" once deaths
are involved -- not the reverse (score primarily on deaths).

`acled_severity()` in `merge_data.py` reworked from severity+escalation
on **fatalities** to three explicit components, all still derived from
the same monthly ACLED political-violence series:
- `unrest_severity` (0-55): log-scaled off that month's real ACLED
  **event count**, against a fixed 10,000-events/month reference (the
  world's most intense active unrest, not derived from our 8-country
  sample) — was fatality-based (0-75, 5,000-fatalities/month reference).
- `unrest_escalation_bonus` (0-15): only activates when this month's
  **event count** exceeds the country's own trailing-12-month average —
  was fatality-ratio-based.
- `fatality_boost` (0-20, new): log-scaled off fatalities against a much
  lower 500-fatalities/month reference, deliberately chosen so it climbs
  fast at low death tolls (50 deaths already ~63% of max) rather than a
  slow-building curve — the "act more swiftly" requirement.

`acled_component` stays 0-90 (unchanged ceiling, still conflict_signal's
dominant term). Verified against live data before shipping: Ukraine
unrest ~54 (highest event count, 8199/month), Sudan ~33, Lebanon ~38,
Haiti ~25 — ordered by real event-count scale, not death toll. Turkey
(9 events, but 3x its own tiny baseline) earns the full +15 escalation
bonus and outranks higher-volume-but-stable countries. Sudan (876
fatalities) and Haiti (103 fatalities) both max the +20 fatality
accelerant even though their event counts alone wouldn't justify that —
this is the intended "swift action once people are dying" effect.

Renamed fields throughout (`merge_data.py` output, `App/app.js`,
`App/index.html`'s About panel): `severity`→`unrest_severity`,
`escalation_bonus`→`unrest_escalation_bonus`, `escalation_ratio`→
`events_ratio`, new `baseline_events` alongside the still-present
`baseline_fatalities`/`scoring_fatalities` (now secondary). The
"Baseline & escalation" detail box is now "Unrest & escalation" and
leads with the event count/trend, with fatalities shown as a second
line that explicitly flags when the toll is high enough to be driving
urgency on its own (`fatality_boost >= 15`). Regenerated
`App/data/dataset.json` and re-tested in-browser: no console errors,
new distribution renders correctly (Ukraine 86, Sudan 63, Lebanon 58 —
still Red/Orange as expected, just for the right reasons now).

## 2026-09-15: Supabase Auth + RLS access control

Explicit ask: only pre-approved users may see the app's data. Scoped
first (see the "Explicit permission" writeup earlier this session, not
duplicated here): the static UI shell (HTML/CSS/JS) stays public --
GitHub Pages on a public repo has no mechanism to gate file serving --
but the actual dataset moves behind Supabase Auth + Postgres RLS.

**Connected via the Supabase MCP server**, added through the `claude`
CLI (`claude mcp add --transport http supabase
"https://mcp.supabase.com/mcp?project_ref=<ref>&features=database"`,
then `claude mcp login supabase` in an interactive terminal for the
OAuth flow -- deliberately scoped to this one project and to database
tools only, not full account access). This replaced the original plan
of having the user copy-paste SQL into Supabase Studio's SQL Editor by
hand (which had already failed twice on truncated pastes) -- MCP let
the schema and data go in directly and verifiably.

**Schema** (`Scripts/supabase/001_schema.sql`, idempotent, safe to
re-run, committed since it's structure-only, no data):
- `allowed_users(email, note, created_at)` -- RLS enabled, **zero**
  policies (intentional deny-by-default; not even readable by
  authenticated users via the API, only via SQL/MCP as project owner).
- `dataset_snapshot(id, generated_at, payload jsonb)` -- singleton row
  (`id=1`), RLS enabled, one explicit SELECT policy: `to authenticated
  using (exists (select 1 from allowed_users where lower(email) =
  lower(auth.jwt()->>'email')))`. No insert/update/delete policies at
  all -- writes only via MCP/SQL as project owner.

**Auth configuration** (done by the user in Supabase Studio, browser
only): public sign-ups disabled (`Authentication -> Providers -> Email
-> Allow new users to sign up` off -- confirmed via
`GET /auth/v1/settings` returning `disable_signup: true`); two test
accounts created with "Auto Confirm User" so no confirmation-email
dependency (`allowed.tester@example.com`, `blocked.tester@example.com`)
without touching the project's real email-confirmation setting. Only
`allowed.tester@example.com` was inserted into `allowed_users` --
`blocked.tester@example.com` exists as a valid login but is deliberately
not on the allowlist, to exercise the "authenticated but not authorized"
path.

**Frontend** (`App/index.html`, `App/app.js`, `App/auth.js`,
`App/supabase-config.js`, `App/styles.css`):
- Three screens (`#login-gate`, `#access-denied`, `#app-shell`), driven
  entirely by `sb.auth.onAuthStateChange` in `auth.js` -- no session ->
  login form; session but the `dataset_snapshot` query comes back empty
  (RLS silently filters rows for non-allowlisted users, surfaced via
  `.maybeSingle()` returning `null` rather than an error) -> access-denied
  screen showing which account is signed in; session + row returned ->
  `startApp(payload)` (renamed from the old `init()`) renders the map/list/
  charts from the fetched `payload`, no more `fetch("data/dataset.json")`.
- Sign-out (both the header button and the access-denied screen's button)
  calls `resetApp()` (new in `app.js`) before showing the login screen
  again -- tears down the Leaflet map instance and Chart.js instances so
  a second login within the same page load doesn't hit "Map container is
  already initialized."
- `App/supabase-config.js` holds only the Project URL and the `anon`
  public key (role confirmed by decoding the JWT: `"role":"anon"`) --
  intentionally public, safe to commit; the real boundary is the RLS
  policy above, not keeping this file secret. No service-role key or DB
  password anywhere in the repo, frontend, or this conversation.

**Data migration**: `App/data/dataset.json` removed from git entirely
(`git rm -f`) -- the merged dataset is no longer a public static file.
`Scripts/merge_data.py`'s `OUT_PATH` now points at
`Data/dataset_snapshot.local.json` (gitignored, local preview only,
never published). The actual seeding into `dataset_snapshot` was done
directly via the MCP `execute_sql` tool: one small `insert` for the
top-level metadata (`generated_at`/`note`/`data_sources`, empty
`countries` array) followed by 8 small `update ... jsonb_set(...)`
statements, one per country (~38KB each), appending that country's
object into the `countries` array -- chosen over one giant ~480KB
`insert` specifically to stay well under any single-tool-call output
size risk. Verified after: `jsonb_array_length(payload->'countries') =
8`, all 8 country names present, matching the original `dataset.json`.

**Verified end-to-end (real backend, not mocked)**:
- Logged out: `index.html` shows only the login form; no app UI, no
  data fetch of any kind.
- Wrong credentials: Supabase Auth rejects, "Invalid login credentials"
  shown inline -- confirmed against the real Auth API, not simulated.
- Direct API request, no session: `curl` against
  `.../rest/v1/dataset_snapshot?select=payload` with only the anon key
  (no `Authorization` bearer token from a logged-in user) returns `[]`
  -- RLS enforcement confirmed independent of any frontend code running.
- No console errors on the login screen against the live Supabase
  project.

**Not yet tested (needs the user, who holds the test-account
passwords)**: successful login as `allowed.tester@example.com` and
confirming the full app renders; login as `blocked.tester@example.com`
and confirming the access-denied screen appears (not the app, not a
silent failure); direct URL access while logged out; re-attempting
access after signing out and logging back in as a different account
within the same page load (tests `resetApp()`'s map/chart teardown).
