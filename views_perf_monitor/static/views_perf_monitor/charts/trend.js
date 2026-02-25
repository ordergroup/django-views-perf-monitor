// ── Trend chart (requests per hour) ───────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const trendRaw = container.dataset.trendChart;
  if (!trendRaw) return;

  const trendData = JSON.parse(trendRaw);
  const labels = Object.keys(trendData).map((h) => {
    const d = new Date(h);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  });

  new Chart(document.getElementById("chartTrend"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Requests",
          data: Object.values(trendData),
          borderColor: "rgba(99,179,237,1)",
          backgroundColor: "rgba(99,179,237,0.15)",
          borderWidth: 2,
          pointRadius: labels.length > 48 ? 0 : 3,
          fill: true,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.y} requests`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: PerfMonitor.gridColor },
          ticks: {
            ...PerfMonitor.tickStyle(),
            maxTicksLimit: 12,
            maxRotation: 0,
          },
        },
        y: {
          grid: { color: PerfMonitor.gridColor },
          ticks: { ...PerfMonitor.tickStyle(), precision: 0 },
          beginAtZero: true,
        },
      },
    },
  });
})();
