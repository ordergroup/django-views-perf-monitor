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

  // Helper function to create click handler for a specific route array
  const createClickHandler = (routeArray, datasetArray) => ({
    onClick: (event, elements) => {
      if (!elements.length) return;
      const { datasetIndex, index } = elements[0];
      const tag = datasetArray[datasetIndex].tag;
      const route = routeArray[index];

      // Preserve existing query parameters from current page
      const currentParams = new URLSearchParams(window.location.search);
      const params = new URLSearchParams();

      // Add the primary parameters (tag and route)
      params.set("tag", tag);
      params.set("route", route);

      // Preserve date range filters if they exist
      if (currentParams.has("since")) {
        params.set("since", currentParams.get("since"));
      }
      if (currentParams.has("until")) {
        params.set("until", currentParams.get("until"));
      }

      window.location.href = `${tagBreakdownUrl}?${params.toString()}`;
    },
    onHover: (event, elements) => {
      event.native.target.style.cursor = elements.length
        ? "pointer"
        : "default";
    },
  });

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

  // Avg chart (stacked) - sorted by average response time
  const routeAvgs = filteredRoutes.map((_, i) => {
    const sum = filteredDatasets.reduce((s, ds) => s + (ds.avgs[i] ?? 0), 0);
    const count = filteredDatasets.filter((ds) => ds.avgs[i] !== null).length;
    return count > 0 ? sum / count : 0;
  });
  const avgOrder = filteredRoutes
    .map((_, i) => i)
    .sort((a, b) => routeAvgs[b] - routeAvgs[a]);
  const avgRoutes = avgOrder.map((i) => filteredRoutes[i]);
  const avgDatasets = filteredDatasets.map((ds) => ({
    ...ds,
    avgs: avgOrder.map((i) => ds.avgs[i]),
  }));

  const avgChartEl = document.getElementById("chartRouteTag");
  if (avgChartEl) {
    avgChartEl.parentElement.style.height =
      Math.max(300, avgRoutes.length * 30 + 80) + "px";

    new Chart(avgChartEl, {
      type: "bar",
      data: {
        labels: avgRoutes,
        datasets: avgDatasets.map((ds, i) => ({
          label: ds.tag,
          data: ds.avgs,
          backgroundColor: tagColors[i].bg,
          borderColor: tagColors[i].border,
          borderWidth: 1,
        })),
      },
      options: {
        indexAxis: "y",
        ...createClickHandler(avgRoutes, avgDatasets),
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
        scales: {
          ...sharedRouteTagScales,
          x: { ...sharedRouteTagScales.x, stacked: true },
          y: { ...sharedRouteTagScales.y, stacked: true },
        },
      },
    });
  }

  // Heatmap for Avg Response Time
  const heatmapEl = document.getElementById("chartRouteTagHeatmap");
  if (heatmapEl) {
    // Prepare data for heatmap: flat array of {x: tag, y: route, v: value}
    const heatmapData = [];
    const allValues = [];

    avgRoutes.forEach((route, routeIdx) => {
      rtData.tags.forEach((tag, tagIdx) => {
        const dsIdx = filteredDatasets.findIndex((ds) => ds.tag === tag);
        if (dsIdx !== -1) {
          const value = avgDatasets[dsIdx].avgs[routeIdx];
          if (value !== null) {
            heatmapData.push({ x: tag, y: route, v: value });
            allValues.push(value);
          }
        }
      });
    });

    // Calculate min/max for color scaling
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);

    // Color function: green (fast) to red (slow)
    const getColor = (value) => {
      if (value === null) return "rgba(100, 100, 100, 0.1)";
      const normalized = (value - minVal) / (maxVal - minVal || 1);
      // Reverse: 0 = green (fast), 1 = red (slow)
      const hue = (1 - normalized) * 120; // 120 = green, 0 = red
      return `hsla(${hue}, 70%, 50%, 0.8)`;
    };

    heatmapEl.parentElement.style.height =
      Math.max(300, avgRoutes.length * 25 + 100) + "px";

    new Chart(heatmapEl, {
      type: "matrix",
      data: {
        datasets: [
          {
            label: "Avg Response Time (ms)",
            data: heatmapData,
            backgroundColor: (ctx) => {
              if (!ctx.raw) return "rgba(100, 100, 100, 0.1)";
              return getColor(ctx.raw.v);
            },
            borderColor: "rgba(0, 0, 0, 0.2)",
            borderWidth: 1,
            width: ({ chart }) => {
              const area = chart.chartArea;
              if (!area) return 0;
              return (area.right - area.left) / rtData.tags.length - 2;
            },
            height: ({ chart }) => {
              const area = chart.chartArea;
              if (!area) return 0;
              return (area.bottom - area.top) / avgRoutes.length - 2;
            },
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (!elements.length) return;
          const dataPoint = elements[0].element.$context.raw;

          // Preserve existing query parameters from current page
          const currentParams = new URLSearchParams(window.location.search);
          const params = new URLSearchParams();

          params.set("tag", dataPoint.x);
          params.set("route", dataPoint.y);

          if (currentParams.has("since")) {
            params.set("since", currentParams.get("since"));
          }
          if (currentParams.has("until")) {
            params.set("until", currentParams.get("until"));
          }

          window.location.href = `${tagBreakdownUrl}?${params.toString()}`;
        },
        onHover: (event, elements) => {
          event.native.target.style.cursor = elements.length
            ? "pointer"
            : "default";
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: () => "",
              label: (ctx) => {
                const v = ctx.raw.v;
                return [
                  `Route: ${ctx.raw.y}`,
                  `Tag: ${ctx.raw.x}`,
                  `Avg: ${v.toFixed(2)} ms`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            type: "category",
            labels: rtData.tags,
            offset: true,
            grid: { display: false },
            ticks: PerfMonitor.tickStyle(11),
          },
          y: {
            type: "category",
            labels: avgRoutes,
            offset: true,
            grid: { display: false },
            ticks: PerfMonitor.tickStyle(11),
          },
        },
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
        ...createClickHandler(countRoutes, countDatasets),
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

  // Heatmap for Request Count
  const countHeatmapEl = document.getElementById("chartRouteTagCountHeatmap");
  if (countHeatmapEl) {
    // Prepare data for heatmap: flat array of {x: tag, y: route, v: value}
    const heatmapCountData = [];
    const allCountValues = [];

    countRoutes.forEach((route, routeIdx) => {
      rtData.tags.forEach((tag, tagIdx) => {
        const dsIdx = filteredDatasets.findIndex((ds) => ds.tag === tag);
        if (dsIdx !== -1) {
          const value = countDatasets[dsIdx].counts[routeIdx];
          if (value !== null && value !== undefined) {
            heatmapCountData.push({ x: tag, y: route, v: value });
            allCountValues.push(value);
          }
        }
      });
    });

    // Calculate min/max for color scaling
    const minCountVal = Math.min(...allCountValues);
    const maxCountVal = Math.max(...allCountValues);

    // Color function: blue (low) to orange (high) for request counts
    const getCountColor = (value) => {
      if (value === null) return "rgba(100, 100, 100, 0.1)";
      const normalized =
        (value - minCountVal) / (maxCountVal - minCountVal || 1);
      // Blue to orange gradient
      const hue = 200 - normalized * 160; // 200 = blue, 40 = orange
      return `hsla(${hue}, 70%, 50%, 0.8)`;
    };

    countHeatmapEl.parentElement.style.height =
      Math.max(300, countRoutes.length * 25 + 100) + "px";

    new Chart(countHeatmapEl, {
      type: "matrix",
      data: {
        datasets: [
          {
            label: "Request Count",
            data: heatmapCountData,
            backgroundColor: (ctx) => {
              if (!ctx.raw) return "rgba(100, 100, 100, 0.1)";
              return getCountColor(ctx.raw.v);
            },
            borderColor: "rgba(0, 0, 0, 0.2)",
            borderWidth: 1,
            width: ({ chart }) => {
              const area = chart.chartArea;
              if (!area) return 0;
              return (area.right - area.left) / rtData.tags.length - 2;
            },
            height: ({ chart }) => {
              const area = chart.chartArea;
              if (!area) return 0;
              return (area.bottom - area.top) / countRoutes.length - 2;
            },
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (event, elements) => {
          if (!elements.length) return;
          const dataPoint = elements[0].element.$context.raw;

          // Preserve existing query parameters from current page
          const currentParams = new URLSearchParams(window.location.search);
          const params = new URLSearchParams();

          params.set("tag", dataPoint.x);
          params.set("route", dataPoint.y);

          if (currentParams.has("since")) {
            params.set("since", currentParams.get("since"));
          }
          if (currentParams.has("until")) {
            params.set("until", currentParams.get("until"));
          }

          window.location.href = `${tagBreakdownUrl}?${params.toString()}`;
        },
        onHover: (event, elements) => {
          event.native.target.style.cursor = elements.length
            ? "pointer"
            : "default";
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: () => "",
              label: (ctx) => {
                const v = ctx.raw.v;
                return [
                  `Route: ${ctx.raw.y}`,
                  `Tag: ${ctx.raw.x}`,
                  `Count: ${v} requests`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            type: "category",
            labels: rtData.tags,
            offset: true,
            grid: { display: false },
            ticks: PerfMonitor.tickStyle(11),
          },
          y: {
            type: "category",
            labels: countRoutes,
            offset: true,
            grid: { display: false },
            ticks: PerfMonitor.tickStyle(11),
          },
        },
      },
    });
  }
})();



