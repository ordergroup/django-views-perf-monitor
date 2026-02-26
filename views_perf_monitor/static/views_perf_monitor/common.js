// ── Theme / style helpers ─────────────────────────────────
// Detection order:
// 1. Unfold stores theme in localStorage under "_x_adminTheme" via Alpine $persist
// 2. Unfold/Tailwind adds .dark class to <html> (may not be set yet if Alpine hasn't run)
// 3. Classic Django admin 4.2+ uses [data-theme="dark"] on <html>
// 4. OS preference as final fallback
function resolveIsDark() {
  const stored =
    localStorage.getItem("adminTheme") ?? localStorage.getItem("_x_adminTheme");
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

const PerfMonitor = {
  isDark: resolveIsDark(),

  get gridColor() {
    return this.isDark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.07)";
  },

  get labelColor() {
    return this.isDark ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.75)";
  },

  get fontFamily() {
    return getComputedStyle(document.body).fontFamily || "sans-serif";
  },

  tickStyle(size = 12) {
    return {
      color: this.labelColor,
      font: { family: this.fontFamily, size },
    };
  },

  // ── Shared chart base ─────────────────────────────────────
  get baseOptions() {
    return {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { mode: "index" },
      },
      scales: {
        x: { grid: { color: this.gridColor }, ticks: this.tickStyle() },
        y: { grid: { display: false }, ticks: this.tickStyle() },
      },
    };
  },

  // ── Reusable factories ────────────────────────────────────
  hslPalette(hueBase, lightness = 55) {
    return (_, i) => ({
      bg: `hsla(${hueBase + i * 15}, 70%, ${lightness}%, 0.75)`,
      border: `hsla(${hueBase + i * 15}, 70%, ${lightness - 10}%, 1)`,
    });
  },

  makeBarDataset(label, rows, valueKey, colorFn) {
    const colors = rows.map(colorFn);
    return {
      label,
      data: rows.map((r) => r[valueKey]),
      backgroundColor: colors.map((c) => c.bg),
      borderColor: colors.map((c) => c.border),
      borderWidth: 1,
      borderRadius: 3,
    };
  },

  makeTooltipLabel(unit) {
    return unit === "ms"
      ? (ctx) => ` ${ctx.parsed.x.toFixed(2)} ms`
      : (ctx) => ` ${ctx.parsed.x} requests`;
  },

  makeClickOptions(baseUrl, paramName) {
    return {
      onClick: (event, elements, chart) => {
        if (!elements.length) return;
        const label = chart.data.labels[elements[0].index];
        
        // Preserve existing query parameters from current page
        const currentParams = new URLSearchParams(window.location.search);
        const params = new URLSearchParams();
        
        // Add the primary parameter (tag or route)
        params.set(paramName, label);
        
        // Preserve date range filters if they exist
        if (currentParams.has('since')) {
          params.set('since', currentParams.get('since'));
        }
        if (currentParams.has('until')) {
          params.set('until', currentParams.get('until'));
        }
        
        window.location.href = `${baseUrl}?${params.toString()}`;
      },
      onHover: (event, elements) => {
        event.native.target.style.cursor = elements.length
          ? "pointer"
          : "default";
      },
    };
  },

  makeSimpleBarChart(
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
          this.makeBarDataset(
            datasetLabel,
            sorted,
            sortKey,
            this.hslPalette(hueBase),
          ),
        ],
      },
      options: {
        ...this.baseOptions,
        ...clickOptions,
        plugins: {
          ...this.baseOptions.plugins,
          tooltip: { callbacks: { label: this.makeTooltipLabel(unit) } },
        },
      },
    });
  },

  getCSRFToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  },
};
