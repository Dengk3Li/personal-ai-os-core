const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const architecture = require("../workbench/architecture.js");
const workbench = require("../workbench/app.js");


test("the system map covers the whole operating loop and exposes recursive drill-down", () => {
  const root = architecture.systemGraph([]);

  assert.equal(root.graph_id, "personal-ai-os");
  assert.ok(root.nodes.some((node) => node.module_id === "secretary-entry"));
  assert.ok(root.nodes.some((node) => node.module_id === "delivery"));
  assert.ok(root.edges.some((edge) => edge[2] === "feedback"));

  const kernel = root.nodes.find((node) => node.module_id === "longtask-kernel");
  assert.equal(kernel.child_graph, "longtask-kernel");
  assert.equal(root.nodes.find((node) => node.module_id === "personal-context").child_graph, "personal-context");
  assert.equal(architecture.systemGraph(["longtask-kernel"]).graph_id, "longtask-kernel");
  assert.deepEqual(
    architecture.systemBreadcrumbs(["longtask-kernel"]).map((item) => item.label),
    ["个人 AI 操作系统", "长期工作内核"],
  );
});

test("a drilled graph keeps its parent and external handoff boundary", () => {
  const graph = architecture.systemGraph(["longtask-kernel"]);

  assert.equal(graph.boundary.parent_graph.graph_id, "personal-ai-os");
  assert.equal(graph.boundary.owner_module.module_id, "longtask-kernel");
  assert.deepEqual(graph.boundary.incoming.map((item) => item.module_id), ["domain-routing"]);
  assert.deepEqual(graph.boundary.outgoing.map((item) => item.module_id), ["domain-systems"]);
  assert.deepEqual(graph.boundary.feedback.map((item) => item.module_id), ["learning-cycle"]);
});


test("the long-task kernel explains domain abstraction and evidence-gated learning", () => {
  const graph = architecture.systemGraph(["longtask-kernel"]);
  const ids = new Set(graph.nodes.map((node) => node.module_id));

  assert.ok(ids.has("domain-template"));
  assert.ok(ids.has("workflow-compiler"));
  assert.ok(ids.has("module-task-link"));
  assert.ok(ids.has("experience-candidate"));
  assert.ok(ids.has("human-promotion"));
  assert.equal(graph.nodes.find((node) => node.module_id === "conversation-learning").availability, "PLANNED");
});


test("the system map does not present vision-only modules as operational", () => {
  const root = architecture.systemGraph([]);
  const domainSystems = architecture.systemGraph(["domain-systems"]);
  const learning = architecture.systemGraph(["learning-cycle"]);

  assert.equal(root.nodes.find((node) => node.module_id === "secretary-entry").availability, "PLANNED");
  assert.equal(root.nodes.find((node) => node.module_id === "personal-context").availability, "PROTOTYPE");
  assert.equal(root.nodes.find((node) => node.module_id === "domain-routing").availability, "PROTOTYPE");
  assert.equal(root.nodes.find((node) => node.module_id === "longtask-kernel").availability, "PROTOTYPE");
  assert.equal(root.nodes.find((node) => node.module_id === "learning-cycle").availability, "PROTOTYPE");
  assert.equal(domainSystems.nodes.find((node) => node.module_id === "personal-domain").availability, "PLANNED");
  assert.equal(learning.nodes.find((node) => node.module_id === "signal-capture").availability, "PLANNED");
  assert.equal(learning.nodes.find((node) => node.module_id === "owner-accept").availability, "READY");
  assert.equal(learning.nodes.find((node) => node.module_id === "task-load").availability, "READY");
});


test("system graph validation rejects duplicate and dependency-only cycles", () => {
  const nodes = [
    { module_id: "a" },
    { module_id: "b" },
  ];
  assert.throws(
    () => architecture.validateGraph({ graph_id: "cycle", nodes, edges: [["a", "b", "dependency"], ["b", "a", "dependency"]] }),
    /依赖循环/,
  );
  assert.throws(
    () => architecture.validateGraph({ graph_id: "duplicate", nodes, edges: [["a", "b", "dependency"], ["a", "b", "dependency"]] }),
    /连接重复/,
  );
  assert.doesNotThrow(
    () => architecture.validateGraph({ graph_id: "feedback", nodes, edges: [["a", "b", "dependency"], ["b", "a", "feedback"]] }),
  );
});


test("workflow projection assigns explicit programming-logic kinds", () => {
  const projection = workbench.workflowProjection(workbench.createShowcaseState(), "research");
  const nodes = projection.groups.flatMap((group) => group.nodes);

  assert.ok(nodes.some((node) => node.flow_kind === "branch"));
  assert.ok(nodes.some((node) => node.flow_kind === "join"));
  assert.ok(nodes.some((node) => node.flow_kind === "condition"));
  assert.ok(nodes.some((node) => node.flow_kind === "loop"));
  assert.ok(nodes.every((node) => ["sequence", "branch", "join", "condition", "loop"].includes(node.flow_kind)));
});


test("the report-facing workbench surface uses Chinese action language", () => {
  const html = fs.readFileSync(path.join(__dirname, "../workbench/index.html"), "utf8")
    .replace(/<details class="technical-reference">[\s\S]*?<\/details>/, "");
  const app = fs.readFileSync(path.join(__dirname, "../workbench/app.js"), "utf8");
  const visibleSurface = `${html}\n${app}`;

  [/\bINSPECT\b/, /\bCONFIRM\b/, /\bEXECUTE\b/, /Human Gate/, /\bAttempt\b/, /Data pool/, /Draft Agent/, /Protocol 设计/].forEach((pattern) => {
    assert.doesNotMatch(visibleSurface, pattern);
  });
  assert.doesNotMatch(visibleSurface, /配置 Adapter 后推进/);
  assert.match(visibleSurface, /尚未连接执行适配器/);
  assert.match(html, /v0\.15\.0/);
});
