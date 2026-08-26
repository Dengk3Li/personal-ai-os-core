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
- 工作进度以 Domain 为一级分页、工作线为二级分页；页面只呈现当前工作线的目标、结构、任务和运行轨迹。
- 模块地图默认展示从总管入口、个人上下文、领域抽象、长期工作内核、执行、验收到经验反馈的系统全景；复合模块支持双击下钻和面包屑返回。
- 模块详情将结构上下游、反馈关系、外部输入、内部处理、主要输出和接口协议分开呈现；下钻后的子图同时保留所属上层模块及跨层输入、输出和反馈交接。
- “组件依赖”视图从 `personal-ai-os.module/v1` manifest 解析实际安装能力和依赖，与描述顶层操作架构的“系统全景”保持语义分离；选中模块的批注可以进入当前工作流成为修正任务。
- `personal-ai-os.workflow-structure/v1` 校验并计算任务、顺序、分支、汇合、条件和有界循环。条件只能引用登记规则，未知条件等待人工决定，循环必须设置最大轮次。结构求值尚未直接驱动 RuntimeStore 与 AutoAdvance。
- `personal-ai-os.presentation/v1` 通过严格白名单替换工作线和任务的浏览器文案，并允许设置仅供阅读器使用的 `sequence / branch / join / condition / loop` 结构提示。结构提示不参与调度或状态判断；运行标识和关系标签在浏览器中使用稳定顺序别名，操作由服务端还原；展示包不修改 SQLite 事实，也不接受上下文、本机路径、Git 收口或模型载荷。
- 通用任务状态为 `QUEUED`、`IN_PROGRESS`、`REVIEW`、`DONE`、`BLOCKED`、`PAUSED` 和 `ARCHIVED`；UI 分别呈现待分配、进行中、待验收、已收口、已阻塞、已暂停和已归档。
- SQLite 运行库持久保存工作流、任务、运行、事件、模型输出产物和人工决定，并支持服务重启后读回。
- `personal-ai-os.runtime-event/v1` 为有 `run_id` 的运行事件提供统一动作、观察和回执信封，分开表达产物、验收、决定、恢复门与终态；旧事件字段保持不变，并可序列化为兼容 SSE 的 `data` 帧。当前仍没有后台 SSE 推送端点。
- Execution Broker 在依赖、Human Gate 和 Adapter 可用性通过校验后，以同一 SQLite 事务完成任务执行权占用、本地 run 创建和分配事件登记。只有取得执行权的实例会调用模型；外部运行标识在 Adapter 响应后补入 run。
- 当前本地服务使用 Python 标准库 HTTP server，提供运行投影、工作流与任务创建、任务转换、运行启动和决定记录的有限 JSON API。
- 本地服务显式区分 `private-local` 与 `public-safe`：前者只允许 loopback 并保留本地真实任务文案；后者要求展示包并输出安全浏览器投影。两种模式都对白名单外的 Adapter 探测字段和异常详情关闭输出。
- 当前真实模型入口包括同步的 OpenAI-compatible Chat Completions Adapter 与 Codex app-server Adapter。Workbench 在请求期间轮询持久化状态，因此真实调用阶段可见 `IN_PROGRESS` 与 working 宠物。终态输出登记为本地产物后送入 `REVIEW`。
- `personal-ai-os.runtime-plan/v1` 可以把本地实际工作线幂等同步到 SQLite。计划文件保存在 Git 忽略目录；重复同步不会覆盖任务状态、运行证据或结果。
- 任务 `context` 只在服务端保存，并从浏览器投影移除，也不会整体发送给模型。模型接收任务 envelope、最多 12,000 字符的显式 `context.model_context`，以及有界的已接受上游产物。
- Secretary 已提供最小上下文包和只读简报：从运行库汇总进行中、待验收、阻塞、暂停、待决定和下一动作，不复制记忆正文。
- `personal-ai-os.domain-context/v1` 按 `domain contract → active project → current state → relevant knowledge → historical decisions → constraints → excluded context` 的固定顺序编译一个领域的引用清单；领域歧义和未知层级 fail closed。
- `personal-ai-os.auto-advance/v1` 有界扫描当前就绪任务，逐项调用同一个 Broker，并记录 `AUTO_ADVANCE_SELECTED / FINISHED` 事件。它不会自动批准 Human Gate、接受 `REVIEW`、解除阻塞或重派遗留的 `IN_PROGRESS` 任务。
- `personal-ai-os.single-owner-progression/v1` 为其他执行适配器提供无存储的单一执行权合同：显式 READY 选择、CAS 版本、租约、触发去重、步骤与 Token 预算、恢复边界和人工验收边界均由稳定状态转换表达。该合同不启动进程、不调用模型、不写入运行库，也不自动接受结果。
- `personal-ai-os.goal/v1` 把跨工作线长期目标独立于聊天和工作线说明持久化。目标保存完成条件、单次与累计预算、累计步数、已观测 Token 和追加式事件；预算耗尽进入 `BUDGET_LIMITED`，范围任务收口进入 `AWAITING_ACCEPTANCE`，只有人工验收才进入 `COMPLETE`。
- GoalController 复用现有依赖、Human Gate、路由、原子任务占用与结果验收。SQLite 目标续推占用阻止两个进程重复续推；未结束占用在重启后进入恢复确认，不自动重放未知外部动作。
- `personal-ai-os.memory-candidate/v1` 按个人或团队、领域、类别和证据保存工作方式候选。新候选必须为 `PROPOSED`；只有带非空审核主体的显式审核可以写为 `APPROVED / REJECTED`，审核事件追加保存。模型上下文只加载主体与领域同时匹配的已确认规则，并与显式模型上下文共享 12,000 字符预算。
- `personal-ai-os.practice-candidate/v1` 是不携带正文的公开候选边界，只允许候选引用、来源引用、匿名范围引用和人工审核状态。`PROPOSED` 只能表示待审核；`APPROVED / REJECTED` 必须带审核者引用。该纯合同不写入长期记忆、不携带路径或业务标签，适配器必须在本地保存正文并先完成脱敏。
- `personal-ai-os.memory-read-receipt/v1` 与 `personal-ai-os.memory-update-candidate/v1` 把运行前记忆读取与运行后候选更新固定为独立引用合同。它们只接受范围、批准权威、时效、运行前读取证明和审核引用，不携带记忆正文、路径、凭据、模型输出或激活操作；可通过不透明引用与执行回执、任务因果交接组合。
- `personal-ai-os.execution-receipt/v1` 是项目执行的通用只读交接边界，只携带已验证的 `project_id`、`thread_id`、`host_id` 引用，以及不含正文的终态、结果和产物引用。已完成回执必须有最终输出引用，且不能等待用户输入或人工裁决；纯校验器不写入运行库、不携带路径、业务标签或凭据。
- `personal-ai-os.task-causality/v1` 以 `inputs -> current_action -> artifacts -> downstream -> next_action` 连接跨对话或跨执行器的任务现场，只携带不透明引用、有界状态和固定下游关系；纯校验器拒绝正文、路径、业务标签、凭据、未知字段、重复引用与超限数据。
- `personal-ai-os.work-protocols/v1` 把强制指令、模板引用、执行规则和个人或团队记忆主体绑定到工作流。Broker 在领取运行权前加载协议和已确认习惯；缺少协议时任务保持待分配。成功运行只发起经验复核，不自动提升长期记忆。
- 模型、自动路由、执行适配器和 API 状态集中在后台“设置”；工作进度不提供逐任务配置控件。私人本地模式可以在浏览器中自动绑定本机 Codex，或把兼容 API 的地址、模型和密钥绑定到当前服务会话。密钥不进入浏览器投影、SQLite 或运行事件。
- `personal-ai-os.module-task-link/v1` 用 `BUILDS / CHANGES / USES / VALIDATES / BLOCKED_BY / AFFECTS` 连接任务和系统模块。自动分析关系保持候选，已确认关系才进入模块进度统计；未关联任务保持可见。
- 模块地图与工作进度使用同一组勾稽关系。模块批注转成任务时保留模块标识；模块详情可以跳到关联任务，任务节点可以显示已确认模块关系。
- 自动推进可以读取 `personal-ai-os.runtime-routes/v1` 服务端目录，按每项任务的能力、层级、预计上下文和可用性选择模型与 Adapter。路线只在任务原子 claim 成功后写入同一 run 的事件；竞争失败方不留下路线证据。
- 内置工作流预设包括 science、meeting notes 和 analytical report。Science 预设实现五类 Agent 与并行实验路径的任务合同，但不把工程运行状态当作科学结论。
- 首次扫描与计划生成仍是候选结果，未经用户确认不写入被分析的工作区。
- 静态演示中的心跳仍是合成事件。连接本地运行库后，working 宠物只消费真实 `IN_PROGRESS` 状态；它不会反向改变任务状态。
- 当前版本没有后台 daemon、心跳续租、未知外部运行对账、SSE、流式 token 展示、运行取消或续接、服务端宠物注册表、VS Code Adapter、远程执行 Adapter，也没有自动递归理解整仓内部结构的分形扫描。Codex 自动配置只读取本机可执行文件、登录状态与默认模型；兼容 API 密钥为进程内会话绑定，服务重启后需要重新输入。
- 过往对话的自动采集、候选提取与冲突核验仍是规划能力。公开内核已经能够按工作协议强制读取已确认习惯并在任务后登记复核请求，但不会自动推断人格或自动提升个人模型。
- 能力自动发现、安装、启用和自我修改尚未交付；未来接入必须经过权限、许可证、验证和人工确认。
- `privacy_class` 当前是候选审阅元数据，不是单独的执行授权系统。模块关系允许插件定义新 `module_id`；尚未接入模块目录的标识不会出现在系统图，跨目录 unresolved-link 检查属于下一阶段。
- Token Manager 仍是规划中的可组合模块，不能标为已可用。

## Brand Commitments

界面延续 Cognitive Intake 的浅色、克制、信息密集但可快速摄取的产品语言。用户可见文案直接描述任务、状态、结果和动作，不展示 Agent 推理、调试记录或管理仪式。静态演示和本地运行状态必须具有明确且不同的数据来源标识。

## Evidence on Hand

- `src/personal_ai_os/` 已包含计划拆分、动态路由、任务分配、统一状态、SQLite 运行库、Execution Broker、OpenAI-compatible Adapter、Secretary 简报、连续性和验收能力。
- `workbench/` 能在本地 API 可用时读取运行投影，并在连接失败时回到匿名合成演示。
- 当前全量测试通过 315 个 Python 用例和 89 个 Workbench 用例，覆盖 Codex app-server 协议、浏览器执行绑定、密钥不回显、路由原子替换、非敏感执行设置重启恢复、最终消息边界、实时运行与重启恢复区分，以及工作协议、任务后经验复核、自动路由、计划同步、模块边界、持久目标、Human Gate、刷新位置保持、工作线推进门、只读验收投影、研究输入门和因果交接合同。
- SQLite 原子状态转换保证同一任务只有一个模型调用方；完整的多进程调度、租约续期和崩溃恢复仍未交付。
- 公开仓库不包含真实用户工作区数据、模型密钥、商业指标或研究结论；用户选择的本地 SQLite 文件可能保存模型输出，必须按本地敏感数据管理，不能提交到 Git。

## License boundary

公开代码以 [PolyForm Noncommercial 1.0.0](LICENSE) 提供。许可证范围内的个人与非商业使用须保留版权声明；商业使用需要另行取得 Dengk3Li 的书面付费许可并署名。`PracticeCandidate/v1` 只定义安全元数据边界，不改变仓库许可证条件，也不授予任何商业权利。

当前全量测试通过 315 个 Python 用例和 89 个 Workbench 用例（`make test`）。

## Product Principles

1. 先让长期工作可持续推进，再增加管理维度。
2. 一个事实来源，多种适合业务线的视图。
3. 自动分析提出候选，人类只在关键节点介入。
4. 模块契约和操作协议优先于隐式约定。
5. 只有持久化本地运行记录并取得任务执行权后，界面才展示真实运行状态；外部运行标识和结果按实际响应补齐。
6. 已交付能力与静态演示、规划能力和开放产品决策分别标注。
