// ── Dashboard tag chart (doughnut) ──────────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const tagsRaw = container.dataset.tagsChart;
  if (!tagsRaw) return;

  const tagRows = JSON.parse(tagsRaw);
  const routesStatsUrl = container.dataset.routesStatsUrl;
  const chartEl = document.getElementById("chartTags");
  
  if (!chartEl) return;

  new Chart(chartEl, {
    type: "doughnut",
    data: {
      labels: tagRows.map((r) => r.tag),
      datasets: [
        {
          data: tagRows.map((r) => r.count),
          backgroundColor: tagRows.map(
            (_, i) => `hsla(${(i * 137) % 360}, 65%, 55%, 0.75)`,
          ),
          borderColor: tagRows.map(
            (_, i) => `hsla(${(i * 137) % 360}, 65%, 40%, 1)`,
          ),
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (event, elements) => {
        if (!elements.length) return;
        const index = elements[0].index;
        const tag = tagRows[index].tag;
        window.location.href = `${routesStatsUrl}?tag=${encodeURIComponent(tag)}`;
      },
      onHover: (event, elements) => {
        event.native.target.style.cursor = elements.length ? "pointer" : "default";
      },
      plugins: {
        legend: {
          display: true,
          position: "right",
          labels: {
            color: PerfMonitor.labelColor,
            font: { family: PerfMonitor.fontFamily, size: 12 },
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed} requests`,
          },
        },
      },
    },
  });
})();
