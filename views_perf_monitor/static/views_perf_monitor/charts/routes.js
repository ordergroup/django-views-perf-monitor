// ── Route charts (avg duration & request count) ───────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const routesRaw = container.dataset.routesChart;
  if (!routesRaw) return;

  const routeRows = JSON.parse(routesRaw);
  const routeBreakdownUrl = container.dataset.routeBreakdownUrl;
  const routeClickOptions = PerfMonitor.makeClickOptions(
    routeBreakdownUrl,
    "route",
  );

  PerfMonitor.makeSimpleBarChart(
    "chartRouteAvgDuration",
    "route",
    "avg",
    routeRows,
    "Avg (ms)",
    30,
    "ms",
    routeClickOptions,
  );

  PerfMonitor.makeSimpleBarChart(
    "chartRouteRequestCount",
    "route",
    "count",
    routeRows,
    "Requests",
    270,
    "requests",
    routeClickOptions,
  );
})();
