(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  // ── Theme / style helpers ─────────────────────────────────
  // Detection order:
  // 1. Unfold stores theme in localStorage under "_x_adminTheme" via Alpine $persist
  // 2. Unfold/Tailwind adds .dark class to <html> (may not be set yet if Alpine hasn't run)
  // 3. Classic Django admin 4.2+ uses [data-theme="dark"] on <html>
  // 4. OS preference as final fallback
  function resolveIsDark() {
    const stored =
      localStorage.getItem("adminTheme") ??
      localStorage.getItem("_x_adminTheme");
    if (stored) {
      const val = stored.replace(/^"|"$/g, "");
      if (val === "dark") return true;
      if (val === "light") return false;
      // "auto" — fall through to OS preference
    }
    if (document.documentElement.classList.contains("dark")) return true;
    if (document.documentElement.dataset.theme === "dark") return true;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  const isDark = resolveIsDark();

  const gridColor = isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.07)";
  const labelColor = isDark ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.75)";
  const fontFamily = getComputedStyle(document.body).fontFamily || "sans-serif";

  const tickStyle = (size = 12) => ({
    color: labelColor,
    font: { family: fontFamily, size },
  });

  // ── Shared chart base ─────────────────────────────────────
  const baseOptions = {
    indexAxis: "y",
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { mode: "index" },
    },
    scales: {
      x: { grid: { color: gridColor }, ticks: tickStyle() },
      y: { grid: { display: false }, ticks: tickStyle() },
    },
  };

  // ── Reusable factories ────────────────────────────────────
  function hslPalette(hueBase, lightness = 55) {
    return (_, i) => ({
      bg: `hsla(${hueBase + i * 15}, 70%, ${lightness}%, 0.75)`,
      border: `hsla(${hueBase + i * 15}, 70%, ${lightness - 10}%, 1)`,
    });
  }

  function makeBarDataset(label, rows, valueKey, colorFn) {
    const colors = rows.map(colorFn);
    return {
      label,
      data: rows.map((r) => r[valueKey]),
      backgroundColor: colors.map((c) => c.bg),
      borderColor: colors.map((c) => c.border),
      borderWidth: 1,
      borderRadius: 3,
    };
  }

  function makeTooltipLabel(unit) {
    return unit === "ms"
      ? (ctx) => ` ${ctx.parsed.x.toFixed(2)} ms`
      : (ctx) => ` ${ctx.parsed.x} requests`;
  }

  function makeClickOptions(baseUrl, paramName) {
    return {
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const label = chart.data.labels[elements[0].index];
        window.location.href = `${baseUrl}?${paramName}=${encodeURIComponent(label)}`;
      },
      onHover: (event, elements) => {
        event.native.target.style.cursor = elements.length
          ? "pointer"
          : "default";
      },
    };
  }

  function makeSimpleBarChart(
    elId,
    labelKey,
    sortKey,
    rows,
    datasetLabel,
    hueBase,
    unit,
    clickOptions,
  ) {
    const sorted = [...rows].sort((a, b) => b[sortKey] - a[sortKey]);
    new Chart(document.getElementById(elId), {
      type: "bar",
      data: {
        labels: sorted.map((r) => r[labelKey]),
        datasets: [
          makeBarDataset(datasetLabel, sorted, sortKey, hslPalette(hueBase)),
        ],
      },
      options: {
        ...baseOptions,
        ...clickOptions,
        plugins: {
          ...baseOptions.plugins,
          tooltip: { callbacks: { label: makeTooltipLabel(unit) } },
        },
      },
    });
  }

  // ── URLs ──────────────────────────────────────────────────
  const tagBreakdownUrl = container.dataset.tagBreakdownUrl;
  const routeBreakdownUrl = container.dataset.routeBreakdownUrl;

  // ── Trend chart ───────────────────────────────────────────
  const trendRaw = container.dataset.trendChart;
  if (trendRaw) {
    const trendData = JSON.parse(trendRaw);
    const labels = Object.keys(trendData).map((h) => {
      const d = new Date(h);
      return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
    });
    new Chart(document.getElementById("chartTrend"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Requests",
          data: Object.values(trendData),
          borderColor: "rgba(99,179,237,1)",
          backgroundColor: "rgba(99,179,237,0.15)",
          borderWidth: 2,
          pointRadius: labels.length > 48 ? 0 : 3,
          fill: true,
          tension: 0.3,
        }],
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
            grid: { color: gridColor },
            ticks: {
              ...tickStyle(),
              maxTicksLimit: 12,
              maxRotation: 0,
            },
          },
          y: {
            grid: { color: gridColor },
            ticks: { ...tickStyle(), precision: 0 },
            beginAtZero: true,
          },
        },
      },
    });
  }

  // ── Status code chart ─────────────────────────────────────
  const statusRaw = container.dataset.statusChart;
  if (statusRaw) {
    const statusRows = JSON.parse(statusRaw);

    const groupColors = {
      "2xx": { bg: "rgba(34,197,94,0.75)",  border: "rgba(21,128,61,1)"  },
      "3xx": { bg: "rgba(34,211,238,0.75)", border: "rgba(14,116,144,1)" },
      "4xx": { bg: "rgba(251,191,36,0.75)", border: "rgba(146,64,14,1)"  },
      "5xx": { bg: "rgba(239,68,68,0.75)",  border: "rgba(185,28,28,1)"  },
      "other": { bg: "rgba(161,161,170,0.75)", border: "rgba(63,63,70,1)" },
    };

    new Chart(document.getElementById("chartStatusCode"), {
      type: "doughnut",
      data: {
        labels: statusRows.map((r) => String(r.status_code)),
        datasets: [{
          data: statusRows.map((r) => r.count),
          backgroundColor: statusRows.map((r) => (groupColors[r.group] ?? groupColors["other"]).bg),
          borderColor: statusRows.map((r) => (groupColors[r.group] ?? groupColors["other"]).border),
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "right",
            labels: { color: labelColor, font: { family: fontFamily, size: 12 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed} requests`,
            },
          },
        },
      },
    });
  }

  // ── Tag charts ────────────────────────────────────────────
  const tagsRaw = container.dataset.tagsChart;
  if (tagsRaw) {
    const tagRows = JSON.parse(tagsRaw);
    const tagClickOptions = makeClickOptions(tagBreakdownUrl, "tag");
    makeSimpleBarChart(
      "chartAvgDuration",
      "tag",
      "avg",
      tagRows,
      "Avg (ms)",
      210,
      "ms",
      tagClickOptions,
    );
    makeSimpleBarChart(
      "chartRequestCount",
      "tag",
      "count",
      tagRows,
      "Requests",
      150,
      "requests",
      tagClickOptions,
    );
  }

  // ── Route charts ──────────────────────────────────────────
  const routesRaw = container.dataset.routesChart;
  if (routesRaw) {
    const routeRows = JSON.parse(routesRaw);
    const routeClickOptions = makeClickOptions(routeBreakdownUrl, "route");
    makeSimpleBarChart(
      "chartRouteAvgDuration",
      "route",
      "avg",
      routeRows,
      "Avg (ms)",
      30,
      "ms",
      routeClickOptions,
    );
    makeSimpleBarChart(
      "chartRouteRequestCount",
      "route",
      "count",
      routeRows,
      "Requests",
      270,
      "requests",
      routeClickOptions,
    );
  }

  // ── Route × Tag grouped chart ─────────────────────────────
  const rtRaw = container.dataset.routeTagChart;
  if (rtRaw) {
    const rtData = JSON.parse(rtRaw);

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
        window.location.href = `${tagBreakdownUrl}?tag=${encodeURIComponent(tag)}&route=${encodeURIComponent(route)}`;
      },
      onHover: (event, elements) => {
        event.native.target.style.cursor = elements.length
          ? "pointer"
          : "default";
      },
    };

    const sharedRouteTagScales = {
      x: { grid: { color: gridColor }, ticks: tickStyle() },
      y: { grid: { display: false }, ticks: tickStyle(11) },
    };

    const sharedLegend = {
      display: true,
      position: "top",
      labels: { color: labelColor, font: { family: fontFamily, size: 12 } },
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


