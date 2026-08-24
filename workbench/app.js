(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PersonalAIWorkbench = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TASKS = [
    { task_id: "scope", title: "确认研究问题与边界", depends_on: [], human_gate: true, complexity: "standard", capabilities: ["research"], estimated_tokens: 18000 },
    { task_id: "evidence", title: "建立证据与来源地图", depends_on: ["scope"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 120000 },
    { task_id: "outline", title: "裁决文章结构与主张", depends_on: ["evidence"], human_gate: true, complexity: "standard", capabilities: ["research", "writing"], estimated_tokens: 48000 },
    { task_id: "draft", title: "分段生成长文初稿", depends_on: ["outline"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 82000 },
    { task_id: "final", title: "核对引用并完成终审", depends_on: ["draft"], human_gate: true, complexity: "deep", capabilities: ["research", "writing"], estimated_tokens: 150000 },
  ];

  const ROUTES = [
    { route: "quick", tier: 1, max_tokens: 64000, capabilities: ["writing"] },
    { route: "standard", tier: 2, max_tokens: 100000, capabilities: ["research", "writing"] },
    { route: "deep", tier: 3, max_tokens: 240000, capabilities: ["research", "writing"] },
  ];

  const EXECUTORS = [
    { executor: "Research Agent", routes: ["standard", "deep"], capabilities: ["research", "writing"] },
    { executor: "Writing Agent", routes: ["quick", "standard"], capabilities: ["writing"] },
  ];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createDemoState() {
    return {
      goal: "完成一份可核验、可持续迭代的跨学科研究综述",
      planApproved: false,
      tasks: clone(TASKS),
      taskStates: Object.fromEntries(TASKS.map((task) => [task.task_id, "QUEUED"])),
      decisions: {},
      assignments: {},
    };
  }

  function approvePlan(state) {
    return { ...clone(state), planApproved: true };
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
    if (current === "DONE") return "NONE";
    if (current === "BLOCKED") return "BLOCKED";
    if (task.depends_on.some((dependency) => state.taskStates[dependency] !== "DONE")) {
      return "WAITING_DEPENDENCY";
    }
    if (task.human_gate && state.decisions[taskId] !== "APPROVED") {
      return "HUMAN_DECISION_REQUIRED";
    }
    if (current === "QUEUED") return "DISPATCH";
    if (current === "IN_PROGRESS") return "REQUEST_REVIEW";
    if (current === "REVIEW") return "ACCEPT";
    return "NONE";
  }

  function routeTask(task) {
    const requiredTier = { quick: 1, standard: 2, deep: 3 }[task.complexity] || 2;
    return ROUTES.find((route) =>
      route.tier >= requiredTier &&
      route.max_tokens >= task.estimated_tokens &&
      task.capabilities.every((capability) => route.capabilities.includes(capability))
    );
  }

  function assignTask(task, route) {
    return EXECUTORS.find((executor) =>
      executor.routes.includes(route.route) &&
      task.capabilities.every((capability) => executor.capabilities.includes(capability))
    );
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
      next.assignments[taskId] = { route: route.route, executor: executor.executor };
      next.taskStates[taskId] = "IN_PROGRESS";
    } else if (action === "REQUEST_REVIEW") {
      next.taskStates[taskId] = "REVIEW";
    } else if (action === "ACCEPT") {
      next.taskStates[taskId] = "DONE";
    }
    return next;
  }

  function progress(state) {
    const total = state.tasks.length;
    const done = Object.values(state.taskStates).filter((value) => value === "DONE").length;
    return { done, total, percent: total ? Math.floor(done * 100 / total) : 0 };
  }

  function viewModel(state) {
    const lanes = { QUEUED: [], IN_PROGRESS: [], REVIEW: [], DONE: [], BLOCKED: [] };
    const tasks = {};
    state.tasks.forEach((task) => {
      const status = state.taskStates[task.task_id];
      if (lanes[status]) lanes[status].push(task.task_id);
      tasks[task.task_id] = {
        ...task,
        status,
        action: actionForTask(state, task.task_id),
        assignment: state.assignments[task.task_id] || null,
        decision: state.decisions[task.task_id] || "PENDING",
      };
    });
    const pendingHumanGates = state.tasks.filter(
      (task) => task.human_gate && !state.decisions[task.task_id]
    ).length;
    return {
      goal: state.goal,
      planApproved: state.planApproved,
      progress: progress(state),
      pendingHumanGates,
      lanes,
      tasks,
    };
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  const ACTION_LABELS = {
    PLAN_APPROVAL_REQUIRED: "等待计划确认",
    HUMAN_DECISION_REQUIRED: "需要你裁决",
    WAITING_DEPENDENCY: "等待前置任务",
    DISPATCH: "分派并开始",
    REQUEST_REVIEW: "提交验收",
    ACCEPT: "接受结果",
    BLOCKED: "已阻塞",
    NONE: "已完成",
  };

  function renderTaskCard(task) {
    const assignment = task.assignment
      ? `<span class="task-chip route">${escapeHtml(task.assignment.route)}</span><span class="task-chip">${escapeHtml(task.assignment.executor)}</span>`
      : "";
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action);
    return `<article class="task-card status-${escapeHtml(task.status.toLowerCase())}" data-task-id="${escapeHtml(task.task_id)}">
      <div class="task-card-top"><span class="task-id">${escapeHtml(task.task_id)}</span><span class="task-complexity">${escapeHtml(task.complexity)}</span></div>
      <h3>${escapeHtml(task.title)}</h3>
      <div class="task-meta">
        ${task.human_gate ? '<span class="task-chip human">Human Gate</span>' : ""}
        <span class="task-chip">约 ${Math.round(Number(task.estimated_tokens || 0) / 1000)}k tokens</span>
        ${assignment}
      </div>
      <button class="task-action" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(ACTION_LABELS[task.action] || task.action)}</button>
    </article>`;
  }

  function renderHierarchy(state) {
    return state.tasks.map((task, index) => {
      const status = state.taskStates[task.task_id];
      const connector = index < state.tasks.length - 1 ? '<span class="tree-line"></span>' : "";
      return `<li class="tree-item"><span class="tree-index">${index + 1}</span>${connector}<div><b>${escapeHtml(task.title)}</b><small>${escapeHtml(status)}</small></div></li>`;
    }).join("");
  }

  function mount(doc) {
    let state = createDemoState();
    let pendingDecision = null;
    const byId = (id) => doc.getElementById(id);

    function render() {
      const view = viewModel(state);
      byId("goal").textContent = view.goal;
      byId("progress-text").textContent = `${view.progress.done} / ${view.progress.total}`;
      byId("progress-percent").textContent = `${view.progress.percent}%`;
      byId("progress-bar").style.width = `${view.progress.percent}%`;
      byId("plan-state").textContent = view.planApproved ? "计划已确认" : "等待你确认计划";
      byId("approve-plan").hidden = view.planApproved;
      byId("task-tree").innerHTML = renderHierarchy(state);
      byId("human-gates").textContent = String(view.pendingHumanGates);
      byId("context-total").textContent = `${Math.round(state.tasks.reduce(
        (sum, task) => sum + task.estimated_tokens, 0
      ) / 1000)}k`;
      Object.keys(view.lanes).forEach((lane) => {
        const target = doc.querySelector(`[data-lane="${lane}"]`);
        if (!target) return;
        target.innerHTML = view.lanes[lane].map((taskId) => renderTaskCard(view.tasks[taskId])).join("")
          || '<p class="lane-empty">暂无任务</p>';
        const count = doc.querySelector(`[data-count="${lane}"]`);
        if (count) count.textContent = String(view.lanes[lane].length);
      });
    }

    doc.addEventListener("click", (event) => {
      const card = event.target.closest && event.target.closest("[data-task-id]");
      if (!card || event.target.dataset.action !== "task") return;
      const taskId = card.dataset.taskId;
      const action = actionForTask(state, taskId);
      if (action === "HUMAN_DECISION_REQUIRED") {
        pendingDecision = taskId;
        byId("decision-title").textContent = taskById(state, taskId).title;
        byId("decision-modal").hidden = false;
        return;
      }
      state = applyTaskAction(state, taskId);
      render();
    });
    byId("approve-plan").addEventListener("click", () => { state = approvePlan(state); render(); });
    byId("decision-approve").addEventListener("click", () => {
      state = recordDecision(state, pendingDecision, "APPROVED");
      pendingDecision = null;
      byId("decision-modal").hidden = true;
      render();
    });
    byId("decision-reject").addEventListener("click", () => {
      state = recordDecision(state, pendingDecision, "REJECTED");
      pendingDecision = null;
      byId("decision-modal").hidden = true;
      render();
    });
    byId("reset-demo").addEventListener("click", () => {
      state = createDemoState();
      pendingDecision = null;
      byId("decision-modal").hidden = true;
      render();
    });
    render();
  }

  return {
    actionForTask,
    applyTaskAction,
    approvePlan,
    createDemoState,
    progress,
    recordDecision,
    renderTaskCard,
    viewModel,
    mount,
  };
});
