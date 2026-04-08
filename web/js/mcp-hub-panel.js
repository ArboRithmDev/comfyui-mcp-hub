// Use the same pattern as comfyui-kjnodes (known working on ComfyUI Desktop)
const { app } = window.comfyAPI?.app ?? await import("../../../scripts/app.js");

const PANEL_ID = "mcp-hub-panel";
const API_BASE = "/mcp-hub";

const STYLES = `
  #${PANEL_ID} {
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    width: 100%;
    height: 100%;
    padding: 12px;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 13px;
    background: #1a1a2e;
    overflow: hidden;
  }
  #${PANEL_ID} *, #${PANEL_ID} *::before, #${PANEL_ID} *::after {
    box-sizing: border-box;
  }

  /* ── Popup overlay (only used in fallback mode) ── */
  #${PANEL_ID}.popup-mode {
    position: fixed;
    inset: 5vh 5vw;
    width: auto;
    height: auto;
    border-radius: 12px;
    border: 1px solid #16213e;
    z-index: 10000;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }

  /* ── Header ── */
  #${PANEL_ID} .hub-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-bottom: 8px;
    flex-shrink: 0;
  }
  #${PANEL_ID} .hub-header h2 {
    margin: 0;
    font-size: 16px;
    color: #fff;
    white-space: nowrap;
  }
  #${PANEL_ID} .hub-header .close-btn {
    margin-left: auto;
    background: none;
    border: none;
    color: #888;
    font-size: 20px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
  }
  #${PANEL_ID} .hub-header .close-btn:hover { color: #fff; }

  /* ── Status dot ── */
  #${PANEL_ID} .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }
  #${PANEL_ID} .status-dot.running  { background: #4caf50; }
  #${PANEL_ID} .status-dot.stopped  { background: #f44336; }
  #${PANEL_ID} .status-dot.unknown  { background: #ff9800; }

  /* ── Tabs ── */
  #${PANEL_ID} .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    border-bottom: 1px solid #2a2a4a;
    padding-bottom: 8px;
    margin-bottom: 0;
    flex-shrink: 0;
  }
  #${PANEL_ID} .tab {
    padding: 5px 10px;
    border-radius: 6px;
    cursor: pointer;
    background: transparent;
    color: #888;
    border: none;
    font-size: 12px;
    white-space: nowrap;
  }
  #${PANEL_ID} .tab.active {
    background: #2a2a4a;
    color: #fff;
  }

  /* ── Tab content (scrollable area) ── */
  #${PANEL_ID} .tab-content {
    display: none;
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 10px 0 4px;
    min-height: 0; /* required for flex overflow */
  }
  #${PANEL_ID} .tab-content.active { display: flex; flex-direction: column; }

  /* ── Buttons ── */
  #${PANEL_ID} button.primary,
  #${PANEL_ID} button.danger,
  #${PANEL_ID} button.success {
    color: #fff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    padding: 6px 12px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  #${PANEL_ID} button.primary  { background: #4a5cd6; }
  #${PANEL_ID} button.primary:hover  { background: #5a6ce6; }
  #${PANEL_ID} button.danger   { background: #d63a3a; }
  #${PANEL_ID} button.danger:hover   { background: #e64a4a; }
  #${PANEL_ID} button.success  { background: #2e7d32; }
  #${PANEL_ID} button.success:hover  { background: #388e3c; }
  #${PANEL_ID} button.sm { padding: 4px 8px; font-size: 11px; }

  /* ── Rows (tools, CLIs, instances) ── */
  #${PANEL_ID} .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px solid #2a2a4a;
    flex-wrap: wrap;
  }
  #${PANEL_ID} .row:last-child { border-bottom: none; }
  #${PANEL_ID} .row-label {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  #${PANEL_ID} .row-actions {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
    align-items: center;
  }

  /* ── Inputs ── */
  #${PANEL_ID} input[type="text"],
  #${PANEL_ID} input[type="number"] {
    background: #2a2a4a;
    border: 1px solid #3a3a5a;
    color: #e0e0e0;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 12px;
    min-width: 0;
    flex: 1 1 60px;
  }

  /* ── Toggle switch ── */
  #${PANEL_ID} .switch {
    position: relative;
    width: 36px; height: 18px;
    flex-shrink: 0;
  }
  #${PANEL_ID} .switch input { opacity: 0; width: 0; height: 0; }
  #${PANEL_ID} .slider {
    position: absolute;
    inset: 0;
    background: #444;
    border-radius: 18px;
    cursor: pointer;
    transition: .3s;
  }
  #${PANEL_ID} .slider::before {
    content: "";
    position: absolute;
    width: 14px; height: 14px;
    left: 2px; bottom: 2px;
    background: #fff;
    border-radius: 50%;
    transition: .3s;
  }
  #${PANEL_ID} .switch input:checked + .slider { background: #4a5cd6; }
  #${PANEL_ID} .switch input:checked + .slider::before { transform: translateX(18px); }

  /* ── Badges ── */
  #${PANEL_ID} .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
    white-space: nowrap;
    flex-shrink: 0;
  }
  #${PANEL_ID} .badge.installed       { background: #1b5e20; color: #a5d6a7; }
  #${PANEL_ID} .badge.not-installed   { background: #424242; color: #9e9e9e; }
  #${PANEL_ID} .badge.configured      { background: #1a237e; color: #9fa8da; }
  #${PANEL_ID} .badge.not-configured  { background: #4e342e; color: #bcaaa4; }
  #${PANEL_ID} .badge.format          { background: #37474f; color: #b0bec5; }

  /* ── CLI-specific ── */
  #${PANEL_ID} .cli-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    flex: 1 1 0;
  }
  #${PANEL_ID} .cli-badges { display: flex; gap: 4px; flex-wrap: wrap; }
  #${PANEL_ID} .cli-path {
    font-size: 10px;
    color: #666;
    font-family: monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  #${PANEL_ID} .cli-note {
    font-size: 10px;
    color: #ff9800;
    font-style: italic;
  }

  /* ── Top bar (configure-all, etc.) ── */
  #${PANEL_ID} .top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 6px;
    flex-shrink: 0;
  }
  #${PANEL_ID} .top-bar span { font-size: 12px; color: #888; }

  /* ── Add form (instances) ── */
  #${PANEL_ID} .add-form {
    display: flex;
    gap: 6px;
    margin-top: 10px;
    align-items: center;
    flex-wrap: wrap;
  }

  /* ── Settings inputs ── */
  #${PANEL_ID} input[type="password"] {
    background: #2a2a4a;
    border: 1px solid #3a3a5a;
    color: #e0e0e0;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 12px;
    width: 100%;
  }
  #${PANEL_ID} select {
    background: #2a2a4a;
    border: 1px solid #3a3a5a;
    color: #e0e0e0;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
  }
  #${PANEL_ID} .setting-group {
    padding: 8px 0;
    border-bottom: 1px solid #2a2a4a;
  }
  #${PANEL_ID} .setting-group:last-child { border-bottom: none; }
  #${PANEL_ID} .setting-label {
    font-size: 12px;
    color: #aaa;
    margin-bottom: 4px;
  }

  /* ── Server tab centered ── */
  #${PANEL_ID} .server-center {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    gap: 12px;
    text-align: center;
  }
  #${PANEL_ID} .server-center p { margin: 0; }
  #${PANEL_ID} .server-hint { font-size: 11px; color: #888; }

  /* ── Section label ── */
  #${PANEL_ID} .section-label {
    font-size: 11px;
    color: #666;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid #2a2a4a;
  }

  /* ── Activity log ── */
  #${PANEL_ID} .activity-entry {
    display: flex;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid #1e1e3a;
    font-size: 11px;
    align-items: flex-start;
  }
  #${PANEL_ID} .activity-entry:last-child { border-bottom: none; }
  #${PANEL_ID} .activity-time { color: #555; white-space: nowrap; flex-shrink: 0; font-family: monospace; }
  #${PANEL_ID} .activity-dot {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 4px;
  }
  #${PANEL_ID} .activity-dot.info    { background: #4a5cd6; }
  #${PANEL_ID} .activity-dot.success { background: #4caf50; }
  #${PANEL_ID} .activity-dot.warning { background: #ff9800; }
  #${PANEL_ID} .activity-dot.error   { background: #f44336; }
  #${PANEL_ID} .activity-dot.download { background: #2196f3; }
  #${PANEL_ID} .activity-detail { flex: 1; min-width: 0; word-break: break-word; }
  #${PANEL_ID} .activity-action { color: #aaa; font-weight: 600; }

  /* ── Download progress bar ── */
  #${PANEL_ID} .download-bar {
    padding: 6px 0;
    border-bottom: 1px solid #1e1e3a;
  }
  #${PANEL_ID} .download-info {
    display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;
  }
  #${PANEL_ID} .download-info .dl-name { color: #e0e0e0; }
  #${PANEL_ID} .download-info .dl-stats { color: #888; }
  #${PANEL_ID} .progress-track {
    height: 4px; background: #2a2a4a; border-radius: 2px; overflow: hidden;
  }
  #${PANEL_ID} .progress-fill {
    height: 100%; background: #4a5cd6; border-radius: 2px; transition: width 0.3s;
  }

  /* ── Dimmed rows ── */
  #${PANEL_ID} .row.dimmed { opacity: 0.45; }
`;

class MCPHubPanel {
  constructor() {
    this.panel = null;
    this.serverStatus = "unknown";
    this.config = {};
    this.instances = [];
    this.clis = [];
    this.inlineMode = false;
    this.inlineContainer = null;
    this.activityEntries = [];
    this.activeDownloads = {};
    this.versionInfo = null;
    this.availableVersions = [];
  }

  async init() {
    this.config = await this.fetchJSON(`${API_BASE}/config`);
    await this.refreshStatus();
    await this.refreshInstances();
    await this.refreshCLIs();
    this.createUI();
  }

  async initInline(container) {
    this.inlineMode = true;
    this.inlineContainer = container;
    this.config = await this.fetchJSON(`${API_BASE}/config`);
    await this.refreshStatus();
    await this.refreshInstances();
    await this.refreshCLIs();
    this.createUI();
  }

  async fetchJSON(url, options = {}) {
    try {
      const resp = await fetch(url, options);
      return await resp.json();
    } catch (e) {
      console.error(`MCP Hub: fetch error ${url}`, e);
      return {};
    }
  }

  async refreshStatus() {
    const data = await this.fetchJSON(`${API_BASE}/server/status`);
    this.serverStatus = data.status || "stopped";
  }

  async refreshInstances() {
    this.instances = await this.fetchJSON(`${API_BASE}/instances`);
    if (!Array.isArray(this.instances)) this.instances = [];
  }

  async refreshCLIs() {
    const data = await this.fetchJSON(`${API_BASE}/clis`);
    this.clis = Array.isArray(data) ? data : [];
  }

  createUI() {
    if (this.inlineMode) {
      this.inlineContainer.innerHTML = "";
      this.panel = document.createElement("div");
      this.panel.id = PANEL_ID;
      this.inlineContainer.style.cssText = "display:flex;flex-direction:column;height:100%;overflow:hidden;";
      this.inlineContainer.appendChild(this.panel);
    } else {
      const existing = document.getElementById(PANEL_ID);
      if (existing) existing.remove();
      this.panel = document.createElement("div");
      this.panel.id = PANEL_ID;
      this.panel.classList.add("popup-mode");
      document.body.appendChild(this.panel);
    }

    this.panel.innerHTML = `
      <style>${STYLES}</style>
      <div class="hub-header">
        <span class="status-dot ${this.serverStatus}"></span>
        <h2>MCP Hub</h2>
        ${this.inlineMode ? "" : `<button class="close-btn" id="mcp-hub-close">&times;</button>`}
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="server">Server</button>
        <button class="tab" data-tab="activity">Activity</button>
        <button class="tab" data-tab="tools">Tools</button>
        <button class="tab" data-tab="clis">AI Clients</button>
        <button class="tab" data-tab="instances">Instances</button>
        <button class="tab" data-tab="settings">Settings</button>
      </div>
      <div class="tab-content active" data-tab="server">
        ${this.renderServerTab()}
      </div>
      <div class="tab-content" data-tab="activity">
        <div id="mcp-hub-activity-list"></div>
      </div>
      <div class="tab-content" data-tab="tools">
        ${this.renderToolsTab()}
      </div>
      <div class="tab-content" data-tab="clis">
        ${this.renderCLIsTab()}
      </div>
      <div class="tab-content" data-tab="instances">
        ${this.renderInstancesTab()}
      </div>
      <div class="tab-content" data-tab="settings">
        ${this.renderSettingsTab()}
      </div>
    `;

    this.bindEvents();

    // Register for live activity updates
    if (window._mcpHubSetActivePanel) window._mcpHubSetActivePanel(this);
  }

  // ── Tab renderers ────────────────────────────────────────────────────

  renderServerTab() {
    const isRunning = this.serverStatus === "running";
    const autostart = this.config.autostart || false;
    return `
      <div class="server-center">
        <p>Server status: <strong>${this.serverStatus}</strong></p>
        ${isRunning
          ? `<button class="danger" id="mcp-hub-stop">Stop MCP Server</button>`
          : `<button class="primary" id="mcp-hub-start">Start MCP Server</button>`
        }
        <div class="row" style="width:100%;max-width:280px;">
          <span class="row-label">Start with ComfyUI</span>
          <label class="switch">
            <input type="checkbox" id="mcp-hub-autostart" ${autostart ? "checked" : ""}>
            <span class="slider"></span>
          </label>
        </div>
        <p class="server-hint">
          Transport: stdio &mdash; Use the <strong>AI Clients</strong> tab to auto-configure your AI tools.
        </p>
      </div>
    `;
  }

  renderToolsTab() {
    const tools = this.config.enabled_tools || {};
    const labels = {
      introspection: "Introspection",
      workflows: "Workflows",
      generation: "Generation",
      models: "Models",
      packages: "Packages",
      instances: "Instances",
    };
    return Object.entries(labels).map(([key, label]) => `
      <div class="row">
        <span class="row-label">${label}</span>
        <label class="switch">
          <input type="checkbox" data-tool="${key}" ${tools[key] !== false ? "checked" : ""}>
          <span class="slider"></span>
        </label>
      </div>
    `).join("");
  }

  renderCLIsTab() {
    const detected = this.clis.filter(c => c.installed || c.config_path);
    const notDetected = this.clis.filter(c => !c.installed && !c.config_path);
    const configurable = detected.filter(c => c.can_configure !== false);
    const configuredCount = this.clis.filter(c => c.configured).length;

    let html = `
      <div class="top-bar">
        <span>${configuredCount}/${configurable.length} configured</span>
        <button class="success sm" id="mcp-hub-configure-all">Configure All</button>
      </div>
    `;

    html += detected.map(cli => this.renderCLIRow(cli, false)).join("");

    if (notDetected.length > 0) {
      html += `<div class="section-label">Not detected</div>`;
      html += notDetected.map(cli => this.renderCLIRow(cli, true)).join("");
    }

    return html;
  }

  renderCLIRow(cli, dimmed) {
    const badges = [];
    if (cli.installed) {
      badges.push(`<span class="badge installed">Installed</span>`);
    } else if (!dimmed) {
      badges.push(`<span class="badge not-installed">Config only</span>`);
    }
    if (cli.can_configure === false) {
      badges.push(`<span class="badge not-configured">No MCP</span>`);
    } else if (cli.configured) {
      badges.push(`<span class="badge configured">Configured</span>`);
    } else if (!dimmed) {
      badges.push(`<span class="badge not-configured">Not configured</span>`);
    }
    if (cli.config_format && cli.config_format !== "json" && cli.config_format !== "none") {
      badges.push(`<span class="badge format">${cli.config_format.toUpperCase()}</span>`);
    }

    let actionBtn = "";
    if (!dimmed && cli.can_configure !== false) {
      actionBtn = cli.configured
        ? `<button class="danger sm" data-unconfigure-cli="${cli.name}">Remove</button>`
        : `<button class="primary sm" data-configure-cli="${cli.name}">Configure</button>`;
    }

    return `
      <div class="row${dimmed ? " dimmed" : ""}">
        <div class="cli-info">
          <div>
            <strong>${cli.display_name}</strong>
            <span class="cli-badges">${badges.join("")}</span>
          </div>
          ${cli.config_path && !dimmed ? `<span class="cli-path">${cli.config_path}</span>` : ""}
          ${cli.note ? `<span class="cli-note">${cli.note}</span>` : ""}
        </div>
        <div class="row-actions">${actionBtn}</div>
      </div>
    `;
  }

  renderInstancesTab() {
    const rows = this.instances.map(inst => `
      <div class="row">
        <div class="row-label">
          <strong>${inst.name}</strong>${inst.default ? " (default)" : ""}
          <br><span style="color:#888;font-size:11px">${inst.host}:${inst.port}</span>
        </div>
        <div class="row-actions">
          ${!inst.default ? `<button class="primary sm" data-set-default="${inst.name}">Default</button>` : ""}
          ${inst.name !== "local" ? `<button class="danger sm" data-remove-inst="${inst.name}">Remove</button>` : ""}
        </div>
      </div>
    `).join("");

    return `
      ${rows}
      <div class="add-form">
        <input type="text" id="inst-name" placeholder="Name">
        <input type="text" id="inst-host" placeholder="Host / IP">
        <input type="number" id="inst-port" placeholder="Port" value="8188">
        <button class="primary sm" id="mcp-hub-add-inst">Add</button>
      </div>
    `;
  }

  renderSettingsTab() {
    const civitaiToken = this.config.civitai_token || "";
    const hfToken = this.config.huggingface_token || "";
    const nsfwFilter = this.config.nsfw_filter || "soft";
    const autoResolve = this.config.auto_resolve_on_execute !== false;

    return `
      <div class="setting-group">
        <div class="setting-label">CivitAI API Token</div>
        <input type="password" id="setting-civitai-token" value="${civitaiToken}" placeholder="Optional — enables gated model downloads">
      </div>
      <div class="setting-group">
        <div class="setting-label">HuggingFace Token</div>
        <input type="password" id="setting-hf-token" value="${hfToken}" placeholder="Optional — for private/gated repos">
      </div>
      <div class="setting-group">
        <div class="row">
          <span class="row-label">NSFW Filter</span>
          <select id="setting-nsfw-filter">
            <option value="none" ${nsfwFilter === "none" ? "selected" : ""}>None (SFW only)</option>
            <option value="soft" ${nsfwFilter === "soft" ? "selected" : ""}>Soft (hide Mature & X)</option>
            <option value="mature" ${nsfwFilter === "mature" ? "selected" : ""}>Mature (hide X only)</option>
            <option value="x" ${nsfwFilter === "x" ? "selected" : ""}>All (no filter)</option>
          </select>
        </div>
      </div>
      <div class="setting-group">
        <div class="row">
          <span class="row-label">Auto-resolve on execute</span>
          <label class="switch">
            <input type="checkbox" id="setting-auto-resolve" ${autoResolve ? "checked" : ""}>
            <span class="slider"></span>
          </label>
        </div>
      </div>
      <div style="margin-top:12px;">
        <button class="primary" id="mcp-hub-save-settings">Save Settings</button>
      </div>

      <div class="setting-group" style="margin-top:20px;border-top:1px solid #333;padding-top:16px;">
        <div class="setting-label" style="font-size:13px;font-weight:600;">Version</div>
        <div id="mcp-hub-version-info" style="font-size:12px;color:#aaa;margin-bottom:8px;">
          ${this.versionInfo ? `Current: <strong>v${this.versionInfo.current}</strong>${this.versionInfo.update_available ? ` — <span style="color:#4ecdc4;">v${this.versionInfo.latest} available</span>` : " — up to date"}` : "Loading..."}
        </div>
        <div style="display:flex;gap:6px;align-items:center;">
          <select id="mcp-hub-version-select" style="flex:1;">
            ${this.availableVersions.length > 0
              ? this.availableVersions.map(v => `<option value="${v.tag}" ${v.is_current ? "selected" : ""}>${v.version}${v.prerelease ? " (pre)" : ""}${v.is_current ? " (current)" : ""} — ${v.name || v.tag}</option>`).join("")
              : `<option value="">Click "Check" to load versions</option>`}
          </select>
          <button class="sm" id="mcp-hub-version-check">Check</button>
          <button class="primary sm" id="mcp-hub-version-apply" ${this.availableVersions.length === 0 ? "disabled" : ""}>Apply</button>
        </div>
        <div id="mcp-hub-version-notes" style="font-size:11px;color:#888;margin-top:6px;max-height:80px;overflow-y:auto;white-space:pre-wrap;"></div>
        <div id="mcp-hub-version-status" style="font-size:11px;margin-top:4px;"></div>
      </div>
    `;
  }

  // ── Event binding ────────────────────────────────────────────────────

  bindEvents() {
    const closeBtn = this.panel.querySelector("#mcp-hub-close");
    if (closeBtn) closeBtn.onclick = () => this.panel.remove();

    this.panel.querySelectorAll(".tab").forEach(tab => {
      tab.onclick = () => {
        this.panel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        this.panel.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        this.panel.querySelector(`.tab-content[data-tab="${tab.dataset.tab}"]`).classList.add("active");
      };
    });

    const startBtn = this.panel.querySelector("#mcp-hub-start");
    const stopBtn = this.panel.querySelector("#mcp-hub-stop");
    if (startBtn) startBtn.onclick = () => this.startServer();
    if (stopBtn) stopBtn.onclick = () => this.stopServer();

    const autostartCb = this.panel.querySelector("#mcp-hub-autostart");
    if (autostartCb) autostartCb.onchange = () => this.toggleAutostart(autostartCb.checked);

    this.panel.querySelectorAll("[data-tool]").forEach(cb => {
      cb.onchange = () => this.toggleTool(cb.dataset.tool, cb.checked);
    });

    this.panel.querySelectorAll("[data-configure-cli]").forEach(btn => {
      btn.onclick = () => this.configureCLI(btn.dataset.configureCli);
    });
    this.panel.querySelectorAll("[data-unconfigure-cli]").forEach(btn => {
      btn.onclick = () => this.unconfigureCLI(btn.dataset.unconfigureCli);
    });
    const configAllBtn = this.panel.querySelector("#mcp-hub-configure-all");
    if (configAllBtn) configAllBtn.onclick = () => this.configureAllCLIs();

    this.panel.querySelectorAll("[data-set-default]").forEach(btn => {
      btn.onclick = () => this.setDefault(btn.dataset.setDefault);
    });
    this.panel.querySelectorAll("[data-remove-inst]").forEach(btn => {
      btn.onclick = () => this.removeInstance(btn.dataset.removeInst);
    });

    const addBtn = this.panel.querySelector("#mcp-hub-add-inst");
    if (addBtn) addBtn.onclick = () => this.addInstance();

    const saveSettingsBtn = this.panel.querySelector("#mcp-hub-save-settings");
    if (saveSettingsBtn) saveSettingsBtn.onclick = () => this.saveSettings();

    // Version management
    const versionCheckBtn = this.panel.querySelector("#mcp-hub-version-check");
    if (versionCheckBtn) versionCheckBtn.onclick = () => this.checkVersions();
    const versionApplyBtn = this.panel.querySelector("#mcp-hub-version-apply");
    if (versionApplyBtn) versionApplyBtn.onclick = () => this.applyVersion();
    const versionSelect = this.panel.querySelector("#mcp-hub-version-select");
    if (versionSelect) versionSelect.onchange = () => this.showVersionNotes();

    // Load version info at startup (non-blocking)
    this.loadVersionInfo();

    // Load activity log
    this.loadActivity();
  }

  // ── Activity log ────────────────────────────────────────────────────

  async loadActivity() {
    const data = await this.fetchJSON(`${API_BASE}/activity?limit=50`);
    this.activityEntries = Array.isArray(data) ? data : [];
    const downloads = await this.fetchJSON(`${API_BASE}/activity/downloads`);
    this.activeDownloads = {};
    if (Array.isArray(downloads)) {
      for (const dl of downloads) this.activeDownloads[dl.id] = dl;
    }
    this.renderActivityList();
  }

  renderActivityList() {
    const container = this.panel?.querySelector("#mcp-hub-activity-list");
    if (!container) return;

    let html = "";

    // Active downloads first
    const dls = Object.values(this.activeDownloads);
    if (dls.length > 0) {
      for (const dl of dls) {
        const pct = dl.progress || 0;
        const speed = dl.speed_mbps ? `${dl.speed_mbps} MB/s` : "";
        const size = dl.total_bytes ? `${Math.round(dl.downloaded_bytes / 1048576)}/${Math.round(dl.total_bytes / 1048576)} MB` : "";
        html += `
          <div class="download-bar" data-dl-id="${dl.id}">
            <div class="download-info">
              <span class="dl-name">${dl.filename}</span>
              <span class="dl-stats">${size} ${speed}</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" style="width:${pct}%"></div>
            </div>
          </div>
        `;
      }
    }

    // Activity entries
    if (this.activityEntries.length === 0 && dls.length === 0) {
      html += `<div style="text-align:center;color:#666;padding:20px;font-size:12px;">No activity yet</div>`;
    } else {
      for (const entry of this.activityEntries) {
        html += `
          <div class="activity-entry">
            <span class="activity-time">${entry.time_str || ""}</span>
            <span class="activity-dot ${entry.level || "info"}"></span>
            <div class="activity-detail">
              <span class="activity-action">${entry.action || ""}</span>
              ${entry.detail || ""}
            </div>
          </div>
        `;
      }
    }

    container.innerHTML = html;
  }

  onActivityEvent(entry) {
    this.activityEntries.unshift(entry);
    if (this.activityEntries.length > 50) this.activityEntries.pop();
    this.renderActivityList();
  }

  onDownloadProgress(dl) {
    if (dl.status === "completed" || dl.status === "failed") {
      delete this.activeDownloads[dl.id];
    } else {
      this.activeDownloads[dl.id] = dl;
    }
    this.renderActivityList();
  }

  // ── Version management ───────────────────────────────────────────────

  async loadVersionInfo() {
    try {
      this.versionInfo = await this.fetchJSON(`${API_BASE}/version/check`);
      const infoEl = this.panel?.querySelector("#mcp-hub-version-info");
      if (infoEl && this.versionInfo.current) {
        const current = `Current: <strong>v${this.versionInfo.current}</strong>`;
        if (this.versionInfo.update_available) {
          infoEl.innerHTML = `${current} — <span style="color:#4ecdc4;">v${this.versionInfo.latest} available</span>`;
        } else {
          infoEl.innerHTML = `${current} — up to date`;
        }
      }
    } catch (e) {
      console.error("MCP Hub: version check error", e);
    }
  }

  async checkVersions() {
    const btn = this.panel?.querySelector("#mcp-hub-version-check");
    if (btn) { btn.textContent = "..."; btn.disabled = true; }

    const data = await this.fetchJSON(`${API_BASE}/version/list`);
    this.availableVersions = data.versions || [];
    this.versionInfo = { current: data.current, current_tag: data.current_tag };

    const select = this.panel?.querySelector("#mcp-hub-version-select");
    if (select) {
      select.innerHTML = this.availableVersions.length > 0
        ? this.availableVersions.map(v =>
            `<option value="${v.tag}" ${v.is_current ? "selected" : ""}>${v.version}${v.prerelease ? " (pre)" : ""}${v.is_current ? " (current)" : ""} — ${v.name || v.tag}</option>`
          ).join("")
        : `<option value="">No releases found</option>`;
    }

    const applyBtn = this.panel?.querySelector("#mcp-hub-version-apply");
    if (applyBtn) applyBtn.disabled = this.availableVersions.length === 0;

    if (btn) { btn.textContent = "Check"; btn.disabled = false; }
    this.showVersionNotes();
  }

  showVersionNotes() {
    const select = this.panel?.querySelector("#mcp-hub-version-select");
    const notesEl = this.panel?.querySelector("#mcp-hub-version-notes");
    if (!select || !notesEl) return;

    const tag = select.value;
    const ver = this.availableVersions.find(v => v.tag === tag);
    notesEl.textContent = ver?.notes || "";
  }

  async applyVersion() {
    const select = this.panel?.querySelector("#mcp-hub-version-select");
    const statusEl = this.panel?.querySelector("#mcp-hub-version-status");
    const btn = this.panel?.querySelector("#mcp-hub-version-apply");
    if (!select?.value) return;

    const tag = select.value;
    const ver = this.availableVersions.find(v => v.tag === tag);
    if (ver?.is_current) {
      if (statusEl) { statusEl.innerHTML = `<span style="color:#888;">Already on this version.</span>`; }
      return;
    }

    if (btn) { btn.textContent = "Switching..."; btn.disabled = true; }
    if (statusEl) { statusEl.innerHTML = `<span style="color:#4ecdc4;">Switching to ${tag}...</span>`; }

    const result = await this.fetchJSON(`${API_BASE}/version/switch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });

    if (result.error) {
      if (statusEl) { statusEl.innerHTML = `<span style="color:#ff6b6b;">${result.error}</span>`; }
    } else {
      if (statusEl) { statusEl.innerHTML = `<span style="color:#4ecdc4;">${result.message}</span>`; }
      // Update the current markers
      this.availableVersions.forEach(v => { v.is_current = v.tag === tag; });
      this.checkVersions();
    }

    if (btn) { btn.textContent = "Apply"; btn.disabled = false; }
  }

  // ── Actions ──────────────────────────────────────────────────────────

  async startServer() {
    await this.fetchJSON(`${API_BASE}/server/start`, { method: "POST" });
    await this.refreshStatus();
    this.createUI();
  }

  async stopServer() {
    await this.fetchJSON(`${API_BASE}/server/stop`, { method: "POST" });
    await this.refreshStatus();
    this.createUI();
  }

  async saveSettings() {
    const civitaiToken = this.panel.querySelector("#setting-civitai-token")?.value || "";
    const hfToken = this.panel.querySelector("#setting-hf-token")?.value || "";
    const nsfwFilter = this.panel.querySelector("#setting-nsfw-filter")?.value || "soft";
    const autoResolve = this.panel.querySelector("#setting-auto-resolve")?.checked ?? true;

    this.config.civitai_token = civitaiToken;
    this.config.huggingface_token = hfToken;
    this.config.nsfw_filter = nsfwFilter;
    this.config.auto_resolve_on_execute = autoResolve;

    await this.fetchJSON(`${API_BASE}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(this.config),
    });

    const btn = this.panel.querySelector("#mcp-hub-save-settings");
    if (btn) { btn.textContent = "Saved!"; setTimeout(() => { btn.textContent = "Save Settings"; }, 1500); }
  }

  async toggleAutostart(enabled) {
    this.config.autostart = enabled;
    await this.fetchJSON(`${API_BASE}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(this.config),
    });
  }

  async toggleTool(tool, enabled) {
    this.config.enabled_tools = this.config.enabled_tools || {};
    this.config.enabled_tools[tool] = enabled;
    await this.fetchJSON(`${API_BASE}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(this.config),
    });
  }

  async configureCLI(name) {
    const btn = this.panel.querySelector(`[data-configure-cli="${name}"]`);
    if (btn) { btn.textContent = "..."; btn.disabled = true; }
    await this.fetchJSON(`${API_BASE}/clis/${name}/configure`, { method: "POST" });
    await this.refreshCLIs();
    this.createUI();
  }

  async unconfigureCLI(name) {
    const btn = this.panel.querySelector(`[data-unconfigure-cli="${name}"]`);
    if (btn) { btn.textContent = "..."; btn.disabled = true; }
    await this.fetchJSON(`${API_BASE}/clis/${name}/unconfigure`, { method: "POST" });
    await this.refreshCLIs();
    this.createUI();
  }

  async configureAllCLIs() {
    const btn = this.panel.querySelector("#mcp-hub-configure-all");
    if (btn) { btn.textContent = "..."; btn.disabled = true; }
    await this.fetchJSON(`${API_BASE}/clis/configure-all`, { method: "POST" });
    await this.refreshCLIs();
    this.createUI();
  }

  async setDefault(name) {
    await this.fetchJSON(`${API_BASE}/instances/${name}/default`, { method: "POST" });
    await this.refreshInstances();
    this.createUI();
  }

  async removeInstance(name) {
    await this.fetchJSON(`${API_BASE}/instances/${name}`, { method: "DELETE" });
    await this.refreshInstances();
    this.createUI();
  }

  async addInstance() {
    const name = this.panel.querySelector("#inst-name").value.trim();
    const host = this.panel.querySelector("#inst-host").value.trim();
    const port = parseInt(this.panel.querySelector("#inst-port").value) || 8188;
    if (!name || !host) return;
    await this.fetchJSON(`${API_BASE}/instances`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, host, port }),
    });
    await this.refreshInstances();
    this.createUI();
  }
}

// ── Icon style ────────────────────────────────────────────────────────
const iconStyle = document.createElement("style");
iconStyle.innerHTML = `.mcp-hub-icon:before { content: '\\2699'; font-size: 18px; }`;
document.body.append(iconStyle);

// ── Register as sidebar tab (ComfyUI Desktop) ────────────────────────
function registerSidebar() {
  if (app?.extensionManager?.registerSidebarTab) {
    app.extensionManager.registerSidebarTab({
      id: "mcp-hub",
      title: "MCP Hub",
      icon: "mcp-hub-icon",
      type: "custom",
      render: (container) => {
        const panel = new MCPHubPanel();
        panel.initInline(container);
      },
    });
    return true;
  }
  return false;
}

// ── Register as extension ─────────────────────────────────────────────
app.registerExtension({
  name: "comfyui.mcp-hub",
  async setup() {
    if (registerSidebar()) return;

    // Fallback: classic menu button
    const menu = document.querySelector(".comfy-menu");
    if (menu) {
      const btn = document.createElement("button");
      btn.textContent = "MCP Hub";
      btn.style.cssText = "font-size:13px;";
      btn.onclick = () => {
        const panel = new MCPHubPanel();
        panel.init();
      };
      menu.appendChild(btn);
    }
  },
});
