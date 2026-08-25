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
      durableGoals: [{ goal_id: "goal-01", title: "持续封包", status: "ACTIVE", usage: { steps_used: 2 } }],
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: ["science"] },
    },
  });

  assert.equal(state.runtime, true);
  assert.equal(state.dataSource, "runtime");
  assert.equal(state.defaultModel, "model-a");
  assert.equal(state.taskStates["science:hypothesis"], "QUEUED");
  assert.equal(state.adapters[0].adapter_id, "openai-compatible");
  assert.equal(state.durableGoals[0].title, "持续封包");
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

test("task cards expose confirmed module links as compact navigation chips", () => {
  const html = workbench.renderWorkflowNode({
    task_id: "system:task",
    public_label: "任务 01",
    title: "建设长期工作内核",
    status: "QUEUED",
    attempts: 0,
    module_links: [
      { module_id: "longtask-kernel", relation: "BUILDS", status: "CONFIRMED" },
      { module_id: "personal-context", relation: "USES", status: "PROPOSED" },
    ],
  }, false);

  assert.match(html, /data-task-module="longtask-kernel"/);
  assert.match(html, /建设模块/);
  assert.doesNotMatch(html, /personal-context/);
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

  assert.doesNotMatch(html, /data-runtime-adapter/);
  assert.match(html, /使用已保存的执行策略/);
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

test("automatic task dispatch uses the saved route without asking for a fixed model", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-routed",
      public_label: "任务 01",
      status: "QUEUED",
      action: "DISPATCH",
      attempts: 0,
      events: [],
    },
    {
      runtime: true,
      defaultModel: "",
      adapters: [{ adapter_id: "codex-app-server", available: true }],
      execution: {
        advance_route_mode: "automatic",
        task_dispatch_ready: true,
        advance_ready: true,
      },
    },
  );

  assert.match(html, />分派并开始<\/button>/);
  assert.doesNotMatch(html, /配置模型后开始/);
});

test("an in-progress model run cannot be manually submitted before its receipt arrives", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-running",
      public_label: "任务 01",
      status: "IN_PROGRESS",
      action: "SUBMIT_REVIEW",
      attempts: 1,
      events: [],
    },
    {
      runtime: true,
      defaultModel: "model-a",
      adapters: [{ adapter_id: "codex-app-server", available: true }],
      execution: { task_dispatch_ready: true },
    },
  );

  assert.match(html, /<button[^>]+disabled[^>]*>正在执行<\/button>/);
  assert.doesNotMatch(html, />提交验收<\/button>/);
});

test("task detail uses saved execution settings without exposing configuration controls", () => {
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

  assert.doesNotMatch(html, /execution-settings/);
  assert.doesNotMatch(html, /data-runtime-model/);
  assert.doesNotMatch(html, /data-runtime-adapter/);
  assert.match(html, /使用已保存的执行策略/);
});

test("settings explain saved routing and keep credentials on the server", () => {
  const html = workbench.renderSettings({
    runtime: true,
    execution: { advance_route_mode: "automatic", task_dispatch_ready: true },
    adapters: [{ adapter_id: "adapter-01", available: true, protocol: "chat-completions" }],
    executionSettings: {
      routes: [{ route: "route-01", model: "model-01", adapter_id: "adapter-01", capabilities: ["writing"], enabled: true }],
      default_adapter_id: "adapter-01",
      credential_source: "server-environment",
    },
    cognitiveLearning: { proposed: 1, approved: 2 },
  });

  assert.match(html, /自动路由/);
  assert.match(html, /route-01/);
  assert.match(html, /服务端环境变量/);
  assert.match(html, /只发起经验复核/);
  assert.doesNotMatch(html, /工作结果只生成候选/);
  assert.doesNotMatch(html, /api_key|Bearer|password/i);
});

test("private runtime settings bind Codex API and routes only inside settings", () => {
  const html = workbench.renderSettings({
    runtime: true,
    execution: { advance_route_mode: "automatic", task_dispatch_ready: true },
    adapters: [{ adapter_id: "codex-app-server", available: true, protocol: "codex-app-server" }],
    executionSettings: {
      writable: true,
      mode: "automatic",
      routes: [{ route: "research-deep", tier: "deep", model: "gpt-codex", adapter_id: "codex-app-server", capabilities: ["research"], max_context_tokens: 120000, enabled: true }],
      default_adapter_id: "",
      credential_source: "browser-session",
    },
    cognitiveLearning: { proposed: 0, approved: 0 },
  });

  assert.match(html, /data-bind-codex/);
  assert.match(html, /data-bind-openai/);
  assert.match(html, /type="password"/);
  assert.match(html, /autocomplete="new-password"/);
  assert.match(html, /data-save-routes/);
  assert.match(html, /research-deep/);
});

test("low-frequency controls are reachable only from the top-right settings surface", () => {
  const page = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../workbench/index.html"),
    "utf8",
  );
  const script = require("node:fs").readFileSync(
    require("node:path").join(__dirname, "../workbench/app.js"),
    "utf8",
  );
  const topActions = page.match(/<div class="top-actions">([\s\S]*?)<\/div>/)?.[1] || "";
  const settings = workbench.renderSettings({
    runtime: false,
    petPreference: "off",
  });

  assert.equal((topActions.match(/<button/g) || []).length, 1);
  assert.match(topActions, /id="settings-toggle"/);
  assert.doesNotMatch(topActions, /pet-preference|reset-demo|data-board/);
  assert.match(settings, /id="pet-preference"/);
  assert.match(settings, /value="off" selected/);
  assert.match(settings, /data-reset-demo/);
  assert.doesNotMatch(script, /byId\("reset-demo"\)/);
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
  await client.continueGoal("goal:1", "openai-compatible", "model-a");
  await client.configureExecution({ mode: "fixed" });

  assert.deepEqual(calls.map((call) => call.url), [
    "/api/runtime",
    "/api/runs",
    "/api/tasks/task%3A1/transition",
    "/api/tasks",
    "/api/decisions/decision%3A1/resolve",
    "/api/advance",
    "/api/goals/goal%3A1/continue",
    "/api/settings/execution",
  ]);
  assert.equal(JSON.parse(calls[1].options.body).adapter_id, "openai-compatible");
  assert.equal(JSON.parse(calls[2].options.body).to, "DONE");
  assert.equal(JSON.parse(calls[4].options.body).selected_option, "B");
  assert.equal(JSON.parse(calls[5].options.body).max_steps, 4);
  assert.equal(JSON.parse(calls[5].options.body).workflow_id, "science");
  assert.equal(JSON.parse(calls[6].options.body).model, "model-a");
  assert.equal(JSON.parse(calls[7].options.body).mode, "fixed");
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

test("durable goal strip distinguishes continuation limits from completion", () => {
  const active = workbench.renderDurableGoal({
    goal_id: "goal:release",
    title: "持续完成公开封包",
    objective: "推进已登记任务并等待人工验收",
    status: "ACTIVE",
    continuation_policy: { max_total_steps: 20, max_total_tokens: 1000 },
    usage: { steps_used: 4, tokens_used: 300, continuation_count: 2 },
    recovery_required: false,
  }, { advanceReady: true });
  const limited = workbench.renderDurableGoal({
    goal_id: "goal:release",
    title: "持续完成公开封包",
    status: "BUDGET_LIMITED",
    continuation_policy: { max_total_steps: 20, max_total_tokens: 1000 },
    usage: { steps_used: 20, tokens_used: 900, continuation_count: 5 },
    recovery_required: false,
  }, { advanceReady: true });
  const recovering = workbench.renderDurableGoal({
    goal_id: "goal:release",
    title: "持续完成公开封包",
    status: "RECOVERY_REQUIRED",
    continuation_policy: { max_total_steps: 20, max_total_tokens: 1000 },
    usage: { steps_used: 5, tokens_used: 400, continuation_count: 3 },
    recovery_required: true,
  }, { advanceReady: true });

  assert.match(active, /持续完成公开封包/);
  assert.match(active, /<b>4<\/b> \/ 20 步/);
  assert.match(active, /data-goal-continue="goal:release"/);
  assert.match(limited, /预算受限/);
  assert.match(limited, /核验收口状态/);
  assert.match(limited, /data-goal-continue="goal:release"/);
  assert.doesNotMatch(limited, /确认完成/);
  assert.match(recovering, /等待恢复确认/);
  assert.doesNotMatch(recovering, /data-goal-continue/);
});

test("private operating domains use report-ready Chinese labels", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "",
    adapters: [],
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "foundation",
      activeTaskId: null,
      planApproved: true,
      tasks: [],
      businessLines: [
        { line_id: "foundation", domain_id: "system", name: "长期任务运行底座", caption: "", layout: "milestones", stages: [] },
        { line_id: "public-extraction", domain_id: "governance", name: "公共能力抽离", caption: "", layout: "milestones", stages: [] },
      ],
      taskStates: {}, decisions: {}, assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: [] },
    },
  });

  assert.deepEqual(
    workbench.workspaceView(state).work.domains.map((domain) => domain.name),
    ["资产与治理", "系统建设"],
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
