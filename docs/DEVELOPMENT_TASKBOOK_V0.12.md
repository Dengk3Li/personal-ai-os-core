# Personal AI OS v0.12 开发任务书

## 交付目标

把“长期目标”和“单次自动推进”从概念上、数据上和操作上分开。目标在服务重启后仍可恢复；每次续推保持有界；预算耗尽、范围任务收口和人工验收分别拥有不同状态。

## 已交付范围

### 持久目标

- `personal-ai-os.goal/v1` 登记目标、范围工作线、完成条件和续推策略。
- SQLite 保存目标状态、累计步数、已观测模型 Token、续推次数、最后停止原因和追加式事件。
- 工作线自身的 goal 文案继续描述单条工作线；Durable Goal 负责跨工作线结果，不再混用一个字段。

### 有界续推

- GoalController 复用 AutoAdvanceEngine 和 ExecutionBroker，不新建第二套调度器。
- 一次续推按目标登记顺序扫描多条工作线，并遵守依赖、Human Gate、路由、任务原子占用和 `REVIEW` 停止边界。
- 单次最大步数、累计最大步数、累计最大 Token 和单次失败预算均来自目标策略。
- 达到累计上限时进入 `BUDGET_LIMITED`，不会写成 `COMPLETE`。

### 完成与恢复

- 全部范围任务为 `DONE / ARCHIVED` 时，目标进入 `AWAITING_ACCEPTANCE`。
- 只有用户提供完成依据并明确确认后，目标进入 `COMPLETE`。
- SQLite 原子占用目标续推；竞争者不能重复启动同一目标。
- 未结束续推在重启后返回 `GOAL_RECOVERY_REQUIRED`，等待人工处理未知外部运行。

### 本地工作台

- 私人本地投影显示真实目标、目标说明、预算和使用量。
- `public-safe` 只显示目标顺序别名、状态、工作线数量和使用量，不暴露目标原文或真实标识。
- 工作进度页只增加一条紧凑目标栏，不新增管理大屏。

## 设计参考与许可证

Prime Agent 的 durable goal 与 continuation policy 分离、LangGraph 的 checkpoint/interrupt 边界、OpenHands 的事件与执行服务分层、Letta Code 的持久上下文、LoopX 的本地状态隔离用于检验设计。实现为本项目独立代码。详细许可证条件见 `REFERENCE_PROJECT_LICENSES_V0.12.md`。

## 验收

- 154 个 Python 用例通过。
- 57 个 Workbench 用例通过。
- 两条工作线可以在一次目标续推中各执行一项就绪任务。
- 预算上限、范围收口和明确完成三种状态彼此独立。
- 两个 RuntimeStore 竞争同一目标时只产生一次模型调用。
- 私人目标原文不进入 `public-safe` 浏览器投影。

## 未交付边界

- 没有后台 daemon、计划时钟、心跳续租或跨机器 Worker。
- 未结束的外部运行没有自动对账和恢复命令。
- Token 只统计 Adapter 回执中提供的输入与输出用量；没有价格换算或供应商账单核对。
- 目标预算调整 API、定时续推、流式事件、取消和跨目标公平调度仍属于后续版本。
