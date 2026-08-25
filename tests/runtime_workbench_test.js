const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

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

test("workflow task selection updates the active task and selected node", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "model-a",
    adapters: [],
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "research",
      activeTaskId: "PLT-020",
      planApproved: true,
      tasks: [
        { task_id: "PLT-020", line_id: "research", public_label: "任务 20", title: "上游任务", status: "DONE", depends_on: [] },
        { task_id: "PLT-021", line_id: "research", public_label: "任务 21", title: "当前任务", status: "REVIEW", depends_on: ["PLT-020"] },
      ],
      businessLines: [{ line_id: "research", domain_id: "research", name: "科研线", caption: "", layout: "loop", stages: [] }],
      taskStates: { "PLT-020": "DONE", "PLT-021": "REVIEW" },
      decisions: {},
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: [] },
    },
  });

  const selected = workbench.selectWorkflowTask(state, "PLT-021");
  assert.equal(selected.activeTaskId, "PLT-021");
  assert.equal(selected.activeLineId, "research");
  const projection = workbench.workflowProjection(selected, "research");
  const html = workbench.renderWorkflowCanvas(projection, selected.activeTaskId);
  assert.match(html, /data-workflow-task="PLT-021"[^>]*aria-pressed="true"/);
  assert.match(html, /data-workflow-task="PLT-020"[^>]*aria-pressed="false"/);
  const detail = workbench.renderRunDetail(
    { ...state.tasks[1], status: "REVIEW", action: "ACCEPT", attempts: 1, events: [] },
    { runtime: true, defaultModel: "model-a", adapters: [] },
  );
  assert.match(detail, /当前任务/);
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

test("task detail keeps model and adapter details inside settings", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "task-001",
      public_label: "任务 01",
      title: "匿名任务",
      status: "QUEUED",
      action: "DISPATCH",
      attempts: 0,
      assignment: { model: "private-model", executor: "private-adapter" },
      events: [],
    },
    {
      runtime: true,
      defaultModel: "private-model",
      adapters: [{ adapter_id: "private-adapter", available: true }],
    },
  );

  assert.doesNotMatch(html, /private-model/);
  assert.doesNotMatch(html, /private-adapter/);
  assert.doesNotMatch(html, /<dt>模型<\/dt>/);
  assert.doesNotMatch(html, /<dt>执行适配器<\/dt>/);
  assert.match(html, /使用已保存的执行策略/);
});

test("task cards show assignment state without exposing route or adapter identifiers", () => {
  const html = workbench.renderTaskCard({
    task_id: "task-001",
    title: "匿名任务",
    status: "IN_PROGRESS",
    action: "REQUEST_REVIEW",
    complexity: "standard",
    assignment: { route: "private-route", executor: "private-adapter" },
  });

  assert.doesNotMatch(html, /private-route/);
  assert.doesNotMatch(html, /private-adapter/);
  assert.match(html, /已分配/);
});

test("workflow nodes show assignment state without exposing model or adapter identifiers", () => {
  const html = workbench.renderWorkflowNode({
    task_id: "task-002",
    public_label: "任务 02",
    title: "匿名工作节点",
    status: "IN_PROGRESS",
    stage: "执行阶段",
    assignment: { model: "gpt-5.6-sol", executor: "codex-app-server" },
    attempts: 1,
  }, false);

  assert.doesNotMatch(html, /gpt-5\.6-sol/);
  assert.doesNotMatch(html, /codex-app-server/);
  assert.match(html, /已分配/);
});

test("task detail explains why it ran, what it produced, and what follows", () => {
  const task = {
    task_id: "task-result",
    public_label: "任务 02",
    title: "整理实验结果",
    status: "REVIEW",
    action: "ACCEPT",
    attempts: 1,
    depends_on: ["task-input"],
    events: [
      { event_id: "e-1", kind: "assigned", label: "已分配执行器", at: "2026-08-25T23:40:00+08:00", occurred_at: "2026-08-25T23:40:00+08:00", run_id: "run-1" },
      { event_id: "e-2", kind: "artifact_created", label: "阶段产物已登记", at: "2026-08-25T23:42:00+08:00", occurred_at: "2026-08-25T23:42:00+08:00", run_id: "run-1" },
    ],
    result: { status: "REGISTERED", summary: "已形成实验结果摘要", preview: "证据显示假设 A 得到初步支持。", artifact_id: "artifact-1", created_at: "2026-08-25T23:42:00+08:00" },
  };
  const html = workbench.renderRunDetail(
    task,
    {
      runtime: true,
      defaultModel: "model-a",
      adapters: [{ adapter_id: "test-adapter", available: true }],
      tasks: [
        { task_id: "task-input", public_label: "任务 01", title: "整理原始数据", status: "DONE" },
        task,
        { task_id: "task-next", public_label: "任务 03", title: "进入下一轮验证", status: "QUEUED", depends_on: ["task-result"] },
      ],
    },
  );

  assert.match(html, /前因/);
  assert.match(html, /本轮结果/);
  assert.match(html, /后果与下一步/);
  assert.match(html, /整理原始数据/);
  assert.match(html, /已形成实验结果摘要/);
  assert.match(html, /证据显示假设 A 得到初步支持/);
  assert.match(html, /进入下一轮验证/);
  assert.match(html, /2026-08-25 23:40/);
  assert.match(html, /2026-08-25 23:42/);
});

test("task story derives causal inputs and downstream impact from persisted dependency states", () => {
  const task = {
    task_id: "task-result",
    public_label: "任务 02",
    title: "整理实验结果",
    status: "REVIEW",
    action: "ACCEPT",
    attempts: 1,
    line_id: "research-line",
    depends_on: ["task-input"],
    acceptance: "结果摘要可追溯并可供下一轮验证使用",
    result: { status: "REGISTERED", summary: "已形成实验结果摘要", created_at: "2026-08-25T23:42:00+08:00" },
  };
  const html = workbench.renderRunDetail(
    task,
    {
      runtime: true,
      defaultModel: "model-a",
      adapters: [{ adapter_id: "test-adapter", available: true }],
      businessLines: [{ line_id: "research-line", name: "科研线", caption: "问题、证据与下一轮验证" }],
      tasks: [
        {
          task_id: "task-input",
          public_label: "任务 01",
          title: "整理原始数据",
          status: "DONE",
          result: { status: "REGISTERED", summary: "原始数据已完成清洗", created_at: "2026-08-25T23:30:00+08:00" },
        },
        task,
        { task_id: "task-next", public_label: "任务 03", title: "进入下一轮验证", status: "QUEUED", depends_on: ["task-result"], acceptance: "完成验证方案" },
      ],
    },
  );

  assert.match(html, /上游已完成/);
  assert.match(html, /原始数据已完成清洗/);
  assert.match(html, /下游待启动/);
  assert.match(html, /任务 03/);
  assert.match(html, /等待本任务收口/);
  assert.doesNotMatch(html, /继续寻找下游任务/);
});

test("task story keeps long causal text inside the detail panel", () => {
  const css = fs.readFileSync(require.resolve("../workbench/style.css"), "utf8");
  assert.match(css, /\.story-block(?:\s*,\s*\.story-block \*)?[^}]*overflow-wrap:\s*anywhere/);
  assert.match(css, /\.story-block(?:\s*,\s*\.story-block \*)?[^}]*min-width:\s*0/);
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

  assert.match(html, /data-bind-codex-project/);
  assert.match(html, /data-bind-openai/);
  assert.match(html, /type="password"/);
  assert.match(html, /autocomplete="new-password"/);
  assert.match(html, /data-save-routes/);
  assert.match(html, /research-deep/);
});

test("private settings bind the active workline to a native Codex project", () => {
  const html = workbench.renderSettings({
    runtime: true,
    activeLineId: "science",
    activeDomainId: "research",
    businessLines: [
      { line_id: "science", domain_id: "research", name: "科研主线" },
    ],
    execution: { advance_route_mode: "fixed", task_dispatch_ready: true },
    adapters: [
      { adapter_id: "codex-project", available: true, protocol: "codex-project-bridge" },
    ],
    executionSettings: {
      writable: true,
      mode: "fixed",
      default_adapter_id: "codex-project",
      credential_source: "codex-session",
      routes: [],
      codex_projects: [
        {
          project_key: "science-workspace",
          label: "AI Workspace",
          path: "/workspace/ai-os",
          workflow_ids: ["science"],
          domain_ids: [],
          environment: "worktree",
        },
      ],
    },
    cognitiveLearning: { proposed: 0, approved: 0 },
  });

  assert.match(html, /Codex 项目/);
  assert.match(html, /AI Workspace/);
  assert.match(html, /科研主线/);
  assert.match(html, /\/workspace\/ai-os/);
  assert.match(html, /id="codex-project-path"/);
  assert.match(html, /data-bind-codex-project/);
  assert.doesNotMatch(html, /自动绑定 Codex/);
});

test("task detail shows the native Codex project execution state", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "science:hypothesis",
      public_label: "任务 01",
      title: "科研任务",
      status: "IN_PROGRESS",
      action: "REQUEST_REVIEW",
      attempts: 1,
      events: [],
      codex_dispatch: {
        status: "RUNNING",
        project: { label: "科研项目", environment: "worktree" },
        thread_id: "codex-thread-1",
        project_id: "codex-project-1",
      },
    },
    { runtime: true, defaultModel: "model-a", adapters: [{ adapter_id: "codex-project", available: true }] },
  );

  assert.match(html, /Codex 项目执行/);
  assert.match(html, /科研项目/);
  assert.match(html, /已绑定原生任务/);
  assert.match(html, /codex-thread-1/);
});

test("task detail keeps a completed Codex receipt visible for review", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "science:hypothesis",
      public_label: "任务 01",
      title: "科研任务",
      status: "REVIEW",
      action: "ACCEPT",
      attempts: 1,
      events: [],
      codex_dispatch: {
        status: "SUCCEEDED",
        project: { label: "科研项目", environment: "worktree" },
        thread_id: "codex-thread-1",
        project_id: "codex-project-1",
      },
    },
    { runtime: true, defaultModel: "model-a", adapters: [{ adapter_id: "codex-project", available: true }] },
  );

  assert.match(html, /结果已登记，等待验收/);
  assert.match(html, /codex-thread-1/);
  assert.match(html, /codex-project-1/);
});

test("task detail marks a legacy Codex result without a terminal receipt for manual review", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "science:hypothesis",
      public_label: "任务 01",
      title: "科研任务",
      status: "REVIEW",
      action: "ACCEPT",
      attempts: 1,
      events: [],
      codex_dispatch: {
        status: "SUCCEEDED",
        project: { label: "科研项目", environment: "worktree" },
        thread_id: "codex-thread-legacy",
        project_id: "codex-project-1",
        completion_receipt: {},
      },
    },
    { runtime: true, defaultModel: "model-a", adapters: [{ adapter_id: "codex-project", available: true }] },
  );

  assert.match(html, /历史终态回执缺失/);
  assert.match(html, /需人工复核/);
});

test("task detail does not verify a receipt that still needs a user decision", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "science:hypothesis",
      public_label: "任务 01",
      title: "科研任务",
      status: "REVIEW",
      action: "ACCEPT",
      attempts: 1,
      events: [],
      codex_dispatch: {
        status: "SUCCEEDED",
        project: { label: "科研项目", environment: "worktree" },
        thread_id: "codex-thread-gated",
        project_id: "codex-project-1",
        completion_receipt: {
          status: "completed",
          verified: true,
          needs_user_input: true,
          human_gate: false,
        },
      },
    },
    { runtime: true, defaultModel: "model-a", adapters: [{ adapter_id: "codex-project", available: true }] },
  );

  assert.match(html, /历史终态回执缺失/);
  assert.doesNotMatch(html, /终态回执已验证/);
});

test("task detail exposes Codex ownership and the reason a receipt needs review", () => {
  const html = workbench.renderRunDetail(
    {
      task_id: "science:hypothesis",
      public_label: "任务 01",
      title: "科研任务",
      status: "REVIEW",
      action: "ACCEPT",
      attempts: 1,
      events: [],
      codex_dispatch: {
        status: "SUCCEEDED",
        project: { label: "科研项目", environment: "worktree" },
        ownership: {
          project_id: "codex-project-1",
          project_path: "/tmp/science-project",
          environment: "worktree",
          thread_id: "codex-thread-gated",
          host_id: "local",
          verified: true,
          verification_source: "thread-project-assignments",
        },
        thread_id: "codex-thread-gated",
        project_id: "codex-project-1",
        manual_review_reason: "USER_INPUT_REQUIRED",
        receipt_state: "UNVERIFIED",
        completion_receipt: {
          status: "completed",
          verified: true,
          needs_user_input: true,
          human_gate: false,
        },
      },
    },
    { runtime: true, defaultModel: "model-a", adapters: [{ adapter_id: "codex-project", available: true }] },
  );

  assert.match(html, /项目归属已核验/);
  assert.match(html, /等待用户输入/);
  assert.doesNotMatch(html, /终态回执已验证/);
});

test("Codex project binding replaces only the active workline mapping", () => {
  const payload = workbench.codexProjectSettingsPayload({
    activeLineId: "science",
    executionSettings: {
      codex_projects: [
        { project_key: "science-old", label: "旧科研项目", path: "/old", workflow_ids: ["science"], domain_ids: [], environment: "local" },
        { project_key: "writing", label: "写作项目", path: "/writing", workflow_ids: ["writing"], domain_ids: [], environment: "worktree" },
      ],
    },
  }, {
    label: "AI Workspace",
    path: "/workspace/ai-os",
    environment: "worktree",
    model: "gpt-5.6-sol",
  });

  assert.equal(payload.adapter.kind, "codex-project");
  assert.equal(payload.adapter.projects.length, 2);
  assert.deepEqual(payload.adapter.projects.find((item) => item.workflow_ids.includes("science")), {
    project_key: "science-old",
    label: "AI Workspace",
    path: "/workspace/ai-os",
    workflow_ids: ["science"],
    domain_ids: [],
    environment: "worktree",
  });
  assert.equal(payload.adapter.projects.find((item) => item.workflow_ids.includes("writing")).label, "写作项目");
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

test("runtime client reads execution settings without mutating them", async () => {
  const calls = [];
  const client = workbench.createRuntimeClient(async (url, options = {}) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() { return { status: "READY" }; },
    };
  });

  await client.loadExecutionSettings();

  assert.deepEqual(calls, [{ url: "/api/settings/execution", options: {} }]);
});

test("workbench assets use the current v0.17 cache version", () => {
  const page = fs.readFileSync(require.resolve("../workbench/index.html"), "utf8");
  assert.match(page, /v=0\.17\.0/);
  assert.match(page, /· v0\.17\.0<\/footer>/);
  assert.doesNotMatch(page, /v=0\.15\.0|v0\.15\.0/);
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

test("runtime refresh preserves the reader's viewport position", () => {
  const viewport = {
    scrollX: 24,
    scrollY: 860,
    scrollTo({ left, top }) {
      this.scrollX = left;
      this.scrollY = top;
    },
  };

  workbench.preserveViewportPosition(viewport, () => {
    viewport.scrollX = 0;
    viewport.scrollY = 0;
  });

  assert.equal(viewport.scrollX, 24);
  assert.equal(viewport.scrollY, 860);
});

test("a workline waiting for review does not pretend it can open another Codex task", () => {
  const state = workbench.runtimeStateFromPayload({
    status: "READY",
    data_source: "runtime",
    default_model: "",
    adapters: [{ adapter_id: "codex-app-server", available: true }],
    execution: {
      advance_route_mode: "automatic",
      advance_ready: true,
      task_dispatch_ready: true,
    },
    state: {
      goal: "Persistent goal",
      activeBoard: "work",
      activeLineId: "private-authority",
      activeTaskId: "PLT-001",
      planApproved: true,
      tasks: [
        { task_id: "PLT-001", line_id: "private-authority", title: "First", acceptance: "Review", depends_on: [], status: "REVIEW" },
        { task_id: "PLT-002", line_id: "private-authority", title: "Second", acceptance: "Run", depends_on: ["PLT-001"], status: "QUEUED" },
      ],
      businessLines: [{ line_id: "private-authority", domain_id: "governance", name: "Private", caption: "", layout: "milestones", stages: [] }],
      taskStates: { "PLT-001": "REVIEW", "PLT-002": "QUEUED" },
      decisions: {},
      assignments: {},
      onboarding: { status: "RUNTIME_READY", readOnly: false, detectedLines: [] },
    },
  });

  assert.deepEqual(workbench.worklineAdvanceState(state, ["PLT-001", "PLT-002"]), {
    canAdvance: false,
    reason: "WAITING_REVIEW",
    message: "1 项结果等待验收",
    actionLabel: "先验收当前结果",
  });
});

test("an independent ready task keeps a workline runnable while another result waits for review", () => {
  const state = workbench.createDemoState();
  state.planApproved = true;
  state.tasks = [
    { task_id: "review", line_id: "line", depends_on: [], status: "REVIEW" },
    { task_id: "ready", line_id: "line", depends_on: [], status: "QUEUED" },
  ];
  state.taskStates = { review: "REVIEW", ready: "QUEUED" };

  assert.deepEqual(workbench.worklineAdvanceState(state, ["review", "ready"]), {
    canAdvance: true,
    reason: "READY",
    message: "1 项任务可以启动",
    actionLabel: "推进当前工作线",
  });
});
