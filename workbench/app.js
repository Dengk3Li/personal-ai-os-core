(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PersonalAIWorkbench = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
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
    { line_id: "research", name: "科研线", caption: "问题、材料与验证任务", layout: "timeline", stages: ["问题边界", "材料整理", "验证执行", "结果复核"], traceStatus: "OPEN_DECISION", note: "研究脉络的专用模型暂不定义；当前只使用通用任务状态。" },
    { line_id: "product", name: "产品线", caption: "模块、能力与版本里程碑", layout: "milestones", stages: ["系统契约", "核心骨架", "交互实现", "版本验收"] },
    { line_id: "writing", name: "写作线", caption: "资料、结构与长文交付", layout: "pipeline", stages: ["材料整理", "结构确认", "分段写作", "终稿验收"] },
  ];

  const SHOWCASE_WORKFLOWS = [
    { line_id: "loop-validation", name: "循环验证流", caption: "问题冻结、假设并行与重复验证", layout: "loop", stages: ["冻结输入", "提出假设", "并行验证", "裁决与回环"] },
    { line_id: "parallel-production", name: "并行生产流", caption: "输入整理、结构生成与分段汇合", layout: "branch", stages: ["整理输入", "提取结构", "并行生产", "合并复核"] },
    { line_id: "system-build", name: "系统构建流", caption: "能力模块、适配器与端到端验收", layout: "milestones", stages: ["定义端口", "装配模块", "连接执行", "运行验收"] },
  ];

  const SHOWCASE_TASKS = [
    { task_id: "flow-a-01", public_label: "任务 A-01", line_id: "loop-validation", stage: "冻结输入", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "standard", capabilities: ["analysis"], estimated_tokens: 18000 },
    { task_id: "flow-a-02", public_label: "任务 A-02", line_id: "loop-validation", stage: "基线检查", iteration: 1, parallel_group: "main", attempts: 2, depends_on: ["flow-a-01"], human_gate: false, complexity: "deep", capabilities: ["analysis"], estimated_tokens: 68000 },
    { task_id: "flow-a-03", public_label: "任务 A-03", line_id: "loop-validation", stage: "假设分支 α", iteration: 2, parallel_group: "branch-alpha", attempts: 2, depends_on: ["flow-a-02"], human_gate: false, complexity: "deep", capabilities: ["analysis"], estimated_tokens: 82000 },
    { task_id: "flow-a-04", public_label: "任务 A-04", line_id: "loop-validation", stage: "假设分支 β", iteration: 2, parallel_group: "branch-beta", attempts: 1, depends_on: ["flow-a-02"], human_gate: false, complexity: "deep", capabilities: ["analysis"], estimated_tokens: 82000 },
    { task_id: "flow-a-05", public_label: "任务 A-05", line_id: "loop-validation", stage: "结果汇合", iteration: 3, parallel_group: "main", attempts: 0, depends_on: ["flow-a-03", "flow-a-04"], human_gate: false, complexity: "standard", capabilities: ["analysis"], estimated_tokens: 36000 },
    { task_id: "flow-a-06", public_label: "任务 A-06", line_id: "loop-validation", stage: "人类裁决", iteration: 3, parallel_group: "gate", attempts: 0, depends_on: ["flow-a-05"], human_gate: true, complexity: "standard", capabilities: ["analysis"], estimated_tokens: 12000 },
    { task_id: "flow-b-01", public_label: "任务 B-01", line_id: "parallel-production", stage: "输入清点", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "quick", capabilities: ["writing"], estimated_tokens: 12000 },
    { task_id: "flow-b-02", public_label: "任务 B-02", line_id: "parallel-production", stage: "证据提取", iteration: 1, parallel_group: "main", attempts: 1, depends_on: ["flow-b-01"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 32000 },
    { task_id: "flow-b-03", public_label: "任务 B-03", line_id: "parallel-production", stage: "结构生成", iteration: 2, parallel_group: "main", attempts: 3, depends_on: ["flow-b-02"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 44000 },
    { task_id: "flow-b-04", public_label: "任务 B-04", line_id: "parallel-production", stage: "分支段落 α", iteration: 3, parallel_group: "branch-alpha", attempts: 0, depends_on: ["flow-b-03"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 38000 },
    { task_id: "flow-b-05", public_label: "任务 B-05", line_id: "parallel-production", stage: "分支段落 β", iteration: 3, parallel_group: "branch-beta", attempts: 0, depends_on: ["flow-b-03"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 38000 },
    { task_id: "flow-b-06", public_label: "任务 B-06", line_id: "parallel-production", stage: "分支段落 γ", iteration: 3, parallel_group: "branch-gamma", attempts: 0, depends_on: ["flow-b-03"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 38000 },
    { task_id: "flow-b-07", public_label: "任务 B-07", line_id: "parallel-production", stage: "合并复核", iteration: 4, parallel_group: "main", attempts: 0, depends_on: ["flow-b-04", "flow-b-05", "flow-b-06"], human_gate: true, complexity: "deep", capabilities: ["writing"], estimated_tokens: 76000 },
    { task_id: "flow-c-01", public_label: "任务 C-01", line_id: "system-build", stage: "端口契约", iteration: 1, parallel_group: "main", attempts: 1, depends_on: [], human_gate: false, complexity: "deep", capabilities: ["engineering"], estimated_tokens: 52000 },
    { task_id: "flow-c-02", public_label: "任务 C-02", line_id: "system-build", stage: "模块装配", iteration: 1, parallel_group: "main", attempts: 0, depends_on: ["flow-c-01"], human_gate: false, complexity: "standard", capabilities: ["engineering"], estimated_tokens: 42000 },
    { task_id: "flow-c-03", public_label: "任务 C-03", line_id: "system-build", stage: "执行适配", iteration: 2, parallel_group: "branch-alpha", attempts: 0, depends_on: ["flow-c-02"], human_gate: false, complexity: "deep", capabilities: ["engineering"], estimated_tokens: 58000 },
    { task_id: "flow-c-04", public_label: "任务 C-04", line_id: "system-build", stage: "状态投影", iteration: 2, parallel_group: "branch-beta", attempts: 1, depends_on: [], human_gate: false, complexity: "standard", capabilities: ["engineering"], estimated_tokens: 36000 },
    { task_id: "flow-c-05", public_label: "任务 C-05", line_id: "system-build", stage: "端到端验收", iteration: 3, parallel_group: "main", attempts: 0, depends_on: ["flow-c-03", "flow-c-04"], human_gate: true, complexity: "deep", capabilities: ["engineering"], estimated_tokens: 68000 },
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
    { executor: "Research Agent", routes: ["standard", "deep"], capabilities: ["research", "writing"] },
    { executor: "Product Agent", routes: ["standard", "deep"], capabilities: ["engineering"] },
    { executor: "Writing Agent", routes: ["quick", "standard"], capabilities: ["writing"] },
  ];

  const OPERATION_CHAIN = ["INSPECT", "MAP", "PLAN", "CONFIRM", "ROUTE", "EXECUTE", "REVIEW", "ARCHIVE"];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createDemoState() {
    return {
      goal: "把一个复杂工作区变成可理解、可裁决、可持续推进的长期工作系统",
      activeBoard: "work",
      activeLineId: "research",
      planApproved: false,
      tasks: clone(TASKS),
      businessLines: clone(BUSINESS_LINES),
      taskStates: Object.fromEntries(TASKS.map((task) => [task.task_id, "UNASSIGNED"])),
      decisions: {},
      assignments: {},
      onboarding: { status: "NOT_STARTED", readOnly: true, detectedLines: [] },
      activeTemplate: null,
      taskProposal: null,
    };
  }

  function runEvents(taskId, attempts, status) {
    if (!attempts) return [];
    const events = [
      { kind: "assigned", label: "已分配执行器", at: "09:12" },
      { kind: "adapter_started", label: "适配器已启动", at: "09:13" },
      { kind: "heartbeat", label: "运行心跳正常", at: "09:18" },
    ];
    if (["REVIEW", "CLOSED", "COMPLETED", "ARCHIVED"].includes(status)) {
      events.push({ kind: "artifact", label: "阶段产物已登记", at: "09:26" });
    }
    if (attempts > 1) {
      events.unshift({ kind: "retry", label: `前一轮已保留 · 当前第 ${attempts} 次运行`, at: "09:08" });
    }
    return events.map((event) => ({ ...event, event_id: `${taskId}-${event.kind}` }));
  }

  function createShowcaseState() {
    const statuses = {
      "flow-a-01": "CLOSED", "flow-a-02": "CLOSED", "flow-a-03": "IN_PROGRESS", "flow-a-04": "IN_PROGRESS", "flow-a-05": "UNASSIGNED", "flow-a-06": "BLOCKED",
      "flow-b-01": "CLOSED", "flow-b-02": "CLOSED", "flow-b-03": "IN_PROGRESS", "flow-b-04": "UNASSIGNED", "flow-b-05": "UNASSIGNED", "flow-b-06": "UNASSIGNED", "flow-b-07": "UNASSIGNED",
      "flow-c-01": "REVIEW", "flow-c-02": "UNASSIGNED", "flow-c-03": "UNASSIGNED", "flow-c-04": "REVIEW", "flow-c-05": "UNASSIGNED",
    };
    const assignmentSpecs = {
      "flow-a-01": ["deep", "Reasoning model", "Validation adapter"],
      "flow-a-02": ["deep", "Reasoning model", "Validation adapter"],
      "flow-a-03": ["deep", "Reasoning model", "Validation adapter"],
      "flow-a-04": ["standard", "General model", "Parallel adapter"],
      "flow-b-01": ["quick", "Fast model", "Content adapter"],
      "flow-b-02": ["standard", "General model", "Content adapter"],
      "flow-b-03": ["standard", "General model", "Content adapter"],
      "flow-c-01": ["deep", "Reasoning model", "Code adapter"],
      "flow-c-04": ["standard", "General model", "Code adapter"],
    };
    const assignments = Object.fromEntries(Object.entries(assignmentSpecs).map(([taskId, values]) => [taskId, { route: values[0], model: values[1], executor: values[2] }]));
    const tasks = clone(SHOWCASE_TASKS).map((task) => ({
      ...task,
      events: runEvents(task.task_id, task.attempts, statuses[task.task_id]),
    }));
    return {
      goal: "把长期目标拆成可分配、可重复运行、可由人类裁决的短任务",
      activeBoard: "work",
      activeLineId: "loop-validation",
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
    if (["CLOSED", "ARCHIVED", "COMPLETED"].includes(current)) return "NONE";
    if (current === "BLOCKED") return "BLOCKED";
    if (task.depends_on.some((dependency) => !["CLOSED", "ARCHIVED", "COMPLETED"].includes(state.taskStates[dependency]))) return "WAITING_DEPENDENCY";
    if (task.human_gate && state.decisions[taskId] !== "APPROVED") return "HUMAN_DECISION_REQUIRED";
    if (current === "UNASSIGNED") return "DISPATCH";
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
      next.taskStates[taskId] = "CLOSED";
      const task = taskById(next, taskId);
      if (task && Array.isArray(task.events)) task.events.push({ event_id: `${taskId}-accepted`, kind: "accepted", label: "人工验收已通过", at: "09:31" });
    }
    return next;
  }

  function progress(state, taskIds) {
    const ids = taskIds || state.tasks.map((task) => task.task_id);
    const done = ids.filter((taskId) => ["CLOSED", "ARCHIVED", "COMPLETED"].includes(state.taskStates[taskId])).length;
    return { done, total: ids.length, percent: ids.length ? Math.floor(done * 100 / ids.length) : 0 };
  }

  function viewModel(state) {
    const lanes = { UNASSIGNED: [], IN_PROGRESS: [], REVIEW: [], BLOCKED: [], CLOSED: [], ARCHIVED: [], COMPLETED: [] };
    const tasks = {};
    state.tasks.forEach((task) => {
      const status = state.taskStates[task.task_id] || "UNASSIGNED";
      if (lanes[status]) lanes[status].push(task.task_id);
      tasks[task.task_id] = { ...task, status, action: actionForTask(state, task.task_id), assignment: state.assignments[task.task_id] || null, decision: state.decisions[task.task_id] || "PENDING" };
    });
    const pendingHumanGates = state.tasks.filter((task) => task.human_gate && !state.decisions[task.task_id]).length;
    return { goal: state.goal, planApproved: state.planApproved, progress: progress(state), pendingHumanGates, lanes, tasks };
  }

  function workflowSummary(state, taskIds) {
    const allowed = taskIds ? new Set(taskIds) : null;
    const tasks = allowed ? state.tasks.filter((task) => allowed.has(task.task_id)) : state.tasks;
    const completedStates = ["CLOSED", "ARCHIVED", "COMPLETED"];
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
      status: state.taskStates[task.task_id] || "UNASSIGNED",
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
    const pending = state.planApproved ? [
      ...state.tasks.filter((task) => state.taskStates[task.task_id] === "BLOCKED").map((task) => ({ ...task, title: task.title || task.public_label, acceptance: task.acceptance || task.stage, kind: "blocked", summary: "任务已阻塞，需要调整边界或重新批准。" })),
      ...state.tasks.filter((task) => actionForTask(state, task.task_id) === "HUMAN_DECISION_REQUIRED").map((task) => ({ ...task, title: task.title || task.public_label, acceptance: task.acceptance || task.stage, kind: "task" })),
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
      ? lineId === "system-build" ? ["engineering"] : lineId === "parallel-production" ? ["writing"] : ["research"]
      : lineId === "product" ? ["engineering"] : lineId === "research" ? ["research"] : ["writing"];
    const task = { task_id: `created-${state.tasks.length + 1}`, public_label: `任务 N-${String(state.tasks.length + 1).padStart(2, "0")}`, line_id: lineId, title: text, acceptance: "产出可检查、可继续推进的阶段结果", stage: "待拆解", iteration: 1, parallel_group: "main", attempts: 0, events: [], depends_on: [], human_gate: false, complexity, capabilities, estimated_tokens: complexity === "deep" ? 120000 : 48000, status: "UNASSIGNED" };
    return { status: "CANDIDATE", line_id: lineId, task, route: routeTask(task) };
  }

  function addTaskProposal(state, proposal) {
    if (!proposal || proposal.status !== "CANDIDATE") return clone(state);
    const next = clone(state);
    const task = clone(proposal.task);
    delete task.status;
    next.tasks.push(task);
    next.taskStates[task.task_id] = "UNASSIGNED";
    next.activeLineId = task.line_id;
    next.activeBoard = "work";
    next.taskProposal = null;
    return next;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }

  const ACTION_LABELS = { PLAN_APPROVAL_REQUIRED: "等待计划确认", HUMAN_DECISION_REQUIRED: "需要你裁决", WAITING_DEPENDENCY: "等待前置任务", DISPATCH: "分派并开始", REQUEST_REVIEW: "提交验收", ACCEPT: "接受并收口", BLOCKED: "需要处理", NONE: "已收口" };
  const STATUS_LABELS = { UNASSIGNED: "待分配", IN_PROGRESS: "进行中", REVIEW: "待验收", BLOCKED: "已阻塞", CLOSED: "已收口", ARCHIVED: "已归档", COMPLETED: "已完成" };

  function renderTaskCard(task) {
    const assignment = task.assignment ? `<span class="task-chip route">${escapeHtml(task.assignment.route)}</span><span class="task-chip">${escapeHtml(task.assignment.executor)}</span>` : "";
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action);
    return `<article class="task-row status-${escapeHtml(task.status.toLowerCase())}" data-task-id="${escapeHtml(task.task_id)}">
      <div class="task-state"><span class="status-dot"></span><b>${escapeHtml(STATUS_LABELS[task.status] || task.status)}</b></div>
      <div class="task-main"><div class="card-meta"><span>${escapeHtml(task.complexity)}</span>${task.human_gate ? '<span class="signal-pill">Human Gate</span>' : ""}</div><h3>${escapeHtml(task.title || task.public_label)}</h3><p>${escapeHtml(task.acceptance || task.stage)}</p></div>
      <div class="task-route">${assignment || '<span class="task-chip">等待路由</span>'}</div>
      <button class="task-action" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(ACTION_LABELS[task.action] || task.action)}</button>
    </article>`;
  }

  function renderDecisionCard(item) {
    if (item.kind === "plan") return `<article class="decision-card plan-decision"><div><span class="signal-pill">计划确认</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p></div><button class="primary-button" type="button" data-plan-action="approve">确认并开始</button></article>`;
    if (item.kind === "blocked") return `<article class="decision-card blocked-decision" data-decision-task="${escapeHtml(item.task_id)}"><div><span class="status-pill status-blocked">已阻塞</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)}</p></div><div class="card-actions"><button class="card-action" type="button" data-decision="APPROVED">调整后重开</button></div></article>`;
    return `<article class="decision-card" data-decision-task="${escapeHtml(item.task_id)}"><div><span class="signal-pill">Human Gate</span><h3>${escapeHtml(item.title)}</h3><p>验收条件：${escapeHtml(item.acceptance)}</p></div><div class="card-actions"><button class="card-action reject" type="button" data-decision="REJECTED">退回</button><button class="card-action approve" type="button" data-decision="APPROVED">批准并继续</button></div></article>`;
  }

  function renderModuleCard(module, selected, upstream) {
    const dependency = upstream.length ? `上游 · ${upstream.join(" / ")}` : "系统入口";
    return `<button class="module-card${selected ? " active" : ""}" type="button" data-module-id="${escapeHtml(module.module_id)}" aria-pressed="${selected ? "true" : "false"}"><span class="module-card-head"><span class="module-layer">${escapeHtml(module.layer)} · ${module.optional ? "可选" : "核心"}</span><em class="availability availability-${escapeHtml(module.availability.toLowerCase())}">${module.availability === "READY" ? "可用" : "规划中"}</em></span><b>${escapeHtml(module.name)}</b><small>${escapeHtml(module.summary)}</small><span class="module-upstream">${escapeHtml(dependency)}</span></button>`;
  }

  function renderDependencyEdge(edge, moduleNames) {
    return `<li><b>${escapeHtml(moduleNames[edge[0]] || edge[0])}</b><span aria-hidden="true">→</span><b>${escapeHtml(moduleNames[edge[1]] || edge[1])}</b></li>`;
  }

  function renderLineButton(line, active) {
    return `<button class="line-tab${active ? " active" : ""}" type="button" data-line-id="${escapeHtml(line.line_id)}" aria-pressed="${active ? "true" : "false"}"><span><b>${escapeHtml(line.name)}</b><small>${escapeHtml(line.caption)}</small></span><em>${line.progress.done}/${line.progress.total}</em></button>`;
  }

  function renderStageRail(line) {
    return `<ol class="stage-rail layout-${escapeHtml(line.layout)}">${line.stages.map((stage, index) => `<li class="${index === 0 ? "current" : ""}"><span>${String(index + 1).padStart(2, "0")}</span><b>${escapeHtml(stage)}</b></li>`).join("")}</ol>`;
  }

  function renderWorkflowNode(task, selected) {
    const assignment = task.assignment;
    const route = assignment ? `${escapeHtml(assignment.model)}<span>${escapeHtml(assignment.executor)}</span>` : "等待分配<span>尚未选择执行器</span>";
    return `<button class="workflow-node status-${escapeHtml(task.status.toLowerCase())}${selected ? " selected" : ""}" type="button" data-workflow-task="${escapeHtml(task.task_id)}" aria-pressed="${selected ? "true" : "false"}">
      <span class="workflow-node-head"><span class="workflow-node-id">${escapeHtml(task.public_label || task.title || task.task_id)}</span><span class="workflow-node-status"><i class="run-pulse" aria-hidden="true"></i>${escapeHtml(STATUS_LABELS[task.status] || task.status)}</span></span>
      <span class="workflow-node-stage">${escapeHtml(task.stage || "自定义任务")}</span>
      <span class="workflow-node-route">${route}<span>${task.attempts ? `第 ${task.attempts} 次运行` : "尚未运行"}</span></span>
    </button>`;
  }

  function renderWorkflowCanvas(projection, selectedTaskId) {
    if (!projection || !projection.groups.length) return '<p class="empty-trace">当前工作流还没有任务。</p>';
    const groups = projection.groups.map((group, index) => {
      const active = group.nodes.some((task) => task.status === "IN_PROGRESS" || task.status === "REVIEW");
      const label = projection.layout === "loop" ? `Loop ${String(group.iteration).padStart(2, "0")}` : `阶段 ${String(group.iteration).padStart(2, "0")}`;
      const returnEdge = projection.layout === "loop" && index < projection.groups.length - 1 ? '<div class="loop-return">复核后进入下一轮</div>' : "";
      return `<section class="workflow-group${active ? " active" : ""}"><header class="group-heading"><strong>${label}</strong><span>${group.nodes.length} 个节点 · ${new Set(group.nodes.map((task) => task.parallel_group)).size} 个分支</span></header><div class="workflow-nodes">${group.nodes.map((task) => renderWorkflowNode(task, task.task_id === selectedTaskId)).join("")}</div>${returnEdge}</section>`;
    }).join("");
    return `<div class="workflow-groups">${groups}</div>`;
  }

  function renderRunDetail(task) {
    if (!task) return '<p class="empty-trace">选择一个节点查看运行轨迹。</p>';
    const assignment = task.assignment;
    const events = task.events && task.events.length
      ? `<ol class="event-trace">${task.events.map((event) => `<li><time>${escapeHtml(event.at)}</time><span>${escapeHtml(event.label)}</span></li>`).join("")}</ol>`
      : '<p class="empty-trace">任务尚未分配。分配后会记录适配器启动、心跳、产物与复核事件。</p>';
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action);
    return `<div class="run-detail-head"><span>${escapeHtml(task.public_label || task.title || task.task_id)} · ${escapeHtml(STATUS_LABELS[task.status] || task.status)}</span><h3>${escapeHtml(task.stage || "自定义任务")}</h3></div>
      <dl class="run-detail-meta"><div><dt>模型</dt><dd>${escapeHtml(assignment ? assignment.model : "等待选择")}</dd></div><div><dt>执行适配器</dt><dd>${escapeHtml(assignment ? assignment.executor : "尚未分配")}</dd></div><div><dt>运行轮次</dt><dd>${task.attempts ? `Attempt ${String(task.attempts).padStart(2, "0")}` : "尚未运行"}</dd></div><div><dt>并行分支</dt><dd>${escapeHtml(task.parallel_group || "main")}</dd></div></dl>
      ${events}
      <div data-task-id="${escapeHtml(task.task_id)}"><button class="task-action" type="button" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(ACTION_LABELS[task.action] || task.action)}</button></div>`;
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
    let selectedModule = "workflow-core";
    let proposal = null;
    const byId = (id) => doc.getElementById(id);

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

      const moduleNames = Object.fromEntries(view.global.modules.map((item) => [item.module_id, item.name]));
      byId("module-grid").innerHTML = view.global.modules.map((module) => {
        const upstream = view.global.edges.filter((edge) => edge[1] === module.module_id).map((edge) => moduleNames[edge[0]] || edge[0]);
        return renderModuleCard(module, module.module_id === selectedModule, upstream);
      }).join("");
      byId("dependency-edge-list").innerHTML = view.global.edges.map((edge) => renderDependencyEdge(edge, moduleNames)).join("");
      const module = view.global.modules.find((item) => item.module_id === selectedModule) || view.global.modules[0];
      byId("module-detail-name").textContent = module ? module.name : "没有已安装模块";
      byId("module-detail-summary").textContent = module ? module.summary : "把 module.json 放入模块目录后即可参与解析。";
      byId("module-provides").textContent = module ? module.provides.join(" · ") : "—";
      byId("module-requires").textContent = module && module.requires.length ? module.requires.join(" · ") : "无前置 capability";
      byId("scan-status").textContent = view.onboarding.status === "CANDIDATE_READY" ? `已只读识别 ${view.onboarding.fileCount} 个文件信号，生成 ${view.onboarding.detectedLines.length} 条候选业务线。` : view.onboarding.status === "TEMPLATE_READY" ? `已载入${view.onboarding.workspaceName}模板；确认后生成对应任务。` : "首次运行先读取本地结构，再生成可编辑的模块图与工作计划。";
      doc.querySelectorAll("[data-template-line]").forEach((button) => button.classList.toggle("active", button.dataset.templateLine === state.activeTemplate));

      byId("line-tabs").innerHTML = view.work.lines.map((line) => renderLineButton(line, line.line_id === view.work.activeLine.line_id)).join("");
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
      const projection = workflowProjection(state, view.work.activeLine.line_id);
      const projectedTasks = projection ? projection.groups.flatMap((group) => group.nodes) : [];
      let selectedTask = projectedTasks.find((task) => task.task_id === state.activeTaskId);
      if (!selectedTask) selectedTask = projectedTasks.find((task) => task.status === "IN_PROGRESS") || projectedTasks[0];
      if (selectedTask) state.activeTaskId = selectedTask.task_id;
      byId("workflow-canvas").innerHTML = renderWorkflowCanvas(projection, state.activeTaskId);
      const selectedTaskView = selectedTask ? view.work.tasks[selectedTask.task_id] : null;
      byId("run-detail").innerHTML = renderRunDetail(selectedTaskView);
      byId("proposal-zone").innerHTML = renderProposal(proposal, view.work.lines);

      byId("decision-list").innerHTML = view.decision.pending.length ? view.decision.pending.map(renderDecisionCard).join("") : '<div class="empty-state"><span>✓</span><h3>当前没有待裁决事项</h3><p>新的计划确认、阻塞和 Human Gate 会集中出现在这里。</p></div>';
      byId("decision-visible-count").textContent = `${view.decision.pending.length} 项待处理`;
      if (doc.defaultView && doc.defaultView.history) doc.defaultView.history.replaceState(null, "", `#${view.activeBoard}`);
      if (focusToken) {
        const attribute = `data-${focusToken[0].replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
        const target = Array.from(doc.querySelectorAll(`[${attribute}]`)).find((item) => item.dataset[focusToken[0]] === focusToken[1]);
        if (target) target.focus();
      }
    }

    doc.addEventListener("click", (event) => {
      const boardButton = event.target.closest && event.target.closest("[data-board]");
      if (boardButton) {
        state = selectBoard(state, boardButton.dataset.board);
        render();
        scrollActiveBoardIntoView(doc, state.activeBoard);
        return;
      }
      const moduleButton = event.target.closest && event.target.closest("[data-module-id]");
      if (moduleButton) { selectedModule = moduleButton.dataset.moduleId; render(); return; }
      const lineButton = event.target.closest && event.target.closest("[data-line-id]");
      if (lineButton) { state = selectBusinessLine(state, lineButton.dataset.lineId); render(); return; }
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
      if (event.target.closest && event.target.closest("[data-add-proposal]")) { state = addTaskProposal(state, proposal); proposal = null; render(); return; }
      const decisionCard = event.target.closest && event.target.closest("[data-decision-task]");
      if (decisionCard && event.target.dataset.decision) {
        const taskId = decisionCard.dataset.decisionTask;
        state = recordDecision(state, taskId, event.target.dataset.decision);
        if (event.target.dataset.decision === "APPROVED" && state.taskStates[taskId] === "BLOCKED") state.taskStates[taskId] = "UNASSIGNED";
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
      if (actionForTask(state, taskId) === "HUMAN_DECISION_REQUIRED") state = selectBoard(state, "decision");
      else state = applyTaskAction(state, taskId);
      render();
    });

    byId("task-prompt-form").addEventListener("submit", (event) => {
      event.preventDefault();
      proposal = proposeTaskFromPrompt(state, byId("task-prompt").value);
      render();
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
    byId("reset-demo").addEventListener("click", () => { state = createShowcaseState(); selectedModule = "workflow-core"; proposal = null; render(); });
    render();
  }

  return {
    actionForTask,
    addTaskProposal,
    analyzeFirstRun,
    applyTemplate,
    applyTaskAction,
    approvePlan,
    buildModuleGraph,
    createDemoState,
    createShowcaseState,
    moduleGraph,
    progress,
    proposeTaskFromPrompt,
    recordDecision,
    renderDecisionCard,
    renderTaskCard,
    scrollActiveBoardIntoView,
    selectBoard,
    selectBusinessLine,
    viewModel,
    workflowProjection,
    workflowSummary,
    workspaceView,
    mount,
  };
});
