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
const drilldownPanel = document.getElementById("drilldown-panel");
const drilldownContent = document.getElementById("drilldown-content");
const previewPatternButton = document.getElementById("preview-pattern");
const savePatternButton = document.getElementById("save-pattern");
const patternNameInput = document.getElementById("pattern-name");
const patternTextInput = document.getElementById("pattern-text");
const patternKindSelect = document.getElementById("pattern-kind");
const patternTypeSelect = document.getElementById("pattern-type");
const outputManifestInput = document.getElementById("output-manifest");
const patternPreviewList = document.getElementById("pattern-preview-list");
const patternPreviewSummary = document.getElementById("pattern-preview-summary");

let currentManifest = null;
let currentViolations = [];

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

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
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
    if (payload.default_repo_root) {
      repoPathInput.value = payload.default_repo_root;
    }
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
  currentViolations = violations || [];
  violationsList.innerHTML = "";
  if (!currentViolations.length) {
    violationsList.innerHTML = '<div class="empty-state">No violations found. Nice work.</div>';
    violationsCount.textContent = "0 findings";
    drilldownContent.innerHTML = (
      '<div class="empty-state">Select a violation to inspect its surrounding file content.</div>'
    );
    return;
  }

  violationsCount.textContent = `${currentViolations.length} finding${currentViolations.length === 1 ? "" : "s"}`;
  for (const violation of currentViolations) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "violation-card";
    const location = violation.line ? `${violation.path}:${violation.line}` : violation.path;
    card.innerHTML = `
      <header>
        <span class="rule-id">${escapeHtml(violation.rule_id)}</span>
        <span class="path">${escapeHtml(location)}</span>
      </header>
      <p class="message">${escapeHtml(violation.message)}</p>
    `;
    card.addEventListener("click", () => showViolationContext(violation));
    violationsList.appendChild(card);
  }
}

async function showViolationContext(violation) {
  setStatus(`Loading context for ${violation.path}…`);
  try {
    const payload = await requestJson("/api/violation-context", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoPathInput.value.trim() || ".",
        violation,
      }),
    });
    renderViolationContext(payload);
    setStatus(`Context loaded for ${violation.path}.`, "success");
  } catch (error) {
    renderViolationContext({ path: violation.path, line: violation.line || null, lines: [] });
    setStatus(`Unable to load context: ${error.message}`, "error");
  }
}

function renderViolationContext(payload) {
  if (!payload || !payload.lines || !payload.lines.length) {
    drilldownContent.innerHTML = (
      '<div class="empty-state">No surrounding content is available for this violation.</div>'
    );
    return;
  }

  const lines = payload.lines
    .map((line) => {
      const lineNumber = line.line;
      const lineText = escapeHtml(line.text);
      return (
        `<div class="context-line"><span class="line-number">${lineNumber}</span>` +
        `<span class="line-text">${lineText}</span></div>`
      );
    })
    .join("");

  drilldownContent.innerHTML = `
    <div class="drilldown-header">
      <h3>${escapeHtml(payload.path || "Unknown file")}${payload.line ? `:${payload.line}` : ""}</h3>
      <p>${payload.violation && payload.violation.message ? escapeHtml(payload.violation.message) : ""}</p>
    </div>
    <div class="context-block">${lines}</div>
  `;
}

function renderPatternPreview(payload) {
  const previewViolations = payload.violations || [];
  patternPreviewSummary.textContent = (
    `${previewViolations.length} previewed violation${previewViolations.length === 1 ? "" : "s"}`
  );
  if (!previewViolations.length) {
    patternPreviewList.innerHTML = (
      '<div class="empty-state">No preview violations would be emitted by this pattern.</div>'
    );
    return;
  }

  const items = previewViolations.map((violation) => {
    const location = violation.line ? `${violation.path}:${violation.line}` : violation.path;
    return (
      `<div class="summary-chip"><span>${escapeHtml(violation.rule_id)}</span>` +
      `<strong>${escapeHtml(location)}</strong></div>`
    );
  });
  patternPreviewList.innerHTML = items.join("");
}

function togglePanels() {
  summaryPanel.classList.toggle("hidden", !showSummaryCheckbox.checked);
  manifestPanel.classList.toggle("hidden", !showManifestCheckbox.checked);
}

showSummaryCheckbox.addEventListener("change", togglePanels);
showManifestCheckbox.addEventListener("change", togglePanels);
refreshManifestButton.addEventListener("click", loadManifest);

previewPatternButton.addEventListener("click", async () => {
  const repoRoot = repoPathInput.value.trim() || ".";
  const manifestPath = manifestPathInput.value.trim();
  const patternName = patternNameInput.value.trim();
  const patternText = patternTextInput.value.trim();
  const ruleKind = patternKindSelect.value;
  const patternType = patternTypeSelect.value;
  if (!patternName || !patternText) {
    setStatus("Provide a pattern name and pattern text before previewing.", "error");
    return;
  }

  setStatus("Previewing pattern…");
  try {
    const payload = await requestJson("/api/pattern-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoRoot,
        manifest_path: manifestPath || null,
        pattern_name: patternName,
        pattern_text: patternText,
        rule_kind: ruleKind,
        pattern_type: patternType,
      }),
    });
    renderPatternPreview(payload);
    const previewStatus = (
      `Preview ready. ${payload.preview_violation_count} violation${payload.preview_violation_count === 1 ? "" : "s"}` +
      " would be emitted."
    );
    setStatus(previewStatus, "success");
  } catch (error) {
    patternPreviewSummary.textContent = "Preview failed";
    patternPreviewList.innerHTML = '<div class="empty-state">Preview failed.</div>';
    setStatus(`Preview failed: ${error.message}`, "error");
  }
});

savePatternButton.addEventListener("click", async () => {
  const repoRoot = repoPathInput.value.trim() || ".";
  const manifestPath = manifestPathInput.value.trim();
  const patternName = patternNameInput.value.trim();
  const patternText = patternTextInput.value.trim();
  const ruleKind = patternKindSelect.value;
  const patternType = patternTypeSelect.value;
  const outputManifestPath = outputManifestInput.value.trim();
  if (!patternName || !patternText) {
    setStatus("Provide a pattern name and pattern text before saving.", "error");
    return;
  }

  setStatus("Saving pattern…");
  try {
    const payload = await requestJson("/api/pattern-save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoRoot,
        manifest_path: manifestPath || null,
        output_manifest_path: outputManifestPath || null,
        pattern_name: patternName,
        pattern_text: patternText,
        rule_kind: ruleKind,
        pattern_type: patternType,
      }),
    });
    currentManifest = {
      manifest_path: payload.manifest_path,
      manifest: payload.manifest || { rules: [] },
      default_repo_root: repoRoot,
    };
    manifestOutput.textContent = JSON.stringify(payload.manifest || {}, null, 2);
    if (payload.manifest_path) {
      manifestPathInput.value = payload.manifest_path;
      outputManifestInput.value = payload.manifest_path;
    }
    renderPatternPreview(payload);
    setStatus(`Pattern saved to ${payload.manifest_path}.`, "success");
  } catch (error) {
    patternPreviewSummary.textContent = "Save failed";
    patternPreviewList.innerHTML = '<div class="empty-state">Save failed.</div>';
    setStatus(`Save failed: ${error.message}`, "error");
  }
});

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
