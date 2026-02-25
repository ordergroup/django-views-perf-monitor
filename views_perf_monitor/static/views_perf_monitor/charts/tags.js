// ── Tag charts (avg duration & request count) ─────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const tagsRaw = container.dataset.tagsChart;
  if (!tagsRaw) return;

  const tagRows = JSON.parse(tagsRaw);
  const tagBreakdownUrl = container.dataset.tagBreakdownUrl;
  const tagClickOptions = PerfMonitor.makeClickOptions(tagBreakdownUrl, "tag");

  PerfMonitor.makeSimpleBarChart(
    "chartAvgDuration",
    "tag",
    "avg",
    tagRows,
    "Avg (ms)",
    210,
    "ms",
    tagClickOptions,
  );

  PerfMonitor.makeSimpleBarChart(
    "chartRequestCount",
    "tag",
    "count",
    tagRows,
    "Requests",
    150,
    "requests",
    tagClickOptions,
  );
})();
