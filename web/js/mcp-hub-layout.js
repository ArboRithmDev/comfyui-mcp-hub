/**
 * MCP Hub Smart Layout Engine
 *
 * Rules-based + context-aware layout for ComfyUI workflows.
 * Organizes nodes by flow (left→right), assigns colors by category,
 * auto-detects logical groups, and creates visual annotations.
 */

const { app } = window.comfyAPI?.app ?? await import("../../../scripts/app.js");
let api;
try {
  api = (window.comfyAPI?.api ?? await import("../../../scripts/api.js")).api;
} catch (_) {
  api = (await import("/scripts/api.js")).api;
}

// ── Color palettes ──────────────────────────────────────────────────

const CATEGORY_COLORS = {
  // Loaders
  "CheckpointLoaderSimple": "#2b4a3f",
  "CheckpointLoader": "#2b4a3f",
  "LoraLoader": "#3a4a2b",
  "LoraLoaderModelOnly": "#3a4a2b",
  "VAELoader": "#2b3a4a",
  "CLIPLoader": "#2b3a4a",
  "CLIPVisionLoader": "#2b3a4a",
  "DualCLIPLoader": "#2b3a4a",
  "ControlNetLoader": "#4a3a2b",
  "UNETLoader": "#2b4a3f",
  "IPAdapterModelLoader": "#3a2b4a",
  "UpscaleModelLoader": "#4a2b3a",
  // Conditioning
  "CLIPTextEncode": "#4a4a2b",
  "ConditioningCombine": "#4a4a2b",
  "ConditioningSetArea": "#4a4a2b",
  // Sampling
  "KSampler": "#4a2b2b",
  "KSamplerAdvanced": "#4a2b2b",
  "SamplerCustom": "#4a2b2b",
  // Latent
  "EmptyLatentImage": "#3a3a4a",
  "VAEDecode": "#2b3a4a",
  "VAEEncode": "#2b3a4a",
  "LatentUpscale": "#3a3a4a",
  // Image
  "SaveImage": "#2b4a2b",
  "PreviewImage": "#2b4a2b",
  "LoadImage": "#2b4a3f",
  "ImageScale": "#3a4a3a",
  // Utility
  "Note": "#3a3a3a",
  "Reroute": "#3a3a3a",
  "PrimitiveNode": "#3a3a3a",
};

const CATEGORY_GROUP_COLORS = {
  loaders: "#1a3a2a55",
  conditioning: "#3a3a1a55",
  sampling: "#3a1a1a55",
  latent: "#1a1a3a55",
  output: "#1a3a1a55",
  controlnet: "#3a2a1a55",
  ipadapter: "#2a1a3a55",
  upscale: "#3a1a2a55",
};

// ── Node classification ─────────────────────────────────────────────

const NODE_CATEGORIES = {
  loaders: [
    "CheckpointLoaderSimple", "CheckpointLoader", "LoraLoader", "LoraLoaderModelOnly",
    "VAELoader", "CLIPLoader", "CLIPVisionLoader", "DualCLIPLoader", "TripleCLIPLoader",
    "UNETLoader", "ControlNetLoader", "IPAdapterModelLoader", "IPAdapterModelLoaderV2",
    "UpscaleModelLoader", "LoadImage", "ImageOnlyCheckpointLoader",
    "DiffusionModelLoaderKJ", "CheckpointLoaderKJ",
  ],
  conditioning: [
    "CLIPTextEncode", "ConditioningCombine", "ConditioningSetArea",
    "ConditioningConcat", "ConditioningAverage", "ConditioningZeroOut",
    "CLIPSetLastLayer", "unCLIPConditioning",
  ],
  sampling: [
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
  ],
  latent: [
    "EmptyLatentImage", "VAEDecode", "VAEEncode", "LatentUpscale",
    "LatentUpscaleBy", "LatentComposite", "LatentBlend",
  ],
  output: [
    "SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG",
    "VHS_VideoCombine",
  ],
  controlnet: [
    "ControlNetApply", "ControlNetApplyAdvanced",
    "ControlNetApplySD3", "ACN_AdvancedControlNetApply",
  ],
  ipadapter: [
    "IPAdapterApply", "IPAdapterApplyFaceID", "IPAdapterUnifiedLoader",
    "IPAdapterAdvanced", "IPAdapterBatch",
  ],
  upscale: [
    "ImageUpscaleWithModel", "UpscaleModelLoader", "LatentUpscale",
    "ImageScaleBy", "ImageScale",
  ],
};

function classifyNode(nodeType) {
  for (const [cat, types] of Object.entries(NODE_CATEGORIES)) {
    if (types.some(t => nodeType.includes(t) || t.includes(nodeType))) return cat;
  }
  // Heuristic fallback
  const t = nodeType.toLowerCase();
  if (t.includes("load")) return "loaders";
  if (t.includes("clip") || t.includes("condition")) return "conditioning";
  if (t.includes("sampl")) return "sampling";
  if (t.includes("latent") || t.includes("vae")) return "latent";
  if (t.includes("save") || t.includes("preview") || t.includes("output")) return "output";
  if (t.includes("control")) return "controlnet";
  if (t.includes("ipadapter")) return "ipadapter";
  if (t.includes("upscale")) return "upscale";
  return "other";
}

// ── Column order for left→right flow ────────────────────────────────

const COLUMN_ORDER = [
  "loaders", "conditioning", "ipadapter", "controlnet",
  "sampling", "latent", "upscale", "output", "other",
];

// ── Layout engine ───────────────────────────────────────────────────

function smartLayout(options = {}) {
  const nodes = app.graph._nodes;
  if (!nodes || nodes.length === 0) return { error: "No nodes on canvas" };

  const spacing = options.spacing || { x: 80, y: 40 };
  const startX = options.startX || 100;
  const startY = options.startY || 100;
  const applyColors = options.colorize !== false;
  const createGroups = options.group !== false;

  // 1. Classify nodes into columns
  const columns = {};
  for (const cat of COLUMN_ORDER) columns[cat] = [];

  for (const node of nodes) {
    if (node.type === "Reroute" || node.type === "Note") continue;
    const cat = classifyNode(node.type);
    const col = columns[cat] || columns["other"];
    col.push(node);
  }

  // 2. Position nodes column by column (left→right)
  let currentX = startX;
  const groupBounds = {};

  for (const cat of COLUMN_ORDER) {
    const col = columns[cat];
    if (col.length === 0) continue;

    // Sort nodes within column by connections (upstream first)
    col.sort((a, b) => (a.id || 0) - (b.id || 0));

    let currentY = startY;
    let maxWidth = 0;
    const colStartX = currentX;

    for (const node of col) {
      // Auto-compute size
      if (typeof node.computeSize === "function") {
        const sz = node.computeSize();
        node.size = [Math.max(sz[0], node.size?.[0] || 0), Math.max(sz[1], node.size?.[1] || 0)];
      }

      node.pos = [currentX, currentY];
      maxWidth = Math.max(maxWidth, node.size?.[0] || 200);
      currentY += (node.size?.[1] || 100) + spacing.y;

      // Apply category color
      if (applyColors && CATEGORY_COLORS[node.type]) {
        node.color = CATEGORY_COLORS[node.type];
      }
    }

    // Track group bounds
    if (col.length > 0) {
      groupBounds[cat] = {
        x: colStartX - 20,
        y: startY - 50,
        w: maxWidth + 40,
        h: currentY - startY + 20,
        count: col.length,
      };
    }

    currentX += maxWidth + spacing.x;
  }

  // 3. Create groups if requested
  const groupsCreated = [];
  if (createGroups) {
    // Remove existing auto-generated groups
    const existingGroups = app.graph._groups || [];
    for (let i = existingGroups.length - 1; i >= 0; i--) {
      if (existingGroups[i].title?.startsWith("[auto] ")) {
        app.graph._groups.splice(i, 1);
      }
    }

    const groupLabels = {
      loaders: "Loaders", conditioning: "Conditioning", sampling: "Sampling",
      latent: "Latent / VAE", output: "Output", controlnet: "ControlNet",
      ipadapter: "IP-Adapter", upscale: "Upscale", other: "Other",
    };

    for (const [cat, bounds] of Object.entries(groupBounds)) {
      if (bounds.count < 2) continue;
      const group = new LiteGraph.LGraphGroup();
      group.title = `[auto] ${groupLabels[cat] || cat}`;
      group.color = CATEGORY_GROUP_COLORS[cat] || "#33333355";
      group.pos = [bounds.x, bounds.y];
      group.size = [bounds.w, bounds.h];
      app.graph.add(group);
      groupsCreated.push(group.title);
    }
  }

  app.graph.setDirtyCanvas(true, true);

  return {
    status: "arranged",
    nodes_positioned: nodes.length,
    columns_used: Object.entries(columns).filter(([_, v]) => v.length > 0).map(([k]) => k),
    groups_created: groupsCreated,
  };
}

// ── Colorize ────────────────────────────────────────────────────────

function colorizeNodes(options = {}) {
  const nodes = app.graph._nodes;
  if (!nodes) return { error: "No nodes" };

  const scheme = options.scheme || "category";
  let colored = 0;

  if (scheme === "category") {
    for (const node of nodes) {
      const color = CATEGORY_COLORS[node.type];
      if (color) { node.color = color; colored++; }
    }
  } else if (scheme === "branch") {
    // Color by connected branch — use BFS from output nodes
    const branchColors = [
      "#4a2b2b", "#2b4a2b", "#2b2b4a", "#4a4a2b",
      "#4a2b4a", "#2b4a4a", "#3a3a2b", "#2b3a3a",
    ];
    const outputNodes = nodes.filter(n => classifyNode(n.type) === "output");
    let branchIdx = 0;

    for (const outNode of outputNodes) {
      const color = branchColors[branchIdx % branchColors.length];
      const visited = new Set();
      const queue = [outNode];

      while (queue.length > 0) {
        const n = queue.shift();
        if (visited.has(n.id)) continue;
        visited.add(n.id);
        n.color = color;
        colored++;

        // Walk upstream
        if (n.inputs) {
          for (const input of n.inputs) {
            if (input.link != null) {
              const link = app.graph.links[input.link];
              if (link) {
                const srcNode = app.graph.getNodeById(link.origin_id);
                if (srcNode && !visited.has(srcNode.id)) queue.push(srcNode);
              }
            }
          }
        }
      }
      branchIdx++;
    }
  } else if (scheme === "custom" && options.mapping) {
    for (const [nodeId, color] of Object.entries(options.mapping)) {
      const node = app.graph.getNodeById(parseInt(nodeId));
      if (node) { node.color = color; colored++; }
    }
  }

  app.graph.setDirtyCanvas(true, true);
  return { status: "colorized", scheme, nodes_colored: colored };
}

// ── Auto-group detection ────────────────────────────────────────────

function autoGroup(options = {}) {
  const nodes = app.graph._nodes;
  if (!nodes) return { error: "No nodes" };

  const mode = options.mode || "category"; // "category" or "branch"

  // Remove existing auto-groups
  const groups = app.graph._groups || [];
  for (let i = groups.length - 1; i >= 0; i--) {
    if (groups[i].title?.startsWith("[auto] ")) {
      app.graph._groups.splice(i, 1);
    }
  }

  const created = [];

  if (mode === "category") {
    // Group by node category
    const catNodes = {};
    for (const node of nodes) {
      const cat = classifyNode(node.type);
      if (!catNodes[cat]) catNodes[cat] = [];
      catNodes[cat].push(node);
    }

    const labels = {
      loaders: "Loaders", conditioning: "Conditioning", sampling: "Sampling",
      latent: "Latent / VAE", output: "Output", controlnet: "ControlNet",
      ipadapter: "IP-Adapter", upscale: "Upscale", other: "Other",
    };

    for (const [cat, catNodeList] of Object.entries(catNodes)) {
      if (catNodeList.length < 2) continue;
      const group = _createGroupAround(catNodeList, `[auto] ${labels[cat] || cat}`, CATEGORY_GROUP_COLORS[cat]);
      if (group) { app.graph.add(group); created.push(group.title); }
    }
  } else if (mode === "branch") {
    // Group by connected subgraph from output nodes
    const outputNodes = nodes.filter(n => classifyNode(n.type) === "output");
    let idx = 0;
    const globalVisited = new Set();

    for (const outNode of outputNodes) {
      const branchNodes = [];
      const queue = [outNode];
      const visited = new Set();

      while (queue.length > 0) {
        const n = queue.shift();
        if (visited.has(n.id) || globalVisited.has(n.id)) continue;
        visited.add(n.id);
        globalVisited.add(n.id);
        branchNodes.push(n);

        if (n.inputs) {
          for (const input of n.inputs) {
            if (input.link != null) {
              const link = app.graph.links[input.link];
              if (link) {
                const srcNode = app.graph.getNodeById(link.origin_id);
                if (srcNode) queue.push(srcNode);
              }
            }
          }
        }
      }

      if (branchNodes.length >= 2) {
        const colors = Object.values(CATEGORY_GROUP_COLORS);
        const title = `[auto] Branch ${idx + 1} (${outNode.type})`;
        const group = _createGroupAround(branchNodes, title, colors[idx % colors.length]);
        if (group) { app.graph.add(group); created.push(group.title); }
      }
      idx++;
    }
  }

  app.graph.setDirtyCanvas(true, true);
  return { status: "grouped", mode, groups_created: created };
}

function _createGroupAround(nodes, title, color) {
  if (nodes.length === 0) return null;
  const pad = 40;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.pos[0]);
    minY = Math.min(minY, n.pos[1]);
    maxX = Math.max(maxX, n.pos[0] + (n.size?.[0] || 200));
    maxY = Math.max(maxY, n.pos[1] + (n.size?.[1] || 100));
  }
  const group = new LiteGraph.LGraphGroup();
  group.title = title;
  group.color = color || "#33333355";
  group.pos = [minX - pad, minY - pad - 30];
  group.size = [maxX - minX + pad * 2, maxY - minY + pad * 2 + 30];
  return group;
}

// ── Add frame/annotation ────────────────────────────────────────────

function addFrame(data) {
  const group = new LiteGraph.LGraphGroup();
  group.title = data.title || "Frame";
  group.color = data.color || "#33555555";
  group.pos = [data.x || 0, data.y || 0];
  group.size = [data.width || 400, data.height || 300];
  if (data.font_size) group.font_size = data.font_size;
  app.graph.add(group);
  app.graph.setDirtyCanvas(true, true);
  return { status: "added", title: group.title };
}

// ── Register handlers ───────────────────────────────────────────────

// Expose to the bridge
window._mcpLayoutHandlers = {
  smart_layout: (data) => smartLayout(data),
  colorize_nodes: (data) => colorizeNodes(data),
  auto_group: (data) => autoGroup(data),
  add_frame: (data) => addFrame(data),
};

console.log("[MCP Hub] Layout engine loaded.");
