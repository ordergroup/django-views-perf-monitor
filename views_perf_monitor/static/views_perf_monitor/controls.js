// ── Recording toggle and data controls ────────────────────

(function () {
  const container = document.getElementById("perf-dashboard-data");
  if (!container) return;

  const toggleRecordingUrl = container.dataset.toggleRecordingUrl;
  const clearDataUrl = container.dataset.clearDataUrl;

  // ── Recording toggle ──────────────────────────────────────
  const recordingToggle = document.getElementById("recordingToggle");
  const recordingStatus = document.getElementById("recordingStatus");

  if (recordingToggle && toggleRecordingUrl) {
    recordingToggle.addEventListener("change", async function () {
      const action = this.checked ? "enable" : "disable";
      try {
        const formData = new FormData();
        formData.append("action", action);

        const response = await fetch(toggleRecordingUrl, {
          method: "POST",
          headers: PerfMonitor.getCSRFToken()
            ? { "X-CSRFToken": PerfMonitor.getCSRFToken() }
            : {},
          body: formData,
        });

        if (!response.ok) throw new Error("Failed to toggle recording");

        const data = await response.json();
        const enabled = data.recording_enabled;

        // Update UI
        recordingToggle.checked = enabled;
        recordingStatus.innerHTML = `Recording is currently <strong>${enabled ? "enabled" : "disabled"}</strong>.`;
      } catch (error) {
        console.error("Error toggling recording:", error);
        // Revert toggle on error
        recordingToggle.checked = !recordingToggle.checked;
        alert("Failed to toggle recording. Please try again.");
      }
    });
  }

  // ── Clear data button ─────────────────────────────────────
  const clearDataBtn = document.getElementById("clearDataBtn");

  if (clearDataBtn && clearDataUrl) {
    clearDataBtn.addEventListener("click", async function () {
      const confirmed = confirm(
        "Are you sure you want to clear all performance data?\n\n" +
          "This action cannot be undone and will permanently delete:\n" +
          "• All performance records\n" +
          "• All tags and routes data\n" +
          "• All aggregated statistics\n" +
          "• All cached data",
      );

      if (!confirmed) return;

      try {
        const formData = new FormData();

        const response = await fetch(clearDataUrl, {
          method: "POST",
          headers: PerfMonitor.getCSRFToken()
            ? { "X-CSRFToken": PerfMonitor.getCSRFToken() }
            : {},
          body: formData,
        });

        if (!response.ok) throw new Error("Failed to clear data");

        const data = await response.json();

        if (data.success) {
          alert("All performance data has been cleared successfully.");
          window.location.reload();
        } else {
          throw new Error(data.error || "Unknown error");
        }
      } catch (error) {
        console.error("Error clearing data:", error);
        alert("Failed to clear data: " + error.message);
      }
    });
  }
})();
