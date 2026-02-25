// ── Dashboard initialization ──────────────────────────────
// This file loads after common.js, controls.js, and chart modules
// All chart-specific logic is in separate files under charts/

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) {
    console.warn("Performance monitor dashboard container not found");
  }
})();
