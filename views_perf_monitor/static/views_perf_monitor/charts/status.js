// ── Status code chart (doughnut) ──────────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const statusRaw = container.dataset.statusChart;
  if (!statusRaw) return;

  const statusRows = JSON.parse(statusRaw);

  const groupColors = {
    "2xx": { bg: "rgba(34,197,94,0.75)", border: "rgba(21,128,61,1)" },
    "3xx": { bg: "rgba(34,211,238,0.75)", border: "rgba(14,116,144,1)" },
    "4xx": { bg: "rgba(251,191,36,0.75)", border: "rgba(146,64,14,1)" },
    "5xx": { bg: "rgba(239,68,68,0.75)", border: "rgba(185,28,28,1)" },
    other: { bg: "rgba(161,161,170,0.75)", border: "rgba(63,63,70,1)" },
  };

  new Chart(document.getElementById("chartStatusCode"), {
    type: "doughnut",
    data: {
      labels: statusRows.map((r) => String(r.status_code)),
      datasets: [
        {
          data: statusRows.map((r) => r.count),
          backgroundColor: statusRows.map(
            (r) => (groupColors[r.group] ?? groupColors["other"]).bg,
          ),
          borderColor: statusRows.map(
            (r) => (groupColors[r.group] ?? groupColors["other"]).border,
          ),
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
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
