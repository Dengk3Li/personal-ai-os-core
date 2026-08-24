const test = require("node:test");
const assert = require("node:assert/strict");

const workbench = require("../workbench/app.js");


test("runtime payload replaces the synthetic fixture without changing its state contract", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "model-a",
    adapters: [{ adapter_id: "openai-compatible", available: true }],
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "science",
      activeTaskId: "science:hypothesis",
      planApproved: true,
      tasks: [{ task_id: "science:hypothesis", line_id: "science", title: "Task", acceptance: "Result", depends_on: [], status: "QUEUED", attempts: 0, events: [] }],
      businessLines: [{ line_id: "science", name: "Science", caption: "Loop", layout: "loop", stages: [] }],
      taskStates: { "science:hypothesis": "QUEUED" },
      decisions: {},
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: ["science"] },
    },
  });

  assert.equal(state.runtime, true);
  assert.equal(state.dataSource, "runtime");
  assert.equal(state.defaultModel, "model-a");
  assert.equal(state.taskStates["science:hypothesis"], "QUEUED");
  assert.equal(state.adapters[0].adapter_id, "openai-compatible");
});


test("paused runtime tasks stay visible as attention items and cannot dispatch", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "model-a",
    adapters: [],
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "science",
      activeTaskId: "science:gate",
      planApproved: true,
      tasks: [{ task_id: "science:gate", line_id: "science", title: "Paused task", acceptance: "Owner resumes it", depends_on: [], status: "PAUSED", attempts: 0, events: [] }],
      businessLines: [{ line_id: "science", name: "Science", caption: "Loop", layout: "loop", stages: [] }],
      taskStates: { "science:gate": "PAUSED" },
      decisions: { "science:gate": "B" },
      pendingDecisions: [],
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: ["science"] },
    },
  });

  assert.equal(workbench.actionForTask(state, "science:gate"), "RESUME");
  assert.equal(workbench.workspaceView(state).decision.pending[0].kind, "paused");
});


test("fresh runtime human gates wait for a persisted server decision", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "model-a",
    adapters: [{ adapter_id: "openai-compatible", available: true }],
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "science",
      activeTaskId: "science:gate",
      planApproved: true,
      tasks: [{ task_id: "science:gate", line_id: "science", title: "Gate", acceptance: "Record one server decision", depends_on: [], human_gate: true, status: "QUEUED", attempts: 0, events: [] }],
      businessLines: [{ line_id: "science", name: "Science", caption: "Loop", layout: "loop", stages: [] }],
      taskStates: { "science:gate": "QUEUED" },
      decisions: {},
      pendingDecisions: [],
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: ["science"] },
    },
  });

  assert.equal(workbench.actionForTask(state, "science:gate"), "HUMAN_DECISION_REQUIRED");
  assert.deepEqual(workbench.workspaceView(state).decision.pending, []);
});


test("runtime workflow nodes use the persisted task title as their stage", () => {
  const html = workbench.renderWorkflowNode({
    task_id: "science:hypothesis",
    public_label: "Task A-01",
    title: "Clarify the question and generate testable hypotheses",
    status: "QUEUED",
    attempts: 0,
  }, false);

  assert.match(html, /Clarify the question and generate testable hypotheses/);
  assert.doesNotMatch(html, /自定义任务/);
});


test("runtime client calls finite task run transition and decision endpoints", async () => {
  const calls = [];
  const client = workbench.createRuntimeClient(async (url, options = {}) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() { return { ok: true, state: { runtime: true } }; },
    };
  });

  await client.load();
  await client.runTask("task:1", "openai-compatible", "model-a");
  await client.transitionTask("task:1", "DONE", "Accepted result");
  await client.createTask({ task_id: "task:2", workflow_id: "science" });
  await client.resolveDecision("decision:1", "B");

  assert.deepEqual(calls.map((call) => call.url), [
    "/api/runtime",
    "/api/runs",
    "/api/tasks/task%3A1/transition",
    "/api/tasks",
    "/api/decisions/decision%3A1/resolve",
  ]);
  assert.equal(JSON.parse(calls[1].options.body).adapter_id, "openai-compatible");
  assert.equal(JSON.parse(calls[2].options.body).to, "DONE");
  assert.equal(JSON.parse(calls[4].options.body).selected_option, "B");
});


test("runtime client surfaces HTTP failures instead of pretending the action ran", async () => {
  const client = workbench.createRuntimeClient(async () => ({
    ok: false,
    status: 422,
    async json() { return { status: "BLOCKED", reason: "ADAPTER_UNAVAILABLE" }; },
  }));

  await assert.rejects(
    client.runTask("task:1", "missing", "model-a"),
    /ADAPTER_UNAVAILABLE/,
  );
});
