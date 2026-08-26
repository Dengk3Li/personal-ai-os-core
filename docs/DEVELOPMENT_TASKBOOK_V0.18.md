# Personal AI OS v0.18 开发任务书

状态：`CANDIDATE / 公开 feature branch`

## 本轮目标

把“任务运行前读取已批准工作记忆、运行后留下可复核入口”固化为运行时合同，同时兼容未声明该策略的历史任务。

## 已交付

- 任务上下文可声明 `memory_policy: "require_read"`。
- 该策略必须同时提供 `memory_refs`、`memory_subject`（个人或团队）与 `memory_domain_id`；缺失、超限、未获批准、来源未绑定或与任务领域不一致时，Broker 在创建 run 前返回稳定错误，任务保持 `QUEUED`。
- Broker 在 claim 前调用 source-agnostic `read_memory_context` 合同，只把有界的已选引用、事实和决定摘要注入模型上下文；外部系统可以通过 `registered_memory_refs` 提供记忆索引。
- 成功运行只登记带 `CANDIDATE` 状态的 `MEMORY_REVIEW_REQUESTED` 事件，记录本轮策略、范围和已读取的批准引用；不会自动创建、批准或提升记忆候选。
- 未声明 `memory_policy` 的旧任务继续沿用既有工作协议和主体匹配逻辑。

## 路由合同补充

任务路由只读取任务声明的 `complexity`、`required_capabilities` 和
`context.routing.estimated_context_tokens`。`task_route_requirements()` 是不依赖
具体执行器的纯函数：它拒绝任务携带的 `model`、`adapter_id`、`route` 或
`executor` 绑定字段，并保留旧版顶层上下文预算的兼容读取。模型与 Adapter
绑定只能由服务端的版本化路线目录提供。

Broker 在探测执行器、选择路线并领取 run 之前完成路线求值；无效声明、能力不匹配、
上下文预算不足和不可用路线都会保持任务 `QUEUED`。自动推进复用这条边界，
不会通过客户端请求替换路线目录，也不会为失败的路线创建部分执行记录。

## 验收边界

- `require_read` 不会把记忆正文或私人路径写入公开投影。
- `MEMORY_REVIEW_REQUESTED` 是人工复核入口，不是 `APPROVED` 状态。
- 领域、主体和候选引用由 Broker 的记忆合同生成，浏览器不能绕过 Broker 改写；未声明该策略的历史任务继续沿用兼容路径。

## 验证

- 271 个 Python 用例通过。
- 新增覆盖：缺少引用、未批准引用、超大上下文均在 run claim 前 fail closed；已批准引用进入执行上下文；成功后只生成候选复核事件且不写入或晋升记忆候选。
