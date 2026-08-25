# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

主要用户是需要让 AI 持续处理长文本、科研、产品与写作工作的个人。用户面对的通常不是一条清晰指令，而是跨文件、跨对话、跨阶段的长期目标，以及需要先理解和整理的本地工作区。

## Product Purpose

Personal AI OS 把长期目标拆成可执行的短任务，把任务放入可见的业务线和阶段中持续推进，并在人类必须判断时集中请求裁决。成功意味着用户不必在每个新对话中重新核验全部历史，也能看清系统结构、当前进度、阻塞原因、运行证据与下一步动作。

## Positioning

产品提供一层人类可交互的长期工作操作层：模块能够组合，工作能够沿多条业务线推进，不同执行器通过统一运行边界接手任务，而人类保留计划确认、Human Gate 和结果验收权。

## Operating Context

- 本地优先读取项目结构、文件信号和已有状态；首次工作区检查默认只读。
- 长期目标经过工作区检查、模块识别、业务线建立、任务拆分、动态路由、执行、验收与归档形成闭环。
- 科研线、会议纪要线、分析报告线和用户自建工作线可以并行存在，每条线采用适合该工作的详情排版。
- 静态 Workbench 使用匿名合成状态；连接本地服务后，同一界面读取 SQLite 运行库并把受支持的动作提交给服务端。
- CLI 与本地 HTTP API 调用同一套任务、状态和运行内核。
- Secretary 方向目前交付的是运行库只读简报和最小上下文原语；统一自然语言入口、意图识别和自动领域选择尚未交付。

## Capabilities and Constraints

- 一级入口固定为“模块地图”“工作进度”“待我决定”。Research 属于工作进度中的业务线，不拥有独立的一级状态源。
- 模块地图从 `personal-ai-os.module/v1` manifest 解析能力和依赖，支持拖动、平移、缩放、视口适配与上下游聚焦；选中模块的批注可以进入当前工作流成为修正任务。
- 通用任务状态为 `QUEUED`、`IN_PROGRESS`、`REVIEW`、`DONE`、`BLOCKED`、`PAUSED` 和 `ARCHIVED`；UI 分别呈现待分配、进行中、待验收、已收口、已阻塞、已暂停和已归档。
- SQLite 运行库持久保存工作流、任务、运行、事件、模型输出产物和人工决定，并支持服务重启后读回。
- Execution Broker 在依赖、Human Gate 和 Adapter 可用性通过校验后，以同一 SQLite 事务完成任务执行权占用、本地 run 创建和分配事件登记。只有取得执行权的实例会调用模型；外部运行标识在 Adapter 响应后补入 run。
- 当前本地服务使用 Python 标准库 HTTP server，提供运行投影、工作流与任务创建、任务转换、运行启动和决定记录的有限 JSON API。
- 当前真实模型入口是同步的 OpenAI-compatible Chat Completions Adapter。它从服务进程读取 base URL 与密钥；Workbench 在请求期间轮询持久化状态，因此真实调用阶段可见 `IN_PROGRESS` 与 working 宠物。终态输出登记为本地产物后送入 `REVIEW`。
- `personal-ai-os.runtime-plan/v1` 可以把本地实际工作线幂等同步到 SQLite。计划文件保存在 Git 忽略目录；重复同步不会覆盖任务状态、运行证据或结果。
- 任务 `context` 只在服务端保存，并从浏览器投影移除，也不会整体发送给模型。模型接收任务 envelope、最多 12,000 字符的显式 `context.model_context`，以及有界的已接受上游产物。
- Secretary 已提供最小上下文包和只读简报：从运行库汇总进行中、待验收、阻塞、暂停、待决定和下一动作，不复制记忆正文。
- `personal-ai-os.domain-context/v1` 按 `domain contract → active project → current state → relevant knowledge → historical decisions → constraints → excluded context` 的固定顺序编译一个领域的引用清单；领域歧义和未知层级 fail closed。
- `personal-ai-os.auto-advance/v1` 有界扫描当前就绪任务，逐项调用同一个 Broker，并记录 `AUTO_ADVANCE_SELECTED / FINISHED` 事件。它不会自动批准 Human Gate、接受 `REVIEW`、解除阻塞或重派遗留的 `IN_PROGRESS` 任务。
- 自动推进可以读取 `personal-ai-os.runtime-routes/v1` 服务端目录，按每项任务的能力、层级、预计上下文和可用性选择模型与 Adapter。路线只在任务原子 claim 成功后写入同一 run 的事件；竞争失败方不留下路线证据。
- 内置工作流预设包括 science、meeting notes 和 analytical report。Science 预设实现五类 Agent 与并行实验路径的任务合同，但不把工程运行状态当作科学结论。
- 首次扫描与计划生成仍是候选结果，未经用户确认不写入被分析的工作区。
- 静态演示中的心跳仍是合成事件。连接本地运行库后，working 宠物只消费真实 `IN_PROGRESS` 状态；它不会反向改变任务状态。
- 当前版本没有 SSE、流式 token 展示、运行取消或续接、服务端宠物注册表、模型自动发现、Codex App Server Adapter、VS Code Adapter、远程执行 Adapter，也没有自动递归理解整仓内部结构的分形扫描。
- Token Manager 仍是规划中的可组合模块，不能标为已可用。

## Brand Commitments

界面延续 Cognitive Intake 的浅色、克制、信息密集但可快速摄取的产品语言。用户可见文案直接描述任务、状态、结果和动作，不展示 Agent 推理、调试记录或管理仪式。静态演示和本地运行状态必须具有明确且不同的数据来源标识。

## Evidence on Hand

- `src/personal_ai_os/` 已包含计划拆分、动态路由、任务分配、统一状态、SQLite 运行库、Execution Broker、OpenAI-compatible Adapter、Secretary 简报、连续性和验收能力。
- `workbench/` 能在本地 API 可用时读取运行投影，并在连接失败时回到匿名合成演示。
- 当前全量测试通过 106 个 Python 用例和 39 个 Workbench 用例，覆盖逐任务路由、单次可用性快照、路线与 run 原子绑定、工作线作用域、外部运行失败、失败预算与 CLI 失败码、有界自动推进、遗留运行恢复门、Git closure 阻塞、Human Gate 裁决竞态、单一待决定卡、Domain Context 编译、计划整批回滚与定义漂移保护、持久化恢复、模型上下文隔离与限长、依赖产物接续、跨 RuntimeStore 派发竞争、调用期间真实运行态、原子状态与裁决、异常脱敏、证据边界、模块批注交接、同源本地 API、真实兼容 HTTP 调用、API 类型错误和静态回退。
- SQLite 原子状态转换保证同一任务只有一个模型调用方；完整的多进程调度、租约续期和崩溃恢复仍未交付。
- 公开仓库不包含真实用户工作区数据、模型密钥、商业指标或研究结论；用户选择的本地 SQLite 文件可能保存模型输出，必须按本地敏感数据管理，不能提交到 Git。

## Product Principles

1. 先让长期工作可持续推进，再增加管理维度。
2. 一个事实来源，多种适合业务线的视图。
3. 自动分析提出候选，人类只在关键节点介入。
4. 模块契约和操作协议优先于隐式约定。
5. 只有持久化本地运行记录并取得任务执行权后，界面才展示真实运行状态；外部运行标识和结果按实际响应补齐。
6. 已交付能力与静态演示、规划能力和开放产品决策分别标注。
