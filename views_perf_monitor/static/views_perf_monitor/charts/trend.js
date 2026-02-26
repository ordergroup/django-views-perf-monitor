// ── Trend chart (requests per hour) ───────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const trendRaw = container.dataset.trendChart;
  if (!trendRaw) return;

  const trendData = JSON.parse(trendRaw);
  const timestamps = Object.keys(trendData);
  const labels = timestamps.map((h) => {
    const d = new Date(h);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  });

  // Get the base admin URL path
  const routeBreakdownUrl = container.dataset.routeBreakdownUrl;
  const adminBasePath = routeBreakdownUrl.substring(0, routeBreakdownUrl.lastIndexOf('/'));
  const routesStatsUrl = `${adminBasePath.substring(0, adminBasePath.lastIndexOf('/'))}/routes-stats/`;

  const formatDateTime = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
  };

  const formatTimeRange = (startDate, endDate) => {
    const startStr = startDate.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    const endStr = endDate.toLocaleString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    return `${startStr} - ${endStr}`;
  };

  const chartInstance = new Chart(document.getElementById("chartTrend"), {
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
          pointHoverRadius: 6,
          pointHoverBackgroundColor: "rgba(99,179,237,1)",
          pointHoverBorderColor: "#fff",
          pointHoverBorderWidth: 2,
          fill: true,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (event, elements, chart) => {
        // Get the nearest index based on x-axis position, regardless of y-position
        const canvasPosition = Chart.helpers.getRelativePosition(event, chart);
        const dataX = chart.scales.x.getValueForPixel(canvasPosition.x);
        
        if (dataX !== undefined && dataX >= 0 && dataX < timestamps.length) {
          const index = Math.round(dataX);
          const hourStart = new Date(timestamps[index]);
          const hourEnd = new Date(hourStart.getTime() + 60 * 60 * 1000);
          
          const params = new URLSearchParams({
            since: formatDateTime(hourStart),
            until: formatDateTime(hourEnd)
          });
          
          window.location.href = `${routesStatsUrl}?${params.toString()}`;
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: {
            title: (context) => {
              const index = context[0].dataIndex;
              const hourStart = new Date(timestamps[index]);
              const hourEnd = new Date(hourStart.getTime() + 60 * 60 * 1000);
              return formatTimeRange(hourStart, hourEnd);
            },
            label: (ctx) => ` ${ctx.parsed.y} requests`,
            footer: () => '👆 Click to view route details',
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
