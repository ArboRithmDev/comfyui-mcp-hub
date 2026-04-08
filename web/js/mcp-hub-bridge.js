/**
 * MCP Hub Bridge — Frontend handler for canvas commands from AI agents.
 *
 * Listens for WebSocket events from the backend, executes LiteGraph operations
 * on the canvas, and posts results back.
 */

const { app } = window.comfyAPI?.app ?? await import("../../../scripts/app.js");
let api;
try {
  api = (window.comfyAPI?.api ?? await import("../../../scripts/api.js")).api;
} catch (_) {
  api = (await import("/scripts/api.js")).api;
}

const RESPONSE_URL = "/mcp-hub/ui/response";

// ── Command handlers ──────────────────────────────────────────────────

const handlers = {

  get_current_workflow() {
    const data = app.graph.serialize();
    return { workflow: data };
  },

  get_selected_nodes() {
    const selected = app.canvas.selected_nodes || {};
    const nodes = Object.values(selected).map(n => ({
      id: n.id,
      type: n.type,
      title: n.title,
      pos: n.pos,
      size: n.size,
      widgets: (n.widgets || []).map(w => ({
        name: w.name,
        type: w.type,
        value: w.value,
      })),
    }));
    return { nodes };
  },

  get_node_widgets(data) {
    const nodeId = parseInt(data.node_id);
    const node = app.graph.getNodeById(nodeId);
    if (!node) return { error: `Node ${nodeId} not found` };
    return {
      id: node.id,
      type: node.type,
      title: node.title,
      widgets: (node.widgets || []).map(w => ({
        name: w.name,
        type: w.type,
        value: w.value,
        options: w.options || {},
      })),
    };
  },

  capture_canvas() {
    try {
      const canvas = document.querySelector("canvas.graph-canvas") ||
                     document.querySelector("canvas");
      if (!canvas) return { error: "Canvas element not found" };
      const dataUrl = canvas.toDataURL("image/png");
      // Strip data:image/png;base64, prefix
      const base64 = dataUrl.split(",")[1];
      return { image_base64: base64, format: "png" };
    } catch (e) {
      return { error: `Canvas capture failed: ${e.message}` };
    }
  },

  load_workflow_to_canvas(data) {
    try {
      app.loadGraphData(data.workflow);
      app.graph.setDirtyCanvas(true, true);
      return { status: "loaded" };
    } catch (e) {
      return { error: `Failed to load workflow: ${e.message}` };
    }
  },

  clear_canvas() {
    app.graph.clear();
    app.graph.setDirtyCanvas(true, true);
    return { status: "cleared" };
  },

  add_node(data) {
    try {
      const node = LiteGraph.createNode(data.type);
      if (!node) return { error: `Unknown node type: ${data.type}` };
      node.pos = [data.x || 100, data.y || 100];
      app.graph.add(node);

      // Set widget values if provided
      if (data.widgets && node.widgets) {
        for (const [name, value] of Object.entries(data.widgets)) {
          const widget = node.widgets.find(w => w.name === name);
          if (widget) widget.value = value;
        }
      }

      if (data.title) node.title = data.title;

      app.graph.setDirtyCanvas(true, true);
      return { status: "added", node_id: node.id, type: data.type };
    } catch (e) {
      return { error: `Failed to add node: ${e.message}` };
    }
  },

  remove_node(data) {
    const nodeId = parseInt(data.node_id);
    const node = app.graph.getNodeById(nodeId);
    if (!node) return { error: `Node ${nodeId} not found` };
    app.graph.remove(node);
    app.graph.setDirtyCanvas(true, true);
    return { status: "removed", node_id: nodeId };
  },

  connect_nodes(data) {
    const srcNode = app.graph.getNodeById(parseInt(data.src_id));
    const dstNode = app.graph.getNodeById(parseInt(data.dst_id));
    if (!srcNode) return { error: `Source node ${data.src_id} not found` };
    if (!dstNode) return { error: `Target node ${data.dst_id} not found` };
    try {
      srcNode.connect(data.src_slot, dstNode, data.dst_slot);
      app.graph.setDirtyCanvas(true, true);
      return { status: "connected", src_id: data.src_id, dst_id: data.dst_id };
    } catch (e) {
      return { error: `Failed to connect: ${e.message}` };
    }
  },

  update_node(data) {
    const nodeId = parseInt(data.node_id);
    const node = app.graph.getNodeById(nodeId);
    if (!node) return { error: `Node ${nodeId} not found` };

    if (data.title) node.title = data.title;
    if (data.color) node.color = data.color;

    if (data.widgets && node.widgets) {
      for (const [name, value] of Object.entries(data.widgets)) {
        const widget = node.widgets.find(w => w.name === name);
        if (widget) widget.value = value;
      }
    }

    app.graph.setDirtyCanvas(true, true);
    return { status: "updated", node_id: nodeId };
  },

  arrange_nodes() {
    app.graph.arrange();
    app.graph.setDirtyCanvas(true, true);
    return { status: "arranged" };
  },

  move_node(data) {
    const node = app.graph.getNodeById(parseInt(data.node_id));
    if (!node) return { error: `Node ${data.node_id} not found` };
    node.pos = [data.x ?? node.pos[0], data.y ?? node.pos[1]];
    app.graph.setDirtyCanvas(true, true);
    return { status: "moved", node_id: node.id, pos: node.pos };
  },

  resize_node(data) {
    const node = app.graph.getNodeById(parseInt(data.node_id));
    if (!node) return { error: `Node ${data.node_id} not found` };
    if (data.width && data.height) {
      node.size = [data.width, data.height];
    } else if (typeof node.computeSize === "function") {
      node.size = node.computeSize();
    }
    app.graph.setDirtyCanvas(true, true);
    return { status: "resized", node_id: node.id, size: node.size };
  },

  collapse_node(data) {
    const node = app.graph.getNodeById(parseInt(data.node_id));
    if (!node) return { error: `Node ${data.node_id} not found` };
    node.flags = node.flags || {};
    node.flags.collapsed = data.collapsed !== false;
    app.graph.setDirtyCanvas(true, true);
    return { status: node.flags.collapsed ? "collapsed" : "expanded", node_id: node.id };
  },

  align_nodes(data) {
    const nodeIds = (data.node_ids || []).map(id => parseInt(id));
    const nodes = nodeIds.map(id => app.graph.getNodeById(id)).filter(Boolean);
    if (nodes.length < 2) return { error: "Need at least 2 nodes to align" };
    const axis = data.axis || "horizontal";
    const spacing = data.spacing ?? 30;

    if (axis === "horizontal") {
      // Align nodes in a horizontal row, same Y, evenly spaced on X
      const baseY = nodes[0].pos[1];
      let currentX = nodes[0].pos[0];
      for (const n of nodes) {
        n.pos = [currentX, baseY];
        currentX += (n.size?.[0] || 200) + spacing;
      }
    } else {
      // Align nodes in a vertical column, same X, evenly spaced on Y
      const baseX = nodes[0].pos[0];
      let currentY = nodes[0].pos[1];
      for (const n of nodes) {
        n.pos = [baseX, currentY];
        currentY += (n.size?.[1] || 100) + spacing;
      }
    }
    app.graph.setDirtyCanvas(true, true);
    return { status: "aligned", axis, count: nodes.length };
  },

  fit_view() {
    try {
      if (app.canvas && typeof app.canvas.ds?.reset === "function") {
        app.canvas.ds.reset();
      }
      if (typeof app.canvas.centerOnGraph === "function") {
        app.canvas.centerOnGraph();
      } else if (typeof app.canvas.setZoom === "function") {
        app.canvas.setZoom(1);
      }
      app.graph.setDirtyCanvas(true, true);
      return { status: "fitted" };
    } catch (e) {
      return { error: `Fit view failed: ${e.message}` };
    }
  },

  group_nodes(data) {
    try {
      const nodeIds = (data.node_ids || []).map(id => parseInt(id));
      const nodes = nodeIds.map(id => app.graph.getNodeById(id)).filter(Boolean);
      if (nodes.length === 0) return { error: "No valid nodes found" };

      // Calculate bounding box
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of nodes) {
        minX = Math.min(minX, n.pos[0]);
        minY = Math.min(minY, n.pos[1]);
        maxX = Math.max(maxX, n.pos[0] + (n.size?.[0] || 200));
        maxY = Math.max(maxY, n.pos[1] + (n.size?.[1] || 100));
      }

      const padding = 40;
      const group = new LiteGraph.LGraphGroup();
      group.title = data.title || "Group";
      group.color = data.color || "#335";
      group.pos = [minX - padding, minY - padding - 30];
      group.size = [maxX - minX + padding * 2, maxY - minY + padding * 2 + 30];
      app.graph.add(group);
      app.graph.setDirtyCanvas(true, true);
      return { status: "grouped", title: group.title, node_count: nodes.length };
    } catch (e) {
      return { error: `Failed to group: ${e.message}` };
    }
  },

  execute_current() {
    try {
      app.queuePrompt();
      return { status: "queued" };
    } catch (e) {
      return { error: `Failed to queue: ${e.message}` };
    }
  },

  get_execution_preview(data) {
    const nodeId = parseInt(data.node_id);
    const node = app.graph.getNodeById(nodeId);
    if (!node) return { error: `Node ${nodeId} not found` };

    // Try to get the preview image from the node
    if (node.imgs && node.imgs.length > 0) {
      try {
        const img = node.imgs[0];
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || img.width;
        canvas.height = img.naturalHeight || img.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        const dataUrl = canvas.toDataURL("image/png");
        return {
          node_id: nodeId,
          has_preview: true,
          image_base64: dataUrl.split(",")[1],
          format: "png",
          width: canvas.width,
          height: canvas.height,
        };
      } catch (e) {
        return { node_id: nodeId, has_preview: true, error: `Capture failed: ${e.message}` };
      }
    }

    return { node_id: nodeId, has_preview: false };
  },

  refresh_ui(data) {
    const mode = data.mode || "soft";
    try {
      if (mode === "hard") {
        // Full browser reload
        window.location.reload();
        return { status: "reloading" };
      }
      // Soft refresh: redraw canvas + refresh combo widgets (model lists, etc.)
      if (app.graph) {
        app.graph.setDirtyCanvas(true, true);
      }
      if (typeof app.refreshComboInNodes === "function") {
        app.refreshComboInNodes();
      }
      return { status: "refreshed", mode };
    } catch (e) {
      return { error: `Refresh failed: ${e.message}` };
    }
  },
};

// ── Post response back to backend ─────────────────────────────────────

async function postResponse(commandId, result) {
  try {
    await fetch(RESPONSE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command_id: commandId, result }),
    });
  } catch (e) {
    console.error("[MCP Hub Bridge] Failed to post response:", e);
  }
}

// ── Listen for commands from backend ──────────────────────────────────

api.addEventListener("mcp-hub:command", ({ detail }) => {
  const { command_id, command, data } = detail;
  const handler = handlers[command];

  if (!handler) {
    postResponse(command_id, { error: `Unknown command: ${command}` });
    return;
  }

  try {
    const result = handler(data || {});
    postResponse(command_id, result);
  } catch (e) {
    postResponse(command_id, { error: `Command failed: ${e.message}` });
  }
});

// ── Listen for notifications ──────────────────────────────────────────

api.addEventListener("mcp-hub:notify", ({ detail }) => {
  const { message, type } = detail;
  if (app?.extensionManager?.toast) {
    const severity = { info: "info", warning: "warn", error: "error" }[type] || "info";
    app.extensionManager.toast.add({ severity, summary: "MCP Hub", detail: message, life: 5000 });
  } else {
    console.log(`[MCP Hub] ${type}: ${message}`);
  }
});

// ── Listen for activity log events ────────────────────────────────────

// Keep a reference to the active panel for live updates
let _activePanel = null;

api.addEventListener("mcp-hub:activity", ({ detail }) => {
  if (_activePanel) _activePanel.onActivityEvent(detail);
  // Also show a toast for important actions
  if (detail.level === "success" || detail.level === "error" || detail.level === "warning") {
    if (app?.extensionManager?.toast) {
      const severity = { success: "success", warning: "warn", error: "error" }[detail.level] || "info";
      app.extensionManager.toast.add({
        severity,
        summary: detail.action || "MCP Hub",
        detail: detail.detail || "",
        life: 4000,
      });
    }
  }
});

api.addEventListener("mcp-hub:download-progress", ({ detail }) => {
  if (_activePanel) _activePanel.onDownloadProgress(detail);
});

// Export panel registration for mcp-hub-panel.js to use
window._mcpHubSetActivePanel = (panel) => { _activePanel = panel; };

console.log("[MCP Hub] Bridge loaded — listening for agent commands and activity.");
