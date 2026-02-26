// ── Dashboard initialization ──────────────────────────────
// This file loads after common.js, controls.js, and chart modules
// All chart-specific logic is in separate files under charts/

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) {
    console.warn("Performance monitor dashboard container not found");
    return;
  }

  // Add click handlers for tag table rows
  const routesStatsUrl = container.dataset.routesStatsUrl;
  const tagRows = document.querySelectorAll("tr.perf-table-clickable[data-tag]");
  
  tagRows.forEach((row) => {
    row.style.cursor = "pointer";
    row.addEventListener("click", () => {
      const tag = row.dataset.tag;
      window.location.href = `${routesStatsUrl}?tag=${encodeURIComponent(tag)}`;
    });
  });
})();
