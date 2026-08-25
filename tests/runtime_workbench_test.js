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


test("task dispatch controls stay disabled until an adapter is available", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-001",
      public_label: "任务 01",
      title: "公开任务",
      status: "QUEUED",
      action: "DISPATCH",
      attempts: 0,
      events: [],
    },
    {
      runtime: true,
      defaultModel: "model-a",
      adapters: [{ adapter_id: "openai-compatible", available: false }],
    },
  );

  assert.match(html, /<select data-runtime-adapter disabled>/);
  assert.match(html, /暂无可用执行适配器/);
  assert.match(html, /配置执行适配器后开始/);
  assert.doesNotMatch(html, /openai-compatible/);
  assert.match(html, /<button class="task-action"[^>]*disabled/);
});

test("fixed task dispatch stays disabled until both model and adapter are ready", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-001",
      public_label: "任务 01",
      title: "公开任务",
      status: "QUEUED",
      action: "DISPATCH",
      attempts: 0,
      events: [],
    },
    {
      runtime: true,
      defaultModel: "",
      adapters: [{ adapter_id: "adapter-01", available: true }],
      execution: { task_dispatch_ready: false, advance_route_mode: "fixed", advance_ready: false },
    },
  );

  assert.match(html, /配置模型后开始/);
  assert.match(html, /<button class="task-action"[^>]*disabled/);
});

test("automatic advance readiness is independent from the fixed task model", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "",
    adapters: [{ adapter_id: "adapter-01", available: true }],
    execution: {
      task_dispatch_ready: false,
      advance_route_mode: "automatic",
      advance_ready: true,
    },
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "science",
      activeTaskId: null,
      planApproved: true,
      tasks: [],
      businessLines: [{ line_id: "science", domain_id: "science", name: "Science", caption: "Loop", layout: "loop", stages: [] }],
      taskStates: {},
      decisions: {},
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: ["science"] },
    },
  });

  assert.deepEqual(workbench.executionReadiness(state), {
    taskReady: false,
    advanceReady: true,
    advanceRouteMode: "automatic",
    adapterReady: true,
    modelReady: false,
  });
});

test("execution settings stay collapsed until the user needs to configure them", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-001",
      public_label: "任务 01",
      title: "私人任务",
      status: "QUEUED",
      action: "DISPATCH",
      attempts: 0,
      events: [],
    },
    {
      runtime: true,
      defaultModel: "model-a",
      adapters: [{ adapter_id: "local-adapter", available: true }],
    },
  );

  assert.match(html, /<details class="execution-settings">/);
  assert.match(html, /<summary>执行设置/);
  assert.match(html, /data-runtime-model/);
  assert.match(html, /data-runtime-adapter/);
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
  await client.advance("openai-compatible", "model-a", 4, "science");

  assert.deepEqual(calls.map((call) => call.url), [
    "/api/runtime",
    "/api/runs",
    "/api/tasks/task%3A1/transition",
    "/api/tasks",
    "/api/decisions/decision%3A1/resolve",
    "/api/advance",
  ]);
  assert.equal(JSON.parse(calls[1].options.body).adapter_id, "openai-compatible");
  assert.equal(JSON.parse(calls[2].options.body).to, "DONE");
  assert.equal(JSON.parse(calls[4].options.body).selected_option, "B");
  assert.equal(JSON.parse(calls[5].options.body).max_steps, 4);
  assert.equal(JSON.parse(calls[5].options.body).workflow_id, "science");
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


test("a pending model request keeps refreshing the real runtime projection", async () => {
  let finishRun;
  let scheduled;
  let cancelled = false;
  let refreshes = 0;
  const run = new Promise((resolve) => { finishRun = resolve; });
  const pending = workbench.runTaskWithPolling(
    () => run,
    async () => { refreshes += 1; },
    (callback) => { scheduled = callback; return "timer-1"; },
    (timer) => { cancelled = timer === "timer-1"; },
  );

  await scheduled();
  assert.equal(refreshes, 1);
  finishRun({ ok: true, status: "REVIEW" });
  await pending;

  assert.equal(cancelled, true);
  assert.equal(refreshes, 2);
});
