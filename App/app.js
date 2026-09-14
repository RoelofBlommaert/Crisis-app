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

let map;
let tensionChart;
let themeChart;
let markers = {};
let dataset;

function riskScore(country) {
  return Math.max(country.conflict_signal || 0, country.disaster_signal || 0);
}

function gaugeColor(value) {
  if (value >= 60) return LEVEL_COLOR.Red;
  if (value >= 30) return LEVEL_COLOR.Orange;
  return LEVEL_COLOR.Green;
}

async function init() {
  const resp = await fetch("data/dataset.json");
  dataset = await resp.json();

  document.getElementById("snapshot-note").textContent =
    `Snapshot generated ${new Date(dataset.generated_at).toLocaleString()} — not a live feed. Conflict/disaster signals are an illustrative heuristic, not a forecast probability.`;

  renderStatStrip();

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
        weight: 1,
        fillColor: LEVEL_COLOR[country.alert_level] || LEVEL_COLOR.unknown,
        fillOpacity: 0.85,
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
      <span class="mini-bars" title="Conflict signal ${country.conflict_signal} · Disaster signal ${country.disaster_signal}">
        <span class="mini-bar conflict" style="width:${country.conflict_signal}%"></span>
        <span class="mini-bar disaster" style="width:${country.disaster_signal}%"></span>
      </span>
    `;
    btn.addEventListener("click", () => selectCountry(country.name));
    li.appendChild(btn);
    listEl.appendChild(li);
  });

  setupAboutPanel();
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
      ${renderGauge("Conflict signal", country.conflict_signal)}
      ${renderGauge("Disaster signal", country.disaster_signal)}
    </div>
    <p class="gauge-disclaimer">
      Illustrative 0&ndash;100 heuristic combining recent media tone, conflict/disaster theme
      tagging, and confirmed GDACS events &mdash; <strong>not</strong> a statistical forecast or
      probability of war/disaster. See About panel for the method.
    </p>

    <div class="detail-grid">
      <div>
        <h4>Media signal, last 7 days</h4>
        <div class="chart-box"><canvas id="tension-chart"></canvas></div>
        <h4>Conflict vs. disaster theme share</h4>
        <div class="chart-box chart-box-small"><canvas id="theme-chart"></canvas></div>
      </div>
      <div>
        <div class="events-list">
          <strong>Confirmed events (GDACS)</strong>
          ${renderEvents(country.events)}
        </div>
        <div class="travel-box">
          <strong>Dutch outbound travel baseline (CBS)</strong>
          ${renderTravel(country.travel_baseline)}
        </div>
      </div>
    </div>
  `;

  renderTensionChart(country);
  renderThemeChart(country);
}

function renderGauge(label, value) {
  const color = gaugeColor(value);
  return `
    <div class="gauge">
      <div class="gauge-label"><span>${label}</span><span class="gauge-value" style="color:${color}">${value}</span></div>
      <div class="gauge-track"><div class="gauge-fill" style="width:${value}%;background:${color}"></div></div>
    </div>
  `;
}

function renderEvents(events) {
  if (!events || events.length === 0) {
    return '<p class="no-events">No confirmed GDACS disaster events for this country. Note: GDACS covers natural disasters only, not conflict/political crises — see the About panel.</p>';
  }
  const items = events
    .map(
      (e) => `<li><span class="badge ${e.alertlevel}" style="font-size:0.7rem;">${e.alertlevel}</span>
        ${e.eventname || e.eventtype} &mdash; ${e.description}
        <br><span style="color:var(--muted);font-size:0.8rem;">${e.fromdate.slice(0, 10)} to ${e.todate.slice(0, 10)}</span></li>`
    )
    .join("");
  return `<ul>${items}</ul>`;
}

function renderTravel(baseline) {
  if (!baseline || !baseline.series || baseline.series.length === 0) {
    return "<p class=\"no-events\">No travel baseline data available.</p>";
  }
  const granClass = `granularity-${baseline.granularity}`;
  const rows = baseline.series
    .map(
      (r) =>
        `<tr><td>${r.year}</td><td>${r.total_trips_x1000 || "–"}</td><td>${r.total_spend_eur_million || "–"}</td></tr>`
    )
    .join("");
  return `
    <span class="badge ${granClass}">${baseline.granularity === "country" ? "Country-level" : "Region-level: " + baseline.area_label}</span>
    <table>
      <thead><tr><th>Year</th><th>Trips (x1000)</th><th>Spend (€m)</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderTensionChart(country) {
  const ctx = document.getElementById("tension-chart");
  if (!ctx) return;
  if (tensionChart) tensionChart.destroy();

  const series = country.tension_series || [];
  const labels = series.map((p) =>
    new Date(p.timestamp_utc).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })
  );

  tensionChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Article volume",
          data: series.map((p) => p.volume_article_count),
          borderColor: "#2563eb",
          backgroundColor: "rgba(37,99,235,0.08)",
          fill: true,
          yAxisID: "y",
          tension: 0.25,
          pointRadius: 0,
        },
        {
          label: "Avg. tone",
          data: series.map((p) => p.avg_tone),
          borderColor: "#dc2626",
          backgroundColor: "transparent",
          yAxisID: "y1",
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { type: "linear", position: "left", title: { display: true, text: "Articles" } },
        y1: { type: "linear", position: "right", title: { display: true, text: "Tone" }, grid: { drawOnChartArea: false } },
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
          tension: 0.25,
          pointRadius: 0,
        },
        {
          label: "Disaster-theme share (%)",
          data: disasterPct,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245,158,11,0.15)",
          fill: true,
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: "% of articles" } },
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
