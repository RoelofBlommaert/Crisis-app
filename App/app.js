const LEVEL_LABEL = {
  Green: "Low signal",
  Orange: "Elevated",
  Red: "High",
  unknown: "No signal",
};

const LEVEL_COLOR = {
  Green: "#16a34a",
  Orange: "#f59e0b",
  Red: "#dc2626",
  unknown: "#9ca3af",
};

const DRIVER_LABEL = {
  conflict: "Conflict-driven",
  disaster: "Disaster-driven",
};

const GDACS_EVENTTYPE_LABEL = {
  EQ: "Earthquake",
  FL: "Flood",
  TC: "Tropical Cyclone",
  DR: "Drought",
  VO: "Volcanic activity",
  WF: "Wildfire",
  TS: "Tsunami",
  LS: "Landslide",
  EP: "Epidemic",
  ST: "Storm",
};

const CONFLICT_ICON = `<svg class="gauge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" stroke-linecap="round"/></svg>`;
const DISASTER_ICON = `<svg class="gauge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15a4 4 0 0 1 1-7.87A5 5 0 0 1 15 6a4.5 4.5 0 0 1 1 8.9" stroke-linecap="round" stroke-linejoin="round"/><path d="M9 19l1.5-3M13 19l1.5-3M11 21l1-2" stroke-linecap="round"/></svg>`;

let map;
let tensionChart;
let themeChart;
let acledChart;
let markers = {};
let dataset;

function riskScore(country) {
  return Math.max(country.conflict_signal || 0, country.disaster_signal || 0);
}

function gaugeColor(value) {
  if (value >= 65) return LEVEL_COLOR.Red;
  if (value >= 35) return LEVEL_COLOR.Orange;
  return LEVEL_COLOR.Green;
}

function fmtDay(dateStr) {
  return new Date(dateStr + "T00:00:00Z").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function fmtDateTime(iso) {
  if (!iso) return "unknown";
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function init() {
  const resp = await fetch("data/dataset.json");
  dataset = await resp.json();

  document.getElementById("snapshot-note").textContent =
    `Snapshot generated ${new Date(dataset.generated_at).toLocaleString()} — not a live feed. Conflict/disaster signals are scored per day, not a forecast probability.`;

  renderStatStrip();
  setupAboutPanel();
  renderDataSources();

  map = L.map("map", { scrollWheelZoom: false }).setView([25, 40], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 8,
    minZoom: 2,
  }).addTo(map);

  const listEl = document.getElementById("country-list-items");
  const sorted = [...dataset.countries].sort((a, b) => riskScore(b) - riskScore(a));

  sorted.forEach((country) => {
    if (country.coords) {
      const vol = (country.tension_series || []).slice(-24).reduce((s, p) => s + p.volume_article_count, 0);
      const radius = 6 + Math.min(12, Math.sqrt(vol) * 0.6);
      const marker = L.circleMarker(country.coords, {
        radius,
        color: "#fff",
        weight: 1.5,
        fillColor: LEVEL_COLOR[country.alert_level] || LEVEL_COLOR.unknown,
        fillOpacity: 0.88,
      }).addTo(map);
      marker.bindTooltip(
        `<strong>${country.name}</strong><br>Conflict: ${country.conflict_signal} · Disaster: ${country.disaster_signal}`
      );
      marker.on("click", () => selectCountry(country.name));
      markers[country.name] = marker;
    }

    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "country-item";
    btn.dataset.country = country.name;
    btn.innerHTML = `
      <span class="dot ${country.alert_level}"></span>
      <span class="country-item-name">${country.name}</span>
      <span class="mini-bars">
        <span class="mini-bar-track"><span class="mini-bar-fill conflict" style="width:${country.conflict_signal}%"></span></span>
        <span class="mini-bar-track"><span class="mini-bar-fill disaster" style="width:${country.disaster_signal}%"></span></span>
      </span>
      <span class="risk-num">${riskScore(country)}</span>
    `;
    btn.addEventListener("click", () => selectCountry(country.name));
    li.appendChild(btn);
    listEl.appendChild(li);
  });

  selectCountry(sorted[0].name);
}

function renderStatStrip() {
  const counts = { Red: 0, Orange: 0, Green: 0, unknown: 0 };
  dataset.countries.forEach((c) => {
    counts[c.alert_level] = (counts[c.alert_level] || 0) + 1;
  });
  const strip = document.getElementById("stat-strip");
  strip.innerHTML = ["Red", "Orange", "Green"]
    .map(
      (level) =>
        `<span class="stat-chip"><span class="dot ${level}"></span>${counts[level]} ${LEVEL_LABEL[level]}</span>`
    )
    .join("");
}

function renderDataSources() {
  const ds = dataset.data_sources;
  if (!ds) return;
  const el = document.getElementById("data-sources-list");
  el.innerHTML = `
    <li><strong>ACLED</strong> (real) — <span class="acled-tag">GROUND TRUTH</span> ${ds.acled.note}</li>
    <li><strong>GDELT</strong> (real) — ${fmtDateTime(ds.gdelt.earliest_timestamp_utc)} to ${fmtDateTime(ds.gdelt.latest_timestamp_utc)}</li>
    <li><strong>GDACS</strong> (real) — fetched ${ds.gdacs.fetched_on || "unknown"}</li>
  `;
}

function selectCountry(name) {
  const country = dataset.countries.find((c) => c.name === name);
  if (!country) return;

  document.querySelectorAll(".country-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.country === name);
  });

  if (country.coords) {
    map.setView(country.coords, 4, { animate: true });
  }
  if (markers[name]) {
    markers[name].openTooltip();
  }

  renderDetail(country);
}

function renderDetail(country) {
  const panel = document.getElementById("detail-panel");
  const level = country.alert_level || "unknown";

  panel.innerHTML = `
    <div class="detail-header">
      <h3>${country.name}</h3>
      <span class="badge ${level}">${LEVEL_LABEL[level] || "Unknown"}</span>
      <span class="driver-tag">${DRIVER_LABEL[country.driver] || ""}</span>
    </div>

    <div class="gauges">
      ${renderGauge("Conflict signal", CONFLICT_ICON, country.conflict_signal, country.daily_scores, "conflict_signal")}
      ${renderGauge("Disaster signal", DISASTER_ICON, country.disaster_signal, country.daily_scores, "disaster_signal")}
    </div>
    <p class="gauge-disclaimer">
      Illustrative 0&ndash;100 heuristic, scored one day at a time &mdash; <strong>not</strong> a statistical
      forecast or probability of war/disaster. Conflict signal is driven primarily by real ACLED unrest
      (event count and its own escalation, see below), with fatalities as a secondary accelerant and
      GDELT media coverage as corroboration; disaster signal works the same way with GDACS. Bars above
      show each recent day, oldest to newest.
    </p>

    <div class="side-section acled-box">
      <strong>Unrest &amp; escalation (ACLED) <span class="acled-tag">GROUND TRUTH</span></strong>
      ${renderAcledSummary(country.acled)}
      <p class="attribution">Source: <a href="https://acleddata.com" target="_blank" rel="noopener">ACLED</a> (Armed Conflict Location &amp; Event Data Project), via HDX aggregated country files.</p>
    </div>

    <h4>Media attention this week (corroborating, not the driver)</h4>
    <div class="explain-grid">
      ${renderThemeExplain("Conflict themes", country.top_conflict_themes)}
      ${renderThemeExplain("Disaster themes", country.top_disaster_themes)}
    </div>

    <div class="detail-grid">
      <div>
        <h4>Events &amp; fatalities over time (ACLED, 24 months)</h4>
        <div class="chart-box"><canvas id="acled-chart"></canvas></div>
        <h4>Media signal, last 7-8 days</h4>
        <div class="chart-box"><canvas id="tension-chart"></canvas></div>
        <h4>Conflict vs. disaster theme share</h4>
        <div class="chart-box chart-box-small"><canvas id="theme-chart"></canvas></div>
      </div>
      <div>
        <div class="side-section events-list">
          <strong>Confirmed disaster events (GDACS)</strong>
          ${renderEvents(country.events)}
        </div>
      </div>
    </div>
  `;

  renderAcledChart(country);
  renderTensionChart(country);
  renderThemeChart(country);
}

const TREND_BADGE = {
  Escalating: "Red",
  Stable: "Orange",
  "Below baseline": "Green",
  Unknown: "unknown",
};

const TREND_ARROW = {
  Escalating: "↑",
  Stable: "→",
  "Below baseline": "↓",
  Unknown: "",
};

function renderAcledSummary(acled) {
  if (!acled || !acled.severity || !acled.severity.scoring_period) {
    return '<p class="no-events">No ACLED data available for this country.</p>';
  }
  const sev = acled.severity;
  const trendBadge = TREND_BADGE[sev.trend] || "unknown";
  const civ = sev.civilian_targeting || { events: 0, fatalities: 0 };
  const demo = sev.demonstrations || { events: 0 };
  const urgentFatalities = sev.fatality_boost >= 15;

  return `
    <p class="acled-summary">
      <strong>${sev.scoring_period}</strong> (last complete month): <strong>${sev.scoring_events} political-violence events</strong>
      &mdash; the primary signal here. This country's own 12-month average is
      ~${sev.baseline_events}/month &mdash; this month runs at <strong>${sev.events_ratio}&times;</strong>
      that baseline. <span class="badge ${trendBadge}" title="Trend vs. this country's own event-count baseline, not an absolute severity rating">${TREND_ARROW[sev.trend] || ""} ${sev.trend}</span>
    </p>
    <p class="acled-summary">
      <strong>${sev.scoring_fatalities} fatalities</strong> from those events &mdash; a secondary signal that
      accelerates the score once people are actually dying${urgentFatalities ? ", <strong>which this month's toll does</strong>: high enough to warrant swifter action regardless of the raw event count." : ", but this month's toll isn't yet at that level on its own."}
    </p>
    <p class="acled-summary">
      Also that month: ${civ.events} civilian-targeting events (${civ.fatalities ?? 0} fatalities),
      ${demo.events} demonstrations.
    </p>
    <p class="synthetic-note">${sev.latest_period} data exists but is excluded as provisional: ACLED's
      most recent month is consistently far below trend across almost every country here, a reporting/
      verification lag rather than real de-escalation &mdash; see the sudden drop at the right edge of
      the chart below.</p>
  `;
}

function renderGauge(label, icon, value, dailyScores, field) {
  const color = gaugeColor(value);
  const strip = (dailyScores || [])
    .map((d) => `<span class="day-chip ${d.alert_level}" title="${fmtDay(d.date)}: ${field === "conflict_signal" ? "conflict" : "disaster"} ${d[field]}"></span>`)
    .join("");
  return `
    <div class="gauge-card">
      <div class="radial-gauge" style="--value:${value};--gauge-color:${color}">
        <span class="radial-value">${value}</span>
      </div>
      <div class="gauge-info">
        <div class="gauge-title">${icon}${label}</div>
        <div class="day-strip">${strip}</div>
      </div>
    </div>
  `;
}

function renderThemeExplain(title, themes) {
  if (!themes || themes.length === 0) {
    return `<div class="explain-box"><strong>${title}</strong><p class="no-events">No matching themes this week.</p></div>`;
  }
  const items = themes
    .map((t) => `<li>${t.label} <span class="theme-count">${t.count} articles &middot; ${(t.share_of_week * 100).toFixed(1)}% of week</span></li>`)
    .join("");
  return `<div class="explain-box"><strong>${title}</strong><ul>${items}</ul></div>`;
}

function renderEvents(events) {
  if (!events || events.length === 0) {
    return '<p class="no-events">No confirmed GDACS disaster events for this country. Note: GDACS covers natural disasters only, not conflict/political crises — see the About panel.</p>';
  }
  const active = events.filter((e) => e.is_current);
  const historical = events.filter((e) => !e.is_current);

  const renderOne = (e) => `<li>
      <span class="badge ${e.alertlevel}" style="font-size:0.68rem;">${e.alertlevel}</span>
      <span class="event-tag">${GDACS_EVENTTYPE_LABEL[e.eventtype] || e.eventtype}</span><br>
      ${e.eventname || e.eventtype} &mdash; ${e.description}
      <br><span style="color:var(--muted);font-size:0.8rem;">${e.fromdate.slice(0, 10)} to ${e.todate.slice(0, 10)}</span></li>`;

  let html = "";
  if (active.length > 0) {
    html += `<ul>${active.map(renderOne).join("")}</ul>`;
  } else {
    html += '<p class="no-events">No disaster event currently active this week.</p>';
  }
  if (historical.length > 0) {
    html += `<details class="history-toggle"><summary>${historical.length} historical event${historical.length > 1 ? "s" : ""} (most recent: ${historical[0].fromdate.slice(0, 10)})</summary><ul>${historical.map(renderOne).join("")}</ul></details>`;
  }
  return html;
}

function chartTextColor() {
  return getComputedStyle(document.body).getPropertyValue("--muted").trim() || "#6b7280";
}

function chartGridColor() {
  return getComputedStyle(document.body).getPropertyValue("--border").trim() || "#e5e7eb";
}

function renderTensionChart(country) {
  const ctx = document.getElementById("tension-chart");
  if (!ctx) return;
  if (tensionChart) tensionChart.destroy();

  const series = country.tension_series || [];
  const labels = series.map((p) =>
    new Date(p.timestamp_utc).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })
  );
  const textColor = chartTextColor();
  const gridColor = chartGridColor();

  tensionChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Article volume",
          data: series.map((p) => p.volume_article_count),
          borderColor: "#4f46e5",
          backgroundColor: "rgba(79,70,229,0.1)",
          fill: true,
          yAxisID: "y",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: "Avg. tone",
          data: series.map((p) => p.avg_tone),
          borderColor: "#dc2626",
          backgroundColor: "transparent",
          yAxisID: "y1",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: textColor, font: { size: 11 } } } },
      scales: {
        y: { type: "linear", position: "left", title: { display: true, text: "Articles", color: textColor }, ticks: { color: textColor }, grid: { color: gridColor } },
        y1: { type: "linear", position: "right", title: { display: true, text: "Tone", color: textColor }, ticks: { color: textColor }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: textColor, maxRotation: 60, minRotation: 60, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

function renderThemeChart(country) {
  const ctx = document.getElementById("theme-chart");
  if (!ctx) return;
  if (themeChart) themeChart.destroy();

  const series = country.tension_series || [];
  const labels = series.map((p) =>
    new Date(p.timestamp_utc).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })
  );
  const conflictPct = series.map((p) => (p.volume_article_count ? (100 * p.conflict_article_count) / p.volume_article_count : 0));
  const disasterPct = series.map((p) => (p.volume_article_count ? (100 * p.disaster_article_count) / p.volume_article_count : 0));
  const textColor = chartTextColor();

  themeChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Conflict-theme share (%)",
          data: conflictPct,
          borderColor: "#dc2626",
          backgroundColor: "rgba(220,38,38,0.15)",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 1.5,
        },
        {
          label: "Disaster-theme share (%)",
          data: disasterPct,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245,158,11,0.15)",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 1.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: textColor, font: { size: 11 } } } },
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: "% of articles", color: textColor }, ticks: { color: textColor } },
        x: { display: false },
      },
    },
  });
}

function renderAcledChart(country) {
  const ctx = document.getElementById("acled-chart");
  if (!ctx) return;
  if (acledChart) acledChart.destroy();

  const monthly = (country.acled && country.acled.monthly) || [];
  const pv = monthly.filter((r) => r.category === "political_violence").sort((a, b) => a.year - b.year || a.month_num - b.month_num);
  const labels = pv.map((r) => `${r.month.slice(0, 3)} ${r.year}`);
  const textColor = chartTextColor();

  acledChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Fatalities",
          data: pv.map((r) => r.fatalities),
          backgroundColor: "rgba(220,38,38,0.55)",
          yAxisID: "y",
          borderRadius: 3,
        },
        {
          type: "line",
          label: "Events",
          data: pv.map((r) => r.events),
          borderColor: "#4f46e5",
          backgroundColor: "transparent",
          yAxisID: "y1",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: textColor, font: { size: 11 } } } },
      scales: {
        y: { type: "linear", position: "left", title: { display: true, text: "Fatalities", color: textColor }, ticks: { color: textColor } },
        y1: { type: "linear", position: "right", title: { display: true, text: "Events", color: textColor }, ticks: { color: textColor }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: textColor, maxRotation: 60, minRotation: 60, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

function setupAboutPanel() {
  const about = document.getElementById("about");
  document.getElementById("about-link").addEventListener("click", (e) => {
    e.preventDefault();
    about.hidden = false;
  });
  document.getElementById("about-close").addEventListener("click", () => {
    about.hidden = true;
  });
}

init();
