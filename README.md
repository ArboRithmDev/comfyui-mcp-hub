# ComfyUI MCP Hub

**The bridge between AI agents and ComfyUI.**

MCP Hub turns your local ComfyUI into an AI-controllable creative studio. Any MCP-compatible AI assistant — Claude, Gemini, Codex, Cursor, and more — can inspect your workflows, generate images, manage models, install packages, and even manipulate the canvas in real time.

55 tools. One install. Zero cloud dependency.

---

## What can AI agents do with MCP Hub?

| Domain | Capabilities |
|--------|-------------|
| **Canvas Control** | Read the current workflow, add/remove/connect nodes, update widget values, capture screenshots, auto-arrange, group nodes |
| **Generation** | txt2img, img2img with any installed model — the AI picks the right checkpoint, writes the prompt, and queues it |
| **Workflow Execution** | Execute workflows, track job status, retrieve results, get validation errors and debug info |
| **Model Management** | List all model types (checkpoints, LoRAs, VAE, ControlNet, IPAdapter, CLIP Vision, ultralytics, and any custom directory), download from CivitAI or HuggingFace, delete, free VRAM |
| **Package Management** | Search the ComfyUI registry, install/update/uninstall custom nodes, detect and resolve dependency conflicts |
| **Introspection** | Discover all available nodes with their inputs/outputs, system stats (GPU, VRAM, queue), model catalogs |
| **Multi-Instance** | Register ComfyUI instances on your LAN, health-check them, route any command to any instance |
| **Debugging** | Get last execution error with node-level detail, read server logs filtered by level, validation error reporting |

## Quick Start

### 1. Install

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/ArboRithmDev/comfyui-mcp-hub.git
```

Restart ComfyUI. MCP Hub will:
- Auto-install its Python dependencies (`mcp`, `aiohttp`, `websockets`)
- Auto-install ComfyUI-Manager if not present (required dependency)
- Register a sidebar panel in ComfyUI Desktop

### 2. Configure your AI client

Open the **MCP Hub** panel in ComfyUI's sidebar, go to the **AI Clients** tab, and click **Configure All**. Done.

MCP Hub auto-detects and configures:

| Client | Config Format | Config Location |
|--------|:------------:|-----------------|
| Claude Code (CLI) | JSON | `~/.claude.json` |
| Claude Desktop | JSON | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Gemini CLI | JSON | `~/.gemini/settings.json` |
| Codex CLI (OpenAI) | TOML | `~/.codex/config.toml` |
| Mistral Vibe | TOML | `~/.vibe/config.toml` |
| Cursor | JSON | `~/.cursor/mcp.json` |
| Windsurf | JSON | `~/.codeium/windsurf/mcp_config.json` |
| Continue.dev | JSON | `~/.continue/config.json` |
| VS Code | JSON | Platform-specific `settings.json` |
| Ollama | — | Detected but no native MCP (info only) |

Or configure manually — add this to your MCP client config:

```json
{
  "mcpServers": {
    "comfyui-mcp-hub": {
      "command": "/path/to/ComfyUI/.venv/bin/python",
      "args": ["/path/to/ComfyUI/custom_nodes/comfyui-mcp-hub/mcp_server/main.py"],
      "env": {}
    }
  }
}
```

### 3. Talk to ComfyUI

Ask your AI assistant things like:

> "What models do I have installed?"

> "Search CivitAI for a realistic SDXL LoRA"

> "Look at my current workflow and tell me what it does"

> "Add a KSampler node connected to the checkpoint loader"

> "Generate an image of a mountain landscape at sunset"

> "Why did my last execution fail?"

## Control Panel

MCP Hub adds a sidebar panel to ComfyUI Desktop with 6 tabs:

| Tab | Purpose |
|-----|---------|
| **Server** | Start/stop the MCP server, toggle autostart with ComfyUI |
| **Activity** | Real-time log of all agent actions, download progress bars with speed |
| **Tools** | Enable/disable tool categories (introspection, workflows, generation, etc.) |
| **AI Clients** | Detect installed AI CLIs, one-click MCP configuration |
| **Instances** | Manage ComfyUI instances on your LAN (add, remove, health-check, set default) |
| **Settings** | CivitAI/HuggingFace API tokens, NSFW filter level, auto-resolve toggle |

## All 55 MCP Tools

<details>
<summary><strong>Introspection</strong> (5 tools)</summary>

| Tool | Description |
|------|-------------|
| `list_nodes` | List all available nodes, filterable by category or search term |
| `get_node_info` | Detailed info for a specific node (inputs, outputs, defaults) |
| `list_models` | List models by type — supports all directories including custom ones |
| `list_model_types` | Discover all model directories with file counts |
| `get_system_stats` | GPU info, VRAM usage, queue status |

</details>

<details>
<summary><strong>Workflows</strong> (6 tools)</summary>

| Tool | Description |
|------|-------------|
| `list_workflows` | List saved workflow files |
| `get_workflow` | Get workflow JSON by name |
| `save_workflow` | Save a workflow JSON to disk |
| `execute_workflow` | Execute a workflow, returns job ID |
| `get_job_status` | Check job status (running, completed, error) |
| `get_job_result` | Retrieve output files (images, videos, audio) |
| `cancel_job` | Cancel a running or queued job |

</details>

<details>
<summary><strong>Generation</strong> (4 tools)</summary>

| Tool | Description |
|------|-------------|
| `generate_image` | txt2img with prompt, model, size, steps, CFG, seed |
| `transform_image` | img2img with source image, prompt, denoise strength |
| `generate_video` | Video generation (delegates to workflow execution) |
| `generate_audio` | Audio generation (delegates to workflow execution) |

</details>

<details>
<summary><strong>Models</strong> (5 tools)</summary>

| Tool | Description |
|------|-------------|
| `download_model` | Download via ComfyUI-Manager |
| `delete_model` | Delete with safety confirmation (two-step) |
| `delete_model_confirm` | Confirm and execute deletion |
| `get_model_info` | File metadata: size, hash, modification date |
| `unload_models` | Free VRAM/RAM by unloading all models |

</details>

<details>
<summary><strong>Packages</strong> (7 tools)</summary>

| Tool | Description |
|------|-------------|
| `search_packages` | Search the ComfyUI custom node registry |
| `install_package` | Install a custom node |
| `update_package` | Update a custom node |
| `uninstall_package` | Uninstall a custom node |
| `list_installed` | List installed nodes with versions |
| `check_updates` | Check for available updates |
| `resolve_conflicts` | Detect and suggest dependency conflict resolutions |

</details>

<details>
<summary><strong>Resolver & CivitAI</strong> (5 tools)</summary>

| Tool | Description |
|------|-------------|
| `resolve_workflow` | Full pipeline: detect and resolve missing nodes, models, and dependencies |
| `search_civitai` | Search CivitAI with NSFW filtering |
| `download_civitai` | Download a model from CivitAI with progress tracking |
| `find_missing_models` | Analyze workflow for missing models, find candidates by hash or name |
| `fix_dependencies` | Three-tier resolution: auto-fix → diagnose → propose |

</details>

<details>
<summary><strong>UI Bridge</strong> (15 tools)</summary>

| Tool | Description |
|------|-------------|
| `get_current_workflow` | Read the workflow currently on the canvas |
| `get_selected_nodes` | Get selected nodes with properties |
| `get_node_widgets` | Read all widget values for a node |
| `capture_canvas` | Screenshot the canvas as base64 PNG |
| `load_workflow_to_canvas` | Load a workflow JSON into the canvas |
| `clear_canvas` | Clear the entire canvas |
| `add_node` | Add a node at position with optional widget values |
| `remove_node` | Remove a node by ID |
| `connect_nodes` | Connect two nodes (source slot → target slot) |
| `update_node` | Update widget values, title, or color |
| `arrange_nodes` | Auto-arrange all nodes |
| `group_nodes` | Create a visual group around nodes |
| `execute_current` | Execute the canvas workflow, returns job ID and validation errors |
| `get_execution_preview` | Get preview image from a node |
| `notify_ui` | Show toast notification in ComfyUI |

</details>

<details>
<summary><strong>Debugging</strong> (2 tools)</summary>

| Tool | Description |
|------|-------------|
| `get_last_error` | Get the last validation or execution error with node-level detail |
| `get_logs` | Read recent ComfyUI server logs, filterable by level |

</details>

<details>
<summary><strong>Instances</strong> (4 tools)</summary>

| Tool | Description |
|------|-------------|
| `list_instances` | List registered ComfyUI instances |
| `register_instance` | Add a LAN instance (name, host, port) |
| `remove_instance` | Remove an instance |
| `health_check` | Check connectivity and GPU info |
| `set_default_instance` | Set the default target instance |

</details>

## Architecture

```
┌─────────────────────────────────────┐
│         ComfyUI Desktop             │
│  ┌───────────────────────────────┐  │
│  │   MCP Hub Panel (JS)          │  │
│  │   + Bridge (WebSocket ↔ API)  │  │
│  └──────────┬────────────────────┘  │
│             │ REST + WebSocket      │
│  ┌──────────▼────────────────────┐  │
│  │   Backend (Python)            │  │
│  │   Routes, UI Bridge,         │  │
│  │   Activity Log, Process Mgr  │  │
│  └──────────┬────────────────────┘  │
└─────────────┼───────────────────────┘
              │ subprocess (stdio)
┌─────────────▼───────────────────────┐
│   MCP Server (separate process)     │
│   55 tools, 4 resources             │
│   Communicates with ComfyUI via     │
│   HTTP/WS (auto-detects v1/v2 API)  │
└──────┬──────────────┬───────────────┘
       │ HTTP/WS      │ HTTP/WS
┌──────▼──────┐ ┌─────▼───────┐
│ ComfyUI     │ │ ComfyUI     │
│ (local)     │ │ (LAN)       │
└─────────────┘ └─────────────┘
```

## Configuration

MCP Hub stores its config in `mcp_server/hub_config.json` (auto-generated, git-ignored):

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
    {"name": "local", "host": "127.0.0.1", "port": 8188, "default": true}
  ]
}
```

The config auto-syncs with ComfyUI's actual port on every startup.

### NSFW Filtering

CivitAI search results respect your filter preference:

| Setting | What's shown |
|---------|-------------|
| `none` | SFW content only |
| `soft` | Hide Mature and X-rated |
| `mature` | Hide X-rated only |
| `x` | No filtering |

## ComfyUI Desktop Compatibility

MCP Hub is built for ComfyUI Desktop and handles its specifics:

- **Manager V2 API** — auto-detects `/v2/` routes vs legacy routes
- **Port detection** — syncs with whatever port ComfyUI starts on
- **Sidebar integration** — registers via `extensionManager.registerSidebarTab`
- **Clean shutdown** — stops MCP server on ComfyUI exit (atexit + SIGTERM)

Also works with standalone ComfyUI (legacy Manager routes, classic menu fallback).

## Requirements

- ComfyUI (Desktop or standalone)
- Python 3.10+
- Git (for installation)

Dependencies are auto-installed: `mcp`, `aiohttp`, `websockets`

## License

MIT

---

Built with Claude Code.
