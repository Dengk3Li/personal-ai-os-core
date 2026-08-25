(function (root, factory) {
  const architecture = typeof module === "object" && module.exports
    ? require("./architecture.js")
    : root.PersonalAIArchitecture;
  const api = factory(architecture);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PersonalAIWorkbench = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (architecture) {
  "use strict";

  const TASKS = [
    { task_id: "scope", line_id: "research", title: "确认研究问题与边界", acceptance: "问题、范围和排除项得到确认", depends_on: [], human_gate: true, complexity: "standard", capabilities: ["research"], estimated_tokens: 18000 },
    { task_id: "evidence", line_id: "research", title: "建立材料与来源地图", acceptance: "主要问题能够对应到可追溯材料", depends_on: ["scope"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 120000 },
    { task_id: "architecture", line_id: "product", title: "定义模块与操作契约", acceptance: "模块输入、输出、依赖和操作边界明确", depends_on: [], human_gate: false, complexity: "deep", capabilities: ["engineering"], estimated_tokens: 68000 },
    { task_id: "interface", line_id: "product", title: "重塑长期工作界面", acceptance: "三入口与动态业务线能够完整操作", depends_on: ["architecture"], human_gate: false, complexity: "standard", capabilities: ["engineering"], estimated_tokens: 52000 },
    { task_id: "materials", line_id: "writing", title: "整理项目叙事材料", acceptance: "痛点、机制与使用场景形成统一提纲", depends_on: [], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 26000 },
    { task_id: "draft", line_id: "writing", title: "撰写项目介绍", acceptance: "介绍能够脱离对话独立说明产品价值", depends_on: ["materials"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 42000 },
    { task_id: "release", line_id: "writing", title: "确认公开封包", acceptance: "公开范围、文案和演示内容得到最终确认", depends_on: ["evidence", "interface", "draft"], human_gate: true, complexity: "standard", capabilities: ["research", "writing"], estimated_tokens: 36000 },
  ];

  const BUSINESS_LINES = [
    { line_id: "research", name: "科研线", caption: "科学假设、实验方案、自主实验、数据分析与反馈优化", layout: "loop", stages: ["科学假设", "实验方案设计", "自主实验", "分析与反馈"], traceStatus: "PRESET_READY", note: "科学假设、实验方案设计、自主实验执行、数据分析与反馈优化五类角色共用同一任务状态源。" },
    { line_id: "product", name: "产品线", caption: "模块、能力与版本里程碑", layout: "milestones", stages: ["系统契约", "核心骨架", "交互实现", "版本验收"] },
    { line_id: "writing", name: "写作线", caption: "资料、结构与长文交付", layout: "pipeline", stages: ["材料整理", "结构确认", "分段写作", "终稿验收"] },
  ];

  const SHOWCASE_WORKFLOWS = [
    { line_id: "research", name: "科研线", caption: "五类角色协作 · 多实验路径 · 反馈进入下一轮", layout: "loop", stages: ["科学假设", "实验方案设计", "自主实验", "数据分析与反馈"] },
    { line_id: "meeting-notes", name: "会议纪要", caption: "原始材料、信息抽取、初稿与内容审核", layout: "milestones", stages: ["获取原件", "信息抽取", "生成初稿", "审核定稿"] },
    { line_id: "industry-report", name: "行业研究 / 专业报告", caption: "全网收集、证据池、报告规划、章节生产与视觉呈现", layout: "branch", stages: ["广泛收集", "证据池", "论证规划", "写作与视觉"] },
  ];

  const SHOWCASE_TASKS = [
    { task_id: "flow-a-01", public_label: "任务 A-01", line_id: "research", agent_role: "科学假设角色", stage: "澄清问题、识别缺口与生成假设", flow_kind: "loop", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 68000 },
    { task_id: "flow-a-02", public_label: "任务 A-02", line_id: "research", agent_role: "实验方案设计角色", stage: "实验路径 α · 设计与质量控制", flow_kind: "branch", iteration: 2, parallel_group: "branch-alpha", attempts: 2, depends_on: ["flow-a-01"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 82000 },
    { task_id: "flow-a-03", public_label: "任务 A-03", line_id: "research", agent_role: "实验方案设计角色", stage: "实验路径 β · 设计与质量控制", flow_kind: "branch", iteration: 2, parallel_group: "branch-beta", attempts: 2, depends_on: ["flow-a-01"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 82000 },
    { task_id: "flow-a-04", public_label: "任务 A-04", line_id: "research", agent_role: "自主实验执行角色", stage: "路径 α · 动作编排与异常诊断", iteration: 3, parallel_group: "branch-alpha", attempts: 1, depends_on: ["flow-a-02"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 96000 },
    { task_id: "flow-a-05", public_label: "任务 A-05", line_id: "research", agent_role: "自主实验执行角色", stage: "路径 β · 动作编排与异常诊断", iteration: 3, parallel_group: "branch-beta", attempts: 0, depends_on: ["flow-a-03"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 96000 },
    { task_id: "flow-a-06", public_label: "任务 A-06", line_id: "research", agent_role: "数据分析角色", stage: "证据更新、数据分析与结论产出", flow_kind: "join", iteration: 4, parallel_group: "main", attempts: 0, depends_on: ["flow-a-04", "flow-a-05"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 76000 },
    { task_id: "flow-a-07", public_label: "任务 A-07", line_id: "research", agent_role: "反馈优化角色", stage: "判断是否进入下一轮并更新路径", flow_kind: "condition", iteration: 4, parallel_group: "gate", attempts: 0, depends_on: ["flow-a-06"], human_gate: true, complexity: "deep", capabilities: ["research"], estimated_tokens: 36000 },
    { task_id: "flow-b-01", public_label: "任务 B-01", line_id: "meeting-notes", agent_role: "材料摄取角色", stage: "获取录音、演示材料与项目资料原件", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 18000 },
    { task_id: "flow-b-02", public_label: "任务 B-02", line_id: "meeting-notes", agent_role: "信息抽取角色", stage: "抽取事实、观点、数字与待确认项", iteration: 2, parallel_group: "main", attempts: 1, depends_on: ["flow-b-01"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 32000 },
    { task_id: "flow-b-03", public_label: "任务 B-03", line_id: "meeting-notes", agent_role: "初稿生成角色", stage: "生成结构化会议纪要初稿", iteration: 3, parallel_group: "main", attempts: 3, depends_on: ["flow-b-02"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 44000 },
    { task_id: "flow-b-04", public_label: "任务 B-04", line_id: "meeting-notes", agent_role: "内容审核角色", stage: "核对归因、遗漏与表达边界", iteration: 4, parallel_group: "gate", attempts: 0, depends_on: ["flow-b-03"], human_gate: true, complexity: "deep", capabilities: ["writing"], estimated_tokens: 42000 },
    { task_id: "flow-b-05", public_label: "任务 B-05", line_id: "meeting-notes", agent_role: "交付角色", stage: "定稿并生成可交付版本", iteration: 5, parallel_group: "main", attempts: 0, depends_on: ["flow-b-04"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 26000 },
    { task_id: "flow-c-01", public_label: "任务 C-01", line_id: "industry-report", agent_role: "广域检索角色", stage: "全网广泛收集信息与来源", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 120000 },
    { task_id: "flow-c-02", public_label: "任务 C-02", line_id: "industry-report", agent_role: "证据池整理角色", stage: "建立证据池并提取结构化数据", iteration: 2, parallel_group: "main", attempts: 1, depends_on: ["flow-c-01"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 120000 },
    { task_id: "flow-c-03", public_label: "任务 C-03", line_id: "industry-report", agent_role: "报告规划角色", stage: "多轮沟通形成结构与论证线", iteration: 3, parallel_group: "plan", attempts: 1, depends_on: ["flow-c-02"], human_gate: false, complexity: "deep", capabilities: ["research", "writing"], estimated_tokens: 96000 },
    { task_id: "flow-c-04", public_label: "任务 C-04", line_id: "industry-report", agent_role: "视觉规划角色", stage: "规划图表、配图与版式说明", iteration: 3, parallel_group: "visual", attempts: 1, depends_on: ["flow-c-02"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 42000 },
    { task_id: "flow-c-05", public_label: "任务 C-05", line_id: "industry-report", agent_role: "章节写作角色", stage: "按章节动态分配模型并行撰写", iteration: 4, parallel_group: "chapters", attempts: 0, depends_on: ["flow-c-03", "flow-c-04"], human_gate: false, complexity: "deep", capabilities: ["writing"], estimated_tokens: 120000 },
    { task_id: "flow-c-06", public_label: "任务 C-06", line_id: "industry-report", agent_role: "排版与配图角色", stage: "统一排版、配图与最终审核", iteration: 5, parallel_group: "gate", attempts: 0, depends_on: ["flow-c-05"], human_gate: true, complexity: "deep", capabilities: ["writing"], estimated_tokens: 76000 },
  ];

  const MODULES = [
    { contract_version: "personal-ai-os.module/v1", module_id: "workspace-intake", name: "本地工作区摄取", layer: "输入", summary: "只读识别文件结构、项目类型和已有状态。", provides: ["workspace.snapshot"], requires: [], availability: "READY", optional: false, entrypoint: "builtin://workspace-intake" },
    { contract_version: "personal-ai-os.module/v1", module_id: "cognitive-intake", name: "认知摄取", layer: "理解", summary: "把材料整理成可检索、可判断的知识候选。", provides: ["knowledge.candidates"], requires: ["workspace.snapshot"], availability: "READY", optional: true, entrypoint: "builtin://cognitive-intake" },
    { contract_version: "personal-ai-os.module/v1", module_id: "workflow-core", name: "长期工作内核", layer: "编排", summary: "建立业务线、任务依赖、状态和人工裁决点。", provides: ["work.plan", "work.task"], requires: ["workspace.snapshot"], availability: "READY", optional: false, entrypoint: "builtin://workflow-core" },
    { contract_version: "personal-ai-os.module/v1", module_id: "dynamic-router", name: "动态路由", layer: "编排", summary: "按复杂度、能力和上下文预算选择执行层。", provides: ["execution.route"], requires: ["work.task"], availability: "READY", optional: true, entrypoint: "builtin://dynamic-router" },
    { contract_version: "personal-ai-os.module/v1", module_id: "execution-adapter", name: "执行适配器", layer: "执行", summary: "把短任务交给兼容的模型或执行者。", provides: ["execution.result"], requires: ["execution.route"], availability: "READY", optional: true, entrypoint: "builtin://execution-adapter" },
    { contract_version: "personal-ai-os.module/v1", module_id: "continuity", name: "连续性与接续", layer: "记忆", summary: "保存当前状态，让下一次对话从真实进度继续。", provides: ["workspace.resume"], requires: ["work.task", "execution.result"], availability: "READY", optional: true, entrypoint: "builtin://continuity" },
    { contract_version: "personal-ai-os.module/v1", module_id: "token-manager", name: "Token Manager", layer: "观测", summary: "规划任务预算、上下文窗口和使用量展示。", provides: ["token.budget"], requires: ["work.task"], availability: "PLANNED", optional: true, entrypoint: "builtin://token-manager" },
  ];

  const PRIMARY_BOARDS = [
    { id: "global", label: "模块地图", summary: "系统由哪些积木组成" },
    { id: "work", label: "工作进度", summary: "多条业务线如何推进" },
    { id: "decision", label: "待我决定", summary: "需要你裁决的节点" },
  ];

  const ROUTES = [
    { route: "quick", model: "Fast model", tier: 1, max_tokens: 64000, capabilities: ["writing"] },
    { route: "standard", model: "Standard reasoning", tier: 2, max_tokens: 100000, capabilities: ["research", "writing", "engineering"] },
    { route: "deep", model: "Deep reasoning", tier: 3, max_tokens: 240000, capabilities: ["research", "writing", "engineering"] },
  ];

  const EXECUTORS = [
    { executor: "研究执行器", routes: ["standard", "deep"], capabilities: ["research", "writing"] },
    { executor: "产品执行器", routes: ["standard", "deep"], capabilities: ["engineering"] },
    { executor: "写作执行器", routes: ["quick", "standard"], capabilities: ["writing"] },
  ];

  const OPERATION_CHAIN = ["检查", "建图", "规划", "确认", "路由", "执行", "验收", "归档"];
  const PET_PREFERENCES = new Set(["blue-whale-maid", "model-animal", "off"]);

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function runtimeStateFromPayload(payload) {
    if (!payload || payload.status !== "READY" || payload.data_source !== "runtime" || !payload.state) {
      throw new Error("RUNTIME_STATE_UNAVAILABLE");
    }
    return {
      ...clone(payload.state),
      runtime: true,
      dataSource: "runtime",
      defaultModel: payload.default_model || "",
      adapters: clone(payload.adapters || []),
      pendingDecisions: clone(payload.state.pendingDecisions || []),
      petPreference: "blue-whale-maid",
    };
  }

  function createRuntimeClient(fetchFn) {
    if (typeof fetchFn !== "function") return null;
    async function request(url, options) {
      const response = await fetchFn(url, options);
      let payload = {};
      try { payload = await response.json(); } catch (_error) { payload = {}; }
      if (!response.ok) {
        const error = new Error(payload.reason || payload.error || `HTTP_${response.status}`);
        error.payload = payload;
        throw error;
      }
      return payload;
    }
    function post(url, payload) {
      return request(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    return {
      load: () => request("/api/runtime"),
      runTask: (taskId, adapterId, model) => post("/api/runs", { task_id: taskId, adapter_id: adapterId, model }),
      advance: (adapterId, model, maxSteps = 25, workflowId = null) => post("/api/advance", { adapter_id: adapterId, model, max_steps: maxSteps, failure_budget: 1, workflow_id: workflowId }),
      transitionTask: (taskId, to, reason) => post(`/api/tasks/${encodeURIComponent(taskId)}/transition`, { to, reason, by: "owner" }),
      createTask: (task) => post("/api/tasks", task),
      createWorkflow: (workflow) => post("/api/workflows", workflow),
      resolveDecision: (decisionId, selectedOption) => post(`/api/decisions/${encodeURIComponent(decisionId)}/resolve`, { selected_option: selectedOption, by: "owner" }),
    };
  }

  async function runTaskWithPolling(
    runTask,
    refresh,
    schedule = (callback) => setInterval(callback, 400),
    cancel = (timer) => clearInterval(timer),
  ) {
    let refreshing = false;
    const timer = schedule(() => {
      if (refreshing) return;
      refreshing = true;
      Promise.resolve(refresh()).catch(() => {}).finally(() => { refreshing = false; });
    });
    try {
      return await runTask();
    } finally {
      cancel(timer);
      await refresh();
    }
  }

  function createDemoState() {
    return {
      goal: "把一个复杂工作区变成可理解、可裁决、可持续推进的长期工作系统",
      activeBoard: "work",
      activeLineId: "research",
      planApproved: false,
      tasks: clone(TASKS),
      businessLines: clone(BUSINESS_LINES),
      taskStates: Object.fromEntries(TASKS.map((task) => [task.task_id, "QUEUED"])),
      decisions: {},
      assignments: {},
      onboarding: { status: "NOT_STARTED", readOnly: true, detectedLines: [] },
      activeTemplate: null,
      taskProposal: null,
      petPreference: "blue-whale-maid",
    };
  }

  function setPetPreference(state, preference) {
    const next = clone(state);
    next.petPreference = PET_PREFERENCES.has(preference) ? preference : "blue-whale-maid";
    return next;
  }

  function runEvents(taskId, attempts, status) {
    if (!attempts) return [];
    const events = [
      { kind: "assigned", label: "已分配执行器", at: "09:12" },
      { kind: "adapter_started", label: "适配器已启动", at: "09:13" },
      { kind: "heartbeat", label: "运行心跳正常", at: "09:18" },
    ];
    if (["REVIEW", "DONE", "ARCHIVED"].includes(status)) {
      events.push({ kind: "artifact", label: "阶段产物已登记", at: "09:26" });
    }
    if (attempts > 1) {
      events.unshift({ kind: "retry", label: `前一轮已保留 · 当前第 ${attempts} 次运行`, at: "09:08" });
    }
    return events.map((event) => ({ ...event, event_id: `${taskId}-${event.kind}` }));
  }

  function createShowcaseState() {
    const statuses = {
      "flow-a-01": "DONE", "flow-a-02": "DONE", "flow-a-03": "IN_PROGRESS", "flow-a-04": "IN_PROGRESS", "flow-a-05": "QUEUED", "flow-a-06": "QUEUED", "flow-a-07": "BLOCKED",
      "flow-b-01": "DONE", "flow-b-02": "DONE", "flow-b-03": "IN_PROGRESS", "flow-b-04": "QUEUED", "flow-b-05": "QUEUED",
      "flow-c-01": "DONE", "flow-c-02": "DONE", "flow-c-03": "REVIEW", "flow-c-04": "REVIEW", "flow-c-05": "QUEUED", "flow-c-06": "QUEUED",
    };
    const assignmentSpecs = {
      "flow-a-01": ["deep", "推理模型", "科学假设角色"],
      "flow-a-02": ["deep", "推理模型", "实验方案设计角色"],
      "flow-a-03": ["deep", "推理模型", "实验方案设计角色"],
      "flow-a-04": ["standard", "通用模型", "自主实验执行角色"],
      "flow-b-01": ["standard", "长上下文模型", "材料摄取角色"],
      "flow-b-02": ["standard", "通用模型", "信息抽取角色"],
      "flow-b-03": ["standard", "写作模型", "初稿生成角色"],
      "flow-c-01": ["deep", "研究模型", "广域检索角色"],
      "flow-c-02": ["deep", "研究模型", "证据池整理角色"],
      "flow-c-03": ["deep", "推理模型", "报告规划角色"],
      "flow-c-04": ["standard", "通用模型", "视觉规划角色"],
    };
    const assignments = Object.fromEntries(Object.entries(assignmentSpecs).map(([taskId, values]) => [taskId, { route: values[0], model: values[1], executor: values[2] }]));
    const tasks = clone(SHOWCASE_TASKS).map((task) => ({
      ...task,
      events: runEvents(task.task_id, task.attempts, statuses[task.task_id]),
    }));
    return {
      goal: "把长期目标拆成可分配、可重复运行、可由人类裁决的短任务",
      activeBoard: "work",
      activeLineId: "research",
      activeTaskId: "flow-a-03",
      planApproved: true,
      privacy: { taskDetails: "ANONYMIZED" },
      tasks,
      businessLines: clone(SHOWCASE_WORKFLOWS),
      taskStates: statuses,
      decisions: {},
      assignments,
      onboarding: { status: "SHOWCASE_READY", readOnly: true, detectedLines: [] },
      activeTemplate: null,
      taskProposal: null,
      petPreference: "blue-whale-maid",
    };
  }

  function selectBoard(state, board) {
    const next = clone(state);
    next.activeBoard = PRIMARY_BOARDS.some((item) => item.id === board) ? board : "work";
    return next;
  }

  function selectBusinessLine(state, lineId) {
    const next = clone(state);
    if (next.businessLines.some((line) => line.line_id === lineId)) {
      next.activeLineId = lineId;
      const lineTasks = next.tasks.filter((task) => task.line_id === lineId);
      const active = lineTasks.find((task) => next.taskStates[task.task_id] === "IN_PROGRESS") || lineTasks[0];
      next.activeTaskId = active ? active.task_id : null;
    }
    return next;
  }

  function createWorkline(state, requestedName) {
    const next = clone(state);
    const sequence = next.businessLines.filter((line) => line.user_created).length + 1;
    const name = String(requestedName || "").trim().slice(0, 40) || `新工作线 ${sequence}`;
    let lineId = `custom-${sequence}`;
    while (next.businessLines.some((line) => line.line_id === lineId)) lineId = `custom-${Number(lineId.split("-").at(-1)) + 1}`;
    next.businessLines.push({
      line_id: lineId,
      name,
      caption: "自定义工作流 · 等待添加任务",
      layout: "custom",
      stages: [],
      user_created: true,
    });
    next.activeLineId = lineId;
    next.activeTaskId = null;
    next.activeBoard = "work";
    return next;
  }

  function approvePlan(state) {
    const next = clone(state);
    next.planApproved = true;
    next.onboarding.status = "READY";
    return next;
  }

  function recordDecision(state, taskId, decision) {
    const next = clone(state);
    next.decisions[taskId] = decision;
    if (decision === "REJECTED") next.taskStates[taskId] = "BLOCKED";
    return next;
  }

  function taskById(state, taskId) {
    return state.tasks.find((task) => task.task_id === taskId);
  }

  function actionForTask(state, taskId) {
    const task = taskById(state, taskId);
    if (!task) return "UNKNOWN_TASK";
    if (!state.planApproved) return "PLAN_APPROVAL_REQUIRED";
    const current = state.taskStates[taskId];
    if (["DONE", "ARCHIVED"].includes(current)) return "NONE";
    if (current === "BLOCKED") return "BLOCKED";
    if (current === "PAUSED") return "RESUME";
    if (task.depends_on.some((dependency) => !["DONE", "ARCHIVED"].includes(state.taskStates[dependency]))) return "WAITING_DEPENDENCY";
    const recordedDecision = state.runtime
      ? state.decisions[taskId] && state.decisions[taskId] !== "PENDING"
      : state.decisions[taskId] === "APPROVED";
    if (task.human_gate && !recordedDecision) return "HUMAN_DECISION_REQUIRED";
    if (current === "QUEUED") return "DISPATCH";
    if (current === "IN_PROGRESS") return "REQUEST_REVIEW";
    if (current === "REVIEW") return "ACCEPT";
    return "NONE";
  }

  function routeTask(task) {
    const requiredTier = { quick: 1, standard: 2, deep: 3 }[task.complexity] || 2;
    return ROUTES.find((route) => route.tier >= requiredTier && route.max_tokens >= task.estimated_tokens && task.capabilities.every((capability) => route.capabilities.includes(capability)));
  }

  function assignTask(task, route) {
    return EXECUTORS.find((executor) => executor.routes.includes(route.route) && task.capabilities.every((capability) => executor.capabilities.includes(capability)));
  }

  function applyTaskAction(state, taskId) {
    const action = actionForTask(state, taskId);
    const next = clone(state);
    if (action === "DISPATCH") {
      const task = taskById(next, taskId);
      const route = routeTask(task);
      const executor = route && assignTask(task, route);
      if (!route || !executor) {
        next.taskStates[taskId] = "BLOCKED";
        return next;
      }
      next.assignments[taskId] = { route: route.route, model: route.model, executor: executor.executor };
      next.taskStates[taskId] = "IN_PROGRESS";
      if (Object.hasOwn(task, "attempts")) {
        task.attempts += 1;
        task.events = runEvents(taskId, task.attempts, "IN_PROGRESS");
      }
    } else if (action === "REQUEST_REVIEW") {
      next.taskStates[taskId] = "REVIEW";
      const task = taskById(next, taskId);
      if (task && Array.isArray(task.events) && !task.events.some((event) => event.kind === "artifact")) {
        task.events.push({ event_id: `${taskId}-artifact`, kind: "artifact", label: "阶段产物已登记", at: "09:26" });
      }
    } else if (action === "ACCEPT") {
      next.taskStates[taskId] = "DONE";
      const task = taskById(next, taskId);
      if (task && Array.isArray(task.events)) task.events.push({ event_id: `${taskId}-accepted`, kind: "accepted", label: "人工验收已通过", at: "09:31" });
    }
    return next;
  }

  function progress(state, taskIds) {
    const ids = taskIds || state.tasks.map((task) => task.task_id);
    const done = ids.filter((taskId) => ["DONE", "ARCHIVED"].includes(state.taskStates[taskId])).length;
    return { done, total: ids.length, percent: ids.length ? Math.floor(done * 100 / ids.length) : 0 };
  }

  function viewModel(state) {
    const lanes = { QUEUED: [], IN_PROGRESS: [], REVIEW: [], BLOCKED: [], PAUSED: [], DONE: [], ARCHIVED: [] };
    const tasks = {};
    state.tasks.forEach((task) => {
      const status = state.taskStates[task.task_id] || "QUEUED";
      if (lanes[status]) lanes[status].push(task.task_id);
      tasks[task.task_id] = { ...task, status, action: actionForTask(state, task.task_id), assignment: state.assignments[task.task_id] || null, decision: state.decisions[task.task_id] || "PENDING" };
    });
    const pendingHumanGates = state.tasks.filter((task) => task.human_gate && !state.decisions[task.task_id]).length;
    return { goal: state.goal, planApproved: state.planApproved, progress: progress(state), pendingHumanGates, lanes, tasks };
  }

  function workflowSummary(state, taskIds) {
    const allowed = taskIds ? new Set(taskIds) : null;
    const tasks = allowed ? state.tasks.filter((task) => allowed.has(task.task_id)) : state.tasks;
    const completedStates = ["DONE", "ARCHIVED"];
    const allocationCounts = {};
    Object.entries(state.assignments || {}).forEach(([taskId, assignment]) => {
      if (!taskById(state, taskId) || (allowed && !allowed.has(taskId))) return;
      const key = `${assignment.model} · ${assignment.executor}`;
      allocationCounts[key] = (allocationCounts[key] || 0) + 1;
    });
    return {
      total: tasks.length,
      assigned: Object.keys(state.assignments || {}).filter((taskId) => Boolean(taskById(state, taskId)) && (!allowed || allowed.has(taskId))).length,
      running: tasks.filter((task) => state.taskStates[task.task_id] === "IN_PROGRESS").length,
      review: tasks.filter((task) => state.taskStates[task.task_id] === "REVIEW").length,
      completed: tasks.filter((task) => completedStates.includes(state.taskStates[task.task_id])).length,
      repeatedRuns: tasks.reduce((total, task) => total + Math.max(0, (task.attempts || 0) - 1), 0),
      allocation: Object.entries(allocationCounts).map(([label, tasks]) => ({ label, tasks })).sort((left, right) => right.tasks - left.tasks || left.label.localeCompare(right.label)),
    };
  }

  function workflowProjection(state, workflowId) {
    const workflow = state.businessLines.find((line) => line.line_id === workflowId);
    if (!workflow) return null;
    const tasks = state.tasks.filter((task) => task.line_id === workflowId).map((task) => ({
      ...task,
      flow_kind: inferFlowKind(task, workflow),
      status: state.taskStates[task.task_id] || "QUEUED",
      assignment: state.assignments[task.task_id] || null,
      events: clone(task.events || []),
    }));
    const iterations = [...new Set(tasks.map((task) => task.iteration || 1))].sort((left, right) => left - right);
    return {
      workflow_id: workflow.line_id,
      name: workflow.name,
      caption: workflow.caption,
      layout: workflow.layout,
      groups: iterations.map((iteration) => ({
        iteration,
        nodes: tasks.filter((task) => (task.iteration || 1) === iteration),
      })),
    };
  }

  function inferFlowKind(task, workflow = {}) {
    if (["sequence", "branch", "join", "condition", "loop"].includes(task.flow_kind)) return task.flow_kind;
    if (task.human_gate) return "condition";
    if ((task.depends_on || []).length > 1) return "join";
    if (task.parallel_group && !["main", "gate"].includes(task.parallel_group)) return "branch";
    if (workflow.layout === "loop" && /反馈|下一轮|复核/.test(`${task.agent_role || ""}${task.stage || task.title || ""}`)) return "loop";
    return "sequence";
  }

  function buildModuleGraph(modules) {
    const nodes = clone(modules);
    const interfaces = {};
    const duplicateProviders = [];
    nodes.forEach((module) => (module.provides || []).forEach((capability) => {
      if (interfaces[capability]) duplicateProviders.push({ capability, first: interfaces[capability], second: module.module_id });
      else interfaces[capability] = module.module_id;
    }));
    const edges = [];
    const unresolved = [];
    const moduleIds = new Set(nodes.map((module) => module.module_id));
    let directModuleReferences = 0;
    let capabilityEdges = 0;
    nodes.forEach((module) => (module.requires || []).forEach((capability) => {
      if (moduleIds.has(capability)) directModuleReferences += 1;
      const provider = interfaces[capability];
      if (!provider) unresolved.push({ module_id: module.module_id, capability });
      else {
        capabilityEdges += 1;
        const edge = [provider, module.module_id];
        if (!edges.some((item) => item[0] === edge[0] && item[1] === edge[1])) edges.push(edge);
      }
    }));
    return {
      status: unresolved.length || duplicateProviders.length || directModuleReferences ? "BLOCKED" : "READY",
      modules: nodes,
      edges,
      unresolved,
      duplicateProviders,
      interfaces,
      coupling: {
        capabilityEdges,
        directModuleReferences,
        optionalModules: nodes.filter((module) => module.optional).length,
      },
    };
  }

  const MODULE_LANES = ["输入", "理解", "编排", "执行", "记忆与观测"];
  const SYSTEM_LANES = ["入口", "认知", "理解", "编排", "结构", "领域", "执行", "验收", "裁决", "交付", "记忆", "学习", "输出"];

  function moduleLaneLabel(layer) {
    const value = String(layer || "").toLowerCase();
    const systemLabel = SYSTEM_LANES.find((label) => label.toLowerCase() === value);
    if (systemLabel) return systemLabel;
    if (value === "输入" || value === "input") return "输入";
    if (value === "理解" || value === "understanding") return "理解";
    if (value === "编排" || value === "orchestration") return "编排";
    if (value === "执行" || value === "execution") return "执行";
    if (["记忆", "观测", "memory", "observation", "observability"].includes(value)) return "记忆与观测";
    return "记忆与观测";
  }

  function moduleLaneOrder(modules) {
    const requested = new Set(modules.map((module) => String(module.layer || "")));
    const systemOnly = ["入口", "认知", "结构", "领域", "验收", "裁决", "交付", "学习", "输出"];
    if (!systemOnly.some((label) => requested.has(label))) return MODULE_LANES;
    const system = SYSTEM_LANES.filter((label) => requested.has(label));
    return system;
  }

  function topologicalModuleOrder(modules, edges) {
    const moduleIds = modules.map((module) => module.module_id);
    const known = new Set(moduleIds);
    const incoming = Object.fromEntries(moduleIds.map((moduleId) => [moduleId, 0]));
    const outgoing = Object.fromEntries(moduleIds.map((moduleId) => [moduleId, []]));
    edges.forEach(([sourceId, targetId]) => {
      if (!known.has(sourceId) || !known.has(targetId)) return;
      incoming[targetId] += 1;
      outgoing[sourceId].push(targetId);
    });
    const queue = moduleIds.filter((moduleId) => incoming[moduleId] === 0);
    const order = [];
    while (queue.length) {
      const moduleId = queue.shift();
      order.push(moduleId);
      outgoing[moduleId].forEach((targetId) => {
        incoming[targetId] -= 1;
        if (incoming[targetId] === 0) queue.push(targetId);
      });
    }
    moduleIds.forEach((moduleId) => {
      if (!order.includes(moduleId)) order.push(moduleId);
    });
    return order;
  }

  function buildModuleTopology(modules, edges) {
    const padding = 32;
    const laneWidth = 220;
    const laneGap = 36;
    const nodeWidth = 176;
    const nodeHeight = 112;
    const nodeGap = 26;
    const headerHeight = 72;
    const order = topologicalModuleOrder(modules, edges);
    const orderIndex = Object.fromEntries(order.map((moduleId, index) => [moduleId, index]));
    const laneOrder = moduleLaneOrder(modules);
    const grouped = Object.fromEntries(laneOrder.map((label) => [label, []]));
    modules.forEach((module) => {
      const requestedLane = moduleLaneLabel(module.layer);
      const lane = grouped[requestedLane] ? requestedLane : "记忆与观测";
      grouped[lane].push(module);
    });
    laneOrder.forEach((label) => grouped[label].sort((left, right) => orderIndex[left.module_id] - orderIndex[right.module_id]));
    const maxLaneSize = Math.max(1, ...laneOrder.map((label) => grouped[label].length));
    const width = padding * 2 + laneOrder.length * laneWidth + (laneOrder.length - 1) * laneGap;
    const height = Math.max(520, headerHeight + padding * 2 + maxLaneSize * nodeHeight + Math.max(0, maxLaneSize - 1) * nodeGap);
    const lanes = laneOrder.map((label, index) => ({
      lane_id: label,
      label,
      x: padding + index * (laneWidth + laneGap),
      width: laneWidth,
      count: grouped[label].length,
    }));
    const nodes = lanes.flatMap((lane) => grouped[lane.label].map((module, index) => ({
      ...clone(module),
      lane: lane.label,
      x: lane.x + (laneWidth - nodeWidth) / 2,
      y: headerHeight + padding + index * (nodeHeight + nodeGap),
      width: nodeWidth,
      height: nodeHeight,
    })));
    return { width, height, padding, nodeWidth, nodeHeight, headerHeight, lanes, nodes, edges: clone(edges) };
  }

  function moduleNeighborhood(edges, moduleId) {
    const directUpstream = edges.filter((edge) => edge[1] === moduleId).map((edge) => edge[0]);
    const directDownstream = edges.filter((edge) => edge[0] === moduleId).map((edge) => edge[1]);
    function walk(seed, nextFor) {
      const pending = [...seed];
      const found = [];
      while (pending.length) {
        const current = pending.shift();
        if (current === moduleId || found.includes(current)) continue;
        found.push(current);
        nextFor(current).forEach((item) => pending.push(item));
      }
      return found;
    }
    return {
      directUpstream,
      directDownstream,
      upstream: walk(directUpstream, (current) => edges.filter((edge) => edge[1] === current).map((edge) => edge[0])),
      downstream: walk(directDownstream, (current) => edges.filter((edge) => edge[0] === current).map((edge) => edge[1])),
    };
  }

  function moveModuleNode(topology, moduleId, x, y) {
    const next = clone(topology);
    next.nodes = next.nodes.map((node) => {
      if (node.module_id !== moduleId) return node;
      return {
        ...node,
        x: Math.min(Math.max(next.padding, x), next.width - next.nodeWidth - next.padding),
        y: Math.min(Math.max(next.padding, y), next.height - next.nodeHeight - next.padding),
      };
    });
    return next;
  }

  function moduleEdgePath(source, target) {
    if (source.x === target.x) {
      const startX = source.x + source.width / 2;
      const startY = source.y + source.height;
      const endX = target.x + target.width / 2;
      const endY = target.y;
      const middleY = (startY + endY) / 2;
      return `M ${startX} ${startY} C ${startX} ${middleY}, ${endX} ${middleY}, ${endX} ${endY}`;
    }
    const startX = source.x + source.width;
    const startY = source.y + source.height / 2;
    const endX = target.x;
    const endY = target.y + target.height / 2;
    const middleX = (startX + endX) / 2;
    return `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`;
  }

  function renderModuleTopology(topology, selectedModuleId) {
    const byId = Object.fromEntries(topology.nodes.map((node) => [node.module_id, node]));
    const neighborhood = moduleNeighborhood(topology.edges, selectedModuleId);
    const upstream = new Set(neighborhood.upstream);
    const downstream = new Set(neighborhood.downstream);
    const relation = (moduleId) => moduleId === selectedModuleId ? "selected" : upstream.has(moduleId) ? "upstream" : downstream.has(moduleId) ? "downstream" : "unrelated";
    const lanes = topology.lanes.map((lane) => `<div class="module-lane" style="left:${lane.x}px;width:${lane.width}px;height:${topology.height}px"><span>${escapeHtml(lane.label)}</span><em>${lane.count}</em></div>`).join("");
    const edges = topology.edges.map(([sourceId, targetId, edgeKind = "dependency"]) => {
      const source = byId[sourceId];
      const target = byId[targetId];
      if (!source || !target) return "";
      const active = relation(sourceId) !== "unrelated" && relation(targetId) !== "unrelated";
      return `<path class="module-edge edge-${escapeHtml(edgeKind)}${active ? " active" : ""}" data-edge-from="${escapeHtml(sourceId)}" data-edge-to="${escapeHtml(targetId)}" d="${moduleEdgePath(source, target)}" marker-end="url(#module-arrow)"></path>`;
    }).join("");
    const nodes = topology.nodes.map((node) => {
      const nodeRelation = relation(node.module_id);
      const status = node.availability === "READY" ? "可用" : node.availability === "PROTOTYPE" ? "试运行" : "规划中";
      const drill = node.child_graph ? " · 可下钻" : "";
      return `<button class="module-node" type="button" data-module-id="${escapeHtml(node.module_id)}" data-relation="${nodeRelation}" aria-pressed="${nodeRelation === "selected" ? "true" : "false"}" aria-controls="module-detail" style="left:${node.x}px;top:${node.y}px;width:${node.width}px;height:${node.height}px"><span class="module-node-meta"><span>${escapeHtml(node.lane)}</span><em>${escapeHtml(status)}</em></span><b>${escapeHtml(node.name)}</b><small>${node.optional ? "可选模块" : "核心模块"}${drill}</small><i aria-hidden="true"></i></button>`;
    }).join("");
    return `<div class="module-scene-content" style="width:${topology.width}px;height:${topology.height}px"><div class="module-lane-layer" aria-hidden="true">${lanes}</div><svg class="module-edge-layer" viewBox="0 0 ${topology.width} ${topology.height}" aria-hidden="true"><defs><marker id="module-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z"></path></marker></defs>${edges}</svg><div class="module-node-layer">${nodes}</div></div>`;
  }

  function zoomModuleView(view, requestedScale, anchor) {
    const scale = Math.min(1.8, Math.max(.16, requestedScale));
    const origin = anchor || { x: 0, y: 0 };
    const worldX = (origin.x - view.x) / view.scale;
    const worldY = (origin.y - view.y) / view.scale;
    return {
      x: origin.x - worldX * scale,
      y: origin.y - worldY * scale,
      scale,
    };
  }

  function captureMapPointerOnDown(kind) {
    return kind === "pan";
  }

  function createDragClickGuard(schedule) {
    const scheduleExpiry = schedule || ((callback) => setTimeout(callback, 0));
    let suppressed = false;
    let generation = 0;
    return {
      markDrag() {
        suppressed = true;
        const current = ++generation;
        scheduleExpiry(() => {
          if (generation === current) suppressed = false;
        });
      },
      consumeClick() {
        if (!suppressed) return false;
        suppressed = false;
        generation += 1;
        return true;
      },
    };
  }

  function moduleGraph() {
    return { readOnly: true, ...buildModuleGraph(MODULES) };
  }

  function workspaceView(state) {
    const work = viewModel(state);
    const lines = state.businessLines.map((line) => {
      const tasks = state.tasks.filter((task) => task.line_id === line.line_id).map((task) => work.tasks[task.task_id]);
      return { ...line, tasks, progress: progress(state, tasks.map((task) => task.task_id)) };
    });
    const activeLine = lines.find((line) => line.line_id === state.activeLineId) || lines[0];
    const persistedDecisions = (state.pendingDecisions || []).map((item) => ({
      ...item,
      kind: "runtime-decision",
      title: item.question,
      summary: item.context,
    }));
    const decidedTasks = new Set(persistedDecisions.map((item) => item.task_id));
    const pausedItems = state.tasks.filter((task) => state.taskStates[task.task_id] === "PAUSED").map((task) => ({ ...task, title: task.title || task.public_label, acceptance: task.acceptance || task.stage, kind: "paused", summary: "任务已按你的决定暂停。恢复后会重新进入分派队列。" }));
    const localDecisionItems = state.runtime ? [] : [
      ...state.tasks.filter((task) => state.taskStates[task.task_id] === "BLOCKED" && !decidedTasks.has(task.task_id)).map((task) => ({ ...task, title: task.title || task.public_label, acceptance: task.acceptance || task.stage, kind: "blocked", summary: "任务已阻塞，需要调整边界或重新批准。" })),
      ...state.tasks.filter((task) => actionForTask(state, task.task_id) === "HUMAN_DECISION_REQUIRED" && !decidedTasks.has(task.task_id)).map((task) => ({ ...task, title: task.title || task.public_label, acceptance: task.acceptance || task.stage, kind: "task" })),
    ];
    const pending = state.planApproved ? [
      ...persistedDecisions,
      ...pausedItems,
      ...localDecisionItems,
    ] : [{ task_id: "plan-approval", kind: "plan", title: "确认自动生成的工作地图", summary: `${lines.length} 条业务线、${state.tasks.length} 项短任务，确认后进入执行队列。` }];

    return {
      activeBoard: PRIMARY_BOARDS.some((board) => board.id === state.activeBoard) ? state.activeBoard : "work",
      boards: PRIMARY_BOARDS.map((board) => ({ ...board, count: board.id === "decision" ? pending.length : null })),
      global: moduleGraph(),
      work: { ...work, lines, activeLine, operationChain: clone(OPERATION_CHAIN) },
      decision: { pending },
      onboarding: clone(state.onboarding),
    };
  }

  function analyzeFirstRun(state, manifest) {
    const next = clone(state);
    const files = (manifest && manifest.files ? manifest.files : []).map((item) => String(item).toLowerCase());
    const detected = [];
    if (files.some((item) => item.startsWith("src/") || item.includes("app.") || item.includes("workbench/"))) detected.push("product");
    if (files.some((item) => item.includes("research/") || item.includes("paper") || item.endsWith(".ipynb"))) detected.push("research");
    if (files.some((item) => item.includes("draft") || item.includes("outline") || item.endsWith(".docx"))) detected.push("writing");
    next.onboarding = { status: "CANDIDATE_READY", readOnly: true, workspaceName: manifest && manifest.name ? manifest.name : "Local workspace", fileCount: files.length, detectedLines: detected.sort() };
    next.planApproved = false;
    return next;
  }

  function applyTemplate(state, lineId) {
    const next = selectBusinessLine(state, lineId);
    const line = next.businessLines.find((item) => item.line_id === lineId);
    if (!line) return next;
    next.activeTemplate = lineId;
    next.onboarding = {
      status: "TEMPLATE_READY",
      readOnly: true,
      detectedLines: [lineId],
      workspaceName: line.name,
      fileCount: 0,
    };
    next.planApproved = false;
    return next;
  }

  function proposeTaskFromPrompt(state, prompt) {
    const text = String(prompt || "").trim();
    if (!text) return { status: "BLOCKED", reason: "PROMPT_REQUIRED" };
    const showcase = state.privacy && state.privacy.taskDetails === "ANONYMIZED";
    const writing = /写|文稿|文章|报告|行业|资料|初稿/.test(text);
    const research = /科研|研究|实验|论文|文献/.test(text);
    const lineId = showcase ? state.activeLineId : writing ? "writing" : research ? "research" : "product";
    const complexity = /复杂|全面|系统性|实验/.test(text) ? "deep" : "standard";
    const capabilities = showcase
      ? lineId === "research" ? ["research"] : lineId === "industry-report" ? ["research", "writing"] : ["writing"]
      : lineId === "product" ? ["engineering"] : lineId === "research" ? ["research"] : ["writing"];
    const task = { task_id: `created-${state.tasks.length + 1}`, public_label: `任务 N-${String(state.tasks.length + 1).padStart(2, "0")}`, line_id: lineId, title: text, acceptance: "产出可检查、可继续推进的阶段结果", stage: "待拆解", iteration: 1, parallel_group: "main", attempts: 0, events: [], depends_on: [], human_gate: false, complexity, capabilities, estimated_tokens: complexity === "deep" ? 120000 : 48000, status: "QUEUED" };
    return { status: "CANDIDATE", line_id: lineId, task, route: routeTask(task) };
  }

  function proposeTaskFromModuleAnnotation(state, moduleId, annotation) {
    const text = String(annotation || "").trim();
    const module = MODULES.find((item) => item.module_id === moduleId);
    const lineId = state.activeLineId || (state.businessLines[0] && state.businessLines[0].line_id);
    if (!text) return { status: "BLOCKED", reason: "ANNOTATION_REQUIRED" };
    if (!module || !lineId) return { status: "BLOCKED", reason: "MODULE_CONTEXT_REQUIRED" };
    const sequence = state.tasks.length + 1;
    const task = {
      task_id: `module-issue-${module.module_id}-${sequence}`,
      public_label: `模块问题 ${String(sequence).padStart(2, "0")}`,
      line_id: lineId,
      title: `处理 ${module.name} 的模块批注`,
      acceptance: "批注中的接口、依赖或流程问题得到处理，并登记可检查的结果。",
      stage: "模块修正",
      iteration: 1,
      parallel_group: "module-maintenance",
      attempts: 0,
      events: [],
      depends_on: [],
      human_gate: false,
      complexity: "standard",
      capabilities: ["engineering"],
      estimated_tokens: 48000,
      context: {
        model_context: { module_id: module.module_id, annotation: text },
      },
      status: "QUEUED",
    };
    return { status: "CANDIDATE", line_id: lineId, module_id: module.module_id, task, route: routeTask(task) };
  }

  function addTaskProposal(state, proposal) {
    if (!proposal || proposal.status !== "CANDIDATE") return clone(state);
    const next = clone(state);
    const task = clone(proposal.task);
    delete task.status;
    next.tasks.push(task);
    next.taskStates[task.task_id] = "QUEUED";
    next.activeLineId = task.line_id;
    next.activeBoard = "work";
    next.taskProposal = null;
    return next;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }

  const ACTION_LABELS = { PLAN_APPROVAL_REQUIRED: "等待计划确认", HUMAN_DECISION_REQUIRED: "需要你裁决", WAITING_DEPENDENCY: "等待前置任务", DISPATCH: "分派并开始", REQUEST_REVIEW: "提交验收", ACCEPT: "接受并收口", BLOCKED: "需要处理", RESUME: "恢复到待分配", NONE: "已收口" };
  const STATUS_LABELS = { QUEUED: "待分配", IN_PROGRESS: "进行中", REVIEW: "待验收", BLOCKED: "已阻塞", PAUSED: "已暂停", DONE: "已收口", ARCHIVED: "已归档" };

  function renderTaskCard(task) {
    const assignment = task.assignment ? `<span class="task-chip route">${escapeHtml(task.assignment.route)}</span><span class="task-chip">${escapeHtml(task.assignment.executor)}</span>` : "";
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action);
    return `<article class="task-row status-${escapeHtml(task.status.toLowerCase())}" data-task-id="${escapeHtml(task.task_id)}">
      <div class="task-state"><span class="status-dot"></span><b>${escapeHtml(STATUS_LABELS[task.status] || task.status)}</b></div>
      <div class="task-main"><div class="card-meta"><span>${escapeHtml(task.complexity)}</span>${task.human_gate ? '<span class="signal-pill">人工确认</span>' : ""}</div><h3>${escapeHtml(task.title || task.public_label)}</h3><p>${escapeHtml(task.acceptance || task.stage)}</p></div>
      <div class="task-route">${assignment || '<span class="task-chip">等待路由</span>'}</div>
      <button class="task-action" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(ACTION_LABELS[task.action] || task.action)}</button>
    </article>`;
  }

  function renderDecisionCard(item) {
    if (item.kind === "plan") return `<article class="decision-card plan-decision"><div><span class="signal-pill">计划确认</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p></div><button class="primary-button" type="button" data-plan-action="approve">确认并开始</button></article>`;
    if (item.kind === "runtime-decision") {
      const options = (item.options || []).map((option) => `<button class="card-action${option.letter === item.recommended_option ? " approve" : ""}" type="button" data-runtime-decision="${escapeHtml(item.decision_id)}" data-decision-option="${escapeHtml(option.letter)}">${escapeHtml(option.label)}</button>`).join("");
      return `<article class="decision-card"><div><span class="signal-pill">需要你决定</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p>${item.recommendation_reason ? `<small>建议：${escapeHtml(item.recommendation_reason)}</small>` : ""}</div><div class="card-actions">${options}</div></article>`;
    }
    if (item.kind === "blocked") return `<article class="decision-card blocked-decision" data-decision-task="${escapeHtml(item.task_id)}"><div><span class="status-pill status-blocked">已阻塞</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p></div><div class="card-actions"><button class="card-action" type="button" data-decision="APPROVED">调整后重开</button></div></article>`;
    if (item.kind === "paused") return `<article class="decision-card paused-decision"><div><span class="status-pill status-paused">已暂停</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p></div></article>`;
    return `<article class="decision-card" data-decision-task="${escapeHtml(item.task_id)}"><div><span class="signal-pill">人工确认</span><h3>${escapeHtml(item.title)}</h3><p>验收条件：${escapeHtml(item.acceptance)}</p></div><div class="card-actions"><button class="card-action reject" type="button" data-decision="REJECTED">退回</button><button class="card-action approve" type="button" data-decision="APPROVED">批准并继续</button></div></article>`;
  }

  function renderDependencyEdge(edge, moduleNames) {
    return `<li><b>${escapeHtml(moduleNames[edge[0]] || edge[0])}</b><span aria-hidden="true">→</span><b>${escapeHtml(moduleNames[edge[1]] || edge[1])}</b></li>`;
  }

  function renderLineButton(line, active) {
    return `<button class="line-tab${active ? " active" : ""}" type="button" data-line-id="${escapeHtml(line.line_id)}" aria-pressed="${active ? "true" : "false"}"><span><b>${escapeHtml(line.name)}</b><small>${escapeHtml(line.caption)}</small></span><em>${line.progress.done}/${line.progress.total}</em></button>`;
  }

  function petForTask(task, preference = "model-animal") {
    if (!task || task.status !== "IN_PROGRESS" || !task.assignment) return null;
    if (preference === "off") return null;
    const model = String(task.assignment.model || "");
    if (preference === "blue-whale-maid") {
      const activitySource = `${task.agent_role || ""} ${task.domain_id || ""} ${task.title || ""}`;
      const activity = /science|research|analysis|experiment|data|hypothesis|科研|实验|分析|数据|假设/i.test(activitySource) ? "mining" : "coding";
      const seed = Array.from(String(task.task_id || task.public_label || model)).reduce((total, character) => total + character.charCodeAt(0), 0);
      const mood = Number(task.attempts || 0) > 1 ? "tired" : seed % 2 ? "happy" : "normal";
      return {
        pet_id: "blue-whale-maid",
        kind: "image",
        src: `assets/pets/blue-whale-maid/blue-whale-maid-${activity}-${mood}.gif`,
        label: `${model || "当前模型"} 的蓝鲸女仆正在工作`,
      };
    }
    if (/Reasoning|Research|推理|研究/i.test(model)) return { pet_id: "reasoning-owl", glyph: "🦉", label: `${model} 工作宠物` };
    if (/Writing|Long-context|写作|长上下文/i.test(model)) return { pet_id: "writing-whale", glyph: "🐋", label: `${model} 工作宠物` };
    if (/Fast|快速/i.test(model)) return { pet_id: "fast-rabbit", glyph: "🐇", label: `${model} 工作宠物` };
    return { pet_id: "general-fox", glyph: "🦊", label: `${model || "当前模型"} 工作宠物` };
  }

  function renderStageRail(line) {
    return `<ol class="stage-rail layout-${escapeHtml(line.layout)}">${line.stages.map((stage, index) => `<li class="${index === 0 ? "current" : ""}"><span>${String(index + 1).padStart(2, "0")}</span><b>${escapeHtml(stage)}</b></li>`).join("")}</ol>`;
  }

  function renderWorkflowNode(task, selected, petPreference = "model-animal") {
    const assignment = task.assignment;
    const pet = petForTask(task, petPreference);
    const route = assignment ? `${escapeHtml(assignment.model)}<span>${escapeHtml(assignment.executor)}</span>` : "等待分配<span>尚未选择执行器</span>";
    const agent = task.agent_role ? `<span class="workflow-node-agent">${escapeHtml(task.agent_role)}</span>` : "";
    const flowLabels = { sequence: "顺序", branch: "分支", join: "汇合", condition: "条件", loop: "循环" };
    const flowKind = inferFlowKind(task);
    const petMedia = pet && pet.kind === "image"
      ? `<img src="${escapeHtml(pet.src)}" alt="" loading="lazy" decoding="async"><span class="pet-static" aria-hidden="true">🐋</span>`
      : pet ? `<span aria-hidden="true">${pet.glyph}</span>` : "";
    const petSlot = pet ? `<span class="workflow-pet${pet.kind === "image" ? " image-pet" : ""}" data-pet-id="${escapeHtml(pet.pet_id)}" aria-label="${escapeHtml(pet.label)}" title="${escapeHtml(pet.label)}">${petMedia}</span>` : "";
    return `<button class="workflow-node status-${escapeHtml(task.status.toLowerCase())}${selected ? " selected" : ""}${pet ? " has-pet" : ""}" type="button" data-workflow-task="${escapeHtml(task.task_id)}" aria-pressed="${selected ? "true" : "false"}">
      <span class="workflow-node-head"><span class="workflow-node-id">${escapeHtml(task.public_label || task.title || task.task_id)}</span><span class="workflow-node-status"><i class="run-pulse" aria-hidden="true"></i>${escapeHtml(STATUS_LABELS[task.status] || task.status)}</span></span>
      <span class="workflow-node-logic kind-${escapeHtml(flowKind)}">${escapeHtml(flowLabels[flowKind])}</span>
      ${agent}<span class="workflow-node-stage">${escapeHtml(task.stage || task.title || "自定义任务")}</span>
      <span class="workflow-node-route">${route}<span>${task.attempts ? `第 ${task.attempts} 次运行` : "尚未运行"}</span></span>
      ${petSlot}</button>`;
  }

  function renderWorkflowCanvas(projection, selectedTaskId, petPreference = "model-animal") {
    if (!projection || !projection.groups.length) return '<p class="empty-trace">当前工作流还没有任务。</p>';
    const groups = projection.groups.map((group, index) => {
      const active = group.nodes.some((task) => task.status === "IN_PROGRESS" || task.status === "REVIEW");
      const label = projection.layout === "loop" ? `Loop ${String(group.iteration).padStart(2, "0")}` : `阶段 ${String(group.iteration).padStart(2, "0")}`;
      const returnEdge = projection.layout === "loop" && index < projection.groups.length - 1 ? '<div class="loop-return">复核后进入下一轮</div>' : "";
      return `<section class="workflow-group${active ? " active" : ""}"><header class="group-heading"><strong>${label}</strong><span>${group.nodes.length} 个节点 · ${new Set(group.nodes.map((task) => task.parallel_group)).size} 个分支</span></header><div class="workflow-nodes">${group.nodes.map((task) => renderWorkflowNode(task, task.task_id === selectedTaskId, petPreference)).join("")}</div>${returnEdge}</section>`;
    }).join("");
    return `<div class="workflow-groups">${groups}</div>`;
  }

  function renderRunDetail(task, runtimeState) {
    if (!task) return '<p class="empty-trace">选择一个节点查看运行轨迹。</p>';
    const assignment = task.assignment;
    const events = task.events && task.events.length
      ? `<ol class="event-trace">${task.events.map((event) => `<li><time>${escapeHtml(event.at)}</time><span>${escapeHtml(event.label)}</span></li>`).join("")}</ol>`
      : '<p class="empty-trace">任务尚未分配。分配后会记录适配器启动、心跳、产物与复核事件。</p>';
    const availableAdapters = runtimeState && runtimeState.runtime
      ? (runtimeState.adapters || []).filter((adapter) => adapter.available)
      : [];
    const needsAdapter = ["DISPATCH", "HUMAN_DECISION_REQUIRED"].includes(task.action);
    const adapterUnavailable = Boolean(runtimeState && runtimeState.runtime && needsAdapter && !availableAdapters.length);
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action) || adapterUnavailable;
    const runtimeControls = runtimeState && runtimeState.runtime && ["DISPATCH", "HUMAN_DECISION_REQUIRED"].includes(task.action)
      ? `<div class="runtime-controls"><label><span>模型</span><input data-runtime-model value="${escapeHtml(runtimeState.defaultModel || "")}" autocomplete="off"></label><label><span>执行适配器</span><select data-runtime-adapter ${adapterUnavailable ? "disabled" : ""}>${availableAdapters.length ? availableAdapters.map((adapter) => `<option value="${escapeHtml(adapter.adapter_id)}">${escapeHtml(adapter.adapter_id)}</option>`).join("") : '<option value="">暂无可用执行适配器</option>'}</select></label></div>`
      : "";
    const actionLabel = adapterUnavailable
      ? "配置执行适配器后开始"
      : (ACTION_LABELS[task.action] || task.action);
    return `<div class="run-detail-head"><span>${escapeHtml(task.public_label || task.title || task.task_id)} · ${escapeHtml(STATUS_LABELS[task.status] || task.status)}</span><h3>${escapeHtml(task.stage || task.title || "自定义任务")}</h3></div>
      <dl class="run-detail-meta"><div><dt>模型</dt><dd>${escapeHtml(assignment ? assignment.model : "等待选择")}</dd></div><div><dt>执行适配器</dt><dd>${escapeHtml(assignment ? assignment.executor : "尚未分配")}</dd></div><div><dt>运行轮次</dt><dd>${task.attempts ? `第 ${String(task.attempts).padStart(2, "0")} 次` : "尚未运行"}</dd></div><div><dt>节点类型</dt><dd>${escapeHtml(({ sequence: "顺序", branch: "分支", join: "汇合", condition: "条件", loop: "循环" })[inferFlowKind(task)] || "顺序")}</dd></div></dl>
      ${events}
      ${runtimeControls}
      <div data-task-id="${escapeHtml(task.task_id)}"><button class="task-action" type="button" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(actionLabel)}</button></div>`;
  }

  function renderProposal(proposal, lines) {
    if (!proposal) return "";
    if (proposal.status !== "CANDIDATE") return '<div class="proposal-error">请先描述你想完成的事情。</div>';
    const line = lines.find((item) => item.line_id === proposal.line_id);
    return `<div class="proposal-card"><div><span>系统建议</span><h3>${escapeHtml(proposal.task.title)}</h3><p>${escapeHtml(line ? line.name : proposal.line_id)} · ${escapeHtml(proposal.route ? proposal.route.model : "需要人工选择模型")}</p></div><button type="button" class="primary-button" data-add-proposal>加入待分配</button></div>`;
  }

  function scrollActiveBoardIntoView(doc, board) {
    const viewport = doc.defaultView;
    if (!viewport || !viewport.matchMedia || !viewport.matchMedia("(max-width: 980px)").matches) return false;
    const panel = Array.from(doc.querySelectorAll("[data-panel]")).find((item) => item.dataset.panel === board);
    if (!panel || !panel.scrollIntoView) return false;
    const reducedMotion = viewport.matchMedia("(prefers-reduced-motion: reduce)").matches;
    panel.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    return true;
  }

  function mount(doc) {
    const initialBoard = doc.defaultView && doc.defaultView.location ? String(doc.defaultView.location.hash || "").replace(/^#/, "") : "work";
    let state = selectBoard(createShowcaseState(), initialBoard);
    const runtimeFetch = doc.defaultView && typeof doc.defaultView.fetch === "function" ? doc.defaultView.fetch.bind(doc.defaultView) : null;
    const runtimeClient = createRuntimeClient(runtimeFetch);
    let moduleMapMode = "system";
    let modulePath = [];
    let selectedModule = "secretary-entry";
    let moduleTopology = null;
    let moduleTopologySignature = "";
    let moduleView = { x: 20, y: 20, scale: 1 };
    let moduleViewFitted = false;
    let moduleFocusEnabled = true;
    let mapGesture = null;
    let moduleClickTimer = null;
    const dragClickGuard = createDragClickGuard();
    let proposal = null;
    let lineComposerOpen = false;
    const byId = (id) => doc.getElementById(id);

    function activeModuleGraph(view) {
      if (moduleMapMode === "modules" || !architecture) return view.global;
      const graph = architecture.systemGraph(modulePath);
      return {
        graph_id: graph.graph_id,
        name: graph.name,
        summary: graph.summary,
        modules: graph.nodes,
        edges: graph.edges,
        unresolved: [],
      };
    }

    function enterModuleGraph(module) {
      if (!module || !module.child_graph || moduleMapMode !== "system") return false;
      modulePath = [...modulePath, module.child_graph];
      const graph = architecture.systemGraph(modulePath);
      selectedModule = graph.nodes[0] ? graph.nodes[0].module_id : null;
      moduleTopology = null;
      moduleTopologySignature = "";
      moduleViewFitted = false;
      return true;
    }

    function applyModuleView() {
      const scene = byId("module-scene");
      if (!scene) return;
      scene.style.transform = `translate(${moduleView.x}px, ${moduleView.y}px) scale(${moduleView.scale})`;
      byId("map-zoom-value").textContent = `${Math.round(moduleView.scale * 100)}%`;
    }

    function fitModuleMap() {
      const viewport = byId("module-map-viewport");
      if (!viewport || !moduleTopology) return;
      const inset = 28;
      const availableWidth = Math.max(1, viewport.clientWidth - inset * 2);
      const availableHeight = Math.max(1, viewport.clientHeight - inset * 2);
      const scale = Math.min(1.2, Math.max(.16, Math.min(availableWidth / moduleTopology.width, availableHeight / moduleTopology.height)));
      moduleView = {
        x: (viewport.clientWidth - moduleTopology.width * scale) / 2,
        y: (viewport.clientHeight - moduleTopology.height * scale) / 2,
        scale,
      };
      applyModuleView();
    }

    function refreshModuleGeometry() {
      if (!moduleTopology) return;
      const scene = byId("module-scene");
      const nodes = Object.fromEntries(moduleTopology.nodes.map((node) => [node.module_id, node]));
      scene.querySelectorAll("[data-module-id]").forEach((element) => {
        const node = nodes[element.dataset.moduleId];
        if (!node) return;
        element.style.left = `${node.x}px`;
        element.style.top = `${node.y}px`;
      });
      scene.querySelectorAll("[data-edge-from][data-edge-to]").forEach((path) => {
        const source = nodes[path.dataset.edgeFrom];
        const target = nodes[path.dataset.edgeTo];
        if (source && target) path.setAttribute("d", moduleEdgePath(source, target));
      });
    }

    function announce(message) {
      byId("status-message").textContent = message;
    }

    async function refreshRuntime() {
      if (!runtimeClient) return false;
      const activeBoard = state.activeBoard;
      const petPreference = state.petPreference;
      const payload = await runtimeClient.load();
      state = selectBoard(runtimeStateFromPayload(payload), activeBoard);
      state.petPreference = petPreference || state.petPreference;
      render();
      announce("已读取本地运行库");
      return true;
    }

    function render() {
      const focused = doc.activeElement;
      const focusToken = focused && focused.dataset
        ? focused.dataset.moduleId ? ["moduleId", focused.dataset.moduleId]
          : focused.dataset.lineId ? ["lineId", focused.dataset.lineId]
            : focused.dataset.workflowTask ? ["workflowTask", focused.dataset.workflowTask]
              : null
        : null;
      const view = workspaceView(state);
      const summary = workflowSummary(state);
      byId("goal").textContent = view.work.goal;
      byId("metric-total").textContent = String(summary.total);
      byId("metric-assigned").textContent = String(summary.assigned);
      byId("metric-running").textContent = String(summary.running);
      byId("metric-repeated").textContent = String(summary.repeatedRuns);
      byId("progress-copy").textContent = `${view.work.progress.done} / ${view.work.progress.total} 项已收口`;
      byId("progress-bar").style.width = `${view.work.progress.percent}%`;
      byId("current-phase").textContent = summary.running ? "并行执行中" : state.planApproved ? "运行与验收" : "工作地图待确认";
      byId("data-source-mode").textContent = state.runtime ? "本地运行库 · 状态已持久化" : "结构演示 · 任务内容已匿名";
      byId("source-note-title").textContent = state.runtime ? "本地运行状态" : "公开演示数据";
      byId("source-note-copy").textContent = state.runtime ? "任务、运行、产物与裁决保存在当前 SQLite 运行库。模型密钥只从服务端环境变量读取。" : "只保留结构、数量、分配与运行事件。具体任务内容不会进入页面数据。";
      byId("work-source-label").textContent = state.runtime ? "真实运行状态" : "任务内容已匿名";
      byId("reset-demo").textContent = state.runtime ? "刷新状态" : "重置演示";
      byId("footer-mode").textContent = state.runtime ? "本地持久化运行库" : "匿名结构演示";
      doc.querySelectorAll('[role="tab"][data-board]').forEach((button) => {
        const active = button.dataset.board === view.activeBoard;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.setAttribute("tabindex", active ? "0" : "-1");
        const count = button.querySelector("[data-board-count]");
        const board = view.boards.find((item) => item.id === button.dataset.board);
        if (count && board) count.textContent = board.count == null ? "" : String(board.count);
      });
      doc.querySelectorAll("[data-panel]").forEach((panel) => { panel.hidden = panel.dataset.panel !== view.activeBoard; });

      const mapGraph = activeModuleGraph(view);
      const moduleNames = Object.fromEntries(mapGraph.modules.map((item) => [item.module_id, item.name]));
      const signature = `${moduleMapMode}:${modulePath.join("/")}:` + mapGraph.modules.map((module) => module.module_id).join("|") + "::" + mapGraph.edges.map((edge) => edge.join(">"));
      if (!moduleTopology || moduleTopologySignature !== signature) {
        moduleTopology = buildModuleTopology(mapGraph.modules, mapGraph.edges);
        moduleTopologySignature = signature;
        moduleViewFitted = false;
      }
      if (!mapGraph.modules.some((item) => item.module_id === selectedModule)) selectedModule = mapGraph.modules[0] ? mapGraph.modules[0].module_id : null;
      byId("module-scene").innerHTML = renderModuleTopology(moduleTopology, selectedModule);
      byId("module-map-viewport").dataset.focused = moduleFocusEnabled ? "true" : "false";
      byId("module-map-title").textContent = mapGraph.name || "运行模块";
      byId("module-count").textContent = String(mapGraph.modules.length);
      byId("module-edge-count").textContent = String(mapGraph.edges.length);
      byId("module-unresolved-count").textContent = String(mapGraph.unresolved.length);
      byId("dependency-edge-list").innerHTML = mapGraph.edges.map((edge) => renderDependencyEdge(edge, moduleNames)).join("");
      const module = mapGraph.modules.find((item) => item.module_id === selectedModule) || mapGraph.modules[0];
      const neighborhood = module ? moduleNeighborhood(mapGraph.edges, module.module_id) : { directUpstream: [], directDownstream: [] };
      byId("module-detail-name").textContent = module ? module.name : "没有已安装模块";
      byId("module-detail-summary").textContent = module ? module.summary : "把 module.json 放入模块目录后即可参与解析。";
      byId("module-provides").textContent = module ? module.provides.join(" · ") : "—";
      byId("module-requires").textContent = module && module.requires.length ? module.requires.join(" · ") : "无前置 capability";
      byId("module-upstream-list").textContent = neighborhood.directUpstream.length ? neighborhood.directUpstream.map((moduleId) => moduleNames[moduleId] || moduleId).join(" · ") : "系统入口";
      byId("module-downstream-list").textContent = neighborhood.directDownstream.length ? neighborhood.directDownstream.map((moduleId) => moduleNames[moduleId] || moduleId).join(" · ") : "没有下游模块";
      byId("module-inputs").textContent = module && module.inputs && module.inputs.length ? module.inputs.join(" · ") : "由 capability 合同定义";
      byId("module-outputs").textContent = module && module.outputs && module.outputs.length ? module.outputs.join(" · ") : "由 capability 合同定义";
      byId("module-control").textContent = module && module.control ? module.control : "按模块合同运行";
      const drillButton = doc.querySelector("[data-map-drill]");
      drillButton.hidden = !(moduleMapMode === "system" && module && module.child_graph);
      drillButton.textContent = module && module.child_graph ? `进入${module.name}` : "进入内部结构";
      doc.querySelectorAll("[data-map-mode]").forEach((button) => {
        const active = button.dataset.mapMode === moduleMapMode;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      const crumbs = moduleMapMode === "system" && architecture ? architecture.systemBreadcrumbs(modulePath) : [{ label: "运行模块", depth: 0 }];
      byId("module-breadcrumbs").innerHTML = crumbs.map((crumb, index) => `<button type="button" data-map-depth="${index}" ${index === crumbs.length - 1 ? 'aria-current="page"' : ""}>${escapeHtml(crumb.label)}</button>`).join('<span aria-hidden="true">›</span>');
      const focusButton = doc.querySelector("[data-map-focus-toggle]");
      focusButton.classList.toggle("active", moduleFocusEnabled);
      focusButton.textContent = moduleFocusEnabled ? "显示全部模块" : "只看上下游";
      applyModuleView();
      if (!moduleViewFitted && view.activeBoard === "global") {
        fitModuleMap();
        moduleViewFitted = true;
      }
      byId("scan-status").textContent = view.onboarding.status === "CANDIDATE_READY" ? `已只读识别 ${view.onboarding.fileCount} 个文件信号，生成 ${view.onboarding.detectedLines.length} 条候选业务线。` : view.onboarding.status === "TEMPLATE_READY" ? `已载入${view.onboarding.workspaceName}模板；确认后生成对应任务。` : "首次运行先读取本地结构，再生成可编辑的模块图与工作计划。";
      doc.querySelectorAll("[data-template-line]").forEach((button) => button.classList.toggle("active", button.dataset.templateLine === state.activeTemplate));

      byId("line-tabs").innerHTML = view.work.lines.map((line) => renderLineButton(line, line.line_id === view.work.activeLine.line_id)).join("") + (lineComposerOpen
        ? '<form class="line-create-form" data-line-form><label for="new-line-name">工作线名称</label><input id="new-line-name" data-line-name maxlength="40" placeholder="例如：新产品验证" required><span><button type="button" data-cancel-line>取消</button><button type="submit">创建</button></span></form>'
        : '<button class="line-tab-create" type="button" data-create-line aria-label="创建工作线"><b>＋</b><span>新建工作线</span></button>');
      byId("active-line-name").textContent = view.work.activeLine.name;
      byId("active-line-caption").textContent = view.work.activeLine.caption;
      byId("line-progress").textContent = `${view.work.activeLine.progress.percent}%`;
      const activeTaskIds = view.work.activeLine.tasks.map((task) => task.task_id);
      const lineSummary = workflowSummary(state, activeTaskIds);
      byId("workflow-total").textContent = String(lineSummary.total);
      byId("workflow-assigned").textContent = String(lineSummary.assigned);
      byId("workflow-running").textContent = String(lineSummary.running);
      byId("workflow-repeated").textContent = String(lineSummary.repeatedRuns);
      byId("workflow-progress-bar").style.width = `${view.work.activeLine.progress.percent}%`;
      const autoControls = byId("auto-advance-controls");
      autoControls.hidden = !state.runtime;
      if (state.runtime) {
        byId("auto-advance-model").value = state.defaultModel || "";
        const availableAdapters = (state.adapters || []).filter((adapter) => adapter.available);
        const adapterSelect = byId("auto-advance-adapter");
        adapterSelect.innerHTML = availableAdapters.length
          ? (state.adapters || []).map((adapter) => `<option value="${escapeHtml(adapter.adapter_id)}" ${adapter.available ? "" : "disabled"}>${escapeHtml(adapter.adapter_id)}${adapter.available ? "" : " · 未配置"}</option>`).join("")
          : '<option value="">暂无可用执行适配器</option>';
        adapterSelect.disabled = !availableAdapters.length;
        const advanceButton = doc.querySelector("[data-auto-advance]");
        advanceButton.disabled = !state.defaultModel || !availableAdapters.length;
        advanceButton.textContent = !state.defaultModel
          ? "配置模型后推进"
          : !availableAdapters.length
            ? "配置执行适配器后推进"
            : "推进当前工作线";
      }
      const projection = workflowProjection(state, view.work.activeLine.line_id);
      const projectedTasks = projection ? projection.groups.flatMap((group) => group.nodes) : [];
      let selectedTask = projectedTasks.find((task) => task.task_id === state.activeTaskId);
      if (!selectedTask) selectedTask = projectedTasks.find((task) => task.status === "IN_PROGRESS") || projectedTasks[0];
      if (selectedTask) state.activeTaskId = selectedTask.task_id;
      byId("workflow-canvas").innerHTML = renderWorkflowCanvas(projection, state.activeTaskId, state.petPreference);
      byId("pet-preference").value = state.petPreference || "blue-whale-maid";
      const selectedTaskView = selectedTask ? view.work.tasks[selectedTask.task_id] : null;
      byId("run-detail").innerHTML = renderRunDetail(selectedTaskView, state);
      byId("proposal-zone").innerHTML = renderProposal(proposal, view.work.lines);

      byId("decision-list").innerHTML = view.decision.pending.length ? view.decision.pending.map(renderDecisionCard).join("") : '<div class="empty-state"><span>✓</span><h3>当前没有待裁决事项</h3><p>新的计划确认、条件判断和阻塞会集中出现在这里。</p></div>';
      byId("decision-visible-count").textContent = `${view.decision.pending.length} 项待处理`;
      if (doc.defaultView && doc.defaultView.history) doc.defaultView.history.replaceState(null, "", `#${view.activeBoard}`);
      if (focusToken) {
        const attribute = `data-${focusToken[0].replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
        const target = Array.from(doc.querySelectorAll(`[${attribute}]`)).find((item) => item.dataset[focusToken[0]] === focusToken[1]);
        if (target) target.focus();
      }
    }

    doc.addEventListener("change", (event) => {
      if (event.target.id !== "pet-preference") return;
      state = setPetPreference(state, event.target.value);
      try { doc.defaultView.localStorage.setItem("personal-ai-os.pet-preference", state.petPreference); } catch (_error) {}
      render();
      announce(state.petPreference === "off" ? "工作宠物已关闭" : "工作宠物已更新");
    });

    try {
      state = setPetPreference(state, doc.defaultView.localStorage.getItem("personal-ai-os.pet-preference"));
    } catch (_error) {}

    doc.addEventListener("click", async (event) => {
      const boardButton = event.target.closest && event.target.closest("[data-board]");
      if (boardButton) {
        state = selectBoard(state, boardButton.dataset.board);
        render();
        scrollActiveBoardIntoView(doc, state.activeBoard);
        return;
      }
      const mapModeButton = event.target.closest && event.target.closest("[data-map-mode]");
      if (mapModeButton) {
        moduleMapMode = mapModeButton.dataset.mapMode;
        modulePath = [];
        const graph = activeModuleGraph(workspaceView(state));
        selectedModule = graph.modules[0] ? graph.modules[0].module_id : null;
        moduleTopology = null;
        moduleTopologySignature = "";
        moduleViewFitted = false;
        render();
        announce(moduleMapMode === "system" ? "已切换到系统全景" : "已切换到运行模块");
        return;
      }
      const breadcrumb = event.target.closest && event.target.closest("[data-map-depth]");
      if (breadcrumb) {
        modulePath = modulePath.slice(0, Number(breadcrumb.dataset.mapDepth));
        const graph = activeModuleGraph(workspaceView(state));
        selectedModule = graph.modules[0] ? graph.modules[0].module_id : null;
        moduleTopology = null;
        moduleTopologySignature = "";
        moduleViewFitted = false;
        render();
        announce(`已返回${graph.name}`);
        return;
      }
      const zoomButton = event.target.closest && event.target.closest("[data-map-zoom]");
      if (zoomButton) {
        const viewport = byId("module-map-viewport");
        const anchor = { x: viewport.clientWidth / 2, y: viewport.clientHeight / 2 };
        const factor = zoomButton.dataset.mapZoom === "in" ? 1.15 : .85;
        moduleView = zoomModuleView(moduleView, moduleView.scale * factor, anchor);
        applyModuleView();
        announce(`模块地图缩放到 ${Math.round(moduleView.scale * 100)}%`);
        return;
      }
      if (event.target.closest && event.target.closest("[data-map-fit]")) {
        fitModuleMap();
        announce("模块地图已适应当前窗口");
        return;
      }
      if (event.target.closest && event.target.closest("[data-map-reset]")) {
        const graph = activeModuleGraph(workspaceView(state));
        moduleTopology = buildModuleTopology(graph.modules, graph.edges);
        moduleViewFitted = true;
        render();
        fitModuleMap();
        announce("模块布局已恢复为系统拓扑");
        return;
      }
      if (event.target.closest && event.target.closest("[data-map-drill]")) {
        const graph = activeModuleGraph(workspaceView(state));
        const module = graph.modules.find((item) => item.module_id === selectedModule);
        if (enterModuleGraph(module)) {
          render();
          announce(`已进入${module.name}`);
        }
        return;
      }
      if (event.target.closest && event.target.closest("[data-map-focus-toggle]")) {
        moduleFocusEnabled = !moduleFocusEnabled;
        render();
        announce(moduleFocusEnabled ? "已聚焦当前模块的上下游" : "已显示全部模块");
        return;
      }
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      if (moduleButton) {
        if (dragClickGuard.consumeClick()) return;
        if (moduleClickTimer) doc.defaultView.clearTimeout(moduleClickTimer);
        const moduleId = moduleButton.dataset.moduleId;
        const moduleLabel = moduleButton.textContent.trim();
        moduleClickTimer = doc.defaultView.setTimeout(() => {
          selectedModule = moduleId;
          moduleFocusEnabled = true;
          moduleClickTimer = null;
          render();
          announce(`已选择${moduleLabel}`);
        }, 180);
        return;
      }
      const lineButton = event.target.closest && event.target.closest("[data-line-id]");
      if (lineButton) { state = selectBusinessLine(state, lineButton.dataset.lineId); render(); return; }
      if (event.target.closest && event.target.closest("[data-create-line]")) {
        lineComposerOpen = true;
        render();
        const input = doc.querySelector("[data-line-name]");
        if (input) input.focus();
        return;
      }
      if (event.target.closest && event.target.closest("[data-cancel-line]")) {
        lineComposerOpen = false;
        render();
        return;
      }
      const templateButton = event.target.closest && event.target.closest("[data-template-line]");
      if (templateButton) {
        if (state.privacy && state.privacy.taskDetails === "ANONYMIZED") {
          state = selectBusinessLine(state, templateButton.dataset.templateLine);
          state.activeTemplate = templateButton.dataset.templateLine;
        } else state = applyTemplate(state, templateButton.dataset.templateLine);
        render();
        return;
      }
      if (event.target.closest && event.target.closest("[data-run-scan]")) {
        if (state.privacy && state.privacy.taskDetails === "ANONYMIZED") {
          state.onboarding = { status: "CANDIDATE_READY", readOnly: true, workspaceName: "Synthetic workspace", fileCount: 42, detectedLines: state.businessLines.map((line) => line.line_id) };
        } else state = analyzeFirstRun(state, { name: "Synthetic workspace", files: ["src/app.js", "inputs/source.md", "outputs/draft.md", "AGENTS.md"] });
        render();
        return;
      }
      if (event.target.closest && event.target.closest("[data-add-proposal]")) {
        if (state.runtime && runtimeClient && proposal && proposal.status === "CANDIDATE") {
          try {
            const task = proposal.task;
            await runtimeClient.createTask({
              ...task,
              workflow_id: task.line_id,
              required_capabilities: task.capabilities || [],
            });
            proposal = null;
            await refreshRuntime();
          } catch (error) { announce(`任务未创建：${error.message}`); }
        } else {
          state = addTaskProposal(state, proposal);
          proposal = null;
          render();
        }
        return;
      }
      const runtimeDecision = event.target.closest && event.target.closest("[data-runtime-decision]");
      if (runtimeDecision && runtimeClient) {
        try {
          await runtimeClient.resolveDecision(runtimeDecision.dataset.runtimeDecision, runtimeDecision.dataset.decisionOption);
          await refreshRuntime();
        } catch (error) { announce(`裁决未记录：${error.message}`); }
        return;
      }
      if (event.target.closest && event.target.closest("[data-auto-advance]") && state.runtime && runtimeClient) {
        const adapter = byId("auto-advance-adapter");
        const model = byId("auto-advance-model");
        try {
          announce("正在推进当前可运行任务");
          const result = await runTaskWithPolling(
            () => runtimeClient.advance(adapter ? adapter.value : "", model ? model.value : state.defaultModel, 25, state.activeLineId),
            refreshRuntime,
          );
          announce(`当前工作线已推进 ${result.advanced_count || 0} 项，停在 ${result.stop_reason || "UNKNOWN"}`);
        } catch (error) { announce(`自动推进未执行：${error.message}`); }
        return;
      }
      const decisionCard = event.target.closest && event.target.closest("[data-decision-task]");
      if (decisionCard && event.target.dataset.decision) {
        const taskId = decisionCard.dataset.decisionTask;
        state = recordDecision(state, taskId, event.target.dataset.decision);
        if (event.target.dataset.decision === "APPROVED" && state.taskStates[taskId] === "BLOCKED") state.taskStates[taskId] = "QUEUED";
        render();
        return;
      }
      if (event.target.dataset.planAction === "approve") { state = approvePlan(state); render(); return; }
      const workflowTask = event.target.closest && event.target.closest("[data-workflow-task]");
      if (workflowTask) {
        state.activeTaskId = workflowTask.dataset.workflowTask;
        render();
        return;
      }
      const card = event.target.closest && event.target.closest("[data-task-id]");
      if (!card || event.target.dataset.action !== "task") return;
      const taskId = card.dataset.taskId;
      const action = actionForTask(state, taskId);
      if (state.runtime && runtimeClient) {
        try {
          let refreshAfterAction = true;
          if (action === "ACCEPT") {
            await runtimeClient.transitionTask(taskId, "DONE", "Accepted result");
          } else if (action === "RESUME") {
            await runtimeClient.transitionTask(taskId, "QUEUED", "Resumed by owner");
          } else if (["DISPATCH", "HUMAN_DECISION_REQUIRED"].includes(action)) {
            const adapter = doc.querySelector("[data-runtime-adapter]");
            const model = doc.querySelector("[data-runtime-model]");
            announce("正在连接执行适配器");
            await runTaskWithPolling(
              () => runtimeClient.runTask(taskId, adapter ? adapter.value : "", model ? model.value : state.defaultModel),
              refreshRuntime,
            );
            refreshAfterAction = false;
          } else {
            announce("当前任务还不能执行这个动作");
            return;
          }
          if (refreshAfterAction) await refreshRuntime();
        } catch (error) {
          if (error.payload && error.payload.reason === "HUMAN_DECISION_REQUIRED") {
            await refreshRuntime();
            state = selectBoard(state, "decision");
            render();
            announce("任务需要你先做选择");
          } else announce(`操作未执行：${error.message}`);
        }
        return;
      }
      if (action === "HUMAN_DECISION_REQUIRED") state = selectBoard(state, "decision");
      else state = applyTaskAction(state, taskId);
      render();
    });

    const mapViewport = byId("module-map-viewport");
    mapViewport.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      mapViewport.focus({ preventScroll: true });
      if (moduleButton) {
        const node = moduleTopology.nodes.find((item) => item.module_id === moduleButton.dataset.moduleId);
        if (!node) return;
        mapGesture = { kind: "node", pointerId: event.pointerId, moduleId: node.module_id, startX: event.clientX, startY: event.clientY, nodeX: node.x, nodeY: node.y, moved: false };
      } else {
        mapGesture = { kind: "pan", pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, viewX: moduleView.x, viewY: moduleView.y, moved: false };
        mapViewport.classList.add("is-panning");
      }
      if (captureMapPointerOnDown(mapGesture.kind) && mapViewport.setPointerCapture) {
        mapViewport.setPointerCapture(event.pointerId);
      }
    });
    mapViewport.addEventListener("pointermove", (event) => {
      if (!mapGesture || mapGesture.pointerId !== event.pointerId) return;
      const deltaX = event.clientX - mapGesture.startX;
      const deltaY = event.clientY - mapGesture.startY;
      if (Math.hypot(deltaX, deltaY) > 4 && !mapGesture.moved) {
        mapGesture.moved = true;
        if (mapGesture.kind === "node" && mapViewport.setPointerCapture) {
          mapViewport.setPointerCapture(event.pointerId);
        }
      }
      if (!mapGesture.moved) return;
      event.preventDefault();
      if (mapGesture.kind === "node") {
        moduleTopology = moveModuleNode(moduleTopology, mapGesture.moduleId, mapGesture.nodeX + deltaX / moduleView.scale, mapGesture.nodeY + deltaY / moduleView.scale);
        refreshModuleGeometry();
      } else {
        moduleView = { ...moduleView, x: mapGesture.viewX + deltaX, y: mapGesture.viewY + deltaY };
        applyModuleView();
      }
    });
    function finishMapGesture(event) {
      if (!mapGesture || mapGesture.pointerId !== event.pointerId) return;
      if (mapGesture.kind === "node" && mapGesture.moved) {
        dragClickGuard.markDrag();
        announce("模块位置已更新，依赖连接保持同步");
      }
      mapViewport.classList.remove("is-panning");
      if (mapViewport.hasPointerCapture && mapViewport.hasPointerCapture(event.pointerId)) mapViewport.releasePointerCapture(event.pointerId);
      mapGesture = null;
    }
    mapViewport.addEventListener("pointerup", finishMapGesture);
    mapViewport.addEventListener("pointercancel", finishMapGesture);
    mapViewport.addEventListener("lostpointercapture", () => {
      mapViewport.classList.remove("is-panning");
      mapGesture = null;
    });
    mapViewport.addEventListener("wheel", (event) => {
      const focused = doc.activeElement;
      const focusInsideMap = focused === mapViewport || (focused && focused.closest && focused.closest("#module-map-viewport"));
      if (!focusInsideMap || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      const rect = mapViewport.getBoundingClientRect();
      const anchor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      moduleView = zoomModuleView(moduleView, moduleView.scale * (event.deltaY > 0 ? .9 : 1.1), anchor);
      applyModuleView();
    }, { passive: false });
    mapViewport.addEventListener("contextmenu", (event) => {
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      if (!moduleButton) return;
      event.preventDefault();
      selectedModule = moduleButton.dataset.moduleId;
      moduleFocusEnabled = true;
      render();
      byId("module-annotation").focus();
      announce("已打开当前模块的批注入口");
    });
    mapViewport.addEventListener("dblclick", (event) => {
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      if (!moduleButton || dragClickGuard.consumeClick()) return;
      if (moduleClickTimer) {
        doc.defaultView.clearTimeout(moduleClickTimer);
        moduleClickTimer = null;
      }
      const graph = activeModuleGraph(workspaceView(state));
      const module = graph.modules.find((item) => item.module_id === moduleButton.dataset.moduleId);
      if (!enterModuleGraph(module)) return;
      render();
      announce(`已进入${module.name}`);
    });
    mapViewport.addEventListener("keydown", (event) => {
      const arrows = { ArrowLeft: [-12, 0], ArrowRight: [12, 0], ArrowUp: [0, -12], ArrowDown: [0, 12] };
      if (!arrows[event.key]) return;
      event.preventDefault();
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      if (moduleButton && event.shiftKey) {
        const node = moduleTopology.nodes.find((item) => item.module_id === moduleButton.dataset.moduleId);
        const [deltaX, deltaY] = arrows[event.key];
        moduleTopology = moveModuleNode(moduleTopology, node.module_id, node.x + deltaX, node.y + deltaY);
        refreshModuleGeometry();
        announce(`${node.name}位置已更新`);
        return;
      }
      const [deltaX, deltaY] = arrows[event.key];
      moduleView = { ...moduleView, x: moduleView.x + deltaX * 2, y: moduleView.y + deltaY * 2 };
      applyModuleView();
    });

    byId("task-prompt-form").addEventListener("submit", (event) => {
      event.preventDefault();
      proposal = proposeTaskFromPrompt(state, byId("task-prompt").value);
      render();
    });
    byId("module-annotation-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const annotation = byId("module-annotation");
      const candidate = proposeTaskFromModuleAnnotation(
        state,
        selectedModule,
        annotation.value,
      );
      if (candidate.status !== "CANDIDATE") {
        announce("请先填写模块批注");
        return;
      }
      if (state.runtime && runtimeClient) {
        try {
          await runtimeClient.createTask({
            ...candidate.task,
            workflow_id: candidate.task.line_id,
            required_capabilities: candidate.task.capabilities,
          });
          annotation.value = "";
          await refreshRuntime();
          state = selectBoard(state, "work");
          render();
          announce("模块批注已加入待分配任务");
        } catch (error) {
          announce(`批注任务未创建：${error.message}`);
        }
      } else {
        state = addTaskProposal(state, candidate);
        annotation.value = "";
        render();
        announce("模块批注已加入待分配任务");
      }
    });
    doc.addEventListener("submit", async (event) => {
      const lineForm = event.target.closest && event.target.closest("[data-line-form]");
      if (!lineForm) return;
      event.preventDefault();
      const input = lineForm.querySelector("[data-line-name]");
      const nextState = createWorkline(state, input ? input.value : "");
      const createdLine = nextState.businessLines.at(-1);
      if (state.runtime && runtimeClient) {
        try {
          await runtimeClient.createWorkflow({
            workflow_id: createdLine.line_id,
            name: createdLine.name,
            caption: createdLine.caption,
            layout: createdLine.layout,
            goal: createdLine.name,
          });
          await refreshRuntime();
          state = selectBusinessLine(state, createdLine.line_id);
        } catch (error) {
          announce(`工作线未创建：${error.message}`);
          return;
        }
      } else state = nextState;
      lineComposerOpen = false;
      render();
      announce(`已创建工作线：${createdLine.name}`);
    });
    byId("board-tabs").addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
      const tabs = Array.from(doc.querySelectorAll('[role="tab"][data-board]'));
      const current = tabs.findIndex((tab) => tab === event.target);
      if (current < 0) return;
      event.preventDefault();
      let nextIndex = current;
      if (event.key === 'Home') nextIndex = 0;
      else if (event.key === 'End') nextIndex = tabs.length - 1;
      else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (current + 1) % tabs.length;
      else nextIndex = (current - 1 + tabs.length) % tabs.length;
      state = selectBoard(state, tabs[nextIndex].dataset.board);
      render();
      tabs[nextIndex].focus();
    });
    byId("reset-demo").addEventListener("click", async () => {
      if (state.runtime && runtimeClient) {
        try { await refreshRuntime(); } catch (error) { announce(`状态未刷新：${error.message}`); }
        return;
      }
      state = createShowcaseState();
      moduleMapMode = "system";
      modulePath = [];
      selectedModule = "secretary-entry";
      moduleTopology = null;
      moduleTopologySignature = "";
      moduleViewFitted = false;
      moduleFocusEnabled = true;
      proposal = null;
      lineComposerOpen = false;
      render();
    });
    render();
    if (runtimeClient) refreshRuntime().catch(() => announce("未连接本地运行库，当前使用合成演示"));
  }

  return {
    actionForTask,
    addTaskProposal,
    analyzeFirstRun,
    applyTemplate,
    applyTaskAction,
    approvePlan,
    buildModuleGraph,
    buildModuleTopology,
    captureMapPointerOnDown,
    createDragClickGuard,
    createDemoState,
    createRuntimeClient,
    createShowcaseState,
    createWorkline,
    moduleGraph,
    moduleNeighborhood,
    moveModuleNode,
    petForTask,
    progress,
    proposeTaskFromPrompt,
    proposeTaskFromModuleAnnotation,
    recordDecision,
    renderDecisionCard,
    renderRunDetail,
    renderWorkflowNode,
    renderModuleTopology,
    renderTaskCard,
    runtimeStateFromPayload,
    runTaskWithPolling,
    setPetPreference,
    scrollActiveBoardIntoView,
    selectBoard,
    selectBusinessLine,
    viewModel,
    workflowProjection,
    workflowSummary,
    workspaceView,
    zoomModuleView,
    mount,
  };
});
