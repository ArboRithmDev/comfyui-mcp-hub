<p align="center">
  <h1 align="center">ComfyUI MCP Hub</h1>
  <p align="center">
    <strong>Give AI agents full control over your local ComfyUI.</strong>
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &nbsp;&bull;&nbsp;
    <a href="#supported-ai-clients">Supported Clients</a> &nbsp;&bull;&nbsp;
    <a href="#all-61-tools">All 61 Tools</a> &nbsp;&bull;&nbsp;
    <a href="#architecture">Architecture</a> &nbsp;&bull;&nbsp;
    <a href="#configuration">Configuration</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/version-0.2.0-blueviolet" alt="Version 0.2.0">
    <img src="https://img.shields.io/badge/tools-61-blue" alt="61 MCP Tools">
    <img src="https://img.shields.io/badge/python-3.10+-green" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/protocol-MCP-orange" alt="Model Context Protocol">
    <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT License">
  </p>
</p>

---

MCP Hub is a [Model Context Protocol](https://modelcontextprotocol.io/) server packaged as a ComfyUI custom node. It exposes **61 tools** that let any MCP-compatible AI assistant — Claude, Gemini, Codex, Cursor, and more — interact with your local ComfyUI instance: inspect workflows, generate images, manage models, install packages, and manipulate the canvas in real time.

**One install. Zero cloud dependency. Fully local.**

---

## Highlights

- **Canvas control** &mdash; AI agents can read the graph, add/remove/connect nodes, update parameters, capture screenshots, execute workflows, and arrange the layout (move, align, collapse, resize, fit view) directly on the canvas.
- **CivitAI & HuggingFace integration** &mdash; Search models, download with progress tracking, NSFW filtering, hash-based exact matching.
- **Smart resolver** &mdash; Submit any workflow: MCP Hub automatically detects missing nodes, missing models, and broken Python dependencies, then fixes them.
- **Multi-instance** &mdash; Register ComfyUI instances across your LAN and route any command to any machine.
- **Activity tracking** &mdash; Real-time log of every agent action, download progress bars, and toast notifications in the ComfyUI UI.
- **One-click client setup** &mdash; Auto-detects 10 AI clients and writes their MCP config for you.

---

## Quick Start

### 1. Install

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/ArboRithmDev/comfyui-mcp-hub.git
```

Restart ComfyUI. On first load, MCP Hub will automatically:
- Install its Python dependencies (`mcp`, `aiohttp`, `websockets`)
- Install [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) if not present
- Register a sidebar panel in ComfyUI Desktop

### 2. Configure your AI client

Open the **MCP Hub** panel in ComfyUI's sidebar &rarr; **AI Clients** tab &rarr; **Configure All**.

That's it. Your AI clients are ready to talk to ComfyUI.

<details>
<summary>Manual configuration</summary>

Add this to your MCP client's config file:

```json
{
  "mcpServers": {
    "comfyui-mcp-hub": {
      "command": "/path/to/ComfyUI/.venv/bin/python",
      "args": ["/path/to/ComfyUI/custom_nodes/comfyui-mcp-hub/mcp_server/main.py"]
    }
  }
}
```

For TOML-based clients (Codex, Mistral Vibe):

```toml
[mcp_servers.comfyui-mcp-hub]
command = "/path/to/ComfyUI/.venv/bin/python"
args = ["/path/to/ComfyUI/custom_nodes/comfyui-mcp-hub/mcp_server/main.py"]
```

</details>

### 3. Start using it

Ask your AI assistant:

```
"What models do I have installed?"
"Search CivitAI for a realistic SDXL LoRA"
"Look at my current workflow and describe it"
"Add a KSampler node connected to the checkpoint loader"
"Generate an image of a mountain landscape at sunset"
"Why did my last execution fail?"
```

---

## Supported AI Clients

MCP Hub auto-detects installed clients and writes the correct config format (JSON or TOML):

| Client | Format | Config path |
|--------|:------:|-------------|
| **Claude Code** (CLI) | JSON | `~/.claude.json` |
| **Claude Desktop** | JSON | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Gemini CLI** | JSON | `~/.gemini/settings.json` |
| **Codex CLI** (OpenAI) | TOML | `~/.codex/config.toml` |
| **Mistral Vibe** | TOML | `~/.vibe/config.toml` |
| **Cursor** | JSON | `~/.cursor/mcp.json` |
| **Windsurf** | JSON | `~/.codeium/windsurf/mcp_config.json` |
| **Continue.dev** | JSON | `~/.continue/config.json` |
| **VS Code** | JSON | Platform-specific `settings.json` |
| **Ollama** | &mdash; | Detected, no native MCP support (info shown) |

> Paths shown are for macOS. Linux and Windows equivalents are handled automatically.

---

## Control Panel

MCP Hub adds a sidebar panel to ComfyUI Desktop:

| Tab | Description |
|-----|-------------|
| **Server** | Start/stop the MCP server, toggle autostart with ComfyUI |
| **Activity** | Live feed of agent actions, download progress bars with speed indicators |
| **Tools** | Enable/disable tool categories per domain |
| **AI Clients** | Detected clients with install status, one-click configuration |
| **Instances** | Manage ComfyUI instances on your LAN |
| **Settings** | API tokens (CivitAI, HuggingFace), NSFW filter level, auto-resolve toggle |

---

## All 61 Tools

<details>
<summary><strong>Introspection</strong> &mdash; 5 tools</summary>

| Tool | Description |
|------|-------------|
| `list_nodes` | List all available nodes, filter by category or search term |
| `get_node_info` | Detailed inputs, outputs, and defaults for a specific node |
| `list_models` | List models by type &mdash; any directory, including custom ones like `ultralytics/bbox` |
| `list_model_types` | Discover all model directories with file counts |
| `get_system_stats` | GPU, VRAM, queue depth, uptime |

</details>

<details>
<summary><strong>Workflows</strong> &mdash; 7 tools</summary>

| Tool | Description |
|------|-------------|
| `list_workflows` | List saved workflow files |
| `get_workflow` | Get a workflow JSON by name |
| `save_workflow` | Save a workflow to disk |
| `execute_workflow` | Submit a workflow for execution, returns a job ID |
| `get_job_status` | Poll job status (queued, running, completed, error) |
| `get_job_result` | Retrieve output files (images, video, audio) |
| `cancel_job` | Cancel a queued or running job |

</details>

<details>
<summary><strong>Generation</strong> &mdash; 4 tools</summary>

| Tool | Description |
|------|-------------|
| `generate_image` | Text-to-image with prompt, model, size, steps, CFG, seed |
| `transform_image` | Image-to-image with source, prompt, denoise strength |
| `generate_video` | Video generation (delegates to workflow) |
| `generate_audio` | Audio generation (delegates to workflow) |

</details>

<details>
<summary><strong>Models</strong> &mdash; 5 tools</summary>

| Tool | Description |
|------|-------------|
| `download_model` | Download via ComfyUI-Manager |
| `delete_model` | Two-step safe deletion with size preview |
| `delete_model_confirm` | Execute confirmed deletion |
| `get_model_info` | Size, partial SHA-256, modification date |
| `unload_models` | Free VRAM/RAM |

</details>

<details>
<summary><strong>Packages</strong> &mdash; 7 tools</summary>

| Tool | Description |
|------|-------------|
| `search_packages` | Search the ComfyUI registry |
| `install_package` | Install a custom node |
| `update_package` | Update a custom node |
| `uninstall_package` | Remove a custom node |
| `list_installed` | Installed nodes with versions |
| `check_updates` | Available updates |
| `resolve_conflicts` | Dependency conflict detection and suggestions |

</details>

<details>
<summary><strong>Resolver & CivitAI</strong> &mdash; 5 tools</summary>

| Tool | Description |
|------|-------------|
| `resolve_workflow` | Full pipeline: missing nodes &rarr; install, missing models &rarr; find, broken deps &rarr; fix |
| `search_civitai` | Search CivitAI with type filter and NSFW control |
| `download_civitai` | Download with real-time progress tracking |
| `find_missing_models` | Hash lookup (exact) &rarr; name search (fuzzy) &rarr; interactive candidates |
| `fix_dependencies` | Three-tier: auto-fix &rarr; diagnose root cause &rarr; propose solutions |

</details>

<details>
<summary><strong>UI Bridge</strong> &mdash; 21 tools</summary>

| Tool | Description |
|------|-------------|
| `get_current_workflow` | Serialize the canvas graph |
| `get_selected_nodes` | Selected nodes with types, positions, widgets |
| `get_node_widgets` | All widget names and current values for a node |
| `capture_canvas` | Screenshot as base64 PNG &mdash; for multimodal agents |
| `load_workflow_to_canvas` | Replace the canvas with a workflow JSON |
| `clear_canvas` | Wipe the canvas |
| `add_node` | Place a node with position and widget values |
| `remove_node` | Delete a node |
| `connect_nodes` | Wire source output &rarr; target input |
| `update_node` | Change widgets, title, or color |
| `move_node` | Position a node at exact coordinates |
| `resize_node` | Set dimensions or auto-fit to content |
| `collapse_node` | Toggle collapsed/expanded state |
| `arrange_nodes` | Auto-layout all nodes |
| `align_nodes` | Align nodes horizontally or vertically with configurable spacing |
| `group_nodes` | Visual grouping |
| `fit_view` | Reset canvas zoom to show all nodes |
| `refresh_ui` | Refresh the interface (soft: redraw + reload dropdowns, hard: full page reload) |
| `execute_current` | Queue canvas workflow &mdash; returns `job_id` and validation errors |
| `get_execution_preview` | Node preview as base64 PNG |
| `notify_ui` | Toast notification in ComfyUI |

</details>

<details>
<summary><strong>Debugging</strong> &mdash; 2 tools</summary>

| Tool | Description |
|------|-------------|
| `get_last_error` | Last validation/execution error with node-level detail |
| `get_logs` | Recent server log lines, filterable by level (`error`, `warning`, `info`) |

</details>

<details>
<summary><strong>Instances</strong> &mdash; 5 tools</summary>

| Tool | Description |
|------|-------------|
| `list_instances` | All registered instances |
| `register_instance` | Add a LAN instance by name, host, port |
| `remove_instance` | Remove an instance |
| `health_check` | Connectivity, GPU name, free VRAM |
| `set_default_instance` | Route commands to a specific instance by default |

</details>

---

## Architecture

```
┌──────────────────────────────────────┐
│          ComfyUI Desktop             │
│                                      │
│   ┌──────────────────────────────┐   │
│   │  MCP Hub Panel (JS)         │   │
│   │  + Bridge (WebSocket + API) │   │
│   └─────────────┬────────────────┘   │
│                 │ REST / WS          │
│   ┌─────────────▼────────────────┐   │
│   │  Backend (Python)            │   │
│   │  Routes, UI Bridge,         │   │
│   │  Activity Log, Process Mgr  │   │
│   └─────────────┬────────────────┘   │
└─────────────────┼────────────────────┘
                  │ subprocess (stdio)
┌─────────────────▼────────────────────┐
│    MCP Server (separate process)     │
│    61 tools · 4 resources            │
│    Auto-detects Manager v1/v2 API    │
└────────┬────────────────┬────────────┘
         │                │
    ┌────▼─────┐    ┌─────▼────┐
    │ ComfyUI  │    │ ComfyUI  │
    │ (local)  │    │ (LAN)    │
    └──────────┘    └──────────┘
```

The MCP server runs as an isolated subprocess communicating over `stdio`. It never imports ComfyUI internals &mdash; all interaction goes through HTTP and WebSocket APIs. This keeps the server compatible with any ComfyUI version and allows it to target remote instances.

---

## Configuration

MCP Hub generates `mcp_server/hub_config.json` on first run (git-ignored &mdash; contains your tokens):

```json
{
  "comfyui_url": "http://127.0.0.1:8188",
  "autostart": true,
  "civitai_token": "",
  "huggingface_token": "",
  "nsfw_filter": "soft",
  "auto_resolve_on_execute": true,
  "enabled_tools": {
    "introspection": true,
    "workflows": true,
    "generation": true,
    "models": true,
    "packages": true,
    "instances": true
  },
  "instances": [
    { "name": "local", "host": "127.0.0.1", "port": 8188, "default": true }
  ]
}
```

The config **auto-syncs** with ComfyUI's actual address and port on every startup. No manual editing needed.

### NSFW Filtering

CivitAI results respect your preference:

| Level | Visible content |
|-------|----------------|
| `none` | SFW only |
| `soft` | SFW + Soft (hides Mature, X) |
| `mature` | SFW + Soft + Mature (hides X) |
| `x` | Everything |

Set via the **Settings** tab or directly in `hub_config.json`.

---

## ComfyUI Desktop Compatibility

MCP Hub is designed for ComfyUI Desktop and handles its differences from standalone ComfyUI:

| Feature | How it's handled |
|---------|-----------------|
| Manager V2 API | Auto-detects `/v2/` routes at first call, caches per instance |
| Port detection | Reads `PromptServer.instance.port` at startup, syncs config |
| Sidebar UI | Registers via `extensionManager.registerSidebarTab` with classic menu fallback |
| Shutdown | `atexit` + `SIGTERM` handler ensure the MCP process is cleaned up |
| Empty responses | HTTP client gracefully handles `200` with empty body |

MCP Hub also works with standalone ComfyUI using legacy Manager routes and the classic `.comfy-menu`.

---

## Requirements

| Requirement | Version |
|------------|---------|
| ComfyUI | Desktop or standalone |
| Python | 3.10+ |
| Git | For installation |

Python dependencies (`mcp`, `aiohttp`, `websockets`) are **installed automatically** on first startup.

---

## Changelog

### v0.2.0

- **CivitAI & HuggingFace integration** &mdash; search models, download with progress tracking, NSFW filtering, hash-based exact matching
- **Resolver pipeline** &mdash; `resolve_workflow` auto-detects and fixes missing nodes, models, and Python dependency conflicts (three-tier: auto &rarr; diagnose &rarr; propose)
- **Activity log** &mdash; real-time tracking of all agent actions with toast notifications and download progress bars in the UI
- **UI Bridge** &mdash; bidirectional canvas control: read/write graph, add/remove/connect nodes, capture screenshots, execute workflows, get previews
- **Layout tools** &mdash; `move_node`, `resize_node`, `collapse_node`, `align_nodes`, `fit_view`, `refresh_ui`
- **Debugging tools** &mdash; `get_last_error` (validation + execution errors with node detail), `get_logs` (grouped tracebacks, stderr capture)
- **`execute_current` fixed** &mdash; uses `app.queuePrompt()` for full extension hook support (cg-use-everywhere, rgthree GetNode/SetNode)
- **ComfyUI Desktop compatibility** &mdash; Manager V2 auto-detection (`/v2/` routes), empty response handling, config auto-sync
- **`list_models` extended** &mdash; supports any model directory (`ultralytics/bbox`, `text_encoders`, `LLM`, etc.) via filesystem fallback
- **`list_model_types`** &mdash; discover all model directories with file counts
- **Settings tab** &mdash; CivitAI/HuggingFace tokens, NSFW filter, auto-resolve toggle
- **Autostart** &mdash; MCP server starts with ComfyUI, clean shutdown on exit

### v0.1.0

- Initial release: 32 tools across 6 domains
- Introspection, workflows, generation, models, packages, instances
- Sidebar panel with Server, Tools, AI Clients, Instances tabs
- Auto-detection and configuration of 10 AI CLIs
- Auto-install dependencies on startup

---

## Contributing

Issues and pull requests are welcome at [github.com/ArboRithmDev/comfyui-mcp-hub](https://github.com/ArboRithmDev/comfyui-mcp-hub).

## License

[MIT](LICENSE)

---

<p align="center">
  <sub>Built with <a href="https://claude.com/claude-code">Claude Code</a></sub>
</p>
