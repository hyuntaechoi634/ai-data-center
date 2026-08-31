const FIGURE_IDS = [
  "figure-01",
  "figure-02",
  "figure-03",
  "figure-04",
  "figure-05",
  "figure-06",
  "supplementary-01",
  "supplementary-02",
  "supplementary-03",
  "supplementary-04",
  "supplementary-05",
  "supplementary-06",
];
const SVG_NS = "http://www.w3.org/2000/svg";

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
  activeJobId: "",
  activeJobSessionId: "",
  monitoringJobId: "",
  cancelling: false,
  jobStage: "",
  dragDepth: 0,
  previewUrls: new Map(),
  previewGeneration: 0,
  model: localStorage.getItem("figureStudioModel") || "",
  effort: localStorage.getItem("figureStudioEffort") || "",
  panelSelections: storedPanelSelections(),
  sidebarCollapsed: localStorage.getItem("figureStudioSidebarCollapsed") === "1",
  layout: {
    open: false,
    data: null,
    baseData: null,
    baseBlob: null,
    objectUrl: "",
    selectedId: "",
    hitCycle: null,
    pending: new Map(),
    drag: null,
    previewTimer: 0,
    previewing: false,
    previewQueued: false,
    previewGeneration: 0,
    fontSizeDraftValid: true,
    fontSizeDraftDirty: false,
    textDraftValid: true,
    textDraftDirty: false,
  },
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
    const error = new Error(payload.error || "The request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
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
    image.alt = `${label} figure preview`;
    if (stage.id === "defaultStage") {
      image.addEventListener("load", sizeLayoutCanvas, { once: true });
    }
    image.src = objectUrl;
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
  const number = figureId.slice(-2);
  return figureId.startsWith("supplementary-")
    ? `Supplementary Figure ${number}`
    : `Figure ${number}`;
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
  if (app.activeJobId) {
    agent.textContent = app.cancelling ? "Stopping" : "Working";
    agent.className = "agent-status working";
    agent.title = app.jobStage || "The figure revision is running";
  } else if (app.busy) {
    agent.textContent = "Working";
    agent.className = "agent-status working";
    agent.title = "Figure Studio is working";
  } else if (app.state?.agent_available) {
    agent.textContent = "Ready";
    agent.className = "agent-status ready";
    agent.title = "The figure agent is ready";
  } else if (app.state) {
    agent.textContent = "Unavailable";
    agent.className = "agent-status unavailable";
    agent.title = "The figure agent is unavailable";
  } else {
    agent.textContent = "Checking";
    agent.className = "agent-status";
    agent.title = "Checking the figure agent";
  }
}

function renderBilling(status = app.state?.api_billing) {
  const badge = $("#billingBadge");
  const spent = Number(status?.spent_usd);
  const limit = Number(status?.limit_usd);
  const estimated = status?.estimated === true;
  const spendPrefix = estimated ? "~$" : "$";
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
    badge.textContent = `API ${spendPrefix}${spent.toFixed(2)} / $${limit.toFixed(2)}`;
  } else if (hasSpent) {
    badge.textContent = `API ${spendPrefix}${spent.toFixed(2)}`;
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
  if (hasSpent) {
    details.push(
      `${estimated ? "Estimated" : "Reported"} spend $${spent.toFixed(6)}`,
    );
  }
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
  const panel = selectedPanelRecord(state);
  const revising = Boolean(app.activeJobId);
  const layoutChanging = Boolean(app.layout.pending.size || app.layout.previewing);
  const sendButton = $("#sendButton");
  $("#undoButton").disabled = !state?.can_undo || app.busy || layoutChanging;
  $("#redoButton").disabled = !state?.can_redo || app.busy || layoutChanging;
  $("#resetButton").disabled = (
    (!showCurrent && !hasUnappliedLayoutChanges()) ||
    app.busy ||
    app.layout.previewing
  );
  sendButton.disabled = revising
    ? app.cancelling
    : !state?.agent_available || app.busy || layoutChanging;
  sendButton.classList.toggle("is-cancel", revising);
  sendButton.querySelector("span").textContent = revising ? "×" : "↑";
  sendButton.setAttribute(
    "aria-label",
    revising ? "Cancel revision" : "Send message",
  );
  sendButton.title = revising ? "Cancel revision (Esc)" : "Send message";
  const downloadProjectButton = $("#downloadProject");
  downloadProjectButton.disabled = !state || app.busy || layoutChanging;
  downloadProjectButton.textContent = panel ? "Panel data & code" : "Data & code";
  downloadProjectButton.title = panel
    ? `Download the current ${panelScopeLabel(panel.id)} image, source code, and referenced inputs`
    : "Download the complete figure project";
  const pullRequest = state?.pull_request || {};
  const pullRequestButton = $("#pullRequestButton");
  pullRequestButton.textContent =
    pullRequest.mode === "owner-admin-immediate-merge" ? "Apply PR" : "Propose PR";
  pullRequestButton.disabled =
    !showCurrent || !pullRequest.available || app.busy || layoutChanging;
  pullRequestButton.title =
    pullRequest.message || "Submit a private proposal for owner review";
  $("#modelSelect").disabled = !state?.agent_available || app.busy || layoutChanging;
  $("#effortSelect").disabled = !state?.agent_available || app.busy || layoutChanging;
  $("#promptInput").disabled = layoutChanging;
  renderAgentStatus();

  const panelFigure = (collection) => {
    if (!panel) return jpgArtifact(collection);
    if (collection === "current" && !showCurrent) return null;
    const url = panel[`${collection}_preview_url`];
    if (!url) return null;
    return {
      url,
      download_name: `${state.figure_id}-${panel.id}-${collection}.jpg`,
    };
  };
  [
    ["#downloadDefaultFigure", panelFigure("default")],
    ["#downloadCurrentFigure", panelFigure("current")],
  ].forEach(([selector, figure]) => {
    const button = $(selector);
    button.disabled = !figure || app.busy || layoutChanging;
    button.dataset.path = figure?.url || "";
    button.dataset.name = figure?.download_name || "figure.jpg";
  });
}

function renderSelectedPreviews(state = app.state, preserveLayout = false) {
  if (!state) return;
  if (app.layout.open && !preserveLayout) return;
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
    !preserveLayout && Boolean(panelId) && !hasCurrentRevision(state),
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
  if (preserveLayout) {
    app.layout.selectedId = "";
    renderLayoutOverlays();
    window.requestAnimationFrame(sizeLayoutCanvas);
    return;
  }
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

  const activeJob = state.active_chat_job;
  if (activeJob && !["completed", "cancelled", "failed"].includes(activeJob.status)) {
    const latestMessage = (state.messages || []).at(-1);
    const resumedReply = latestMessage?.role === "user"
      ? appendChatMessage(
          {
            role: "assistant",
            text: activeJob.stage || "The figure revision is still running.",
            panel_id: latestMessage.panel_id || null,
          },
          true,
        )
      : null;
    app.activeJobId = activeJob.id;
    app.activeJobSessionId = state.session_id;
    app.jobStage = activeJob.stage || "Revision in progress";
    app.cancelling = activeJob.status === "cancelling";
    setBusy(
      true,
      app.cancelling ? "Stopping the revision" : "Generating a new revision",
      app.jobStage,
      false,
    );
    window.setTimeout(
      () => monitorChatJob(activeJob.id, state.session_id, resumedReply),
      0,
    );
  }

  const warnings = state.warnings || [];
  const warningBox = $("#warningBox");
  warningBox.textContent = warnings.join("\n");
  warningBox.classList.toggle("hidden", !warnings.length);
  document.title = `${figureLabel()} - Figure Studio`;
  renderNavigator();
}

async function refreshBilling() {
  if (!app.state) return null;
  try {
    const payload = await api("/api/billing", {}, false);
    app.state.api_billing = payload.api_billing;
    renderBilling(payload.api_billing);
    return payload.api_billing;
  } catch (_) {
    return null;
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function refreshBillingAfter(finishedAt) {
  const target = Date.parse(finishedAt || "");
  const delays = [0, 2000, 3000, 5000, 8000, 12000];
  for (const wait of delays) {
    if (wait) await delay(wait);
    const status = await refreshBilling();
    const updated = Date.parse(status?.updated_at || "");
    if (Number.isFinite(target) && Number.isFinite(updated) && updated >= target) {
      return;
    }
  }
}

function selectPanel(panelId) {
  if (app.busy || !app.state || app.state.figure_id !== app.figureId) return;
  if (app.layout.pending.size || app.layout.previewing) return;
  const reuseLayout = Boolean(app.layout.open && app.layout.data);
  if (app.layout.open && !reuseLayout) closeLayoutEditor();
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
  renderActionAvailability();
  renderSelectedPreviews(app.state, reuseLayout);
  if (reuseLayout) return;
  window.setTimeout(() => {
    if (!app.busy && selectedPanelId() === normalized) openLayoutEditor();
  }, 0);
}

async function selectFigure(figureId) {
  if (
    !FIGURE_IDS.includes(figureId) ||
    app.busy ||
    app.layout.pending.size ||
    app.layout.previewing
  ) return;
  if (app.layout.open) closeLayoutEditor();
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
  setBusy(true, `Opening ${figureLabel(figureId)}`, "Preparing its isolated editing session.");
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
    if (!app.activeJobId) setBusy(false);
    autoResizePrompt();
    if (app.state && !app.activeJobId) await openLayoutEditor();
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
  const priorMessageCount = (app.state?.messages || []).length;
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
    const sessionId = app.sessionId;
    const payload = await api(`/api/sessions/${sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message,
        formats: ["jpg"],
        model: app.model,
        effort: app.effort,
        panel_id: panelId || null,
      }),
    });
    app.activeJobId = payload.job.id;
    app.activeJobSessionId = sessionId;
    app.jobStage = payload.job.stage || "Revision queued";
    renderActionAvailability();
    await monitorChatJob(payload.job.id, sessionId, pendingReply);
  } catch (error) {
    let recovered = false;
    try {
      const session = await api(`/api/sessions/${app.sessionId}`, {}, false);
      const serverMessages = session.state.messages || [];
      const requestReachedServer = serverMessages
        .slice(priorMessageCount)
        .some((item) => item.role === "user" && item.text === message);
      recovered = Boolean(session.state.active_chat_job) || requestReachedServer;
      if (recovered && !session.state.active_chat_job) setBusy(false);
    } catch (_) {
      recovered = false;
    }
    if (recovered) return;
    if (pendingReply.isConnected) {
      pendingReply.classList.remove("pending");
      pendingReply.querySelector(".typing-dots")?.remove();
      const text = pendingReply.querySelector(".message-text");
      if (text) text.textContent = `I couldn’t complete that revision. ${error.message}`;
    } else {
      appendChatMessage({
        role: "assistant",
        text: `I couldn’t complete that revision. ${error.message}`,
        panel_id: panelId || null,
      });
    }
    showToast(error.message, 8000);
    setBusy(false);
    input.focus();
  }
}

function updatePendingReply(pendingReply, job) {
  if (!pendingReply?.isConnected) return;
  const text = pendingReply.querySelector(".message-text");
  if (!text) return;
  text.textContent = job.status === "cancelling"
    ? "Stopping the revision and restoring the previous figure."
    : job.stage || "The figure revision is still running.";
}

async function monitorChatJob(jobId, sessionId = app.sessionId, pendingReply = null) {
  if (!jobId || app.monitoringJobId === jobId) return;
  app.monitoringJobId = jobId;
  app.activeJobId = jobId;
  app.activeJobSessionId = sessionId;
  let terminalJob = null;
  let warnedAboutConnection = false;
  try {
    while (
      app.activeJobId === jobId &&
      app.activeJobSessionId === sessionId
    ) {
      let payload;
      try {
        payload = await api(
          `/api/sessions/${sessionId}/jobs/${jobId}`,
          {},
          false,
        );
        warnedAboutConnection = false;
      } catch (error) {
        if (error.status === 404) {
          try {
            await api(`/api/sessions/${sessionId}`, {}, false);
          } catch (_) {
            // The session error is reported below using the original job error.
          }
          showToast("The revision status is no longer available. The figure was reloaded.", 8000);
          break;
        }
        if (!warnedAboutConnection) {
          showToast("Connection interrupted. Figure Studio will keep checking the revision.", 8000);
          warnedAboutConnection = true;
        }
        await delay(2000);
        continue;
      }

      const job = payload.job;
      app.jobStage = job.stage || "Revision in progress";
      app.cancelling = job.status === "cancelling";
      updatePendingReply(pendingReply, job);
      setBusy(
        true,
        app.cancelling ? "Stopping the revision" : "Generating a new revision",
        app.jobStage,
        false,
      );
      if (["completed", "cancelled", "failed"].includes(job.status)) {
        terminalJob = job;
        if (job.status === "cancelled") {
          showToast("Revision cancelled. No figure changes were kept.");
        } else if (job.status === "failed") {
          showToast(job.error || "The revision could not be completed.", 9000);
        }
        break;
      }
      await delay(1500);
    }
  } finally {
    if (app.monitoringJobId === jobId) app.monitoringJobId = "";
    if (app.activeJobId === jobId) {
      app.activeJobId = "";
      app.activeJobSessionId = "";
      app.jobStage = "";
      app.cancelling = false;
    }
    setBusy(false);
    $("#promptInput").focus();
    if (terminalJob) {
      void refreshBillingAfter(terminalJob.finished_at);
    }
  }
}

async function cancelActiveChat() {
  if (!app.activeJobId || app.cancelling) return;
  const jobId = app.activeJobId;
  const sessionId = app.activeJobSessionId || app.sessionId;
  app.cancelling = true;
  app.jobStage = "Stopping the revision";
  setBusy(true, "Stopping the revision", app.jobStage, false);
  try {
    const payload = await api(
      `/api/sessions/${sessionId}/jobs/${jobId}/cancel`,
      { method: "POST", body: "{}" },
      false,
    );
    app.jobStage = payload.job.stage || app.jobStage;
    showToast("Stopping the revision and restoring the previous figure.");
  } catch (error) {
    app.cancelling = false;
    showToast(error.message, 8000);
    renderActionAvailability();
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
  const hasRevision = hasCurrentRevision();
  const hasUnappliedChanges = hasUnappliedLayoutChanges();
  if (
    (!hasRevision && !hasUnappliedChanges) ||
    app.busy ||
    app.layout.previewing
  ) return;
  const confirmation = hasRevision
    ? "Return the figure and code to the default version? Uploaded files will be kept and this version can be restored with Undo."
    : "Discard the unapplied figure-element changes and return to the default figure?";
  if (
    !window.confirm(confirmation)
  ) {
    return;
  }
  if (hasUnappliedChanges) discardLayoutChanges();
  if (!hasRevision) {
    showToast("Unapplied changes discarded. The default figure is restored.");
    return;
  }
  setBusy(true, "Returning to default", "Saving the current revision in version history.");
  let reopenLayout = false;
  try {
    await api(`/api/sessions/${app.sessionId}/reset`, {
      method: "POST",
      body: JSON.stringify({ keep_uploads: true }),
    });
    if (app.layout.open) {
      closeLayoutEditorAfterWork();
      reopenLayout = true;
    }
    showToast("The default figure has been restored.");
  } catch (error) {
    showToast(error.message, 8000);
  } finally {
    setBusy(false);
    if (reopenLayout) await openLayoutEditor();
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
  const panel = selectedPanelRecord();
  setBusy(
    true,
    panel ? `Packaging ${panelScopeLabel(panel.id)}` : "Packaging data and code",
    panel
      ? "Collecting the selected panel image, active figure code, referenced inputs, panel conversation, and checksums."
      : "Collecting source data, uploads, derived data, code, the JPG, chat history, and checksums.",
  );
  try {
    const path = panel?.download_url || app.state.download_url;
    if (!path) throw new Error("The selected panel package is unavailable");
    const response = await fetch(path, { headers: authHeaders() });
    if (!response.ok) throw new Error("The data and code package could not be created");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = panel
      ? `${app.figureId}-panel-${panel.id}.zip`
      : `figure-studio-${app.figureId}-${app.sessionId}.zip`;
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

function layoutElements() {
  const elements = app.layout.data?.elements || [];
  const panelId = selectedPanelId();
  return panelId
    ? elements.filter((element) => element.panel_id === panelId)
    : elements;
}

function layoutElementById(elementId) {
  return (app.layout.data?.elements || []).find(
    (element) => element.id === elementId,
  ) || null;
}

function initialLayoutElementId() {
  const elements = layoutElements().filter((element) => !element.hidden);
  const preferred =
    elements.find(
      (element) => element.kind === "text" && element.id.endsWith(":y-label"),
    ) ||
    elements.find(
      (element) => element.kind === "text" && element.id.endsWith(":x-label"),
    ) ||
    elements.find((element) => element.kind === "text") ||
    elements.find((element) => element.kind === "axis") ||
    elements[0];
  return preferred?.id || "";
}

function layoutPendingRecord(element, create = false) {
  let record = app.layout.pending.get(element.id);
  if (!record && create) {
    record = {
      id: element.id,
      reset: false,
      touched: new Set(),
      offset_px: {
        x: Number(element.offset_px?.x || 0),
        y: Number(element.offset_px?.y || 0),
      },
      hidden: Boolean(element.hidden),
      font_size: element.override?.font_size ?? null,
      font_family: element.override?.font_family || "",
      font_weight: element.override?.font_weight || element.font_weight || "normal",
      font_style: element.override?.font_style || element.font_style || "normal",
      text: element.override?.text ?? element.text ?? element.label ?? "",
      color: element.override?.color || element.color || "",
    };
    app.layout.pending.set(element.id, record);
  }
  return record || null;
}

function layoutVisualState(element) {
  const pending = layoutPendingRecord(element);
  if (!pending) {
    return {
      offset_px: {
        x: Number(element.offset_px?.x || 0),
        y: Number(element.offset_px?.y || 0),
      },
      hidden: Boolean(element.hidden),
    };
  }
  if (pending.reset) {
    return { offset_px: { x: 0, y: 0 }, hidden: false };
  }
  return {
    offset_px: pending.offset_px,
    hidden: pending.hidden,
  };
}

function layoutFilteredElements() {
  return layoutElements();
}

function hasCommittedLayoutOverride(element) {
  const override = baseLayoutElementById(element?.id)?.override;
  return Boolean(
    override &&
    typeof override === "object" &&
    !Array.isArray(override) &&
    Object.keys(override).length
  );
}

function hasIncompleteLayoutDraft() {
  return app.layout.fontSizeDraftDirty || app.layout.textDraftDirty;
}

function hasUnappliedLayoutChanges() {
  return Boolean(app.layout.pending.size || hasIncompleteLayoutDraft());
}

function baseLayoutElementById(elementId) {
  return (app.layout.baseData?.elements || []).find(
    (element) => element.id === elementId,
  ) || null;
}

function layoutScopeBBox() {
  const [canvasWidth, canvasHeight] = app.layout.data?.canvas_px || [0, 0];
  const panel = selectedPanelRecord();
  const bbox = panel?.bbox_px;
  if (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every((value) => Number.isFinite(Number(value)))
  ) {
    const [x0, y0, x1, y1] = bbox.map(Number);
    if (x1 > x0 && y1 > y0) {
      return [
        Math.max(0, x0),
        Math.max(0, y0),
        Math.min(canvasWidth, x1),
        Math.min(canvasHeight, y1),
      ];
    }
  }
  return [0, 0, canvasWidth, canvasHeight];
}

function sizeLayoutCanvas() {
  if (!app.layout.open || !app.layout.data) return;
  const stage = $("#currentStage");
  const viewport = $("#layoutCanvasViewport");
  const canvas = $("#layoutCanvas");
  const [canvasWidth, canvasHeight] = app.layout.data.canvas_px;
  const [x0, y0, x1, y1] = layoutScopeBBox();
  const scopeWidth = x1 - x0;
  const scopeHeight = y1 - y0;
  const style = window.getComputedStyle(stage);
  const availableWidth = stage.clientWidth
    - Number.parseFloat(style.paddingLeft || "0")
    - Number.parseFloat(style.paddingRight || "0");
  const availableHeight = stage.clientHeight
    - Number.parseFloat(style.paddingTop || "0")
    - Number.parseFloat(style.paddingBottom || "0");
  if (!(availableWidth > 0 && availableHeight > 0 && scopeWidth > 0 && scopeHeight > 0)) {
    return;
  }
  let frameWidth = 0;
  let frameHeight = 0;
  const defaultImage = $("#defaultStage img");
  if (defaultImage?.complete && defaultImage.naturalWidth > 0 && defaultImage.naturalHeight > 0) {
    const imageBox = defaultImage.getBoundingClientRect();
    const imageScale = Math.min(
      imageBox.width / defaultImage.naturalWidth,
      imageBox.height / defaultImage.naturalHeight,
    );
    frameWidth = defaultImage.naturalWidth * imageScale;
    frameHeight = defaultImage.naturalHeight * imageScale;
  }
  if (!(frameWidth > 0 && frameHeight > 0)) {
    const fallbackScale = Math.min(
      availableWidth / scopeWidth,
      availableHeight / scopeHeight,
    );
    frameWidth = scopeWidth * fallbackScale;
    frameHeight = scopeHeight * fallbackScale;
  }
  const scaleX = frameWidth / scopeWidth;
  const scaleY = frameHeight / scopeHeight;
  viewport.style.width = `${frameWidth}px`;
  viewport.style.height = `${frameHeight}px`;
  canvas.style.width = `${canvasWidth * scaleX}px`;
  canvas.style.height = `${canvasHeight * scaleY}px`;
  canvas.style.left = `${-x0 * scaleX}px`;
  canvas.style.top = `${-y0 * scaleY}px`;
}

function positionLayoutBox(box, element) {
  const [canvasWidth, canvasHeight] = app.layout.data.canvas_px;
  const [x0, y0, x1, y1] = element.bbox_px;
  const hitPadding = element.kind === "mark" ? 10 : element.kind === "text" ? 3 : 0;
  const hitX0 = Math.max(0, x0 - hitPadding);
  const hitY0 = Math.max(0, y0 - hitPadding);
  const hitX1 = Math.min(canvasWidth, x1 + hitPadding);
  const hitY1 = Math.min(canvasHeight, y1 + hitPadding);
  const visual = layoutVisualState(element);
  const originalX = Number(element.offset_px?.x || 0);
  const originalY = Number(element.offset_px?.y || 0);
  const dx = visual.offset_px.x - originalX;
  const dy = visual.offset_px.y - originalY;
  box.style.left = `${((hitX0 + dx) / canvasWidth) * 100}%`;
  box.style.top = `${((hitY0 + dy) / canvasHeight) * 100}%`;
  box.style.width = `${(Math.max(8, hitX1 - hitX0) / canvasWidth) * 100}%`;
  box.style.height = `${(Math.max(8, hitY1 - hitY0) / canvasHeight) * 100}%`;
  box.classList.toggle("is-hidden", visual.hidden);
  box.classList.toggle("is-reset", Boolean(app.layout.pending.get(element.id)?.reset));
}

function createLayoutSvgShape(shape, className) {
  const kind = shape?.kind;
  let node = null;
  if (kind === "rect" && Array.isArray(shape.bbox_px)) {
    const [x0, y0, x1, y1] = shape.bbox_px.map(Number);
    node = document.createElementNS(SVG_NS, "rect");
    node.setAttribute("x", x0);
    node.setAttribute("y", y0);
    node.setAttribute("width", Math.max(0.5, x1 - x0));
    node.setAttribute("height", Math.max(0.5, y1 - y0));
    node.setAttribute("rx", "1.5");
  } else if (kind === "point" && Array.isArray(shape.center_px)) {
    node = document.createElementNS(SVG_NS, "circle");
    node.setAttribute("cx", Number(shape.center_px[0]));
    node.setAttribute("cy", Number(shape.center_px[1]));
    node.setAttribute("r", Math.max(5, Number(shape.radius_px || 6)));
  } else if (["polyline", "polygon"].includes(kind) && Array.isArray(shape.points_px)) {
    node = document.createElementNS(SVG_NS, kind);
    node.setAttribute(
      "points",
      shape.points_px.map((point) => `${Number(point[0])},${Number(point[1])}`).join(" "),
    );
  }
  if (!node) return null;
  node.setAttribute("class", `${className} ${kind}`);
  node.setAttribute("vector-effect", "non-scaling-stroke");
  return node;
}

function createLayoutMarkTarget(element) {
  const shapes = Array.isArray(element.selection_shapes)
    ? element.selection_shapes
    : [];
  if (!shapes.length) return null;
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", "layout-mark-target");
  group.setAttribute("tabindex", "0");
  group.setAttribute("role", "button");
  group.dataset.elementId = element.id;
  group.setAttribute("aria-label", `Select ${element.role}: ${element.label}`);
  group.classList.toggle("selected", element.id === app.layout.selectedId);
  group.classList.toggle("pending", app.layout.pending.has(element.id));
  group.classList.toggle("is-hidden", layoutVisualState(element).hidden);
  group.classList.toggle("is-reset", Boolean(app.layout.pending.get(element.id)?.reset));
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = `${element.role}: ${element.label}`;
  group.appendChild(title);
  shapes.forEach((shape) => {
    const hit = createLayoutSvgShape(shape, "layout-mark-hit");
    const outline = createLayoutSvgShape(shape, "layout-mark-outline");
    if (hit) group.appendChild(hit);
    if (outline) group.appendChild(outline);
  });
  group.addEventListener("pointerdown", startLayoutDrag);
  group.addEventListener("keydown", handleLayoutElementKeydown);
  return group;
}

function layoutMarkHitPriority(element) {
  const shapes = Array.isArray(element.selection_shapes)
    ? element.selection_shapes
    : [];
  const kinds = new Set(shapes.map((shape) => shape?.kind));
  const role = String(element.role || "").toLowerCase();
  if (kinds.has("point")) return 50;
  if (kinds.has("polyline") || role.includes("line") || role.includes("whisker")) {
    return 40;
  }
  if (role.includes("bar")) return 30;
  if (role.includes("area")) return 10;
  return 20;
}

function renderLayoutOverlays() {
  if (!app.layout.data) return;
  const layer = $("#layoutOverlayLayer");
  const elements = layoutFilteredElements();
  if (!elements.some((element) => element.id === app.layout.selectedId)) {
    app.layout.selectedId = initialLayoutElementId();
  }
  layer.replaceChildren();
  const [canvasWidth, canvasHeight] = app.layout.data.canvas_px;
  const markSvg = document.createElementNS(SVG_NS, "svg");
  markSvg.setAttribute("class", "layout-mark-svg");
  markSvg.setAttribute("viewBox", `0 0 ${canvasWidth} ${canvasHeight}`);
  markSvg.setAttribute("preserveAspectRatio", "none");
  markSvg.setAttribute("aria-label", "Selectable figure marks");
  layer.appendChild(markSvg);
  elements
    .filter((element) => element.kind === "mark")
    .sort((left, right) => layoutMarkHitPriority(left) - layoutMarkHitPriority(right))
    .forEach((element) => {
      const markTarget = createLayoutMarkTarget(element);
      if (markTarget) markSvg.appendChild(markTarget);
    });
  elements.forEach((element) => {
    if (element.kind === "mark") {
      if (Array.isArray(element.selection_shapes) && element.selection_shapes.length) return;
    }
    const box = document.createElement("button");
    box.type = "button";
    box.className = `layout-element-box ${element.kind}`;
    box.dataset.elementId = element.id;
    box.title = `${element.role}: ${element.label}`;
    box.setAttribute("aria-label", `Select ${element.role}: ${element.label}`);
    box.classList.toggle("selected", element.id === app.layout.selectedId);
    box.classList.toggle("pending", app.layout.pending.has(element.id));
    positionLayoutBox(box, element);
    box.addEventListener("pointerdown", startLayoutDrag);
    box.addEventListener("click", () => selectLayoutElement(element.id));
    box.addEventListener("keydown", handleLayoutElementKeydown);
    layer.appendChild(box);
  });
  $("#layoutElementCount").textContent = `${elements.length} element${elements.length === 1 ? "" : "s"}`;
  renderLayoutInspector();
}

function selectLayoutElement(elementId) {
  if (!layoutElementById(elementId)) return;
  app.layout.selectedId = elementId;
  renderLayoutOverlays();
  const selected = document.querySelector(
    `[data-element-id="${CSS.escape(elementId)}"]`,
  );
  selected?.focus({ preventScroll: true });
}

function isBoldFontWeight(value) {
  const normalized = String(value || "normal").toLowerCase();
  const numeric = Number(normalized);
  return Number.isFinite(numeric)
    ? numeric >= 600
    : ["bold", "semibold", "demibold", "heavy", "black"].includes(normalized);
}

function isItalicFontStyle(value) {
  return ["italic", "oblique"].includes(String(value || "normal").toLowerCase());
}

function setLayoutStyleButton(button, active) {
  button.disabled = false;
  button.setAttribute("aria-pressed", active ? "true" : "false");
  button.classList.toggle("active", active);
}

function renderLayoutInspector() {
  const element = layoutElementById(app.layout.selectedId);
  const preserveFontFocus = (
    element?.kind === "text" && document.activeElement === $("#layoutFontSize")
  );
  const preserveTextFocus = (
    element?.text_editable && document.activeElement === $("#layoutText")
  );
  const controls = [
    "#layoutText",
    "#layoutFontSize",
    "#layoutFontFamily",
    "#layoutBoldButton",
    "#layoutItalicButton",
    "#layoutColor",
    "#layoutVisibilityButton",
    "#layoutResetElementButton",
  ];
  controls.forEach((selector) => {
    const preserveFocusedInput = (
      (selector === "#layoutFontSize" && preserveFontFocus) ||
      (selector === "#layoutText" && preserveTextFocus)
    );
    if (!preserveFocusedInput) {
      $(selector).disabled = true;
    }
  });
  $("#layoutInspectorEmpty").classList.toggle("hidden", Boolean(element));
  $("#layoutInspectorControls").classList.toggle("hidden", !element);
  if (!element) {
    $("#layoutText").value = "";
    $("#layoutText").setCustomValidity("");
    $("#layoutFontSize").value = "";
    $("#layoutFontFamily").value = "";
    $("#layoutColor").value = "#176b50";
    $("#layoutColorValue").textContent = "#176B50";
    $("#layoutVisibilityButton").textContent = "Hide element";
    $("#layoutBoldButton").setAttribute("aria-pressed", "false");
    $("#layoutItalicButton").setAttribute("aria-pressed", "false");
    app.layout.fontSizeDraftValid = true;
    app.layout.fontSizeDraftDirty = false;
    app.layout.textDraftValid = true;
    app.layout.textDraftDirty = false;
    renderLayoutApplyAvailability();
    return;
  }
  const isMark = element.kind === "mark";
  const isText = element.kind === "text";
  $("#layoutTypographyControls").classList.toggle("hidden", !isText);
  $("#layoutTextField").classList.toggle("hidden", !element.text_editable);
  $("#layoutColorField").classList.toggle("hidden", !isMark);
  if (!element.text_editable) {
    $("#layoutText").value = "";
    $("#layoutText").setCustomValidity("");
    app.layout.textDraftValid = true;
    app.layout.textDraftDirty = false;
  }
  $("#layoutVisibilityButton").disabled = false;
  const pending = layoutPendingRecord(element);
  $("#layoutResetElementButton").disabled = !(
    (pending && !pending.reset) ||
    (hasCommittedLayoutOverride(element) && !pending?.reset) ||
    (isText && hasIncompleteLayoutDraft())
  );
  const visual = layoutVisualState(element);
  if (isMark) {
    const color = pending && !pending.reset && pending.touched.has("color")
      ? pending.color
      : element.color;
    const safeColor = /^#[0-9a-f]{6}$/i.test(color || "")
      ? color.toLowerCase()
      : "#176b50";
    $("#layoutColor").disabled = false;
    $("#layoutColor").value = safeColor;
    $("#layoutColorValue").textContent = safeColor.toUpperCase();
  } else if (isText) {
    if (element.text_editable) {
      $("#layoutText").disabled = false;
      const text = pending && !pending.reset && pending.touched.has("text")
        ? pending.text
        : element.text;
      const textInput = $("#layoutText");
      if (!preserveTextFocus) {
        textInput.value = String(text ?? element.label ?? "");
        textInput.setCustomValidity("");
        app.layout.textDraftValid = true;
        app.layout.textDraftDirty = false;
      }
    }
    $("#layoutFontSize").disabled = false;
    $("#layoutFontFamily").disabled = false;
    const size = pending && !pending.reset && pending.touched.has("font_size")
      ? pending.font_size
      : element.font_size;
    const fontSizeInput = $("#layoutFontSize");
    if (!preserveFontFocus) {
      fontSizeInput.value = Number.isFinite(Number(size)) ? String(size) : "";
      fontSizeInput.setCustomValidity("");
      app.layout.fontSizeDraftValid = true;
      app.layout.fontSizeDraftDirty = false;
    }
    const family = pending && !pending.reset && pending.touched.has("font_family")
      ? pending.font_family
      : element.font_family;
    const fontSelect = $("#layoutFontFamily");
    fontSelect.value = [...fontSelect.options].some((option) => option.value === family)
      ? family
      : "";
    const weight = pending && !pending.reset && pending.touched.has("font_weight")
      ? pending.font_weight
      : element.font_weight;
    const style = pending && !pending.reset && pending.touched.has("font_style")
      ? pending.font_style
      : element.font_style;
    setLayoutStyleButton($("#layoutBoldButton"), isBoldFontWeight(weight));
    setLayoutStyleButton($("#layoutItalicButton"), isItalicFontStyle(style));
  }
  $("#layoutVisibilityButton").textContent = visual.hidden
    ? "Show element"
    : "Hide element";
  renderLayoutApplyAvailability();
}

function renderLayoutApplyAvailability() {
  $("#layoutApplyButton").disabled = (
    app.busy ||
    app.layout.previewing ||
    Boolean(app.layout.previewTimer) ||
    app.layout.previewQueued ||
    !app.layout.fontSizeDraftValid ||
    !app.layout.textDraftValid ||
    !app.layout.pending.size
  );
  renderActionAvailability();
}

function setLayoutPreviewStatus(message, state = "") {
  const status = $("#layoutPreviewStatus");
  status.textContent = message;
  status.classList.toggle("rendering", state === "rendering");
  status.classList.toggle("error", state === "error");
}

function scheduleLayoutPreview(delay = 320) {
  if (!app.layout.open || !app.layout.pending.size) return;
  window.clearTimeout(app.layout.previewTimer);
  setLayoutPreviewStatus("Updating preview", "rendering");
  app.layout.previewTimer = window.setTimeout(() => {
    app.layout.previewTimer = 0;
    renderPendingLayoutPreview();
  }, delay);
  renderLayoutApplyAvailability();
}

function invalidateLayoutPreview() {
  window.clearTimeout(app.layout.previewTimer);
  app.layout.previewTimer = 0;
  app.layout.previewQueued = false;
  app.layout.previewGeneration += 1;
}

function installLayoutImage(blob) {
  if (!app.layout.open || !(blob instanceof Blob)) return;
  const objectUrl = URL.createObjectURL(blob);
  if (app.layout.objectUrl) URL.revokeObjectURL(app.layout.objectUrl);
  app.layout.objectUrl = objectUrl;
  const image = $("#layoutImage");
  image.onload = () => {
    sizeLayoutCanvas();
    renderLayoutOverlays();
  };
  image.src = objectUrl;
}

function restoreCommittedLayoutImage() {
  invalidateLayoutPreview();
  if (app.layout.baseData) app.layout.data = app.layout.baseData;
  if (app.layout.baseBlob) installLayoutImage(app.layout.baseBlob);
  setLayoutPreviewStatus("Preview ready");
  renderLayoutOverlays();
  renderLayoutApplyAvailability();
}

async function renderPendingLayoutPreview() {
  if (!app.layout.open || !app.layout.pending.size) return;
  if (app.layout.previewing) {
    app.layout.previewQueued = true;
    return;
  }
  const changes = serializedLayoutChanges().filter(
    (change) => change.reset || Object.keys(change).length > 1,
  );
  if (!changes.length) return;
  app.layout.previewing = true;
  app.layout.previewQueued = false;
  const generation = ++app.layout.previewGeneration;
  setLayoutPreviewStatus("Rendering preview", "rendering");
  renderLayoutApplyAvailability();
  try {
    const payload = await api(`/api/sessions/${app.sessionId}/layout-preview`, {
      method: "POST",
      body: JSON.stringify({
        changes,
        panel_id: selectedPanelId() || null,
      }),
    });
    const blob = await protectedBlob(
      authenticatedUrl(payload.preview_url, { v: generation }),
    );
    if (!app.layout.open || generation !== app.layout.previewGeneration) return;
    if (
      payload.layout?.figure_id === app.state?.figure_id &&
      Array.isArray(payload.layout?.elements)
    ) {
      app.layout.data = payload.layout;
    }
    installLayoutImage(blob);
    setLayoutPreviewStatus("Preview updated");
  } catch (error) {
    if (app.layout.open && generation === app.layout.previewGeneration) {
      setLayoutPreviewStatus("Preview unavailable", "error");
    }
  } finally {
    app.layout.previewing = false;
    renderLayoutApplyAvailability();
    if (app.layout.open && app.layout.previewQueued) {
      app.layout.previewQueued = false;
      scheduleLayoutPreview(80);
    }
  }
}

function updateSelectedLayoutValue(
  field,
  value,
  { refreshOverlays = true, previewDelay = 320 } = {},
) {
  const element = layoutElementById(app.layout.selectedId);
  if (!element) return;
  const pending = layoutPendingRecord(element, true);
  pending.reset = false;
  pending.touched.add(field);
  pending[field] = value;
  if (refreshOverlays) {
    renderLayoutOverlays();
  } else {
    const selected = document.querySelector(
      `.layout-element-box[data-element-id="${CSS.escape(element.id)}"]`,
    );
    selected?.classList.add("pending");
    $("#layoutResetElementButton").disabled = false;
    renderLayoutApplyAvailability();
  }
  scheduleLayoutPreview(previewDelay);
}

function handleLayoutFontSizeInput(event) {
  const input = event.currentTarget;
  const raw = String(input.value || "").trim();
  const value = Number(raw);
  const valid = raw !== "" && Number.isFinite(value) && value >= 5 && value <= 72;
  app.layout.fontSizeDraftValid = valid;
  app.layout.fontSizeDraftDirty = !valid;
  input.setCustomValidity(valid ? "" : "Enter a font size from 5 to 72");
  if (!valid) {
    invalidateLayoutPreview();
    setLayoutPreviewStatus("Enter a font size from 5 to 72", "error");
    $("#layoutResetElementButton").disabled = false;
    renderLayoutApplyAvailability();
    return;
  }
  updateSelectedLayoutValue(
    "font_size",
    value,
    { refreshOverlays: false, previewDelay: 750 },
  );
}

function flushLayoutFontSizePreview() {
  if (!app.layout.fontSizeDraftValid) return;
  const element = layoutElementById(app.layout.selectedId);
  const pending = element ? layoutPendingRecord(element) : null;
  if (pending?.touched.has("font_size")) scheduleLayoutPreview(40);
}

function handleLayoutTextInput(event) {
  const input = event.currentTarget;
  const value = String(input.value || "");
  const valid = value.trim() !== "" && value.length <= 240;
  app.layout.textDraftValid = valid;
  app.layout.textDraftDirty = !valid;
  input.setCustomValidity(valid ? "" : "Enter label text with 240 characters or fewer");
  if (!valid) {
    invalidateLayoutPreview();
    setLayoutPreviewStatus(
      "Enter label text with 240 characters or fewer",
      "error",
    );
    $("#layoutResetElementButton").disabled = false;
    renderLayoutApplyAvailability();
    return;
  }
  updateSelectedLayoutValue(
    "text",
    value,
    { refreshOverlays: false, previewDelay: 650 },
  );
}

function flushLayoutTextPreview() {
  if (!app.layout.textDraftValid) return;
  const element = layoutElementById(app.layout.selectedId);
  const pending = element ? layoutPendingRecord(element) : null;
  if (pending?.touched.has("text")) scheduleLayoutPreview(40);
}

function toggleSelectedFontWeight() {
  const active = $("#layoutBoldButton").getAttribute("aria-pressed") === "true";
  updateSelectedLayoutValue("font_weight", active ? "normal" : "bold", {
    previewDelay: 120,
  });
}

function toggleSelectedFontStyle() {
  const active = $("#layoutItalicButton").getAttribute("aria-pressed") === "true";
  updateSelectedLayoutValue("font_style", active ? "normal" : "italic", {
    previewDelay: 120,
  });
}

function toggleSelectedLayoutVisibility() {
  const element = layoutElementById(app.layout.selectedId);
  if (!element) return;
  const pending = layoutPendingRecord(element, true);
  pending.reset = false;
  pending.touched.add("hidden");
  pending.hidden = !layoutVisualState(element).hidden;
  renderLayoutOverlays();
  scheduleLayoutPreview();
}

function resetSelectedLayoutElement() {
  const element = layoutElementById(app.layout.selectedId);
  if (!element) return;
  const pending = layoutPendingRecord(element);
  const committed = hasCommittedLayoutOverride(element);
  if (!pending && !committed && !hasIncompleteLayoutDraft()) return;
  invalidateLayoutPreview();
  $("#layoutFontSize").blur();
  $("#layoutText").blur();
  app.layout.fontSizeDraftValid = true;
  app.layout.fontSizeDraftDirty = false;
  app.layout.textDraftValid = true;
  app.layout.textDraftDirty = false;
  if (!committed) {
    app.layout.pending.delete(element.id);
    renderLayoutOverlays();
    if (app.layout.pending.size) {
      scheduleLayoutPreview(80);
    } else {
      restoreCommittedLayoutImage();
    }
    return;
  }
  app.layout.pending.set(element.id, {
    id: element.id,
    reset: true,
    touched: new Set(),
    offset_px: { x: 0, y: 0 },
    hidden: false,
    font_size: null,
    font_family: "",
    font_weight: "normal",
    font_style: "normal",
    text: element.text || element.label || "",
    color: element.color || "",
  });
  renderLayoutOverlays();
  scheduleLayoutPreview(80);
}

function startLayoutDrag(event) {
  if (event.button !== 0 || app.busy) return;
  const elementId = event.currentTarget.dataset.elementId;
  const element = layoutElementById(elementId);
  if (!element) return;
  event.preventDefault();
  if (element.kind === "mark") {
    const overlappingIds = [];
    document.elementsFromPoint(event.clientX, event.clientY).forEach((target) => {
      const id = target.closest?.(".layout-mark-target")?.dataset?.elementId;
      if (id && !overlappingIds.includes(id)) overlappingIds.push(id);
    });
    if (!overlappingIds.includes(elementId)) overlappingIds.unshift(elementId);
    const signature = overlappingIds.join("|");
    const previous = app.layout.hitCycle;
    const now = performance.now();
    const repeated = Boolean(
      previous &&
      previous.signature === signature &&
      now - previous.time < 1800 &&
      Math.hypot(event.clientX - previous.x, event.clientY - previous.y) < 24
    );
    const index = repeated
      ? (previous.index + 1) % overlappingIds.length
      : 0;
    const selectedId = overlappingIds[index] || elementId;
    app.layout.hitCycle = {
      signature,
      index,
      x: event.clientX,
      y: event.clientY,
      time: now,
    };
    app.layout.selectedId = selectedId;
    document
      .querySelectorAll("[data-element-id].selected")
      .forEach((target) => target.classList.remove("selected"));
    document
      .querySelector(`[data-element-id="${CSS.escape(selectedId)}"]`)
      ?.classList.add("selected");
    renderLayoutInspector();
    return;
  }
  app.layout.hitCycle = null;
  app.layout.selectedId = elementId;
  const visual = layoutVisualState(element);
  app.layout.drag = {
    pointerId: event.pointerId,
    elementId,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: visual.offset_px.x,
    offsetY: visual.offset_px.y,
    moved: false,
  };
  event.currentTarget.setPointerCapture?.(event.pointerId);
  renderLayoutOverlays();
}

function moveLayoutDrag(event) {
  const drag = app.layout.drag;
  if (!drag || drag.pointerId !== event.pointerId || !app.layout.data) return;
  event.preventDefault();
  const element = layoutElementById(drag.elementId);
  if (!element) return;
  const rect = $("#layoutCanvas").getBoundingClientRect();
  const scaleX = rect.width / app.layout.data.canvas_px[0];
  const scaleY = rect.height / app.layout.data.canvas_px[1];
  if (!(scaleX > 0 && scaleY > 0)) return;
  const pointerDx = event.clientX - drag.startX;
  const pointerDy = event.clientY - drag.startY;
  if (!drag.moved && Math.hypot(pointerDx, pointerDy) < 1) return;
  const pending = layoutPendingRecord(element, true);
  pending.reset = false;
  pending.touched.add("offset_px");
  drag.moved = true;
  pending.offset_px = {
    x: Math.round((drag.offsetX + pointerDx / scaleX) * 100) / 100,
    y: Math.round((drag.offsetY + pointerDy / scaleY) * 100) / 100,
  };
  renderLayoutOverlays();
}

function endLayoutDrag(event) {
  if (!app.layout.drag || app.layout.drag.pointerId !== event.pointerId) return;
  const moved = app.layout.drag.moved;
  app.layout.drag = null;
  if (moved) scheduleLayoutPreview();
}

function handleLayoutElementKeydown(event) {
  const elementId = event.currentTarget.dataset.elementId;
  if (!elementId) return;
  if (["Enter", " "].includes(event.key)) {
    event.preventDefault();
    app.layout.hitCycle = null;
    selectLayoutElement(elementId);
    return;
  }
  if (["Delete", "Backspace"].includes(event.key)) {
    event.preventDefault();
    app.layout.selectedId = elementId;
    toggleSelectedLayoutVisibility();
    return;
  }
  const movement = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }[event.key];
  if (!movement) return;
  event.preventDefault();
  app.layout.selectedId = elementId;
  const element = layoutElementById(elementId);
  if (!element || element.kind === "mark") return;
  const pending = layoutPendingRecord(element, true);
  const step = event.shiftKey ? 10 : 1;
  pending.reset = false;
  pending.touched.add("offset_px");
  pending.offset_px.x += movement[0] * step;
  pending.offset_px.y += movement[1] * step;
  renderLayoutOverlays();
  scheduleLayoutPreview();
}

function populateLayoutFonts(fonts) {
  const select = $("#layoutFontFamily");
  const keep = document.createElement("option");
  keep.value = "";
  keep.textContent = "Keep current font";
  const options = (fonts || []).map((font) => {
    const option = document.createElement("option");
    option.value = font.id;
    option.textContent = font.label;
    return option;
  });
  select.replaceChildren(keep, ...options);
}

async function openLayoutEditor() {
  if (!app.state || app.busy) return;
  setBusy(
    true,
    "Opening the layout editor",
    "Loading selectable figure elements.",
    false,
  );
  try {
    const payload = await api(
      `/api/sessions/${app.sessionId}/layout/current`,
      {},
      false,
    );
    const blob = await protectedBlob(
      authenticatedUrl(payload.preview_url, { v: app.state.updated_at || Date.now() }),
    );
    if (app.layout.objectUrl) URL.revokeObjectURL(app.layout.objectUrl);
    app.layout.baseBlob = blob;
    app.layout.objectUrl = URL.createObjectURL(blob);
    app.layout.data = payload.layout;
    app.layout.baseData = payload.layout;
    app.layout.selectedId = "";
    app.layout.hitCycle = null;
    app.layout.pending = new Map();
    app.layout.drag = null;
    app.layout.open = true;
    app.layout.previewQueued = false;
    app.layout.fontSizeDraftValid = true;
    app.layout.fontSizeDraftDirty = false;
    app.layout.textDraftValid = true;
    app.layout.textDraftDirty = false;
    populateLayoutFonts(payload.layout.font_families);
    const canvas = $("#layoutCanvas");
    const viewport = $("#layoutCanvasViewport");
    canvas.style.aspectRatio = `${payload.layout.canvas_px[0]} / ${payload.layout.canvas_px[1]}`;
    app.previewGeneration += 1;
    const currentStage = $("#currentStage");
    currentStage.classList.remove("is-empty");
    currentStage.classList.add("layout-editing");
    currentStage.replaceChildren(viewport);
    $("#currentCard").classList.add("layout-edit-mode");
    $("#currentCard").classList.remove("no-revision");
    $("#layoutControlPanel").classList.add("editing");
    const image = $("#layoutImage");
    image.onload = () => {
      sizeLayoutCanvas();
      renderLayoutOverlays();
    };
    image.src = app.layout.objectUrl;
    setLayoutPreviewStatus("Preview ready");
    window.requestAnimationFrame(sizeLayoutCanvas);
    renderLayoutOverlays();
    renderActionAvailability();
  } catch (error) {
    showToast(error.message, 9000);
  } finally {
    setBusy(false);
  }
}

function closeLayoutEditor() {
  if (!app.layout.open || app.busy) return;
  const viewport = $("#layoutCanvasViewport");
  app.layout.open = false;
  window.clearTimeout(app.layout.previewTimer);
  app.layout.previewTimer = 0;
  app.layout.previewQueued = false;
  app.layout.previewGeneration += 1;
  app.layout.data = null;
  app.layout.baseData = null;
  app.layout.baseBlob = null;
  app.layout.selectedId = "";
  app.layout.hitCycle = null;
  app.layout.pending = new Map();
  app.layout.drag = null;
  app.layout.fontSizeDraftValid = true;
  app.layout.fontSizeDraftDirty = false;
  app.layout.textDraftValid = true;
  app.layout.textDraftDirty = false;
  if (app.layout.objectUrl) {
    URL.revokeObjectURL(app.layout.objectUrl);
    app.layout.objectUrl = "";
  }
  $("#layoutImage").removeAttribute("src");
  $("#layoutOverlayLayer").replaceChildren();
  $("#layoutCanvasHome").appendChild(viewport);
  $("#currentStage").classList.remove("layout-editing");
  $("#currentCard").classList.remove("layout-edit-mode");
  $("#layoutControlPanel").classList.remove("editing");
  setLayoutPreviewStatus("Loading editable elements");
  renderLayoutInspector();
  renderSelectedPreviews();
  renderActionAvailability();
}

function discardLayoutChanges() {
  if (
    !app.layout.open ||
    app.busy ||
    (!app.layout.pending.size && !hasIncompleteLayoutDraft())
  ) return;
  $("#layoutFontSize").blur();
  $("#layoutText").blur();
  app.layout.pending = new Map();
  app.layout.fontSizeDraftValid = true;
  app.layout.fontSizeDraftDirty = false;
  app.layout.textDraftValid = true;
  app.layout.textDraftDirty = false;
  $("#layoutFontSize").setCustomValidity("");
  $("#layoutText").setCustomValidity("");
  restoreCommittedLayoutImage();
}

function serializedLayoutChanges() {
  return [...app.layout.pending.values()].map((pending) => {
    if (pending.reset) return { id: pending.id, reset: true };
    const change = { id: pending.id };
    pending.touched.forEach((field) => {
      if (field === "offset_px") {
        change.offset_px = pending.offset_px;
      } else {
        change[field] = pending[field];
      }
    });
    return change;
  });
}

async function applyLayoutChanges() {
  const changes = serializedLayoutChanges().filter(
    (change) => change.reset || Object.keys(change).length > 1,
  );
  if (!changes.length || app.busy || app.layout.previewing) return;
  window.clearTimeout(app.layout.previewTimer);
  app.layout.previewTimer = 0;
  setBusy(
    true,
    "Applying layout changes",
    "Rendering the figure and checking the selected panel boundary.",
  );
  let reopen = false;
  try {
    const payload = await api(`/api/sessions/${app.sessionId}/layout`, {
      method: "POST",
      body: JSON.stringify({
        changes,
        panel_id: selectedPanelId() || null,
      }),
    });
    closeLayoutEditorAfterWork();
    reopen = true;
    showToast(
      payload.changed
        ? "Layout changes applied. Undo is available in Version."
        : "The selected layout already had those settings.",
      7000,
    );
  } catch (error) {
    showToast(error.message, 9000);
  } finally {
    setBusy(false);
    renderLayoutApplyAvailability();
    if (reopen) await openLayoutEditor();
  }
}

function closeLayoutEditorAfterWork() {
  const wasBusy = app.busy;
  app.busy = false;
  closeLayoutEditor();
  app.busy = wasBusy;
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

$("#sendButton").addEventListener("click", () => {
  if (app.activeJobId) {
    cancelActiveChat();
  } else {
    sendChat();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || event.repeat) return;
  if (
    app.layout.open &&
    (app.layout.pending.size || hasIncompleteLayoutDraft()) &&
    !app.busy
  ) {
    event.preventDefault();
    discardLayoutChanges();
    return;
  }
  if (app.activeJobId) {
    event.preventDefault();
    cancelActiveChat();
  }
});
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
$("#layoutApplyButton").addEventListener("click", applyLayoutChanges);
$("#layoutText").addEventListener("input", handleLayoutTextInput);
$("#layoutText").addEventListener("change", flushLayoutTextPreview);
$("#layoutText").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    flushLayoutTextPreview();
  }
});
$("#layoutFontSize").addEventListener("input", handleLayoutFontSizeInput);
$("#layoutFontSize").addEventListener("change", flushLayoutFontSizePreview);
$("#layoutFontSize").addEventListener("keydown", (event) => {
  if (event.key === "Enter") flushLayoutFontSizePreview();
});
$("#layoutFontFamily").addEventListener("change", (event) =>
  updateSelectedLayoutValue("font_family", event.target.value),
);
$("#layoutBoldButton").addEventListener("click", toggleSelectedFontWeight);
$("#layoutItalicButton").addEventListener("click", toggleSelectedFontStyle);
$("#layoutColor").addEventListener("input", (event) => {
  const value = String(event.target.value || "").toLowerCase();
  $("#layoutColorValue").textContent = value.toUpperCase();
  updateSelectedLayoutValue("color", value);
});
$("#layoutVisibilityButton").addEventListener(
  "click",
  toggleSelectedLayoutVisibility,
);
$("#layoutResetElementButton").addEventListener(
  "click",
  resetSelectedLayoutElement,
);
document.addEventListener("pointermove", moveLayoutDrag);
document.addEventListener("pointerup", endLayoutDrag);
document.addEventListener("pointercancel", endLayoutDrag);
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
  if (app.layout.objectUrl) URL.revokeObjectURL(app.layout.objectUrl);
});
window.addEventListener("resize", sizeLayoutCanvas);

renderNavigator();
initialize();
window.setInterval(refreshBilling, 5 * 60 * 1000);
