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
const commandmentDetail = document.getElementById("commandment-detail");
const manifestEditor = document.getElementById("manifest-editor");
const assetMapList = document.getElementById("asset-map-list");
const assetMapCount = document.getElementById("asset-map-count");
const assetMapSummary = document.getElementById("asset-map-summary");
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
const modalBackdrop = document.getElementById("detail-modal-backdrop");
const modalTitle = document.getElementById("detail-modal-title");
const modalBody = document.getElementById("detail-modal-body");
const modalCloseButton = document.getElementById("detail-modal-close");

let currentManifest = null;
let currentViolations = [];
let currentConcepts = [];
let currentAssetMap = null;
let selectedCommandment = null;

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

function openModal(title, contentHtml) {
  if (!modalTitle || !modalBody || !modalBackdrop) {
    return;
  }
  modalTitle.textContent = title;
  modalBody.innerHTML = contentHtml;
  modalBackdrop.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal() {
  if (!modalBackdrop || !modalBody || !modalTitle) {
    return;
  }
  modalBackdrop.classList.add("hidden");
  modalBody.innerHTML = "";
  modalTitle.textContent = "";
  document.body.classList.remove("modal-open");
}

function bindModalEvents() {
  if (!modalCloseButton || modalCloseButton.dataset.sbgModalBound === "true") {
    return;
  }
  modalCloseButton.dataset.sbgModalBound = "true";
  modalCloseButton.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", (event) => {
    if (event.target === modalBackdrop) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modalBackdrop.classList.contains("hidden")) {
      closeModal();
    }
  });
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

function renderExplorerValue(value, depth = 0) {
  if (value === null) {
    return '<span class="explorer-scalar explorer-null">null</span>';
  }
  if (typeof value === "string") {
    return `<span class="explorer-scalar explorer-string">&quot;${escapeHtml(value)}&quot;</span>`;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return `<span class="explorer-scalar explorer-primitive">${escapeHtml(String(value))}</span>`;
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return '<div class="explorer-empty">Empty array</div>';
    }
    const children = value
      .map((item, index) => {
        const label = `[${index}]`;
        return `
          <div class="explorer-entry">
            <span class="explorer-key">${escapeHtml(label)}</span>
            <div class="explorer-entry-value">${renderExplorerValue(item, depth + 1)}</div>
          </div>
        `;
      })
      .join("");
    return `
      <details class="explorer-node explorer-array" ${depth < 2 ? "open" : ""}>
        <summary>
          <span class="explorer-label">Array</span>
          <span class="explorer-meta">${value.length} item${value.length === 1 ? "" : "s"}</span>
        </summary>
        <div class="explorer-children">${children}</div>
      </details>
    `;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) {
      return '<div class="explorer-empty">Empty object</div>';
    }
    const children = entries
      .map(([key, child]) => `
        <div class="explorer-entry">
          <span class="explorer-key">${escapeHtml(key)}</span>
          <div class="explorer-entry-value">${renderExplorerValue(child, depth + 1)}</div>
        </div>
      `)
      .join("");
    return `
      <details class="explorer-node explorer-object" ${depth < 2 ? "open" : ""}>
        <summary>
          <span class="explorer-label">Object</span>
          <span class="explorer-meta">${entries.length} field${entries.length === 1 ? "" : "s"}</span>
        </summary>
        <div class="explorer-children">${children}</div>
      </details>
    `;
  }
  return `<span class="explorer-scalar">${escapeHtml(String(value))}</span>`;
}

function buildBridgeContextForPath(path) {
  if (!path || !currentAssetMap || !Array.isArray(currentAssetMap.nodes)) {
    return null;
  }
  const normalizedPath = String(path).replace(/\\/g, "/").replace(/^\.\//, "");
  const node = currentAssetMap.nodes.find((candidate) => candidate.id === `file:${normalizedPath}`);
  if (!node) {
    return null;
  }
  const relatedEdges = (currentAssetMap.edges || []).filter(
    (edge) => edge.from === node.id || edge.to === node.id,
  );
  return { node, related_edges: relatedEdges };
}

function renderBridgeContext(bridgeContext) {
  if (!bridgeContext || !bridgeContext.node) {
    return "";
  }
  const node = bridgeContext.node;
  const relatedEdges = Array.isArray(bridgeContext.related_edges) ? bridgeContext.related_edges : [];
  const linkMarkup = relatedEdges.length
    ? relatedEdges
        .map((edge) => {
          const targetNode = (currentAssetMap && Array.isArray(currentAssetMap.nodes)
            ? currentAssetMap.nodes.find((candidate) => candidate.id === edge.to || candidate.id === edge.from)
            : null) || null;
          const label = targetNode && targetNode.id !== node.id ? targetNode.label : edge.kind;
          return `<div class="bridge-link">${escapeHtml(edge.kind)} → ${escapeHtml(label)}</div>`;
        })
        .join("")
    : '<div class="bridge-link">No related edges</div>';
  return `
    <div class="bridge-context">
      <h4>Bridge context</h4>
      <div class="bridge-node">
        <strong>${escapeHtml(node.label)}</strong>
        <span>${escapeHtml(node.kind)}</span>
      </div>
      <div class="bridge-links">${linkMarkup}</div>
    </div>
  `;
}

function renderExplorerContent(data) {
  const bridgeContext = data && data.bridge_context ? data.bridge_context : null;
  const displayData = data && typeof data === "object" ? { ...data } : data;
  if (displayData && typeof displayData === "object") {
    delete displayData.bridge_context;
  }
  return `
    <div class="explorer-shell">
      ${bridgeContext ? renderBridgeContext(bridgeContext) : ""}
      ${renderExplorerValue(displayData)}
    </div>
  `;
}

function renderSourceViewContent(payload, rule = null, path = null) {
  const lines = String(payload && payload.content ? payload.content : "").split(/\r?\n/);
  const renderedLines = lines.length
    ? lines
        .map((line, index) => `
          <div class="source-line">
            <span class="source-line-number">${index + 1}</span>
            <pre class="source-line-text">${escapeHtml(line)}</pre>
          </div>
        `)
        .join("")
    : '<div class="empty-state">No source content was returned.</div>';
  const bridgeContext = path ? buildBridgeContextForPath(path) : null;
  const bridgeBlock = bridgeContext ? renderBridgeContext(bridgeContext) : "";
  const ruleBlock = rule
    ? `<div class="explorer-shell">${renderExplorerValue({ rule })}</div>`
    : "";
  return `
    <div class="modal-stack">
      <div class="explorer-summary">${escapeHtml(payload && payload.path ? payload.path : "Source")}</div>
      ${bridgeBlock}
      ${ruleBlock}
      <div class="source-view-block">${renderedLines}</div>
    </div>
  `;
}

function openExplorerModal(title, data, options = {}) {
  const summary = options.summary ? `<div class="explorer-summary">${escapeHtml(options.summary)}</div>` : "";
  const meta = options.meta ? `<div class="explorer-meta-line">${escapeHtml(options.meta)}</div>` : "";
  const footer = options.footer ? `<div class="explorer-footer">${options.footer}</div>` : "";
  openModal(
    title,
    `
      <div class="modal-stack">
        <div class="panel-header">
          <h3>${escapeHtml(title)}</h3>
          <span class="count-pill">${escapeHtml(options.kind || "raw data")}</span>
        </div>
        ${meta}
        ${summary}
        ${renderExplorerContent(data)}
        ${footer}
      </div>
    `,
  );
}

function renderCommandmentDetail(rule) {
  if (!rule) {
    closeModal();
    return;
  }

  const patternValue = rule.pattern || (rule.patterns ? rule.patterns.join(", ") : "");
  const title = rule.id || rule.type || "Commandment";
  const explorerData = {
    rule,
    repo_root: repoPathInput.value.trim() || ".",
    manifest_path: manifestPathInput.value.trim() || (currentManifest && currentManifest.manifest_path) || null,
    bridge_context: bridgeContext,
  };
  const sourceRefs = Array.isArray(rule.source_refs) ? rule.source_refs : [];
  const bridgeRef = sourceRefs.find((sourceRef) => sourceRef && sourceRef.path && !sourceRef.path.startsWith("docs/"));
  const bridgeContext = buildBridgeContextForPath(bridgeRef && bridgeRef.path ? bridgeRef.path : null);
  const sourceLinks = sourceRefs.length
    ? `
      <div class="source-link-row">
        ${sourceRefs
          .map((sourceRef) => {
            const label = sourceRef.label || sourceRef.path || "Source";
            return `
              <button
                type="button"
                class="secondary"
                data-action="open-rule-source"
                data-source-path="${escapeHtml(sourceRef.path || "") }"
                data-source-label="${escapeHtml(label)}"
                data-source-kind="${escapeHtml(sourceRef.kind || "file") }"
                data-rule-id="${escapeHtml(rule.id || "") }"
              >
                ${escapeHtml(label)}
              </button>
            `;
          })
          .join("")}
      </div>
    `
    : "";
  openModal(
    title,
    `
      <div class="modal-stack">
        <div class="panel-header">
          <h3>${escapeHtml(title)}</h3>
          <span class="count-pill">${escapeHtml(rule.type || "custom")}</span>
        </div>
        <div class="explorer-summary">${escapeHtml(rule.description || `Rule type ${rule.type || "custom"}`)}</div>
        <div class="rule-doc-grid">
          <div class="rule-doc-card">
            <h4>What</h4>
            <p>${escapeHtml(rule.what || "This rule is intended to keep the repository consistent and reviewable.")}</p>
          </div>
          <div class="rule-doc-card">
            <h4>Why</h4>
            <p>${escapeHtml(rule.why || "This rule prevents low-value patterns from drifting into the codebase.")}</p>
          </div>
        </div>
        ${sourceLinks}
        <div class="deep-dive-card">
          <label for="detail-rule-id">
            <span>Rule id</span>
            <input id="detail-rule-id" type="text" value="${escapeHtml(rule.id || "")}">
          </label>
          <label for="detail-rule-description">
            <span>Description</span>
            <textarea id="detail-rule-description" rows="3">${escapeHtml(rule.description || "")}</textarea>
          </label>
          <label for="detail-rule-pattern">
            <span>Pattern text</span>
            <input id="detail-rule-pattern" type="text" value="${escapeHtml(patternValue)}">
          </label>
          <label for="detail-rule-enabled">
            <span>Enabled</span>
            <input id="detail-rule-enabled" type="checkbox" ${rule.enabled === false ? "" : "checked"}>
          </label>
          <div class="detail-actions">
            <button type="button" id="detail-save" class="secondary" data-action="save-commandment-detail">Save edit</button>
            <button type="button" id="detail-close" data-action="close-commandment-detail">Close</button>
          </div>
        </div>
        ${renderExplorerContent(explorerData)}
      </div>
    `,
  );

  bindButtonActions(modalBody);
}

function renderCommandments(rules) {
  commandmentsList.innerHTML = "";
  commandmentsCount.textContent = `${rules.length} rule${rules.length === 1 ? "" : "s"}`;
  if (!rules.length) {
    commandmentDetail.classList.add("hidden");
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
    const what = escapeHtml(rule.what || rule.description || `Rule type ${rule.type || "custom"}`);
    const why = escapeHtml(rule.why || "This rule keeps the repository consistent and reviewable.");
    const sourceRefs = Array.isArray(rule.source_refs) ? rule.source_refs : [];
    const sourceButtons = sourceRefs.length
      ? sourceRefs
          .map((sourceRef) => {
            const label = sourceRef.label || sourceRef.path || "Source";
            return `
              <button
                type="button"
                class="secondary source-link"
                data-action="open-rule-source"
                data-source-path="${escapeHtml(sourceRef.path || "") }"
                data-source-label="${escapeHtml(label)}"
                data-source-kind="${escapeHtml(sourceRef.kind || "file") }"
                data-rule-id="${escapeHtml(rule.id || "") }"
              >
                ${escapeHtml(label)}
              </button>
            `;
          })
          .join("")
      : "";
    const isActive = selectedCommandment && selectedCommandment.id === rule.id;
    const cardClasses = `commandment-card${isActive ? " active" : ""}`;
    return `
      <article
        class="${cardClasses}"
        role="button"
        tabindex="0"
        data-action="select-commandment"
        data-rule-id="${escapeHtml(rule.id || "") }"
      >
        <header>
          <span class="rule-id">${ruleId}</span>
          <span class="meta">${escapeHtml(status)}</span>
        </header>
        <p>${description}</p>
        <div class="meta">${detail}</div>
        <div class="rule-doc-grid compact">
          <div class="rule-doc-card">
            <h4>What</h4>
            <p>${what}</p>
          </div>
          <div class="rule-doc-card">
            <h4>Why</h4>
            <p>${why}</p>
          </div>
        </div>
        ${sourceButtons ? `<div class="source-link-row">${sourceButtons}</div>` : ""}
      </article>
    `;
  });
  commandmentsList.innerHTML = cards.join("");

  bindButtonActions(commandmentsList);

  if (selectedCommandment) {
    const activeRule = rules.find((candidate) => candidate.id === selectedCommandment.id);
    if (activeRule) {
      renderCommandmentDetail(activeRule);
    }
  }
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
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.innerHTML = `
      <header>
        <h3>${escapeHtml(concept.title || concept.id || "Concept")}</h3>
        <span class="meta">${escapeHtml(concept.category || concept.rule_kind || "concept")}</span>
      </header>
      <p>${escapeHtml(concept.description || "")}</p>
      <div class="meta">${escapeHtml(concept.rule_kind || "custom")}</div>
      <div class="concept-actions">
        <button
          type="button"
          class="secondary concept-load"
          data-action="load-concept"
          data-concept-id="${escapeHtml(concept.id || concept.title || "")}"
        >
          Load
        </button>
        <button
          type="button"
          class="concept-freeze"
          data-action="freeze-concept"
          data-concept-id="${escapeHtml(concept.id || concept.title || "")}"
        >
          Freeze
        </button>
      </div>
    `;

    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      openExplorerModal(
        concept.title || concept.id || "Concept",
        { concept, repo_root: repoPathInput.value.trim() || "." },
        {
          kind: "concept",
          summary: concept.description || "",
          meta: concept.rule_kind || "custom",
        },
      );
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openExplorerModal(
          concept.title || concept.id || "Concept",
          { concept, repo_root: repoPathInput.value.trim() || "." },
          {
            kind: "concept",
            summary: concept.description || "",
            meta: concept.rule_kind || "custom",
          },
        );
      }
    });

    conceptsList.appendChild(card);
  }
  bindButtonActions(conceptsList);
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

function getCurrentRules() {
  if (currentManifest && currentManifest.manifest && Array.isArray(currentManifest.manifest.rules)) {
    return currentManifest.manifest.rules;
  }
  return [];
}

async function openRuleSource(button) {
  const sourcePath = button.getAttribute("data-source-path");
  const sourceLabel = button.getAttribute("data-source-label") || sourcePath || "Source";
  const ruleId = button.getAttribute("data-rule-id");
  const rules = getCurrentRules();
  const rule = rules.find((candidate) => candidate.id === ruleId) || null;
  try {
    const payload = await requestJson("/api/source-view", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_root: repoPathInput.value.trim() || ".",
        manifest_path: manifestPathInput.value.trim() || (currentManifest && currentManifest.manifest_path) || null,
        path: sourcePath,
      }),
    });
    openModal(sourceLabel, renderSourceViewContent(payload, rule, sourcePath));
    bindButtonActions(modalBody);
  } catch (error) {
    openModal(sourceLabel, `<div class="empty-state">Unable to load ${escapeHtml(sourcePath || "source")}: ${escapeHtml(error.message)}</div>`);
  }
}

function bindActionButton(button) {
  if (!button || button.dataset.sbgBound === "true") {
    return;
  }
  button.dataset.sbgBound = "true";
  button.addEventListener("click", (event) => {
    const action = button.getAttribute("data-action");
    if (!action) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (action === "scan-repository") {
      void scanRepository();
      return;
    }
    if (action === "refresh-manifest") {
      void loadManifest();
      return;
    }
    if (action === "suggest-rule") {
      void suggestRule();
      return;
    }
    if (action === "preview-pattern") {
      void previewPattern();
      return;
    }
    if (action === "save-pattern") {
      void savePattern();
      return;
    }
    if (action === "save-manifest") {
      void saveManifest();
      return;
    }
    if (action === "open-rule-source") {
      void openRuleSource(button);
      return;
    }
    if (action === "select-commandment") {
      const ruleId = button.getAttribute("data-rule-id");
      const rules = getCurrentRules();
      const rule = rules.find((candidate) => candidate.id === ruleId);
      if (rule) {
        selectedCommandment = rule;
        renderCommandments(rules);
      }
      return;
    }
    if (action === "save-commandment-detail") {
      const rules = getCurrentRules();
      const detailRoot = modalBody && modalBody.querySelector("#detail-rule-id") ? modalBody : commandmentDetail;
      const updatedRules = rules.map((candidate) => {
        if (candidate.id !== selectedCommandment?.id) {
          return candidate;
        }
        const nextId = detailRoot.querySelector("#detail-rule-id").value.trim() || candidate.id;
        return {
          ...candidate,
          id: nextId,
          description: detailRoot.querySelector("#detail-rule-description").value.trim(),
          pattern: detailRoot.querySelector("#detail-rule-pattern").value.trim(),
          enabled: detailRoot.querySelector("#detail-rule-enabled").checked,
        };
      });
      if (currentManifest && currentManifest.manifest) {
        currentManifest.manifest.rules = updatedRules;
        manifestEditor.value = JSON.stringify(currentManifest.manifest, null, 2);
        const nextId = detailRoot.querySelector("#detail-rule-id").value.trim();
        selectedCommandment = updatedRules.find((candidate) => candidate.id === nextId) || null;
        renderCommandments(updatedRules);
        closeModal();
        setStatus("Commandment updated in editor view.", "success");
      }
      return;
    }
    if (action === "close-commandment-detail") {
      closeModal();
      selectedCommandment = null;
      renderCommandments(getCurrentRules());
      return;
    }
    if (action === "load-concept") {
      const conceptId = button.getAttribute("data-concept-id");
      const concept = currentConcepts.find(
        (candidate) => (candidate.id || candidate.title || "") === conceptId
      );
      if (concept) {
        setPatternFormFromConcept(concept);
        setStatus(`Loaded concept ${concept.id || concept.title}.`, "success");
      }
      return;
    }
    if (action === "freeze-concept") {
      const conceptId = button.getAttribute("data-concept-id");
      const concept = currentConcepts.find(
        (candidate) => (candidate.id || candidate.title || "") === conceptId
      );
      if (concept) {
        setPatternFormFromConcept(concept);
        void savePattern(concept);
      }
    }
  });
}

function bindButtonActions(root = document) {
  root.querySelectorAll("[data-action]").forEach((button) => {
    bindActionButton(button);
  });
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
    card.setAttribute("data-action", "inspect-violation");
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
    const bridgeContext = buildBridgeContextForPath(payload.path || violation.path);
    openExplorerModal(
      violation.rule_id || "Violation",
      { violation, context: payload, bridge_context: bridgeContext },
      {
        kind: "violation",
        summary: `${payload.path || violation.path}${payload.line ? `:${payload.line}` : ""}`,
        meta: violation.message || "",
      },
    );
    setStatus(`Context loaded for ${violation.path}.`, "success");
  } catch (error) {
    renderViolationContext({ path: violation.path, line: violation.line || null, lines: [] });
    const bridgeContext = buildBridgeContextForPath(violation.path);
    openExplorerModal(
      violation.rule_id || "Violation",
      { violation, context: { path: violation.path, line: violation.line || null, lines: [] }, bridge_context: bridgeContext },
      {
        kind: "violation",
        summary: violation.path || "Unknown path",
        meta: error.message,
      },
    );
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

function renderAssetMap(graph) {
  currentAssetMap = graph || { nodes: [], edges: [] };
  const nodes = Array.isArray(currentAssetMap.nodes) ? currentAssetMap.nodes : [];
  const edges = Array.isArray(currentAssetMap.edges) ? currentAssetMap.edges : [];
  assetMapCount.textContent = `${edges.length} link${edges.length === 1 ? "" : "s"}`;
  if (!nodes.length) {
    assetMapList.innerHTML = '<div class="empty-state">No asset relationships were discovered.</div>';
    assetMapSummary.textContent = "No asset map available.";
    return;
  }

  const edgesBySource = new Map();
  for (const edge of edges) {
    const bucket = edgesBySource.get(edge.from) || [];
    bucket.push(edge);
    edgesBySource.set(edge.from, bucket);
  }

  assetMapSummary.textContent = (
    `Mapped ${nodes.length} assets and ${edges.length} links into a synthetic view of the dashboard.`
  );
  assetMapList.innerHTML = "";
  for (const node of nodes) {
    const relatedEdges = edges.filter((edge) => edge.from === node.id || edge.to === node.id);
    const links = (edgesBySource.get(node.id) || []).map((edge) => {
      const target = nodes.find((candidate) => candidate.id === edge.to);
      const label = target ? target.label : edge.to;
      return `<div class="asset-link">${escapeHtml(edge.kind)} → ${escapeHtml(label)}</div>`;
    });
    const card = document.createElement("article");
    card.className = "asset-map-card";
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.innerHTML = `
      <header>
        <h3>${escapeHtml(node.label)}</h3>
        <span class="count-pill">${escapeHtml(node.kind)}</span>
      </header>
      <div class="asset-map-links">
        ${links.length ? links.join("") : '<div class="asset-link">No outgoing links</div>'}
      </div>
    `;
    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      openExplorerModal(
        node.label || node.id || "Asset",
        { node, related_edges: relatedEdges },
        {
          kind: "asset map",
          summary: `${relatedEdges.length} related link${relatedEdges.length === 1 ? "" : "s"}`,
          meta: node.kind || "asset",
        },
      );
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openExplorerModal(
          node.label || node.id || "Asset",
          { node, related_edges: relatedEdges },
          {
            kind: "asset map",
            summary: `${relatedEdges.length} related link${relatedEdges.length === 1 ? "" : "s"}`,
            meta: node.kind || "asset",
          },
        );
      }
    });
    assetMapList.appendChild(card);
  }
}

async function loadAssetMap() {
  try {
    const payload = await requestJson("/api/asset-map");
    renderAssetMap(payload);
  } catch (error) {
    renderAssetMap({ nodes: [], edges: [] });
    assetMapSummary.textContent = `Unable to load asset map: ${error.message}`;
  }
}

function togglePanels() {
  summaryPanel.classList.toggle("hidden", !showSummaryCheckbox.checked);
  manifestPanel.classList.toggle("hidden", !showManifestCheckbox.checked);
}

showSummaryCheckbox.addEventListener("change", togglePanels);
showManifestCheckbox.addEventListener("change", togglePanels);

async function scanRepository() {
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
}

async function suggestRule() {
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
}

async function saveManifest() {
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
}

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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void scanRepository();
});

bindModalEvents();
bindButtonActions();
void loadAssetMap();
loadManifest();
togglePanels();
