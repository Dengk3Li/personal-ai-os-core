const assert = require("node:assert/strict");
const test = require("node:test");

const workbench = require("../workbench/app.js");

test("the workspace has three stable entrances over one shared state", () => {
  const view = workbench.workspaceView(workbench.createDemoState());

  assert.deepEqual(view.boards.map((board) => board.id), ["global", "work", "decision"]);
  assert.equal(view.activeBoard, "work");
  assert.equal(view.global.readOnly, true);
});

test("the module map is composable and marks planned capabilities honestly", () => {
  const map = workbench.workspaceView(workbench.createDemoState()).global;
  const tokenManager = map.modules.find((module) => module.module_id === "token-manager");

  assert.ok(map.modules.some((module) => module.module_id === "cognitive-intake"));
  assert.deepEqual(map.edges[0], ["workspace-intake", "cognitive-intake"]);
  assert.equal(tokenManager.availability, "PLANNED");
  assert.equal(map.unresolved.length, 0);
});

test("module edges are resolved from versioned capability manifests", () => {
  assert.equal(typeof workbench.buildModuleGraph, "function");
  const graph = workbench.buildModuleGraph([
    {
      contract_version: "personal-ai-os.module/v1",
      module_id: "source",
      name: "Source",
      layer: "input",
      provides: ["task.input"],
      requires: [],
      availability: "READY",
      optional: false,
      entrypoint: "source:activate",
    },
    {
      contract_version: "personal-ai-os.module/v1",
      module_id: "viewer",
      name: "Viewer",
      layer: "output",
      provides: ["task.view"],
      requires: ["task.input"],
      availability: "READY",
      optional: true,
      entrypoint: "viewer:activate",
    },
  ]);

  assert.deepEqual(graph.edges, [["source", "viewer"]]);
  assert.equal(graph.interfaces["task.input"], "source");
  assert.equal(graph.coupling.directModuleReferences, 0);
});

test("the module topology preserves dependency direction without fixed card slots", () => {
  assert.equal(typeof workbench.buildModuleTopology, "function");
  const graph = workbench.moduleGraph();
  const topology = workbench.buildModuleTopology(graph.modules, graph.edges);
  const positions = Object.fromEntries(topology.nodes.map((node) => [node.module_id, node]));

  assert.deepEqual(topology.lanes.map((lane) => lane.label), ["输入", "理解", "编排", "执行", "记忆与观测"]);
  graph.edges.forEach(([sourceId, targetId]) => {
    const source = positions[sourceId];
    const target = positions[targetId];
    assert.ok(
      source.x < target.x || (source.x === target.x && source.y < target.y),
      `${sourceId} must appear before ${targetId}`,
    );
  });
  assert.equal(new Set(topology.nodes.map((node) => `${node.x}:${node.y}`)).size, topology.nodes.length);
});

test("the module topology grows for many plug-ins instead of assuming seven cards", () => {
  const base = workbench.moduleGraph();
  const plugIns = Array.from({ length: 20 }, (_, index) => ({
    contract_version: "personal-ai-os.module/v1",
    module_id: `observer-${index}`,
    name: `Observer ${index}`,
    layer: "观测",
    summary: "Synthetic plug-in",
    provides: [`observer.${index}`],
    requires: ["work.task"],
    availability: "READY",
    optional: true,
    entrypoint: `observer:${index}`,
  }));
  const graph = workbench.buildModuleGraph([...base.modules, ...plugIns]);
  const topology = workbench.buildModuleTopology(graph.modules, graph.edges);
  const observers = topology.nodes.filter((node) => node.module_id.startsWith("observer-"));

  assert.equal(observers.length, 20);
  assert.equal(new Set(observers.map((node) => node.y)).size, 20);
  assert.ok(topology.height > 1200);
});

test("module focus resolves complete upstream and downstream paths", () => {
  assert.equal(typeof workbench.moduleNeighborhood, "function");
  const graph = workbench.moduleGraph();
  const focus = workbench.moduleNeighborhood(graph.edges, "workflow-core");

  assert.deepEqual(focus.directUpstream, ["workspace-intake"]);
  assert.ok(focus.downstream.includes("dynamic-router"));
  assert.ok(focus.downstream.includes("execution-adapter"));
  assert.ok(focus.downstream.includes("continuity"));
  assert.ok(focus.downstream.includes("token-manager"));
});

test("dragging a module updates only its position inside the canvas bounds", () => {
  assert.equal(typeof workbench.moveModuleNode, "function");
  const graph = workbench.moduleGraph();
  const topology = workbench.buildModuleTopology(graph.modules, graph.edges);
  const original = topology.nodes.find((node) => node.module_id === "workflow-core");
  const moved = workbench.moveModuleNode(topology, "workflow-core", -200, topology.height + 500);
  const updated = moved.nodes.find((node) => node.module_id === "workflow-core");

  assert.notDeepEqual([updated.x, updated.y], [original.x, original.y]);
  assert.equal(updated.x, topology.padding);
  assert.equal(updated.y, topology.height - topology.nodeHeight - topology.padding);
  assert.deepEqual(
    moved.nodes.filter((node) => node.module_id !== "workflow-core"),
    topology.nodes.filter((node) => node.module_id !== "workflow-core"),
  );
});

test("the module renderer draws real edges and marks the focused dependency path", () => {
  assert.equal(typeof workbench.renderModuleTopology, "function");
  const graph = workbench.moduleGraph();
  const topology = workbench.buildModuleTopology(graph.modules, graph.edges);
  const html = workbench.renderModuleTopology(topology, "workflow-core");

  assert.equal((html.match(/data-edge-from=/g) || []).length, graph.edges.length);
  assert.equal((html.match(/data-module-id=/g) || []).length, graph.modules.length);
  assert.match(html, /data-module-id="workflow-core"[^>]+data-relation="selected"/);
  assert.match(html, /data-module-id="workspace-intake"[^>]+data-relation="upstream"/);
  assert.match(html, /data-module-id="execution-adapter"[^>]+data-relation="downstream"/);
});

test("map zoom keeps the pointer anchor stable and clamps unsafe scales", () => {
  assert.equal(typeof workbench.zoomModuleView, "function");
  const zoomed = workbench.zoomModuleView({ x: 0, y: 0, scale: 1 }, 1.5, { x: 100, y: 80 });
  const clamped = workbench.zoomModuleView(zoomed, 20, { x: 0, y: 0 });

  assert.deepEqual(zoomed, { x: -50, y: -40, scale: 1.5 });
  assert.equal(clamped.scale, 1.8);
});

test("the drag click guard expires when a browser emits no synthetic click", () => {
  assert.equal(typeof workbench.createDragClickGuard, "function");
  const scheduled = [];
  const guard = workbench.createDragClickGuard((callback) => scheduled.push(callback));

  guard.markDrag();
  assert.equal(guard.consumeClick(), true);
  assert.equal(guard.consumeClick(), false);

  guard.markDrag();
  scheduled.at(-1)();
  assert.equal(guard.consumeClick(), false);
});

test("workbench task states use the public operation contract", () => {
  const view = workbench.workspaceView(workbench.createDemoState());
  assert.deepEqual(Object.keys(view.work.lanes), [
    "UNASSIGNED", "IN_PROGRESS", "REVIEW", "BLOCKED", "CLOSED", "ARCHIVED", "COMPLETED",
  ]);
  assert.equal(view.work.activeLine.tasks[0].status, "UNASSIGNED");
});

test("starter templates create an explicit read-only candidate", () => {
  const state = workbench.applyTemplate(workbench.createDemoState(), "writing");
  assert.equal(state.activeTemplate, "writing");
  assert.equal(state.activeLineId, "writing");
  assert.equal(state.onboarding.status, "TEMPLATE_READY");
  assert.deepEqual(state.onboarding.detectedLines, ["writing"]);
  assert.equal(state.planApproved, false);
});

test("first-run analysis creates a candidate work map without pretending to write files", () => {
  const original = workbench.createDemoState();
  const next = workbench.analyzeFirstRun(original, {
    name: "Mixed workspace",
    files: ["src/app.js", "research/paper.md", "drafts/outline.md"],
  });
  const view = workbench.workspaceView(next);

  assert.equal(next.onboarding.status, "CANDIDATE_READY");
  assert.equal(next.onboarding.readOnly, true);
  assert.deepEqual(next.onboarding.detectedLines, ["product", "research", "writing"]);
  assert.equal(view.decision.pending[0].kind, "plan");
  assert.equal(original.onboarding.status, "NOT_STARTED");
});

test("conversation task creation proposes a line, task, and execution route", () => {
  const proposal = workbench.proposeTaskFromPrompt(
    workbench.createDemoState(),
    "整理行业资料并写一份长文初稿",
  );

  assert.equal(proposal.status, "CANDIDATE");
  assert.equal(proposal.line_id, "writing");
  assert.equal(proposal.task.status, "UNASSIGNED");
  assert.equal(proposal.route.route, "standard");
  assert.ok(proposal.route.model);
});

test("human gates and blocked tasks are centralized in decisions", () => {
  let state = workbench.approvePlan(workbench.createDemoState());
  state = workbench.recordDecision(state, "scope", "REJECTED");
  const pending = workbench.workspaceView(state).decision.pending;

  assert.ok(pending.some((item) => item.kind === "blocked" && item.task_id === "scope"));
});

test("decision cards escape task content and expose the real action", () => {
  const html = workbench.renderDecisionCard({
    kind: "task",
    task_id: "scope",
    title: "<script>unsafe</script>",
    acceptance: "边界得到确认",
    complexity: "standard",
    estimated_tokens: 18000,
  });

  assert.ok(html.includes("批准并继续"));
  assert.ok(html.includes("&lt;script&gt;unsafe&lt;/script&gt;"));
  assert.ok(!html.includes("<script>"));
});
