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

let map;
let chart;
let markers = {};
let dataset;

async function init() {
  const resp = await fetch("data/dataset.json");
  dataset = await resp.json();

  document.getElementById("snapshot-note").textContent =
    `Snapshot generated ${new Date(dataset.generated_at).toLocaleString()} — not a live feed.`;

  map = L.map("map", { scrollWheelZoom: false }).setView([25, 40], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 8,
    minZoom: 2,
  }).addTo(map);

  const listEl = document.getElementById("country-list-items");

  dataset.countries.forEach((country) => {
    if (country.coords) {
      const marker = L.circleMarker(country.coords, {
        radius: 10,
        color: "#fff",
        weight: 1,
        fillColor: LEVEL_COLOR[country.alert_level] || LEVEL_COLOR.unknown,
        fillOpacity: 0.9,
      }).addTo(map);
      marker.bindTooltip(country.name);
      marker.on("click", () => selectCountry(country.name));
      markers[country.name] = marker;
    }

    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "country-item";
    btn.dataset.country = country.name;
    btn.innerHTML = `<span class="dot ${country.alert_level}"></span> ${country.name}
      <span style="margin-left:auto;color:var(--muted);font-size:0.8rem;">${LEVEL_LABEL[country.alert_level] || "Unknown"}</span>`;
    btn.addEventListener("click", () => selectCountry(country.name));
    li.appendChild(btn);
    listEl.appendChild(li);
  });

  setupAboutPanel();
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

  renderDetail(country);
}

function renderDetail(country) {
  const panel = document.getElementById("detail-panel");
  const level = country.alert_level || "unknown";

  panel.innerHTML = `
    <div class="detail-header">
      <h3>${country.name}</h3>
      <span class="badge ${level}">${LEVEL_LABEL[level] || "Unknown"}</span>
    </div>
    <div class="detail-grid">
      <div>
        <div class="chart-box"><canvas id="tension-chart"></canvas></div>
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

  renderChart(country);
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

function renderChart(country) {
  const ctx = document.getElementById("tension-chart");
  if (!ctx) return;
  if (chart) chart.destroy();

  const series = country.tension_series || [];
  const labels = series.map((p) =>
    new Date(p.timestamp_utc).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" })
  );

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Article volume",
          data: series.map((p) => p.volume_article_count),
          borderColor: "#2563eb",
          backgroundColor: "transparent",
          yAxisID: "y",
          tension: 0.2,
        },
        {
          label: "Avg. tone",
          data: series.map((p) => p.avg_tone),
          borderColor: "#dc2626",
          backgroundColor: "transparent",
          yAxisID: "y1",
          tension: 0.2,
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
