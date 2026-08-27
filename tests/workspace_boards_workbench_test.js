const assert = require("node:assert/strict");
const test = require("node:test");

const workbench = require("../workbench/app.js");

test("the workspace has three stable entrances over one shared state", () => {
  const view = workbench.workspaceView(workbench.createDemoState());

  assert.deepEqual(view.boards.map((board) => board.id), ["global", "work", "decision"]);
  assert.equal(view.activeBoard, "work");
  assert.equal(view.global.readOnly, true);
});

test("selecting a workflow task keeps its line and domain in sync", () => {
  const original = workbench.createShowcaseState();
  const next = workbench.selectWorkflowTask(original, "flow-b-03");

  assert.equal(next.activeTaskId, "flow-b-03");
  assert.equal(next.activeLineId, "meeting-notes");
  assert.equal(next.activeDomainId, "writing");
  assert.equal(original.activeTaskId, "flow-a-03");
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

test("module topology accepts recursive graph layers and feedback edges", () => {
  const graph = require("../workbench/architecture.js").systemGraph(["personal-context"]);
  const topology = workbench.buildModuleTopology(graph.nodes, graph.edges);

  assert.equal(topology.nodes.length, graph.nodes.length);
  assert.ok(topology.lanes.some((lane) => lane.label === "规则"));
  assert.ok(topology.lanes.some((lane) => lane.label === "编译"));
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

test("module inspection explains incoming processing and outgoing connections", () => {
  const graph = require("../workbench/architecture.js").systemGraph([]);
  const connections = workbench.moduleConnectionModel(graph, "longtask-kernel");

  assert.deepEqual(connections.incoming.map((item) => item.module_name), ["领域识别与抽象"]);
  assert.deepEqual(connections.outgoing.map((item) => item.module_name), ["领域工作系统"]);
  assert.ok(connections.processing.some((step) => /工作流结构编译/.test(step)));
  assert.ok(connections.interfaces.some((item) => item.direction === "输入"));
  assert.ok(connections.interfaces.some((item) => item.direction === "输出"));
});

test("drilled module inspection exposes its parent and external handoffs", () => {
  const graph = require("../workbench/architecture.js").systemGraph(["longtask-kernel"]);
  const connections = workbench.moduleConnectionModel(graph, "task-state");

  assert.equal(connections.boundary.owner_module.module_id, "longtask-kernel");
  assert.equal(connections.boundary.parent_graph.name, "个人 AI 操作系统");
  assert.deepEqual(connections.boundary.incoming.map((item) => item.module_name), ["领域识别与抽象"]);
  assert.deepEqual(connections.boundary.outgoing.map((item) => item.module_name), ["领域工作系统"]);
});

test("the secondary map is named as a component dependency view", () => {
  const html = require("node:fs").readFileSync(require("node:path").join(__dirname, "../workbench/index.html"), "utf8");

  assert.match(html, />组件依赖</);
  assert.match(html, /id="module-map-description"/);
  assert.doesNotMatch(html, />运行模块</);
});

test("module inspection derives honest connection details for every system node", () => {
  const graph = require("../workbench/architecture.js").systemGraph([]);

  graph.nodes.forEach((node) => {
    const connections = workbench.moduleConnectionModel(graph, node.module_id);
    assert.ok(connections.processing.length, `${node.module_id} needs processing copy`);
    assert.ok(connections.interfaces.length, `${node.module_id} needs interface copy`);
    connections.interfaces.forEach((item) => {
      assert.ok(item.direction);
      assert.ok(item.name);
      assert.ok(item.protocol);
    });
  });
});

test("feedback connections stay separate from execution dependencies", () => {
  const graph = require("../workbench/architecture.js").systemGraph([]);
  const connections = workbench.moduleConnectionModel(graph, "personal-context");

  assert.ok(!connections.incoming.some((item) => item.module_id === "learning-cycle"));
  assert.ok(connections.feedback.some((item) => item.module_id === "learning-cycle"));
});

test("a module annotation becomes a bounded task candidate for the active workflow", () => {
  const state = workbench.createShowcaseState();
  const proposal = workbench.proposeTaskFromModuleAnnotation(
    state,
    "workflow-core",
    "The handoff state needs a clearer acceptance boundary.",
  );

  assert.equal(proposal.status, "CANDIDATE");
  assert.equal(proposal.task.line_id, state.activeLineId);
  assert.equal(proposal.task.context.model_context.module_id, "workflow-core");
  assert.deepEqual(proposal.task.module_links, [{
    module_id: "workflow-core",
    relation: "CHANGES",
    source: "EXPLICIT",
    status: "CONFIRMED",
  }]);
  assert.equal(
    proposal.task.context.model_context.annotation,
    "The handoff state needs a clearer acceptance boundary.",
  );
  assert.equal(
    workbench.proposeTaskFromModuleAnnotation(state, "workflow-core", " ").status,
    "BLOCKED",
  );
});

test("a system-map annotation keeps its module identity on the task card", () => {
  const state = workbench.createShowcaseState();
  const proposal = workbench.proposeTaskFromModuleAnnotation(
    state,
    "longtask-kernel",
    "补齐旧任务卡恢复现场。",
  );

  assert.equal(proposal.status, "CANDIDATE");
  assert.equal(proposal.task.module_links[0].module_id, "longtask-kernel");
  assert.equal(proposal.task.module_links[0].relation, "CHANGES");
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

test("module nodes show task-backed construction state without changing graph edges", () => {
  const graph = require("../workbench/architecture.js").systemGraph([]);
  const topology = workbench.buildModuleTopology(graph.nodes, graph.edges);
  const html = workbench.renderModuleTopology(topology, "longtask-kernel", {
    by_module: {
      "longtask-kernel": {
        task_ids: ["task-001", "task-002"],
        relations: ["BUILDS", "VALIDATES"],
        status_counts: { IN_PROGRESS: 1, QUEUED: 1 },
      },
    },
  }, { proposed: 3, approved: 2 });

  assert.match(html, /data-module-id="longtask-kernel"[^>]+data-work-count="2"/);
  assert.match(html, /建设中 1 · 关联 2/);
  assert.match(html, /data-module-id="learning-cycle"[^>]+data-cognitive-count="5"/);
  assert.match(html, /候选 3 · 已确认 2/);
  assert.equal((html.match(/data-edge-from=/g) || []).length, graph.edges.length);
});

test("map zoom keeps the pointer anchor stable and clamps unsafe scales", () => {
  assert.equal(typeof workbench.zoomModuleView, "function");
  const zoomed = workbench.zoomModuleView({ x: 0, y: 0, scale: 1 }, 1.5, { x: 100, y: 80 });
  const clamped = workbench.zoomModuleView(zoomed, 20, { x: 0, y: 0 });
  const fittedScale = workbench.zoomModuleView(zoomed, .01, { x: 0, y: 0 });

  assert.deepEqual(zoomed, { x: -50, y: -40, scale: 1.5 });
  assert.equal(clamped.scale, 1.8);
  assert.equal(fittedScale.scale, .16);
});


test("module clicks keep their target until a node drag actually starts", () => {
  assert.equal(workbench.captureMapPointerOnDown("pan"), true);
  assert.equal(workbench.captureMapPointerOnDown("node"), false);
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
    "QUEUED", "IN_PROGRESS", "REVIEW", "BLOCKED", "PAUSED", "DONE", "ARCHIVED",
  ]);
  assert.equal(view.work.activeLine.tasks[0].status, "QUEUED");
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
  assert.equal(proposal.task.status, "QUEUED");
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
