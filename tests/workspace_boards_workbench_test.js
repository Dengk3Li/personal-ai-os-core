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
