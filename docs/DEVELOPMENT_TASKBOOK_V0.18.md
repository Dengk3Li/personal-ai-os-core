# Personal AI OS v0.18 开发任务书

状态：`CANDIDATE / 公开 feature branch`

## 本轮目标

把“任务运行前读取已批准工作记忆、运行后留下可复核入口”固化为运行时合同，同时兼容未声明该策略的历史任务。

## 已交付

- 任务上下文可声明 `memory_policy: "require_read"`。
- 该策略必须同时提供 `memory_subject`（个人或团队）与 `memory_domain_id`；缺失或与任务领域不一致时，Broker 在创建 run 前返回稳定错误，任务保持 `QUEUED`。
- 执行上下文明确携带 `approved_practice_refs`、工作规则和证据引用；只加载主体与领域同时匹配的 `APPROVED` 候选。
- 成功运行只登记 `MEMORY_REVIEW_REQUESTED` 事件，记录本轮策略、范围和已读取的批准引用；不会自动创建、批准或提升记忆候选。
- 未声明 `memory_policy` 的旧任务继续沿用既有工作协议和主体匹配逻辑。

## 验收边界

- `require_read` 不会把记忆正文或私人路径写入公开投影。
- `MEMORY_REVIEW_REQUESTED` 是人工复核入口，不是 `APPROVED` 状态。
- 领域、主体和候选引用由 RuntimeStore 事实生成，浏览器不能绕过 Broker 改写。

## 验证

- 258 个 Python 用例通过。
- 新增覆盖：缺少记忆范围时在 run claim 前 fail closed；批准引用进入执行上下文；成功后只生成复核事件且保留人工批准状态。
