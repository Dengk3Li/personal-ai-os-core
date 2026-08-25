(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PersonalAIArchitecture = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function node(module_id, name, layer, summary, options = {}) {
    return {
      contract_version: "personal-ai-os.system-module/v1",
      module_id,
      name,
      layer,
      summary,
      provides: options.provides || [],
      requires: options.requires || [],
      inputs: options.inputs || [],
      outputs: options.outputs || [],
      control: options.control || "按任务合同运行",
      availability: options.availability || "READY",
      optional: Boolean(options.optional),
      child_graph: options.child_graph || null,
      entrypoint: options.entrypoint || `system://${module_id}`,
    };
  }

  const GRAPHS = {
    "personal-ai-os": {
      graph_id: "personal-ai-os",
      name: "个人 AI 操作系统",
      summary: "从统一入口、个人上下文和领域理解出发，经长期工作、执行与验收形成输出，再把经过核验的经验送回下一轮。",
      nodes: [
        node("secretary-entry", "总管入口", "入口", "接收目标、材料和决定，把一次请求交给唯一主领域。", { provides: ["work.intent"], inputs: ["自然语言目标", "本地材料", "人工决定"], outputs: ["任务意图"], control: "统一自然语言入口尚未接入运行时", availability: "PLANNED" }),
        node("personal-context", "个人上下文", "认知", "按当前任务加载目标、偏好、已确认经验与排除项。", { provides: ["context.pack"], requires: ["work.intent", "memory.accepted"], inputs: ["任务意图", "已确认经验"], outputs: ["最小上下文包"], control: "已有引用式上下文原语，个人记忆自动装载仍在试运行", availability: "PROTOTYPE" }),
        node("domain-routing", "领域识别与抽象", "认知", "识别科研、专业分析、写作或个人事务，并选择对应的工作抽象。", { provides: ["domain.brief"], requires: ["context.pack"], inputs: ["最小上下文包"], outputs: ["领域任务简报"], control: "当前需显式选择主领域，自动识别仍在试运行", availability: "PROTOTYPE" }),
        node("longtask-kernel", "长期工作内核", "编排", "管理可接续任务、依赖和人工裁决；条件、汇合与循环结构正在接入持久化调度。", { provides: ["work.plan", "work.task"], requires: ["domain.brief"], inputs: ["领域任务简报"], outputs: ["工作流结构", "短任务"], control: "依赖调度已可用，完整结构调度仍在试运行", child_graph: "longtask-kernel", availability: "PROTOTYPE" }),
        node("domain-systems", "领域工作系统", "领域", "把同一内核投影成科研、专业分析、长文与个人事务的专用工作面。", { provides: ["domain.work"], requires: ["work.task"], inputs: ["短任务", "领域模板"], outputs: ["领域产物候选"], control: "已有三类预设，完整领域工作面仍在试运行", child_graph: "domain-systems", availability: "PROTOTYPE" }),
        node("execution", "模型与工具执行", "执行", "按能力、复杂度和上下文预算选择模型、工具或本地执行器。", { provides: ["execution.result"], requires: ["domain.work"], inputs: ["任务包", "路由策略"], outputs: ["运行结果", "事件与产物"], control: "原子取得执行权后调用" }),
        node("delivery", "证据验收与交付", "交付", "核对来源、验收条件和人工决定，形成可交付版本。", { provides: ["artifact.accepted", "experience.candidate"], requires: ["execution.result"], inputs: ["运行产物", "验收标准"], outputs: ["交付物", "经验候选"], control: "人工验收保留最终决定权" }),
        node("learning-cycle", "经验学习与下一轮", "学习", "把对话与工作结果先变成候选，经证据核验和人工确认后再供下一轮读取。", { provides: ["memory.accepted", "secretary.brief"], requires: ["experience.candidate"], inputs: ["经验候选", "结果反馈"], outputs: ["已确认经验", "下一轮简报"], control: "已有候选晋升原语，自动提取与个人模型更新尚未接入", child_graph: "learning-cycle", availability: "PROTOTYPE" }),
      ],
      edges: [
        ["secretary-entry", "personal-context", "dependency"],
        ["personal-context", "domain-routing", "dependency"],
        ["domain-routing", "longtask-kernel", "dependency"],
        ["longtask-kernel", "domain-systems", "dependency"],
        ["domain-systems", "execution", "dependency"],
        ["execution", "delivery", "dependency"],
        ["delivery", "learning-cycle", "dependency"],
        ["learning-cycle", "personal-context", "feedback"],
        ["learning-cycle", "longtask-kernel", "feedback"],
      ],
    },
    "longtask-kernel": {
      graph_id: "longtask-kernel",
      name: "长期工作内核",
      summary: "把目标、领域经验和现场状态编译成可恢复、可分派、可裁决的操作链。",
      nodes: [
        node("goal-boundary", "目标与边界", "理解", "确认结果、范围、排除项和验收方式。", { provides: ["goal.contract"], inputs: ["任务意图"], outputs: ["目标合同"], control: "边界不清时停止" }),
        node("domain-template", "领域模板", "理解", "选择科研、专业分析、长文或自定义模板。", { provides: ["domain.template"], requires: ["goal.contract"], inputs: ["目标合同", "领域简报"], outputs: ["工作抽象"], control: "已有三类预设，自定义模板仍在试运行", availability: "PROTOTYPE" }),
        node("workflow-compiler", "工作流结构编译", "编排", "把模板展开为顺序、并行、汇合、条件和有界循环。", { provides: ["workflow.structure"], requires: ["domain.template"], inputs: ["工作抽象"], outputs: ["可验证结构图"], control: "校验与求值已可用，尚未直接驱动持久化调度", child_graph: "workflow-compiler", availability: "PROTOTYPE" }),
        node("task-state", "任务现场与状态", "编排", "保存依赖、当前阶段、上下文引用、运行证据和下一动作。", { provides: ["work.task"], requires: ["workflow.structure"], inputs: ["结构图"], outputs: ["任务现场"], control: "SQLite 为唯一运行事实" }),
        node("dynamic-route", "动态路由", "执行", "按任务能力和上下文预算选择兼容执行层。", { provides: ["execution.route"], requires: ["work.task"], inputs: ["任务现场", "执行目录"], outputs: ["执行路线"], control: "路线不可用时停止" }),
        node("human-decision", "人工裁决", "裁决", "集中处理边界、条件、阻塞和结果验收。", { provides: ["human.decision"], requires: ["work.task"], inputs: ["待决定事项"], outputs: ["持久化决定"], control: "决定先于后续执行" }),
        node("continuity", "跨对话接续", "记忆", "用任务、依赖、运行与产物引用恢复现场。", { provides: ["work.resume"], requires: ["work.task", "execution.result"], inputs: ["任务现场", "运行证据"], outputs: ["恢复简报"], control: "只加载当前任务所需引用" }),
        node("experience-candidate", "经验候选", "学习", "从已验收工作中提取可复用方法，不直接写入长期记忆。", { provides: ["experience.candidate"], requires: ["execution.result"], inputs: ["验收结果"], outputs: ["方法候选"], control: "已有晋升门，自动候选提取仍在试运行", availability: "PROTOTYPE" }),
        node("conversation-learning", "过往对话学习", "学习", "从授权的历史对话中识别稳定偏好与模板候选。", { provides: ["conversation.candidate"], requires: ["work.resume"], inputs: ["授权对话引用"], outputs: ["偏好候选"], control: "尚未接入自动提取", availability: "PLANNED", optional: true }),
        node("human-promotion", "核验与人工吸收", "学习", "证据充分且人工确认后，才把候选加入可复用上下文。", { provides: ["memory.accepted"], requires: ["experience.candidate", "conversation.candidate"], inputs: ["候选", "证据", "人工决定"], outputs: ["已确认经验"], control: "已有纯验证原语，完整运行链仍在试运行", availability: "PROTOTYPE" }),
      ],
      edges: [
        ["goal-boundary", "domain-template", "dependency"],
        ["domain-template", "workflow-compiler", "dependency"],
        ["workflow-compiler", "task-state", "dependency"],
        ["task-state", "dynamic-route", "dependency"],
        ["task-state", "human-decision", "control"],
        ["dynamic-route", "continuity", "dependency"],
        ["continuity", "experience-candidate", "dependency"],
        ["continuity", "conversation-learning", "dependency"],
        ["experience-candidate", "human-promotion", "control"],
        ["conversation-learning", "human-promotion", "control"],
        ["human-promotion", "domain-template", "feedback"],
      ],
    },
    "workflow-compiler": {
      graph_id: "workflow-compiler",
      name: "工作流结构编译",
      summary: "控制节点只决定释放关系；只有任务节点会交给模型或工具执行。",
      nodes: [
        node("sequence-node", "顺序节点", "结构", "前一项完成后释放下一项。", { provides: ["flow.sequence"], outputs: ["确定顺序"], availability: "PROTOTYPE" }),
        node("branch-node", "分支节点", "结构", "同时释放多个彼此独立的路径。", { provides: ["flow.branch"], outputs: ["并行路径"], availability: "PROTOTYPE" }),
        node("join-node", "汇合节点", "结构", "按全部完成或任一完成规则汇合路径。", { provides: ["flow.join"], requires: ["flow.branch"], outputs: ["汇合结果"], availability: "PROTOTYPE" }),
        node("condition-node", "条件节点", "结构", "只引用服务端登记的判断条件，未知结果进入待我决定。", { provides: ["flow.condition"], outputs: ["选中路径"], control: "禁止执行任意代码", availability: "PROTOTYPE" }),
        node("loop-node", "循环节点", "结构", "在明确继续条件与最大轮次内重复工作。", { provides: ["flow.loop"], requires: ["flow.condition"], outputs: ["下一轮或退出"], control: "必须设置最大轮次", availability: "PROTOTYPE" }),
        node("task-node", "任务节点", "执行", "承载可分配的短任务、上下文引用和验收条件。", { provides: ["work.task"], requires: ["flow.sequence"], outputs: ["可分派任务"], availability: "PROTOTYPE" }),
      ],
      edges: [
        ["sequence-node", "branch-node", "dependency"],
        ["branch-node", "join-node", "dependency"],
        ["join-node", "condition-node", "dependency"],
        ["condition-node", "loop-node", "control"],
        ["loop-node", "task-node", "control"],
        ["task-node", "condition-node", "feedback"],
      ],
    },
    "domain-systems": {
      graph_id: "domain-systems",
      name: "领域工作系统",
      summary: "同一任务与运行内核，按不同领域的证据、循环和交付方式呈现。",
      nodes: [
        node("science-domain", "科研工作系统", "领域", "假设、实验方案、自主实验、数据分析与反馈优化形成多轮循环。", { provides: ["domain.science"], inputs: ["科研目标", "证据与实验条件"], outputs: ["结论候选", "下一轮假设"], control: "已有科研预设，科学状态投影仍在试运行", availability: "PROTOTYPE" }),
        node("analysis-domain", "专业分析系统", "领域", "从来源池、证据提取、论证规划到分章撰写和视觉交付。", { provides: ["domain.analysis"], inputs: ["问题", "材料与来源"], outputs: ["分析报告"], control: "已有报告预设，完整工作面仍在试运行", availability: "PROTOTYPE" }),
        node("writing-domain", "长文写作系统", "领域", "读取模板、提取写作规则、建立结构并分段生成可复核文本。", { provides: ["domain.writing"], inputs: ["目标", "模板", "材料"], outputs: ["结构化长文"], control: "已有通用写作链，模板学习仍在试运行", availability: "PROTOTYPE" }),
        node("personal-domain", "个人事务系统", "领域", "维护目标、决定、提醒与日常秘书简报。", { provides: ["domain.personal"], inputs: ["个人目标", "当前状态"], outputs: ["简报", "待办与决定"], control: "个人事务运行层尚未接入", availability: "PLANNED" }),
      ],
      edges: [],
    },
    "learning-cycle": {
      graph_id: "learning-cycle",
      name: "经验学习与下一轮",
      summary: "学习是一条受证据和人工决定约束的候选晋升链，不是后台自动改写用户。",
      nodes: [
        node("signal-capture", "结果与对话信号", "输入", "收集已授权的结果、修改意见和模板遵循情况。", { provides: ["learning.signal"], outputs: ["可追溯信号"], availability: "PLANNED" }),
        node("candidate-extract", "经验候选提取", "理解", "区分事实、可复用方法和个人偏好候选。", { provides: ["experience.candidate"], requires: ["learning.signal"], outputs: ["经验候选"], availability: "PLANNED" }),
        node("evidence-check", "证据核验", "验收", "检查来源、重复性、适用边界和冲突。", { provides: ["experience.verified"], requires: ["experience.candidate"], outputs: ["核验结果"], availability: "PROTOTYPE" }),
        node("owner-accept", "人工确认", "裁决", "由用户决定接受、修改或拒绝候选。", { provides: ["memory.accepted"], requires: ["experience.verified"], outputs: ["已确认经验"], availability: "PROTOTYPE" }),
        node("task-load", "任务级加载", "输出", "仅在相关任务中加载已确认经验和模板规则。", { provides: ["context.reusable"], requires: ["memory.accepted"], outputs: ["下一轮上下文"], availability: "PROTOTYPE" }),
      ],
      edges: [
        ["signal-capture", "candidate-extract", "dependency"],
        ["candidate-extract", "evidence-check", "dependency"],
        ["evidence-check", "owner-accept", "control"],
        ["owner-accept", "task-load", "dependency"],
        ["task-load", "signal-capture", "feedback"],
      ],
    },
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function validateGraph(graph) {
    if (!graph || !graph.graph_id || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error("系统地图结构无效");
    const ids = new Set();
    graph.nodes.forEach((item) => {
      if (!item.module_id || ids.has(item.module_id)) throw new Error(`系统地图节点重复：${item.module_id || "UNKNOWN"}`);
      ids.add(item.module_id);
      if (item.child_graph && !GRAPHS[item.child_graph]) throw new Error(`内部结构不存在：${item.child_graph}`);
    });
    const edgeKeys = new Set();
    const dependencies = new Map([...ids].map((id) => [id, []]));
    graph.edges.forEach((edge) => {
      if (!Array.isArray(edge) || !ids.has(edge[0]) || !ids.has(edge[1])) throw new Error("系统地图连接端点不存在");
      if (!["dependency", "control", "feedback"].includes(edge[2])) throw new Error(`系统地图连接类型无效：${edge[2]}`);
      const key = edge.join("\u0000");
      if (edgeKeys.has(key)) throw new Error("系统地图连接重复");
      edgeKeys.add(key);
      if (edge[2] === "dependency") dependencies.get(edge[0]).push(edge[1]);
    });
    const visiting = new Set();
    const visited = new Set();
    function visit(nodeId) {
      if (visiting.has(nodeId)) throw new Error("系统地图存在依赖循环");
      if (visited.has(nodeId)) return;
      visiting.add(nodeId);
      dependencies.get(nodeId).forEach(visit);
      visiting.delete(nodeId);
      visited.add(nodeId);
    }
    ids.forEach(visit);
    return graph;
  }

  function systemGraph(path = []) {
    let graph = validateGraph(GRAPHS["personal-ai-os"]);
    path.forEach((graphId) => {
      const owner = graph.nodes.find((item) => item.child_graph === graphId);
      if (!owner) throw new Error(`系统地图路径无效：${graphId}`);
      graph = validateGraph(GRAPHS[graphId]);
    });
    return clone(graph);
  }

  function systemBreadcrumbs(path = []) {
    const result = [{ graph_id: "personal-ai-os", label: GRAPHS["personal-ai-os"].name, depth: 0 }];
    let currentPath = [];
    path.forEach((graphId, index) => {
      currentPath = [...currentPath, graphId];
      result.push({ graph_id: graphId, label: systemGraph(currentPath).name, depth: index + 1 });
    });
    return result;
  }

  Object.values(GRAPHS).forEach(validateGraph);

  return { systemBreadcrumbs, systemGraph, validateGraph };
});
