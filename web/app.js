const form = document.getElementById("scan-form");
const repoPathInput = document.getElementById("repo-path");
const manifestPathInput = document.getElementById("manifest-path");
const showSummaryCheckbox = document.getElementById("show-summary");
const showManifestCheckbox = document.getElementById("show-manifest");
const summaryPanel = document.getElementById("summary-panel");
const manifestPanel = document.getElementById("manifest-panel");
const summaryList = document.getElementById("summary-list");
const manifestOutput = document.getElementById("manifest-output");
const violationsList = document.getElementById("violations-list");
const violationsCount = document.getElementById("violations-count");
const status = document.getElementById("status");
const refreshManifestButton = document.getElementById("refresh-manifest");

let currentManifest = null;

function resolveApiUrl(path) {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return new URL(path, window.location.origin).toString();
  }

  const fallbackOrigins = ["http://127.0.0.1:8000", "http://localhost:8000"];
  for (const origin of fallbackOrigins) {
    const candidate = new URL(path, origin).toString();
    return candidate;
  }

  return new URL(path, "http://127.0.0.1:8000").toString();
}

function setStatus(message, kind = "") {
  status.textContent = message;
  status.className = "status";
  if (kind) {
    status.classList.add(kind);
  }
}

async function requestJson(path, options = {}) {
  const response = await fetch(resolveApiUrl(path), options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail = payload && payload.error ? payload.error : payload || "request failed";
    throw new Error(detail);
  }
  return payload;
}

async function loadManifest() {
  try {
    const payload = await requestJson("/api/manifest");
    currentManifest = payload;
    manifestOutput.textContent = JSON.stringify(payload.manifest || {}, null, 2);
    setStatus("Manifest loaded. Ready to scan.");
  } catch (error) {
    setStatus(`Unable to load manifest: ${error.message}`, "error");
  }
}

function renderSummary(summary) {
  summaryList.innerHTML = "";
  if (!summary || summary.total === 0) {
    summaryList.innerHTML = '<div class="empty-state">No violations were found.</div>';
    return;
  }

  const rows = Object.entries(summary.by_rule || {}).sort(([left], [right]) => left.localeCompare(right));
  for (const [ruleId, count] of rows) {
    const row = document.createElement("div");
    row.className = "summary-chip";
    row.innerHTML = `<span>${ruleId}</span><strong>${count}</strong>`;
    summaryList.appendChild(row);
  }
}

function renderViolations(violations) {
  violationsList.innerHTML = "";
  if (!violations.length) {
    violationsList.innerHTML = '<div class="empty-state">No violations found. Nice work.</div>';
    violationsCount.textContent = "0 findings";
    return;
  }

  violationsCount.textContent = `${violations.length} finding${violations.length === 1 ? "" : "s"}`;
  for (const violation of violations) {
    const card = document.createElement("article");
    card.className = "violation-card";
    const location = violation.line ? `${violation.path}:${violation.line}` : violation.path;
    card.innerHTML = `
      <header>
        <span class="rule-id">${violation.rule_id}</span>
        <span class="path">${location}</span>
      </header>
      <p class="message">${violation.message}</p>
    `;
    violationsList.appendChild(card);
  }
}

function togglePanels() {
  summaryPanel.classList.toggle("hidden", !showSummaryCheckbox.checked);
  manifestPanel.classList.toggle("hidden", !showManifestCheckbox.checked);
}

showSummaryCheckbox.addEventListener("change", togglePanels);
showManifestCheckbox.addEventListener("change", togglePanels);
refreshManifestButton.addEventListener("click", loadManifest);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const repoRoot = repoPathInput.value.trim() || ".";
  const manifestPath = manifestPathInput.value.trim();

  setStatus("Scanning repository…");
  try {
    const payload = await requestJson("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoRoot,
        manifest_path: manifestPath || null,
      }),
    });

    renderViolations(payload.violations || []);
    renderSummary(payload.summary || { total: 0, by_rule: {} });
    if (currentManifest) {
      manifestOutput.textContent = JSON.stringify(currentManifest.manifest || {}, null, 2);
    }
    const fileLabel = payload.violation_count === 1 ? "finding" : "findings";
    const summaryMessage = `Scan complete. ${payload.violation_count} ${fileLabel} across ${payload.repo_root}.`;
    setStatus(summaryMessage, payload.violation_count ? "error" : "success");
    togglePanels();
  } catch (error) {
    renderViolations([]);
    renderSummary({ total: 0, by_rule: {} });
    setStatus(`Scan failed: ${error.message}`, "error");
  }
});

loadManifest();
togglePanels();
