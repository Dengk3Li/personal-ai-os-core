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

## 研究报告输入与验收反馈投影

`POST /api/research/report-input-projection` 提供纯只读的研究报告输入检查。输入缺失或格式不合法时，响应使用 `status: BLOCKED`，并返回结构化 `reason`、中文 `next_action`、`missing_inputs` 和 `report_status: NOT_STARTED`；输入齐全时返回 `status: READY`，下一步明确为“开始来源收集与证据核对”。

该投影只表达输入是否具备启动条件，不创建任务、不调用模型、不改变运行库，也不把输入就绪或终态回执当作报告完成。报告仍需经过来源与证据核对、运行回执和人工验收等独立边界。

## 系统全景与运行模块边界

- `system-topology`（系统全景）表达个人 AI 操作系统的顶层架构、模块上下游和反馈回路；复合模块下钻后仍保留所属上层模块，以及跨层外部输入、输出和反馈。
- `runtime-components`（运行模块）表达当前可插拔组件的 capability 供需、可用状态、可选插槽与实际依赖连接；它不替代顶层系统图，也不把规划中的能力标记为已经可运行。
- 两种视图使用不同的 `view_kind` 合同，便于浏览器和后续执行器按正确语义读取地图。

## TaskEnvelope/v1 与 TaskModuleLink/v1

公开核心提供轻量、纯校验的 `TaskEnvelope/v1` 边界，供适配器把运行任务安全地交给后续执行器。封套只包含来源元数据、运行任务状态、受限扩展字段和类型化模块引用；字段之外的任务卡、文件内容、私人路径、业务名称与模型输出不属于公开合同。

- `origin` 使用来源类型、来源引用和非负修订号；来源引用只接受不带路径的匿名标识。
- `runtime_task` 使用任务/工作流/结果引用、状态、尝试次数和有界依赖列表，校验器只返回规范化结构。
- `extensions` 只允许有界的 JSON 标量、列表和对象，键名与字符串值受限，避免把私人文案带入公共核心。
- `module_refs` 使用 `TaskModuleLink/v1` 的既有关系、来源、置信度和确认状态；公开包装器拒绝未知字段、路径型模块标识和重复关系。

私仓适配器可以把本地任务映射为该合同，但必须在边界前完成脱敏与权限判断。该校验器不读取文件、不访问私有任务卡、不调用模型，也不宣称任务或研究报告已经完成。

批量 dry-run 使用 `preview_task_envelopes`。每项以 `{envelope, goal, next_action}` 传入，其中 `goal` 与 `next_action` 也只接受匿名引用；相同 `origin + task_id` 的完全重复项会合并。相同键但内容不同、缺少必要引用或输入不合法时，结果统一为 `BLOCKED`，只返回固定 `reason`、`next_action`、索引级 `issues` 和计数，不回显正文、路径或凭据。该预检是纯函数，明确标记 `read_only: true` 与 `runtime_write: false`。

## TemplateSelection/v1

公开核心提供 `TemplateSelection/v1` 作为模板绑定的只读元数据合同。它只接受 `template_id`、`version`、`source_ref`、`content_sha256` 和 `task_kind`（以及版本字段），所有标识必须是不带路径的匿名标识，正文、凭据和适配器私有字段均被拒绝。

该选择记录只证明某个任务类型绑定了某个版本的模板摘要，不读取或携带模板正文，也不宣称模板已经执行。私仓适配器可在本地完成权限判断和正文读取，再将脱敏后的选择元数据交给公开核心。

## PracticeCandidate/v1

公开核心提供独立的 `PracticeCandidate/v1` 候选合同，用于在记忆或工作方式进入长期记忆前传递最小安全元数据。合同只接受候选引用、来源引用、有界范围引用（`subject_ref`、`domain_ref`）和人工审核状态；不接收工作方式正文、分类、业务名称、路径或凭据。

新候选必须从 `review.status: PROPOSED` 开始；`APPROVED` 或 `REJECTED` 必须同时提供匿名 `reviewer_ref`，从合同层面保留人工审核边界。`validate_practice_candidate` 是纯函数，只返回规范化候选，不写 RuntimeStore、不批准长期记忆，也不把候选正文带入模型上下文。

## ExecutionReceipt/v1

公开核心提供 `personal-ai-os.execution-receipt/v1` 通用只读交接合同，用于在项目执行完成后传递最小可核对事实。`binding` 只允许已验证的 `project_id`、`thread_id`、`host_id` 不透明引用；`receipt` 只允许终态、结果、有界产物引用、最终输出引用、观测时间和用户输入/人工裁决标记。已完成回执必须验证通过、带最终输出引用，并且不能仍在等待用户输入或人工裁决。

`validate_execution_receipt` 是无存储纯校验器，不读取或写入本地路径、任务正文、模型输出、业务标签或凭据。它表达“哪个项目中的哪个线程产生了什么可核对结果”，不替代 RuntimeStore 状态转换、人工验收或长期记忆审核。

## 验证

- `tests/test_memory_context.py`：源无关读取、批准状态、主体/领域边界、上下文上限与复核候选合同。
- `tests/test_runtime_memory_context.py`：Broker 在 run claim 前 fail closed，成功读取只产生候选事件且不写入记忆表。
- `tests/test_work_protocols.py`：协议学习路径的复核事件显式携带 `CANDIDATE` 元数据，并保留未授权提升状态。
- `tests/test_task_envelope.py`：TaskEnvelope/v1 规范化、类型化模块引用、未知字段、路径/业务文案与重复引用拒绝。
- `tests/test_task_envelope.py`：批量预检的去重、冲突、缺少目标/下一动作和敏感值不回显。
- `tests/test_template_selection.py`：TemplateSelection/v1 的字段边界、哈希规范化、路径/正文/凭据与业务文案拒绝。
- `tests/test_practice_candidate.py`：PracticeCandidate/v1 的引用/范围边界、人工审核状态和正文/路径/业务标签拒绝。
- `tests/test_execution_receipt.py`：ExecutionReceipt/v1 的项目—线程—主机归属、终态回执、人工输入边界以及路径/业务字段/凭据拒绝。

## 未交付边界

- 不从聊天记录自动推断个人习惯，不自动批准或固定候选。
- 不提供后台 daemon、隐式恢复、跨机器记忆同步或私人记忆文件读取器。
- 不修改公开 `main`；真实研究报告的终态与人工验收仍是封包门槛。
