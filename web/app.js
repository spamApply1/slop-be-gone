const form = document.getElementById("scan-form");
const repoPathInput = document.getElementById("repo-path");
const manifestPathInput = document.getElementById("manifest-path");
const showSummaryCheckbox = document.getElementById("show-summary");
const showManifestCheckbox = document.getElementById("show-manifest");
const summaryPanel = document.getElementById("summary-panel");
const manifestPanel = document.getElementById("manifest-panel");
const summaryList = document.getElementById("summary-list");
const commandmentsList = document.getElementById("commandments-list");
const commandmentsCount = document.getElementById("commandments-count");
const manifestEditor = document.getElementById("manifest-editor");
const conceptsList = document.getElementById("concepts-list");
const violationsList = document.getElementById("violations-list");
const violationsCount = document.getElementById("violations-count");
const status = document.getElementById("status");
const refreshManifestButton = document.getElementById("refresh-manifest");
const drilldownPanel = document.getElementById("drilldown-panel");
const drilldownContent = document.getElementById("drilldown-content");
const previewPatternButton = document.getElementById("preview-pattern");
const savePatternButton = document.getElementById("save-pattern");
const saveManifestButton = document.getElementById("save-manifest");
const patternNameInput = document.getElementById("pattern-name");
const patternTextInput = document.getElementById("pattern-text");
const patternKindSelect = document.getElementById("pattern-kind");
const patternTypeSelect = document.getElementById("pattern-type");
const ruleDescriptionInput = document.getElementById("rule-description");
const thresholdInput = document.getElementById("threshold-input");
const maxLengthInput = document.getElementById("max-length-input");
const maxBytesInput = document.getElementById("max-bytes-input");
const outputManifestInput = document.getElementById("output-manifest");
const rulePromptInput = document.getElementById("rule-prompt");
const suggestRuleButton = document.getElementById("suggest-rule");
const patternPreviewList = document.getElementById("pattern-preview-list");
const patternPreviewSummary = document.getElementById("pattern-preview-summary");

let currentManifest = null;
let currentViolations = [];
let currentConcepts = [];

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
    currentConcepts = payload.concepts || [];
    renderManifestView(payload);
    if (payload.default_repo_root) {
      repoPathInput.value = payload.default_repo_root;
    }
    if (payload.manifest_path) {
      manifestPathInput.value = payload.manifest_path;
      outputManifestInput.value = payload.manifest_path;
    }
    setStatus("Manifest loaded. Ready to scan.");
  } catch (error) {
    setStatus(`Unable to load manifest: ${error.message}`, "error");
  }
}

function renderManifestView(payload) {
  const manifest = payload && payload.manifest ? payload.manifest : {};
  const rules = Array.isArray(manifest.rules) ? manifest.rules : [];
  currentManifest = payload || {};
  renderCommandments(rules);
  manifestEditor.value = JSON.stringify(manifest || {}, null, 2);
  renderConcepts(currentConcepts);
}

function renderCommandments(rules) {
  commandmentsList.innerHTML = "";
  commandmentsCount.textContent = `${rules.length} rule${rules.length === 1 ? "" : "s"}`;
  if (!rules.length) {
    commandmentsList.innerHTML = '<div class="empty-state">No commandments have been frozen yet.</div>';
    return;
  }

  const cards = rules.map((rule) => {
    const ruleId = escapeHtml(rule.id || rule.type || "rule");
    const description = escapeHtml(rule.description || `Rule type ${rule.type || "custom"}`);
    const status = rule.enabled === false ? "disabled" : "enabled";
    const detail = rule.pattern
      ? `pattern: ${escapeHtml(rule.pattern)}`
      : rule.patterns
        ? `patterns: ${escapeHtml(rule.patterns.join(", "))}`
        : rule.max_length
          ? `max_length: ${escapeHtml(rule.max_length)}`
          : rule.max_bytes
            ? `max_bytes: ${escapeHtml(rule.max_bytes)}`
            : "custom rule";
    return `
      <div class="commandment-card">
        <header>
          <span class="rule-id">${ruleId}</span>
          <span class="meta">${escapeHtml(status)}</span>
        </header>
        <p>${description}</p>
        <div class="meta">${detail}</div>
      </div>
    `;
  });
  commandmentsList.innerHTML = cards.join("");
}

function renderConcepts(concepts) {
  conceptsList.innerHTML = "";
  if (!concepts.length) {
    conceptsList.innerHTML = '<div class="empty-state">No concept library entries are available yet.</div>';
    return;
  }

  for (const concept of concepts) {
    const card = document.createElement("article");
    card.className = "concept-card";
    card.innerHTML = `
      <header>
        <h3>${escapeHtml(concept.title || concept.id || "Concept")}</h3>
        <span class="meta">${escapeHtml(concept.category || concept.rule_kind || "concept")}</span>
      </header>
      <p>${escapeHtml(concept.description || "")}</p>
      <div class="meta">${escapeHtml(concept.rule_kind || "custom")}</div>
      <div class="concept-actions">
        <button type="button" class="secondary concept-load">Load</button>
        <button type="button" class="concept-freeze">Freeze</button>
      </div>
    `;

    const loadButton = card.querySelector(".concept-load");
    loadButton.addEventListener("click", () => {
      setPatternFormFromConcept(concept);
      setStatus(`Loaded concept ${concept.id || concept.title}.`, "success");
    });

    const freezeButton = card.querySelector(".concept-freeze");
    freezeButton.addEventListener("click", () => {
      setPatternFormFromConcept(concept);
      void savePattern(concept);
    });

    conceptsList.appendChild(card);
  }
}

function setPatternFormFromConcept(concept) {
  patternNameInput.value = concept.pattern_name || concept.id || "";
  patternTextInput.value = concept.pattern_text || "";
  patternKindSelect.value = concept.rule_kind || "placeholder-comments";
  patternTypeSelect.value = concept.pattern_type || "plain_text";
  ruleDescriptionInput.value = concept.description || "";
  thresholdInput.value = concept.threshold || "3";
  maxLengthInput.value = concept.max_length || "120";
  maxBytesInput.value = concept.max_bytes || "1048576";
}

function buildPatternPayload(overrides = {}) {
  const repoRoot = repoPathInput.value.trim() || ".";
  const manifestPath = manifestPathInput.value.trim();
  const patternName = patternNameInput.value.trim();
  const patternText = patternTextInput.value.trim();
  const ruleKind = patternKindSelect.value;
  const patternType = patternTypeSelect.value;
  const description = ruleDescriptionInput.value.trim();
  const threshold = thresholdInput.value.trim();
  const maxLength = maxLengthInput.value.trim();
  const maxBytes = maxBytesInput.value.trim();
  const outputManifestPath = outputManifestInput.value.trim();

  return {
    repoRoot,
    manifestPath,
    patternName,
    patternText,
    ruleKind,
    patternType,
    description,
    threshold,
    maxLength,
    maxBytes,
    outputManifestPath,
    ...overrides,
  };
}

function validatePatternPayload(payload) {
  if (!payload.patternName) {
    return "Provide a pattern name before previewing or saving.";
  }
  if (payload.ruleKind === "placeholder-comments" || payload.ruleKind === "marker-spam") {
    if (!payload.patternText) {
      return "Provide pattern text for this rule kind.";
    }
  }
  return null;
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

suggestRuleButton.addEventListener("click", async () => {
  const prompt = rulePromptInput.value.trim();
  if (!prompt) {
    setStatus("Describe the slop pattern you want to freeze before suggesting a rule.", "error");
    return;
  }

  setStatus("Suggesting rule…");
  try {
    const payload = await requestJson("/api/rule-suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const rule = payload.rule || {};
    patternNameInput.value = rule.id || "";
    patternTextInput.value = rule.pattern || "";
    patternKindSelect.value = rule.type || "placeholder-comments";
    patternTypeSelect.value = rule.match_mode || "plain_text";
    ruleDescriptionInput.value = rule.description || "";
    thresholdInput.value = rule.threshold || "3";
    maxLengthInput.value = rule.max_length || "120";
    maxBytesInput.value = rule.max_bytes || "1048576";
    setStatus("Rule suggestion ready. Review and save it.", "success");
  } catch (error) {
    setStatus(`Unable to suggest a rule: ${error.message}`, "error");
  }
});

saveManifestButton.addEventListener("click", async () => {
  const repoRoot = repoPathInput.value.trim() || ".";
  const manifestPath = manifestPathInput.value.trim() || (currentManifest && currentManifest.manifest_path) || null;
  let manifestPayload = null;
  try {
    manifestPayload = JSON.parse(manifestEditor.value);
  } catch (error) {
    setStatus(`Manifest JSON is invalid: ${error.message}`, "error");
    return;
  }

  setStatus("Saving manifest…");
  try {
    const response = await requestJson("/api/manifest-save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoRoot,
        manifest_path: manifestPath || null,
        manifest: manifestPayload,
      }),
    });
    currentManifest = {
      manifest_path: response.manifest_path,
      manifest: response.manifest || { rules: [] },
      default_repo_root: repoRoot,
    };
    renderManifestView(currentManifest);
    if (response.manifest_path) {
      manifestPathInput.value = response.manifest_path;
      outputManifestInput.value = response.manifest_path;
    }
    setStatus(`Manifest saved to ${response.manifest_path}.`, "success");
  } catch (error) {
    setStatus(`Unable to save manifest: ${error.message}`, "error");
  }
});

async function previewPattern() {
  const payload = buildPatternPayload();
  const validationError = validatePatternPayload(payload);
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }

  setStatus("Previewing pattern…");
  try {
    const previewPayload = await requestJson("/api/pattern-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: payload.repoRoot,
        manifest_path: payload.manifestPath || null,
        pattern_name: payload.patternName,
        pattern_text: payload.patternText,
        rule_kind: payload.ruleKind,
        pattern_type: payload.patternType,
        threshold: payload.threshold || null,
        max_length: payload.maxLength || null,
        max_bytes: payload.maxBytes || null,
        description: payload.description || null,
      }),
    });
    renderPatternPreview(previewPayload);
    const previewStatus = (
      `Preview ready. ${previewPayload.preview_violation_count} violation` +
      `${previewPayload.preview_violation_count === 1 ? "" : "s"} would be emitted.`
    );
    setStatus(previewStatus, "success");
  } catch (error) {
    patternPreviewSummary.textContent = "Preview failed";
    patternPreviewList.innerHTML = '<div class="empty-state">Preview failed.</div>';
    setStatus(`Preview failed: ${error.message}`, "error");
  }
}

async function savePattern(concept = null) {
  const payload = buildPatternPayload(concept || {});
  const validationError = validatePatternPayload(payload);
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }

  setStatus("Saving pattern…");
  try {
    const response = await requestJson("/api/pattern-save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: payload.repoRoot,
        manifest_path: payload.manifestPath || null,
        output_manifest_path: payload.outputManifestPath || null,
        pattern_name: payload.patternName,
        pattern_text: payload.patternText,
        rule_kind: payload.ruleKind,
        pattern_type: payload.patternType,
        threshold: payload.threshold || null,
        max_length: payload.maxLength || null,
        max_bytes: payload.maxBytes || null,
        description: payload.description || null,
      }),
    });
    currentManifest = {
      manifest_path: response.manifest_path,
      manifest: response.manifest || { rules: [] },
      default_repo_root: payload.repoRoot,
    };
    renderManifestView(currentManifest);
    if (response.manifest_path) {
      manifestPathInput.value = response.manifest_path;
      outputManifestInput.value = response.manifest_path;
    }
    renderPatternPreview(response);
    setStatus(`Pattern saved to ${response.manifest_path}.`, "success");
  } catch (error) {
    patternPreviewSummary.textContent = "Save failed";
    patternPreviewList.innerHTML = '<div class="empty-state">Save failed.</div>';
    setStatus(`Save failed: ${error.message}`, "error");
  }
}

previewPatternButton.addEventListener("click", () => {
  void previewPattern();
});

savePatternButton.addEventListener("click", () => {
  void savePattern();
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
      renderManifestView(currentManifest);
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
