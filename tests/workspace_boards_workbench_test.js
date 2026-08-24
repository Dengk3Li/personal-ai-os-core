const assert = require("node:assert/strict");
const test = require("node:test");

const workbench = require("../workbench/app.js");

test("the workspace exposes the four primary views over one task state", () => {
  assert.equal(typeof workbench.workspaceView, "function", "workspace projection must exist");
  const view = workbench.workspaceView(workbench.createDemoState());

  assert.deepEqual(
    view.boards.map((board) => board.id),
    ["global", "work", "research", "decision"],
  );
  assert.equal(view.activeBoard, "work");
  assert.equal(view.global.readOnly, true);
  assert.equal(view.research.readOnly, true);
});

test("switching boards preserves the same long-task state", () => {
  assert.equal(typeof workbench.selectBoard, "function", "board selection must exist");
  const original = workbench.createDemoState();

  const globalState = workbench.selectBoard(original, "global");
  const researchState = workbench.selectBoard(globalState, "research");
  const decisionState = workbench.selectBoard(researchState, "decision");

  assert.equal(globalState.activeBoard, "global");
  assert.equal(researchState.activeBoard, "research");
  assert.equal(decisionState.activeBoard, "decision");
  assert.deepEqual(decisionState.taskStates, original.taskStates);
  assert.equal(workbench.selectBoard(original, "unknown").activeBoard, "work");
});

test("human gates live on the decision board and release work after approval", () => {
  let state = workbench.approvePlan(workbench.createDemoState());
  let view = workbench.workspaceView(state);

  assert.deepEqual(view.decision.pending.map((item) => item.task_id), ["scope"]);
  assert.equal(view.work.tasks.scope.action, "HUMAN_DECISION_REQUIRED");

  state = workbench.recordDecision(state, "scope", "APPROVED");
  view = workbench.workspaceView(state);

  assert.deepEqual(view.decision.pending, []);
  assert.equal(view.work.tasks.scope.action, "DISPATCH");
});

test("the global map explains the complete long-work loop without becoming a writer", () => {
  const view = workbench.workspaceView(workbench.createDemoState());

  assert.deepEqual(
    view.global.nodes.map((node) => node.id),
    ["goal", "plan", "human", "route", "executor", "result", "continuity"],
  );
  assert.deepEqual(view.global.edges[0], ["goal", "plan"]);
  assert.deepEqual(view.global.edges.at(-1), ["result", "continuity"]);
  assert.equal(view.global.taskCount, 5);
});

test("decision cards expose the real human action and escape task content", () => {
  assert.equal(typeof workbench.renderDecisionCard, "function", "decision renderer must exist");

  const html = workbench.renderDecisionCard({
    kind: "task",
    task_id: "scope",
    title: "<script>unsafe</script>",
    acceptance: "研究边界得到确认",
    complexity: "standard",
    estimated_tokens: 18000,
  });

  assert.ok(html.includes("批准并继续"));
  assert.ok(html.includes("退回"));
  assert.ok(html.includes("&lt;script&gt;unsafe&lt;/script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes('data-decision-task="scope"'));
});
