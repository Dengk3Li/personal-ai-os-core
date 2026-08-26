# Personal AI OS v0.20 执行记忆钩子验收

状态：`CANDIDATE / 公开 feature branch`

## 本轮结论

公开核心已经具备“运行前按声明读取已确认记忆、运行结束只留下待复核候选”的通用边界。本轮没有新增第二套记忆读取或持久化机制，只补齐了协议学习路径的候选事件字段，并把验收不变量固定下来。

## 执行钩子

- 运行前钩子由 `read_memory_context(task, registered_refs=...)` 提供。任务声明 `context.memory_policy: "require_read"` 后，必须同时声明记忆引用、主体和领域；引用未找到、未确认、来源未绑定、范围不匹配或上下文超限时，Broker 在 `claim_run` 之前返回稳定错误。
- 运行成功钩子由现有工作协议的 `learning_review: "candidate"` 与记忆读取结果共同形成 `MEMORY_REVIEW_REQUESTED` 事件。事件现在始终带有 `candidate.status: "CANDIDATE"`、来源任务/运行引用和未授权的提升状态。
- 任务声明 `require_read` 且读取成功时，候选事件额外带入有界的批准引用；没有该策略时不会伪造 `memory_read_status` 或批准记忆。
- 事件不会创建、修改或批准 `memory_candidates`。候选只有在显式人工复核后才能进入 `APPROVED` 或 `REJECTED`。

## 固定不变量

1. 任何必需记忆读取失败，任务保持 `QUEUED`，没有 run、Adapter 调用或运行事件。
2. 成功运行最多生成一个待复核入口；入口不是验收结果，也不是已确认记忆。
3. 候选只携带有界引用与状态，不携带原始记忆库、私人路径、凭据或模型输出。
4. 记忆读取与候选生成均为执行边界的一部分；浏览器或外部 Provider 不能绕过 Broker 直接写入长期记忆。
5. 未声明 `require_read` 的历史任务保持兼容路径。公共核心无法替调用方推断主体、领域和引用，因此不会在缺少这些声明时猜测记忆范围。

## 参考项目与引入边界

本项目只吸收 Prime Agent、LangGraph 与 OpenHands 的通用机制，并由本项目独立实现；不复制源码、界面、文案、商标或品牌素材。各项目的许可证和直接复用义务集中记录在 [`REFERENCE_PROJECT_LICENSES_V0.13.md`](REFERENCE_PROJECT_LICENSES_V0.13.md)。

未来直接引入第三方代码或文件时，必须逐文件核对来源、许可证、依赖、模型服务和数据条款；分发时按原项目要求保留原始许可证、版权声明和 NOTICE（若该项目提供），并单独核对商标与品牌素材权限。

## 验证

- `tests/test_memory_context.py`：源无关读取、批准状态、主体/领域边界、上下文上限与复核候选合同。
- `tests/test_runtime_memory_context.py`：Broker 在 run claim 前 fail closed，成功读取只产生候选事件且不写入记忆表。
- `tests/test_work_protocols.py`：协议学习路径的复核事件显式携带 `CANDIDATE` 元数据，并保留未授权提升状态。

## 未交付边界

- 不从聊天记录自动推断个人习惯，不自动批准或固定候选。
- 不提供后台 daemon、隐式恢复、跨机器记忆同步或私人记忆文件读取器。
- 不修改公开 `main`；真实研究报告的终态与人工验收仍是封包门槛。
