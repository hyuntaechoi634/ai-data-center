const FIGURE_IDS = [
  "figure-01",
  "figure-02",
  "figure-03",
  "figure-04",
  "figure-05",
  "figure-06",
];

function storedSessions() {
  try {
    const parsed = JSON.parse(localStorage.getItem("figureStudioSessions") || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (_) {
    return {};
  }
}

function storedPanelSelections() {
  try {
    const parsed = JSON.parse(localStorage.getItem("figureStudioPanels") || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (_) {
    return {};
  }
}

const legacySession = localStorage.getItem("figureStudioSession") || "";
const sessionIds = storedSessions();
if (legacySession && !sessionIds["figure-06"]) {
  sessionIds["figure-06"] = legacySession;
}
const storedFigure = localStorage.getItem("figureStudioFigure") || "";

const app = {
  figureId: FIGURE_IDS.includes(storedFigure)
    ? storedFigure
    : legacySession
      ? "figure-06"
      : "figure-01",
  sessionIds,
  sessionId: "",
  token: sessionStorage.getItem("figureStudioToken") || "",
  state: null,
  busy: false,
  dragDepth: 0,
  previewUrls: new Map(),
  previewGeneration: 0,
  model: localStorage.getItem("figureStudioModel") || "",
  effort: localStorage.getItem("figureStudioEffort") || "",
  panelSelections: storedPanelSelections(),
  sidebarCollapsed: localStorage.getItem("figureStudioSidebarCollapsed") === "1",
};

const $ = (selector) => document.querySelector(selector);

function showToast(message, duration = 4200) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), duration);
}

function setBusy(
  active,
  title = "Working on the figure",
  detail = "The agent is editing and rendering the requested revision.",
  showOverlay = true,
) {
  app.busy = active;
  $("#busyTitle").textContent = title;
  $("#busyDetail").textContent = detail;
  $("#busyOverlay").classList.toggle("hidden", !active || !showOverlay);
  renderActionAvailability();
  renderNavigator();
}

function askForToken() {
  const value = window.prompt("Enter the Figure Studio access token", app.token || "");
  if (value !== null) {
    app.token = value.trim();
    sessionStorage.setItem("figureStudioToken", app.token);
  }
  return app.token;
}

async function api(path, options = {}, mayRetry = true) {
  const headers = new Headers(options.headers || {});
  if (app.token) headers.set("X-Figure-Studio-Token", app.token);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_) {
    payload = { ok: false, error: response.statusText };
  }
  if ([401, 403].includes(response.status) && mayRetry && !app.state) {
    askForToken();
    return api(path, options, false);
  }
  if (payload.state) {
    app.state = payload.state;
    renderState();
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || "The request failed");
  }
  return payload;
}

function authenticatedUrl(path, extra = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(extra).forEach(([key, value]) => url.searchParams.set(key, value));
  return url.toString();
}

function authHeaders() {
  return app.token ? { "X-Figure-Studio-Token": app.token } : {};
}

async function protectedBlob(path) {
  const response = await fetch(path, { headers: authHeaders() });
  if (!response.ok) throw new Error("The file could not be loaded");
  return response.blob();
}

function humanBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function setEmptyPreview(stage, message) {
  const prior = app.previewUrls.get(stage.id);
  if (prior) {
    URL.revokeObjectURL(prior);
    app.previewUrls.delete(stage.id);
  }
  const empty = document.createElement("div");
  empty.className = "empty-preview";
  empty.textContent = message;
  stage.classList.add("is-empty");
  stage.replaceChildren(empty);
}

async function preview(stage, url, label, generation) {
  stage.innerHTML = "";
  stage.classList.remove("is-empty");
  if (!url) {
    setEmptyPreview(stage, `${label} preview is unavailable`);
    return;
  }
  try {
    const blob = await protectedBlob(
      authenticatedUrl(url, { v: app.state?.updated_at || Date.now() }),
    );
    const prior = app.previewUrls.get(stage.id);
    if (prior) URL.revokeObjectURL(prior);
    const objectUrl = URL.createObjectURL(blob);
    if (generation !== app.previewGeneration) {
      URL.revokeObjectURL(objectUrl);
      return;
    }
    app.previewUrls.set(stage.id, objectUrl);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.target = "_blank";
    link.rel = "noopener";
    const image = document.createElement("img");
    image.src = objectUrl;
    image.alt = `${label} figure preview`;
    link.appendChild(image);
    stage.classList.remove("is-empty");
    stage.replaceChildren(link);
  } catch (_) {
    if (generation === app.previewGeneration) {
      setEmptyPreview(stage, `${label} preview could not be loaded`);
    }
  }
}

async function downloadArtifact(path, name) {
  const blob = await protectedBlob(authenticatedUrl(path, { download: "1" }));
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

function hasCurrentRevision(state = app.state) {
  if (!state) return false;
  if (typeof state.has_current_revision === "boolean") {
    return state.has_current_revision;
  }
  return state.mode === "custom";
}

function jpgArtifact(collection) {
  if (!app.state) return null;
  if (collection === "current" && !hasCurrentRevision()) return null;
  const artifacts = app.state[`${collection}_artifacts`] || [];
  return (
    artifacts.find((item) => item.extension === "jpg") ||
    artifacts.find((item) => item.extension === "jpeg") ||
    null
  );
}

function selectedPanelId() {
  return String(app.panelSelections[app.figureId] || "").toLowerCase();
}

function selectedPanelRecord(state = app.state) {
  const panelId = selectedPanelId();
  if (!panelId || !state || state.figure_id !== app.figureId) return null;
  return (state.panels || []).find((panel) => panel.id === panelId) || null;
}

function panelScopeLabel(panelId = selectedPanelId()) {
  return panelId ? `Panel ${panelId.toUpperCase()}` : "Whole figure";
}

function figureLabel(figureId = app.figureId) {
  return figureId.replace("figure-", "Figure ");
}

function isWidePanel(panel = selectedPanelRecord()) {
  const [width, height] = panel?.size_px || [];
  return Number(width) > 0 && Number(height) > 0 && width / height >= 2.2;
}

function updateComposerScope() {
  const panelId = selectedPanelId();
  const input = $("#promptInput");
  if (panelId) {
    input.placeholder = `Describe how you want to change panel ${panelId.toUpperCase()}`;
    input.setAttribute(
      "aria-label",
      `Describe a revision to ${figureLabel()} panel ${panelId.toUpperCase()}`,
    );
  } else {
    input.placeholder = "Describe how you want to change the figure";
    input.setAttribute("aria-label", "Describe a figure revision");
  }
}

function appendChatMessage(message, pending = false) {
  const container = $("#chatMessages");
  const item = document.createElement("div");
  item.className = `message ${message.role}`;
  if (pending) item.classList.add("pending");
  if (message.role !== "system") {
    const role = document.createElement("span");
    role.className = "message-role";
    const author = message.role === "user" ? "You" : "GPT";
    const scope = message.panel_id
      ? ` (Panel ${String(message.panel_id).toUpperCase()})`
      : "";
    role.textContent = author + scope;
    item.appendChild(role);
  }
  const text = document.createElement("span");
  text.className = "message-text";
  text.textContent = message.text;
  item.appendChild(text);
  if (pending) {
    const dots = document.createElement("span");
    dots.className = "typing-dots";
    dots.setAttribute("aria-hidden", "true");
    dots.innerHTML = "<i></i><i></i><i></i>";
    item.appendChild(dots);
  }
  container.appendChild(item);
  container.scrollTop = container.scrollHeight;
  return item;
}

function renderMessages(messages) {
  const container = $("#chatMessages");
  container.innerHTML = "";
  messages.forEach((message) => appendChatMessage(message));
  container.scrollTop = container.scrollHeight;
}

function renderUploads(uploads) {
  const container = $("#uploadList");
  container.innerHTML = "";
  container.classList.toggle("hidden", !uploads.length);
  uploads.forEach((upload) => {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    const name = document.createElement("span");
    name.className = "attachment-name";
    name.title = upload.path;
    name.textContent = upload.path;
    const size = document.createElement("span");
    size.className = "attachment-size";
    size.textContent = humanBytes(upload.bytes);
    const remove = document.createElement("button");
    remove.className = "attachment-remove";
    remove.type = "button";
    remove.title = `Remove ${upload.path}`;
    remove.setAttribute("aria-label", `Remove ${upload.path}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeUpload(upload.path));
    chip.append(name, size, remove);
    container.appendChild(chip);
  });
}

function renderNavigator() {
  const shell = $(".workspace-shell");
  shell.classList.toggle("sidebar-collapsed", app.sidebarCollapsed);
  const toggle = $("#sidebarToggle");
  toggle.setAttribute("aria-expanded", String(!app.sidebarCollapsed));
  toggle.setAttribute(
    "aria-label",
    app.sidebarCollapsed ? "Expand figure navigation" : "Collapse figure navigation",
  );
  toggle.title = toggle.getAttribute("aria-label");
  toggle.querySelector("span").textContent = app.sidebarCollapsed ? "›" : "‹";

  document.querySelectorAll(".panel-subnav").forEach((nav) => nav.remove());
  document.querySelectorAll(".figure-tab").forEach((button) => {
    const active = button.dataset.figureId === app.figureId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
    button.disabled = app.busy;
    button.removeAttribute("aria-expanded");
  });

  const activeState = app.state?.figure_id === app.figureId ? app.state : null;
  const panels = activeState?.panels || [];
  const availablePanels = new Set(
    panels.filter((panel) => panel.default_available).map((panel) => panel.id),
  );
  const selected = selectedPanelId();
  if (selected && activeState && !availablePanels.has(selected)) {
    delete app.panelSelections[app.figureId];
    localStorage.setItem("figureStudioPanels", JSON.stringify(app.panelSelections));
  }

  const activeTab = document.querySelector(
    `.figure-tab[data-figure-id="${app.figureId}"]`,
  );
  if (activeTab && panels.length) {
    activeTab.setAttribute("aria-expanded", String(!app.sidebarCollapsed));
    const panelNav = document.createElement("div");
    panelNav.className = "panel-subnav";
    panelNav.setAttribute("aria-label", `${figureLabel()} panels`);
    const choices = [{ id: "", label: "Whole", default_available: true }, ...panels];
    choices.forEach((panel) => {
      const button = document.createElement("button");
      button.className = "panel-nav-button";
      button.type = "button";
      button.dataset.panelId = panel.id;
      button.textContent = panel.label;
      const active = panel.id === selectedPanelId();
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "true" : "false");
      button.disabled =
        app.busy || (Boolean(panel.id) && !panel.default_available);
      button.addEventListener("click", () => selectPanel(panel.id));
      panelNav.appendChild(button);
    });
    activeTab.closest(".figure-nav-group")?.appendChild(panelNav);
  }
  updateComposerScope();
}

function synchronizeSelect(select, options, preferred, fallback) {
  const normalized = Array.isArray(options)
    ? options.filter(
        (option) =>
          option && typeof option.id === "string" && typeof option.label === "string",
      )
    : [];
  const selected = normalized.some((option) => option.id === preferred)
    ? preferred
    : normalized.some((option) => option.id === fallback)
      ? fallback
      : normalized[0]?.id || "";
  select.replaceChildren(
    ...normalized.map((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.label;
      return option;
    }),
  );
  select.value = selected;
  return selected;
}

function renderAgentControls(state) {
  app.model = synchronizeSelect(
    $("#modelSelect"),
    state.agent_models,
    app.model,
    state.default_agent_model,
  );
  const effortOptions = Array.isArray(state.agent_efforts)
    ? state.agent_efforts.map((option) => ({
        ...option,
        label: `Effort ${option.label}`,
      }))
    : [];
  app.effort = synchronizeSelect(
    $("#effortSelect"),
    effortOptions,
    app.effort,
    state.default_agent_effort,
  );
  if (app.model) localStorage.setItem("figureStudioModel", app.model);
  if (app.effort) localStorage.setItem("figureStudioEffort", app.effort);
}

function renderAgentStatus() {
  const agent = $("#agentBadge");
  if (app.busy) {
    agent.textContent = "Working";
    agent.className = "agent-status working";
  } else if (app.state?.agent_available) {
    agent.textContent = "Ready";
    agent.className = "agent-status ready";
  } else if (app.state) {
    agent.textContent = "Unavailable";
    agent.className = "agent-status unavailable";
  } else {
    agent.textContent = "Checking";
    agent.className = "agent-status";
  }
}

function renderBilling(status = app.state?.api_billing) {
  const badge = $("#billingBadge");
  const spent = Number(status?.spent_usd);
  const limit = Number(status?.limit_usd);
  const hasSpent =
    status?.spent_usd !== null &&
    status?.spent_usd !== undefined &&
    status?.spent_usd !== "" &&
    Number.isFinite(spent) &&
    spent >= 0;
  const hasLimit =
    status?.limit_usd !== null &&
    status?.limit_usd !== undefined &&
    status?.limit_usd !== "" &&
    Number.isFinite(limit) &&
    limit >= 0;
  badge.className = "billing-status";
  if (!hasSpent && !hasLimit) {
    badge.classList.add("hidden");
    badge.textContent = "API --";
    badge.title = status?.message || "API billing is not connected";
    return;
  }
  badge.classList.remove("hidden");
  if (hasSpent && hasLimit) {
    badge.textContent = `API $${spent.toFixed(2)} / $${limit.toFixed(2)}`;
  } else if (hasSpent) {
    badge.textContent = `API $${spent.toFixed(2)}`;
  } else {
    badge.textContent = `API -- / $${limit.toFixed(2)}`;
  }
  const ratio = hasSpent && hasLimit && limit > 0 ? spent / limit : 0;
  if (ratio >= 1 || status?.enforcement === "enforcing") {
    badge.classList.add("critical");
  } else if (ratio >= 0.8) {
    badge.classList.add("warning");
  }
  if (status?.stale || !status?.available) badge.classList.add("stale");
  const details = [status?.message || "OpenAI API billing"];
  if (hasSpent) details.push(`Exact spend $${spent.toFixed(6)}`);
  if (hasLimit) {
    details.push(
      `${status?.limit_verified ? "Verified" : "Unverified"} limit $${limit.toFixed(2)}`,
    );
  }
  if (status?.enforcement === "enforcing") {
    details.push("The hard limit is currently blocking requests");
  } else if (status?.enforcement === "inactive") {
    details.push("The hard limit is not currently blocking requests");
  } else if (status?.enforcement) {
    details.push(`Current enforcement state ${status.enforcement}`);
  }
  if (status?.updated_at) {
    details.push(`Updated ${new Date(status.updated_at).toLocaleString()}`);
  }
  badge.title = details.join(". ");
}

function renderActionAvailability() {
  const state = app.state;
  const showCurrent = hasCurrentRevision(state);
  $("#undoButton").disabled = !state?.can_undo || app.busy;
  $("#redoButton").disabled = !state?.can_redo || app.busy;
  $("#resetButton").disabled = !showCurrent || app.busy;
  $("#sendButton").disabled = !state?.agent_available || app.busy;
  $("#downloadProject").disabled = !state || app.busy;
  const pullRequest = state?.pull_request || {};
  const pullRequestButton = $("#pullRequestButton");
  pullRequestButton.textContent =
    pullRequest.mode === "owner-admin-immediate-merge" ? "Apply PR" : "Propose PR";
  pullRequestButton.disabled =
    !showCurrent || !pullRequest.available || app.busy;
  pullRequestButton.title =
    pullRequest.message || "Submit a private proposal for owner review";
  $("#modelSelect").disabled = !state?.agent_available || app.busy;
  $("#effortSelect").disabled = !state?.agent_available || app.busy;
  renderAgentStatus();

  [
    ["#downloadDefaultFigure", jpgArtifact("default")],
    ["#downloadCurrentFigure", jpgArtifact("current")],
  ].forEach(([selector, figure]) => {
    const button = $(selector);
    button.disabled = !figure || app.busy;
    button.dataset.path = figure?.url || "";
    button.dataset.name = figure?.download_name || "figure.jpg";
  });
}

function renderSelectedPreviews(state = app.state) {
  if (!state) return;
  const panel = selectedPanelRecord(state);
  const panelId = panel?.id || "";
  const generation = ++app.previewGeneration;
  const defaultStage = $("#defaultStage");
  const currentStage = $("#currentStage");
  const comparison = $("#comparisonGrid");
  comparison.classList.toggle("panel-mode", Boolean(panelId));
  comparison.classList.toggle("panel-wide", Boolean(panelId) && isWidePanel(panel));
  $("#currentCard").classList.toggle(
    "no-revision",
    Boolean(panelId) && !hasCurrentRevision(state),
  );
  defaultStage.classList.toggle("panel-focused", Boolean(panelId));
  currentStage.classList.toggle("panel-focused", Boolean(panelId));

  $("#defaultLabel").textContent = panelId
    ? `Default Panel ${panelId.toUpperCase()}`
    : "Default";
  $("#currentLabel").textContent = panelId
    ? `Current Panel ${panelId.toUpperCase()}`
    : "Current";

  const defaultUrl = panelId ? panel.default_preview_url : state.default_preview_url;
  const currentUrl = panelId ? panel.current_preview_url : state.current_preview_url;
  preview(
    defaultStage,
    defaultUrl,
    panelId ? `Default panel ${panelId.toUpperCase()}` : "Default",
    generation,
  );
  if (hasCurrentRevision(state)) {
    preview(
      currentStage,
      currentUrl,
      panelId ? `Current panel ${panelId.toUpperCase()}` : "Current",
      generation,
    );
  } else {
    setEmptyPreview(
      currentStage,
      panelId
        ? `Revised panel ${panelId.toUpperCase()} will appear here`
        : "Revised figure will appear here",
    );
  }
}

function renderState() {
  if (!app.state) return;
  const state = app.state;
  if (FIGURE_IDS.includes(state.figure_id)) {
    app.figureId = state.figure_id;
    app.sessionId = state.session_id;
    app.sessionIds[app.figureId] = app.sessionId;
    localStorage.setItem("figureStudioFigure", app.figureId);
    localStorage.setItem("figureStudioSessions", JSON.stringify(app.sessionIds));
  }
  const showCurrent = hasCurrentRevision(state);
  $("#updatedAt").textContent =
    showCurrent && state.updated_at
      ? new Date(state.updated_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";

  renderAgentControls(state);
  renderBilling(state.api_billing);
  $("#tokenButton").classList.toggle("hidden", state.auth_mode === "cloudflare_access");

  renderActionAvailability();

  renderSelectedPreviews(state);
  renderUploads(state.uploads || []);
  renderMessages(state.messages || []);

  const warnings = state.warnings || [];
  const warningBox = $("#warningBox");
  warningBox.textContent = warnings.join("\n");
  warningBox.classList.toggle("hidden", !warnings.length);
  document.title = `${app.figureId.replace("figure-", "Figure ")} - Figure Studio`;
  renderNavigator();
}

async function refreshBilling() {
  if (!app.state) return;
  try {
    const payload = await api("/api/billing", {}, false);
    app.state.api_billing = payload.api_billing;
    renderBilling(payload.api_billing);
  } catch (_) {
    return;
  }
}

function selectPanel(panelId) {
  if (app.busy || !app.state || app.state.figure_id !== app.figureId) return;
  const normalized = String(panelId || "").toLowerCase();
  const available = new Set(
    (app.state.panels || [])
      .filter((panel) => panel.default_available)
      .map((panel) => panel.id),
  );
  if (normalized && !available.has(normalized)) return;
  app.panelSelections[app.figureId] = normalized;
  localStorage.setItem("figureStudioPanels", JSON.stringify(app.panelSelections));
  renderNavigator();
  renderSelectedPreviews();
  $("#promptInput").focus();
}

async function selectFigure(figureId) {
  if (!FIGURE_IDS.includes(figureId) || app.busy) return;
  app.figureId = figureId;
  app.sessionId = app.sessionIds[figureId] || "";
  app.state = null;
  localStorage.setItem("figureStudioFigure", figureId);
  renderNavigator();
  const pendingPanel = selectedPanelId();
  $("#defaultLabel").textContent = pendingPanel
    ? `Default Panel ${pendingPanel.toUpperCase()}`
    : "Default";
  $("#currentLabel").textContent = pendingPanel
    ? `Current Panel ${pendingPanel.toUpperCase()}`
    : "Current";
  $("#defaultStage").classList.toggle("panel-focused", Boolean(pendingPanel));
  $("#currentStage").classList.toggle("panel-focused", Boolean(pendingPanel));
  $("#comparisonGrid").classList.toggle("panel-mode", Boolean(pendingPanel));
  $("#comparisonGrid").classList.remove("panel-wide");
  $("#currentCard").classList.toggle("no-revision", Boolean(pendingPanel));
  setEmptyPreview($("#defaultStage"), "Loading the default figure");
  setEmptyPreview(
    $("#currentStage"),
    pendingPanel
      ? `Revised panel ${pendingPanel.toUpperCase()} will appear here`
      : "Revised figure will appear here",
  );
  renderMessages([]);
  renderUploads([]);
  setBusy(true, `Opening ${figureId.replace("figure-", "Figure ")}`, "Preparing its isolated editing session.");
  try {
    if (app.sessionId) {
      try {
        const payload = await api(`/api/sessions/${app.sessionId}`);
        if (payload.state.figure_id !== figureId) throw new Error("Session figure mismatch");
      } catch (_) {
        delete app.sessionIds[figureId];
        app.sessionId = "";
      }
    }
    if (!app.sessionId) {
      await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ figure_id: figureId }),
      });
    }
  } catch (error) {
    showToast(error.message, 8000);
  } finally {
    setBusy(false);
    autoResizePrompt();
  }
}

async function initialize() {
  await selectFigure(app.figureId);
}

function autoResizePrompt() {
  const input = $("#promptInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 192)}px`;
}

async function sendChat() {
  if (app.busy) return;
  const input = $("#promptInput");
  const message = input.value.trim();
  if (!message) {
    showToast("Describe the change you want first.");
    input.focus();
    return;
  }
  const panelId = selectedPanelId();
  input.value = "";
  autoResizePrompt();
  appendChatMessage({ role: "user", text: message, panel_id: panelId || null });
  const pendingReply = appendChatMessage(
    {
      role: "assistant",
      text: panelId
        ? `I’m reviewing panel ${panelId.toUpperCase()}, updating the code, and checking the full figure.`
        : "I’m reviewing your request, updating the figure code, and rendering the result.",
      panel_id: panelId || null,
    },
    true,
  );
  setBusy(
    true,
    panelId
      ? `Revising ${figureLabel()} panel ${panelId.toUpperCase()}`
      : "Generating a new revision",
    panelId
      ? `The agent is editing panel ${panelId.toUpperCase()}, rebuilding the full figure, and checking that the other panels did not change.`
      : "The agent is inspecting the sources, editing code, and rendering a JPG. This may take several minutes.",
    false,
  );
  try {
    await api(`/api/sessions/${app.sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message,
        formats: ["jpg"],
        model: app.model,
        effort: app.effort,
        panel_id: panelId || null,
      }),
    });
  } catch (error) {
    if (pendingReply.isConnected) {
      pendingReply.classList.remove("pending");
      pendingReply.querySelector(".typing-dots")?.remove();
      const text = pendingReply.querySelector(".message-text");
      if (text) text.textContent = `I couldn’t complete that revision. ${error.message}`;
    }
  } finally {
    setBusy(false);
    input.focus();
  }
}

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function uploadFiles(files) {
  if (!files.length || app.busy) return;
  const oversized = files.find((file) => file.size > 25 * 1024 * 1024);
  if (oversized) {
    showToast(`${oversized.name} exceeds the 25 MB per-file limit.`, 8000);
    return;
  }
  setBusy(
    true,
    "Adding source material",
    "Data and images are being copied into this isolated session.",
  );
  let completed = 0;
  try {
    for (const file of files) {
      const content = await fileAsBase64(file);
      await api(`/api/sessions/${app.sessionId}/upload`, {
        method: "POST",
        body: JSON.stringify({
          files: [{ name: file.name, content_base64: content }],
        }),
      });
      completed += 1;
    }
    showToast(`Added ${completed} file${completed === 1 ? "" : "s"}.`);
    $("#promptInput").focus();
  } catch (error) {
    const prefix = completed ? `Added ${completed} file(s). ` : "";
    showToast(prefix + error.message, 9000);
  } finally {
    $("#fileInput").value = "";
    setBusy(false);
  }
}

async function removeUpload(name) {
  if (app.busy) return;
  try {
    await api(`/api/sessions/${app.sessionId}/remove-upload`, {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    showToast("File removed.");
  } catch (error) {
    showToast(error.message, 8000);
  }
}

async function resetDefault() {
  if (!hasCurrentRevision() || app.busy) return;
  if (
    !window.confirm(
      "Return the figure and code to the default version? Uploaded files will be kept and this version can be restored with Undo.",
    )
  ) {
    return;
  }
  setBusy(true, "Returning to default", "Saving the current revision in version history.");
  try {
    await api(`/api/sessions/${app.sessionId}/reset`, {
      method: "POST",
      body: JSON.stringify({ keep_uploads: true }),
    });
    showToast("The default figure has been restored.");
  } catch (error) {
    showToast(error.message, 8000);
  } finally {
    setBusy(false);
  }
}

async function historyAction(action) {
  if (app.busy) return;
  setBusy(
    true,
    action === "undo" ? "Restoring the previous version" : "Restoring the later version",
    "Code, derived data, uploads, and outputs are being restored together.",
  );
  try {
    await api(`/api/sessions/${app.sessionId}/${action}`, {
      method: "POST",
      body: "{}",
    });
    showToast(action === "undo" ? "Previous version restored." : "Later version restored.");
  } catch (error) {
    showToast(error.message, 8000);
  } finally {
    setBusy(false);
  }
}

async function downloadProject() {
  if (!app.state || app.busy) return;
  setBusy(
    true,
    "Packaging data and code",
    "Collecting source data, uploads, derived data, code, the JPG, chat history, and checksums.",
  );
  try {
    const response = await fetch(app.state.download_url, { headers: authHeaders() });
    if (!response.ok) throw new Error("The data and code package could not be created");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `figure-studio-${app.figureId}-${app.sessionId}.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showToast(error.message, 8000);
  } finally {
    setBusy(false);
  }
}

async function downloadFigure(button) {
  if (!button.dataset.path || app.busy) return;
  try {
    await downloadArtifact(button.dataset.path, button.dataset.name || "figure.jpg");
  } catch (error) {
    showToast(error.message, 8000);
  }
}

async function createPullRequest() {
  if (!app.state || app.busy) return;
  const configuration = app.state.pull_request || {};
  if (!configuration.available) {
    showToast(configuration.message || "Proposal submission is unavailable", 8000);
    return;
  }
  const panelId = selectedPanelId();
  const scope = panelId ? ` panel ${panelId.toUpperCase()}` : "";
  const immediate = configuration.mode === "owner-admin-immediate-merge";
  const confirmation = immediate
    ? `Apply ${figureLabel()}${scope} immediately to the integration branch through a PR? Only exact allowlisted public files can be included.`
    : `Submit ${figureLabel()}${scope} for owner review? No public GitHub branch will be created until the owner reviews the exact file diff.`;
  if (
    !window.confirm(confirmation)
  ) {
    return;
  }
  setBusy(
    true,
    immediate ? "Applying the revision" : "Submitting a proposal",
    immediate
      ? "Validating the exact public file allowlist, creating the PR, and merging it into the integration branch."
      : "Validating the exact public file allowlist and creating a private review bundle.",
  );
  try {
    const payload = await api(`/api/sessions/${app.sessionId}/pull-request`, {
      method: "POST",
      body: JSON.stringify({ panel_id: panelId || null }),
    });
    if (payload.pull_request) {
      showToast(
        `PR #${payload.pull_request.number} was merged into the integration branch.`,
        9000,
      );
    } else {
      showToast(
        `Proposal ${payload.proposal.id} is waiting for owner review.`,
        8000,
      );
    }
  } catch (error) {
    showToast(error.message, 9000);
  } finally {
    setBusy(false);
  }
}

function filesFromEvent(event) {
  return [...(event.dataTransfer?.files || [])];
}

function clearDragState() {
  app.dragDepth = 0;
  $("#composer").classList.remove("dragging");
  $("#dropOverlay").classList.add("hidden");
}

const composer = $("#composer");
composer.addEventListener("dragenter", (event) => {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  app.dragDepth += 1;
  composer.classList.add("dragging");
  $("#dropOverlay").classList.remove("hidden");
});
composer.addEventListener("dragover", (event) => {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
});
composer.addEventListener("dragleave", (event) => {
  if (!event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  app.dragDepth = Math.max(0, app.dragDepth - 1);
  if (!app.dragDepth) clearDragState();
});
composer.addEventListener("drop", (event) => {
  event.preventDefault();
  const files = filesFromEvent(event);
  clearDragState();
  uploadFiles(files);
});
document.addEventListener("dragend", clearDragState);
document.addEventListener("drop", clearDragState);

$("#promptInput").addEventListener("paste", (event) => {
  const files = [...(event.clipboardData?.files || [])];
  if (!files.length) return;
  event.preventDefault();
  uploadFiles(files);
});
$("#promptInput").addEventListener("input", autoResizePrompt);
$("#promptInput").addEventListener("keydown", (event) => {
  if (
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing
  ) {
    event.preventDefault();
    sendChat();
  }
});

$("#sendButton").addEventListener("click", sendChat);
$("#modelSelect").addEventListener("change", (event) => {
  app.model = event.target.value;
  localStorage.setItem("figureStudioModel", app.model);
});
$("#effortSelect").addEventListener("change", (event) => {
  app.effort = event.target.value;
  localStorage.setItem("figureStudioEffort", app.effort);
});
$("#fileInput").addEventListener("change", (event) => {
  uploadFiles([...event.target.files]);
});
$("#downloadDefaultFigure").addEventListener("click", (event) =>
  downloadFigure(event.currentTarget),
);
$("#downloadCurrentFigure").addEventListener("click", (event) =>
  downloadFigure(event.currentTarget),
);
$("#downloadProject").addEventListener("click", downloadProject);
$("#pullRequestButton").addEventListener("click", createPullRequest);
$("#resetButton").addEventListener("click", resetDefault);
$("#undoButton").addEventListener("click", () => historyAction("undo"));
$("#redoButton").addEventListener("click", () => historyAction("redo"));
$("#tokenButton").addEventListener("click", () => {
  askForToken();
  initialize();
});
$("#sidebarToggle").addEventListener("click", () => {
  app.sidebarCollapsed = !app.sidebarCollapsed;
  localStorage.setItem(
    "figureStudioSidebarCollapsed",
    app.sidebarCollapsed ? "1" : "0",
  );
  renderNavigator();
});
document.querySelectorAll(".figure-tab").forEach((button) => {
  button.addEventListener("click", () => selectFigure(button.dataset.figureId));
});
window.addEventListener("beforeunload", () => {
  app.previewUrls.forEach((url) => URL.revokeObjectURL(url));
});

renderNavigator();
initialize();
window.setInterval(refreshBilling, 5 * 60 * 1000);
