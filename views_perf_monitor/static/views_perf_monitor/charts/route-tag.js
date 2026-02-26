// ── Route × Tag grouped chart ─────────────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const rtRaw = container.dataset.routeTagChart;
  if (!rtRaw) return;

  const rtData = JSON.parse(rtRaw);
  const tagBreakdownUrl = container.dataset.tagBreakdownUrl;

  // Drop routes that have no data across all tags
  const routeIndices = rtData.routes
    .map((_, i) => i)
    .filter((i) => rtData.datasets.some((ds) => ds.avgs[i] !== null));
  const filteredRoutes = routeIndices.map((i) => rtData.routes[i]);
  const filteredDatasets = rtData.datasets.map((ds) => ({
    ...ds,
    avgs: routeIndices.map((i) => ds.avgs[i]),
    counts: routeIndices.map((i) => ds.counts[i]),
  }));

  const tagColors = rtData.tags.map((_, i) => ({
    bg: `hsla(${(i * 47) % 360}, 65%, 55%, 0.75)`,
    border: `hsla(${(i * 47) % 360}, 65%, 40%, 1)`,
  }));

  const routeTagClickHandler = {
    onClick: (event, elements) => {
      if (!elements.length) return;
      const { datasetIndex, index } = elements[0];
      const tag = filteredDatasets[datasetIndex].tag;
      const route = filteredRoutes[index];
      
      // Preserve existing query parameters from current page
      const currentParams = new URLSearchParams(window.location.search);
      const params = new URLSearchParams();
      
      // Add the primary parameters (tag and route)
      params.set('tag', tag);
      params.set('route', route);
      
      // Preserve date range filters if they exist
      if (currentParams.has('since')) {
        params.set('since', currentParams.get('since'));
      }
      if (currentParams.has('until')) {
        params.set('until', currentParams.get('until'));
      }
      
      window.location.href = `${tagBreakdownUrl}?${params.toString()}`;
    },
    onHover: (event, elements) => {
      event.native.target.style.cursor = elements.length
        ? "pointer"
        : "default";
    },
  };

  const sharedRouteTagScales = {
    x: {
      grid: { color: PerfMonitor.gridColor },
      ticks: PerfMonitor.tickStyle(),
    },
    y: { grid: { display: false }, ticks: PerfMonitor.tickStyle(11) },
  };

  const sharedLegend = {
    display: true,
    position: "top",
    labels: {
      color: PerfMonitor.labelColor,
      font: { family: PerfMonitor.fontFamily, size: 12 },
    },
  };

  const sharedRouteTagDatasets = (dataKey) =>
    filteredDatasets.map((ds, i) => ({
      label: ds.tag,
      data: ds[dataKey],
      backgroundColor: tagColors[i].bg,
      borderColor: tagColors[i].border,
      borderWidth: 1,
      borderRadius: 2,
    }));

  // Avg chart (grouped)
  const avgChartEl = document.getElementById("chartRouteTag");
  if (avgChartEl) {
    avgChartEl.parentElement.style.height =
      Math.max(300, filteredRoutes.length * filteredDatasets.length * 20 + 80) +
      "px";

    new Chart(avgChartEl, {
      type: "bar",
      data: {
        labels: filteredRoutes,
        datasets: sharedRouteTagDatasets("avgs"),
      },
      options: {
        indexAxis: "y",
        ...routeTagClickHandler,
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: sharedLegend,
          tooltip: {
            callbacks: {
              label: (ctx) =>
                ` ${ctx.dataset.label}: ${ctx.parsed.x != null ? ctx.parsed.x.toFixed(2) + " ms" : "—"}`,
            },
          },
        },
        scales: sharedRouteTagScales,
      },
    });
  }

  // Count chart (stacked, sorted by total desc)
  const routeTotals = filteredRoutes.map((_, i) =>
    filteredDatasets.reduce((sum, ds) => sum + (ds.counts[i] ?? 0), 0),
  );
  const countOrder = filteredRoutes
    .map((_, i) => i)
    .sort((a, b) => routeTotals[b] - routeTotals[a]);
  const countRoutes = countOrder.map((i) => filteredRoutes[i]);
  const countDatasets = filteredDatasets.map((ds) => ({
    ...ds,
    counts: countOrder.map((i) => ds.counts[i]),
  }));

  const countChartEl = document.getElementById("chartRouteTagCount");
  if (countChartEl) {
    countChartEl.parentElement.style.height =
      Math.max(300, countRoutes.length * 40 + 80) + "px";

    new Chart(countChartEl, {
      type: "bar",
      data: {
        labels: countRoutes,
        datasets: countDatasets.map((ds, i) => ({
          label: ds.tag,
          data: ds.counts,
          backgroundColor: tagColors[i].bg,
          borderColor: tagColors[i].border,
          borderWidth: 1,
        })),
      },
      options: {
        indexAxis: "y",
        ...routeTagClickHandler,
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: sharedLegend,
          tooltip: {
            callbacks: {
              label: (ctx) =>
                ` ${ctx.dataset.label}: ${ctx.parsed.x != null ? ctx.parsed.x + " requests" : "—"}`,
            },
          },
        },
        scales: {
          ...sharedRouteTagScales,
          x: { ...sharedRouteTagScales.x, stacked: true },
          y: { ...sharedRouteTagScales.y, stacked: true },
        },
      },
    });
  }
})();
