(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PersonalAIWorkbench = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TASKS = [
    { task_id: "scope", title: "确认研究问题与边界", acceptance: "研究问题、范围和排除项得到确认", depends_on: [], human_gate: true, complexity: "standard", capabilities: ["research"], estimated_tokens: 18000 },
    { task_id: "evidence", title: "建立证据与来源地图", acceptance: "每个主要主张都能追溯到来源", depends_on: ["scope"], human_gate: false, complexity: "deep", capabilities: ["research"], estimated_tokens: 120000 },
    { task_id: "outline", title: "裁决文章结构与主张", acceptance: "章节结构和核心主张得到确认", depends_on: ["evidence"], human_gate: true, complexity: "standard", capabilities: ["research", "writing"], estimated_tokens: 48000 },
    { task_id: "draft", title: "分段生成长文初稿", acceptance: "各章节完成且遵循已确认结构", depends_on: ["outline"], human_gate: false, complexity: "standard", capabilities: ["writing"], estimated_tokens: 82000 },
    { task_id: "final", title: "核对引用并完成终审", acceptance: "引用、结论和不确定性通过终审", depends_on: ["draft"], human_gate: true, complexity: "deep", capabilities: ["research", "writing"], estimated_tokens: 150000 },
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

  const PRIMARY_BOARDS = [
    { id: "global", label: "全局地图", summary: "系统如何接住长期工作" },
    { id: "work", label: "工作进度", summary: "任务现在推进到哪里" },
    { id: "decision", label: "待我决定", summary: "哪些节点需要你的判断" },
  ];

  const GLOBAL_NODES = [
    { id: "goal", title: "长期目标", summary: "保存任务最终要达到的结果。" },
    { id: "plan", title: "任务拆解", summary: "把目标变成有依赖和验收条件的短任务。" },
    { id: "human", title: "人类裁决", summary: "确认计划、关键主张和结果是否可以继续。" },
    { id: "route", title: "动态路由", summary: "按复杂度、能力与上下文预算选择执行层。" },
    { id: "executor", title: "任务分配", summary: "把短任务交给具备能力和容量的执行者。" },
    { id: "result", title: "结果验收", summary: "把执行结果送审、退回或接受。" },
    { id: "continuity", title: "跨对话接续", summary: "保存当前状态并释放下一项可执行任务。" },
  ];

  const GLOBAL_EDGES = [
    ["goal", "plan"],
    ["plan", "human"],
    ["human", "route"],
    ["route", "executor"],
    ["executor", "result"],
    ["result", "continuity"],
  ];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createDemoState() {
    return {
      goal: "完成一份可核验、可持续迭代的跨学科研究综述",
      activeBoard: "work",
      planApproved: false,
      tasks: clone(TASKS),
      taskStates: Object.fromEntries(TASKS.map((task) => [task.task_id, "QUEUED"])),
      decisions: {},
      assignments: {},
    };
  }

  function selectBoard(state, board) {
    const selected = PRIMARY_BOARDS.some((item) => item.id === board) ? board : "work";
    return { ...clone(state), activeBoard: selected };
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

  function workspaceView(state) {
    const work = viewModel(state);
    const pending = state.planApproved
      ? state.tasks
        .filter((task) => actionForTask(state, task.task_id) === "HUMAN_DECISION_REQUIRED")
        .map((task) => ({ ...task, kind: "task" }))
      : [{
        task_id: "plan-approval",
        kind: "plan",
        title: "确认 AI 拆分的任务计划",
        summary: `共 ${state.tasks.length} 项短任务，确认后才会进入执行队列。`,
      }];
    const decided = state.tasks
      .filter((task) => state.decisions[task.task_id])
      .map((task) => ({
        ...task,
        decision: state.decisions[task.task_id],
      }));
    return {
      activeBoard: PRIMARY_BOARDS.some((board) => board.id === state.activeBoard)
        ? state.activeBoard
        : "work",
      boards: PRIMARY_BOARDS.map((board) => ({
        ...board,
        count: board.id === "decision" ? pending.length : null,
      })),
      global: {
        readOnly: true,
        nodes: clone(GLOBAL_NODES),
        edges: clone(GLOBAL_EDGES),
        taskCount: state.tasks.length,
      },
      work,
      decision: { pending, decided },
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

  const STATUS_LABELS = {
    QUEUED: "待启动",
    IN_PROGRESS: "执行中",
    REVIEW: "待验收",
    DONE: "已完成",
    BLOCKED: "已阻塞",
  };

  function renderTaskCard(task) {
    const assignment = task.assignment
      ? `<span class="task-chip route">${escapeHtml(task.assignment.route)}</span><span class="task-chip">${escapeHtml(task.assignment.executor)}</span>`
      : "";
    const disabled = ["PLAN_APPROVAL_REQUIRED", "WAITING_DEPENDENCY", "BLOCKED", "NONE"].includes(task.action);
    const dependency = task.depends_on && task.depends_on.length
      ? `前置任务：${task.depends_on.join("、")}`
      : "首项任务，无前置依赖";
    return `<article class="review-card task-card status-${escapeHtml(task.status.toLowerCase())}" data-task-id="${escapeHtml(task.task_id)}">
      <div class="card-grid">
        <div class="card-body">
          <div class="card-meta">
            <span class="status-pill status-${escapeHtml(task.status.toLowerCase())}">${escapeHtml(STATUS_LABELS[task.status] || task.status)}</span>
            <span>${escapeHtml(task.complexity)}</span>
            ${task.human_gate ? '<span class="signal-pill">Human Gate</span>' : ""}
          </div>
          <h3>${escapeHtml(task.title)}</h3>
          <p class="summary">${escapeHtml(task.acceptance)}</p>
          <div class="reason-box"><strong>推进条件</strong><span>${escapeHtml(dependency)}</span></div>
        </div>
        <div class="card-side">
          <strong>执行安排</strong>
          <div class="task-meta">
            <span class="task-chip">约 ${Math.round(Number(task.estimated_tokens || 0) / 1000)}k tokens</span>
            ${assignment}
          </div>
          <button class="task-action" data-action="task" ${disabled ? "disabled" : ""}>${escapeHtml(ACTION_LABELS[task.action] || task.action)}</button>
        </div>
      </div>
    </article>`;
  }

  function renderDecisionCard(item) {
    if (item.kind === "plan") {
      return `<article class="review-card decision-card plan-decision">
        <div class="card-grid">
          <div class="card-body">
            <div class="card-meta"><span class="signal-pill">计划确认</span><span>长期任务入口</span></div>
            <h3>${escapeHtml(item.title)}</h3>
            <p class="summary">${escapeHtml(item.summary)}</p>
          </div>
          <div class="card-side">
            <strong>你的决定</strong>
            <p>确认任务顺序、边界和 Human Gate 后，系统才会开放第一项工作。</p>
            <button class="primary-button" type="button" data-plan-action="approve">确认计划</button>
          </div>
        </div>
      </article>`;
    }
    return `<article class="review-card decision-card" data-decision-task="${escapeHtml(item.task_id)}">
      <div class="card-grid">
        <div class="card-body">
          <div class="card-meta"><span class="signal-pill">Human Gate</span><span>${escapeHtml(item.complexity)}</span></div>
          <h3>${escapeHtml(item.title)}</h3>
          <p class="summary">验收条件：${escapeHtml(item.acceptance)}</p>
        </div>
        <div class="card-side">
          <strong>你的决定</strong>
          <p>批准后进入动态路由；退回后任务保持阻塞，后续工作不会启动。</p>
          <div class="card-actions">
            <button class="card-action reject" type="button" data-decision="REJECTED">退回</button>
            <button class="card-action approve" type="button" data-decision="APPROVED">批准并继续</button>
          </div>
        </div>
      </div>
    </article>`;
  }

  function renderHierarchy(state) {
    return state.tasks.map((task, index) => {
      const status = state.taskStates[task.task_id];
      const connector = index < state.tasks.length - 1 ? '<span class="tree-line"></span>' : "";
      return `<li class="tree-item"><span class="tree-index">${index + 1}</span>${connector}<div><b>${escapeHtml(task.title)}</b><small>${escapeHtml(status)}</small></div></li>`;
    }).join("");
  }

  function renderGlobalNode(node, selected) {
    return `<button class="system-node${selected ? " active" : ""}" type="button" data-global-node="${escapeHtml(node.id)}">
      <span>${escapeHtml(node.title)}</span><small>${escapeHtml(node.summary)}</small>
    </button>`;
  }

  function mount(doc) {
    const initialBoard = doc.defaultView && doc.defaultView.location
      ? String(doc.defaultView.location.hash || "").replace(/^#/, "")
      : "work";
    let state = selectBoard(createDemoState(), initialBoard);
    let selectedNode = "goal";
    const byId = (id) => doc.getElementById(id);

    function render() {
      const view = workspaceView(state);
      byId("goal").textContent = view.work.goal;
      byId("metric-total").textContent = String(view.work.progress.total);
      byId("metric-active").textContent = String(
        view.work.lanes.IN_PROGRESS.length + view.work.lanes.REVIEW.length
      );
      byId("metric-decisions").textContent = String(view.decision.pending.length);
      byId("metric-done").textContent = String(view.work.progress.done);
      byId("progress-copy").textContent = `${view.work.progress.done} / ${view.work.progress.total} 项完成`;
      byId("progress-bar").style.width = `${view.work.progress.percent}%`;
      byId("task-tree").innerHTML = renderHierarchy(state);
      byId("context-total").textContent = `${Math.round(state.tasks.reduce(
        (sum, task) => sum + task.estimated_tokens, 0
      ) / 1000)}k`;
      doc.querySelectorAll("[data-board]").forEach((button) => {
        const active = button.dataset.board === view.activeBoard;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        const count = button.querySelector("[data-board-count]");
        const board = view.boards.find((item) => item.id === button.dataset.board);
        if (count && board) count.textContent = board.count == null ? "" : String(board.count);
      });
      doc.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== view.activeBoard;
      });
      byId("work-task-list").innerHTML = state.tasks
        .map((task) => renderTaskCard(view.work.tasks[task.task_id]))
        .join("");
      byId("decision-list").innerHTML = view.decision.pending.length
        ? view.decision.pending.map(renderDecisionCard).join("")
        : '<div class="empty-state"><span>✓</span><h3>当前没有待裁决事项</h3><p>任务会继续按依赖推进；新的关键决定会回到这里。</p></div>';
      byId("decision-visible-count").textContent = `${view.decision.pending.length} 项待处理`;
      byId("global-node-list").innerHTML = view.global.nodes
        .map((node) => renderGlobalNode(node, node.id === selectedNode))
        .join('<span class="system-connector" aria-hidden="true">→</span>');
      const activeNode = view.global.nodes.find((node) => node.id === selectedNode) || view.global.nodes[0];
      byId("global-detail-title").textContent = activeNode.title;
      byId("global-detail-copy").textContent = activeNode.summary;
      if (doc.defaultView && doc.defaultView.history) {
        doc.defaultView.history.replaceState(null, "", `#${view.activeBoard}`);
      }
    }

    doc.addEventListener("click", (event) => {
      const boardButton = event.target.closest && event.target.closest("[data-board]");
      if (boardButton) {
        state = selectBoard(state, boardButton.dataset.board);
        render();
        return;
      }
      const globalNode = event.target.closest && event.target.closest("[data-global-node]");
      if (globalNode) {
        selectedNode = globalNode.dataset.globalNode;
        render();
        return;
      }
      const decisionCard = event.target.closest && event.target.closest("[data-decision-task]");
      if (decisionCard && event.target.dataset.decision) {
        state = recordDecision(state, decisionCard.dataset.decisionTask, event.target.dataset.decision);
        render();
        return;
      }
      if (event.target.dataset.planAction === "approve") {
        state = approvePlan(state);
        render();
        return;
      }
      const card = event.target.closest && event.target.closest("[data-task-id]");
      if (!card || event.target.dataset.action !== "task") return;
      const taskId = card.dataset.taskId;
      const action = actionForTask(state, taskId);
      if (action === "HUMAN_DECISION_REQUIRED") {
        state = selectBoard(state, "decision");
        render();
        return;
      }
      state = applyTaskAction(state, taskId);
      render();
    });
    byId("reset-demo").addEventListener("click", () => {
      state = createDemoState();
      selectedNode = "goal";
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
    renderDecisionCard,
    renderTaskCard,
    selectBoard,
    viewModel,
    workspaceView,
    mount,
  };
});
