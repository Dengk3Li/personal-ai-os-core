const assert = require("node:assert/strict");
const test = require("node:test");

let workbench = {};
try {
  workbench = require("../workbench/app.js");
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
}

test("a human can approve a plan and advance dependent work", () => {
  assert.equal(typeof workbench.createDemoState, "function", "workbench demo API must exist");
  assert.equal(typeof workbench.viewModel, "function", "workbench view model must exist");
  let state = workbench.createDemoState();

  assert.equal(workbench.actionForTask(state, "scope"), "PLAN_APPROVAL_REQUIRED");
  state = workbench.approvePlan(state);
  assert.equal(workbench.actionForTask(state, "scope"), "HUMAN_DECISION_REQUIRED");
  state = workbench.recordDecision(state, "scope", "APPROVED");
  assert.equal(workbench.actionForTask(state, "scope"), "DISPATCH");

  state = workbench.applyTaskAction(state, "scope");
  assert.equal(state.taskStates.scope, "IN_PROGRESS");
  assert.equal(state.assignments.scope.route, "standard");
  state = workbench.applyTaskAction(state, "scope");
  assert.equal(state.taskStates.scope, "REVIEW");
  state = workbench.applyTaskAction(state, "scope");
  assert.equal(state.taskStates.scope, "DONE");
  assert.equal(workbench.actionForTask(state, "evidence"), "DISPATCH");
  assert.deepEqual(workbench.progress(state), { done: 1, total: 7, percent: 14 });
  const view = workbench.viewModel(state);
  assert.deepEqual(view.lanes.DONE, ["scope"]);
  assert.equal(view.tasks.evidence.action, "DISPATCH");
});

test("dependency and human gates remain visible instead of auto-advancing", () => {
  assert.equal(typeof workbench.createDemoState, "function", "workbench demo API must exist");
  let state = workbench.approvePlan(workbench.createDemoState());

  assert.equal(workbench.actionForTask(state, "evidence"), "WAITING_DEPENDENCY");
  assert.equal(workbench.actionForTask(state, "scope"), "HUMAN_DECISION_REQUIRED");
  assert.equal(state.taskStates.scope, "QUEUED");
});

test("a recorded rejection is blocked work, not a pending human decision", () => {
  assert.equal(typeof workbench.viewModel, "function", "workbench view model must exist");
  let state = workbench.approvePlan(workbench.createDemoState());

  state = workbench.recordDecision(state, "scope", "REJECTED");
  const view = workbench.viewModel(state);

  assert.equal(state.taskStates.scope, "BLOCKED");
  assert.equal(view.pendingHumanGates, 1);
});

test("task cards expose the human action without injecting task text as markup", () => {
  assert.equal(typeof workbench.renderTaskCard, "function", "task card renderer must exist");
  const html = workbench.renderTaskCard({
    task_id: "unsafe-id",
    title: "<script>alert(1)</script>",
    status: "QUEUED",
    action: "HUMAN_DECISION_REQUIRED",
    human_gate: true,
    complexity: "standard",
    estimated_tokens: 12000,
    assignment: null,
  });

  assert.ok(html.includes("需要你裁决"));
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes('data-task-id="unsafe-id"'));
});

test("the public v0.6 showcase contains workflow structure but no private task copy", () => {
  assert.equal(typeof workbench.createShowcaseState, "function");
  const state = workbench.createShowcaseState();

  assert.equal(state.privacy.taskDetails, "ANONYMIZED");
  assert.ok(state.tasks.length >= 18);
  state.tasks.forEach((task) => {
    assert.equal(Object.hasOwn(task, "title"), false);
    assert.equal(Object.hasOwn(task, "acceptance"), false);
    assert.match(task.public_label, /^任务 [A-Z]-\d{2}$/);
    assert.ok(task.stage);
  });
});

test("workflow summary makes allocation, active runs, and repeated work explicit", () => {
  assert.equal(typeof workbench.workflowSummary, "function");
  const summary = workbench.workflowSummary(workbench.createShowcaseState());

  assert.deepEqual(
    {
      total: summary.total,
      assigned: summary.assigned,
      running: summary.running,
      review: summary.review,
      completed: summary.completed,
      repeatedRuns: summary.repeatedRuns,
    },
    { total: 18, assigned: 11, running: 3, review: 2, completed: 6, repeatedRuns: 4 },
  );
  assert.equal(summary.allocation.reduce((total, item) => total + item.tasks, 0), 11);
});

test("the research preset uses five science agents and parallel experiment paths", () => {
  assert.equal(typeof workbench.workflowProjection, "function");
  const projection = workbench.workflowProjection(workbench.createShowcaseState(), "research");

  assert.equal(projection.workflow_id, "research");
  assert.deepEqual(projection.groups.map((group) => group.iteration), [1, 2, 3, 4]);
  assert.ok(projection.groups[1].nodes.some((node) => node.parallel_group === "branch-alpha"));
  assert.deepEqual(
    new Set(projection.groups.flatMap((group) => group.nodes.map((node) => node.agent_role))),
    new Set(["科学假设 Agent", "Protocol 设计 Agent", "自主实验执行 Agent", "数据分析 Agent", "反馈优化 Agent"]),
  );
  const repeated = projection.groups[1].nodes.find((node) => node.attempts === 2);
  assert.ok(repeated.events.some((event) => event.kind === "heartbeat"));
});

test("showcase worklines are research and two reusable document presets", () => {
  const state = workbench.createShowcaseState();

  assert.deepEqual(state.businessLines.map((line) => line.line_id), ["research", "meeting-notes", "industry-report"]);
  assert.equal(state.businessLines[0].name, "科研线");
  assert.equal(state.businessLines[1].name, "会议纪要");
  assert.equal(state.businessLines[2].name, "行业研究 / 专业报告");
});

test("a user can create and enter a new browser-style workline", () => {
  assert.equal(typeof workbench.createWorkline, "function");
  const original = workbench.createShowcaseState();
  const next = workbench.createWorkline(original, "新产品验证");

  assert.equal(next.businessLines.at(-1).name, "新产品验证");
  assert.equal(next.businessLines.at(-1).user_created, true);
  assert.equal(next.activeLineId, next.businessLines.at(-1).line_id);
  assert.equal(next.tasks.length, original.tasks.length);
});

test("running assignments resolve a model-specific pet without changing task truth", () => {
  assert.equal(typeof workbench.petForTask, "function");
  const pet = workbench.petForTask({
    status: "IN_PROGRESS",
    assignment: { model: "Reasoning model", executor: "Science adapter" },
  });

  assert.deepEqual(pet, { pet_id: "reasoning-owl", glyph: "🦉", label: "Reasoning model 工作宠物" });
  assert.equal(workbench.petForTask({ status: "REVIEW", assignment: { model: "Reasoning model" } }), null);
});

test("an authorized blue whale maid can be selected or disabled", () => {
  const task = {
    task_id: "science:analysis",
    status: "IN_PROGRESS",
    attempts: 1,
    agent_role: "Data Analysis Agent",
    assignment: { model: "Reasoning model", executor: "Science adapter" },
  };

  const pet = workbench.petForTask(task, "blue-whale-maid");
  assert.equal(pet.pet_id, "blue-whale-maid");
  assert.equal(pet.kind, "image");
  assert.match(pet.src, /^assets\/pets\/blue-whale-maid\/blue-whale-maid-mining-(normal|happy|tired)\.gif$/);
  assert.equal(workbench.petForTask(task, "off"), null);
  assert.equal(workbench.setPetPreference({ petPreference: "model-animal" }, "blue-whale-maid").petPreference, "blue-whale-maid");
});

test("every running showcase task has closed prerequisites", () => {
  const state = workbench.createShowcaseState();
  const closed = new Set(["DONE", "ARCHIVED"]);

  state.tasks
    .filter((task) => state.taskStates[task.task_id] === "IN_PROGRESS")
    .forEach((task) => task.depends_on.forEach((dependency) => {
      assert.ok(closed.has(state.taskStates[dependency]), `${task.task_id} cannot run before ${dependency} closes`);
    }));
});
