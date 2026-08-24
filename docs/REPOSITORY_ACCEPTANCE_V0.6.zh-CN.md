# Personal AI OS v0.6 实现验收

验收日期：2026-08-24

## 结论

当前公开实现工作树已经从纯合成演示推进到可运行的本地 MVP：SQLite 是任务与运行状态的持久来源，Python 标准库 HTTP server 向 Workbench 提供有限 JSON API，Execution Broker 可以调用已配置的 OpenAI-compatible Chat Completions 服务，Secretary 可以从同一快照生成简报和最小上下文包。

这项结论适用于当前未提交工作树，不代表远端 `main` 已经包含这些实现。静态演示仍保留为无模型配置时的匿名入口；它与本地运行模式在界面上使用不同的数据来源标识。

## 当前实现

| 范围 | 已验收行为 | 当前边界 |
|---|---|---|
| Python 内核 | 计划校验、统一状态、工作流转换、路由、分配、模块图、只读摄取、连续性与 Git 收口 | 不执行自动全仓分形扫描 |
| SQLite 运行库 | 持久保存 `workflows`、`tasks`、`runs`、`events`、`artifacts`、`decisions`；支持 WAL、重启读回和 integrity check | 事件保存在单一 `events` 表；没有独立的流式事件服务 |
| Execution Broker | 检查任务状态、同工作流依赖、Human Gate、Adapter 可用性和外部运行 ID；把已完成依赖的当前验收产物和任务本地上下文交给下游；同一 runtime 服务实例内，同任务并发派发只允许一次模型调用 | 当前 Adapter 调用是同步终态调用；没有后台作业控制或跨进程派发租约 |
| 本地 HTTP API | 使用 Python 标准库 `ThreadingHTTPServer` 提供运行投影、创建工作流/任务、启动运行、任务转换和决定记录；写接口要求同源 JSON | 不是 FastAPI；没有 API 版本前缀、SSE、取消、续接或打开外部 UI 的端点 |
| 模型 Adapter | OpenAI-compatible Chat Completions 端到端 HTTP 调用通过；密钥不进入返回回执或 SQLite | 没有模型发现、流式 token、Codex App Server、VS Code 或远程执行 Adapter |
| Secretary | `context-pack/v1` 只装配目标、验收、状态、约束、产物与引用；`secretary-brief/v1` 汇总注意事项和最多三项下一动作 | 没有定时巡检、证据过期检测、主动通知或自动 Domain 切换 |
| Workbench | API 可用时切换到 runtime 投影；支持创建工作流/任务、启动运行、接受结果、恢复暂停任务、记录决定，以及模块批注转任务；HTTP 失败会显示错误 | 未接通的扫描、递归模块下钻、模板规划与实时事件仍属于静态或后续能力 |
| 工作流预设 | science、meeting notes、analytical report 可写入运行库；science 含五类 Agent 和并行路径 | 预设是任务合同，不包含实验设备、检索或文档发布工具 |

## 实际 API

| 方法 | 端点 | 行为 |
|---|---|---|
| `GET` | `/api/runtime` | 返回运行库完整 Workbench 投影、Secretary brief、Adapter probe 和默认模型 |
| `POST` | `/api/workflows` | 创建工作流 |
| `POST` | `/api/tasks` | 创建任务并校验依赖存在且属于同一工作流 |
| `POST` | `/api/runs` | 通过 Broker 启动一次 Adapter 调用 |
| `POST` | `/api/tasks/{id}/transition` | 按统一状态机转换任务 |
| `POST` | `/api/decisions/{id}/resolve` | 记录 Human Gate 选择并按合同恢复任务 |

服务同时提供 `workbench/` 静态文件。CLI `runtime serve` 只允许绑定 loopback 地址，并要求显式模型 ID。

## 状态与证据不变量

- 任务状态统一为 `QUEUED`、`IN_PROGRESS`、`REVIEW`、`DONE`、`BLOCKED`、`PAUSED` 和 `ARCHIVED`。
- 新任务引用的依赖必须已经存在，并且属于同一工作流；空依赖 ID、自依赖和跨工作流依赖被拒绝。
- Broker 只有在 Adapter 返回非空外部运行 ID 后才登记 run 并把任务置为 `IN_PROGRESS`。
- Human Gate 在 Adapter 调用前创建决定；暂停选项把任务置为 `PAUSED`，用户可以从 UI 恢复到 `QUEUED`。
- 非 Git 任务进入 `REVIEW` 或 `DONE` 前必须具有已登记结果；要求 Git closure 的任务继续按 review、done 和 archive 回执校验。
- 模型成功响应写入本地 `artifacts`，任务进入 `REVIEW`；模型回合成功不等于用户已经接受结果。
- Adapter、API 或状态校验失败会返回明确错误，Workbench 不执行乐观成功更新。

## 验证证据

- `make test`：58 个 Python 测试全部通过。
- `node --test tests/*workbench*_test.js`：37 个 JavaScript 测试全部通过。
- 覆盖范围包括 SQLite 重启恢复、依赖产物接续、单服务实例并发派发、原子任务状态与裁决、初始状态与证据边界、Human Gate 暂停与恢复、模块批注转任务、外部运行 ID、模型输出登记、Secretary brief、同源 JSON 写入、真实兼容 HTTP 调用、API 路径边界和 Workbench 错误显示。
- 指定公开文档未保留业务专用缩写或本机绝对路径；凭据形态扫描无命中。

测试通过证明当前合同和受控路径符合预期，不证明尚未实现的实时流、后台生命周期、IDE 控制或远程执行能力已经可用。

## 明确未交付

- SSE、WebSocket 或其他事件推送；当前 Workbench 通过请求后重新读取 `/api/runtime` 刷新状态。
- 后台流式执行、运行中取消、续接、超时恢复和断线重放。
- 多个 CLI 或 server 进程共享同一 SQLite 时的派发租约；当前运行库采用单写入进程合同。
- Codex App Server Adapter、VS Code Adapter、远程机器 Adapter 和 DeepSeek Harness 控制。
- 供应商模型目录发现、能力筛选、容量管理和自动回退策略。
- 自动递归扫描并理解整个仓库内部结构的分形地图；当前 `inspect` 只做有边界的只读结构检查，模块图只解析 manifest。
- Secretary 的定时巡检、停滞检测、证据新鲜度判断、主动消息和自动 Domain 路由。
- 已许可的第三方宠物动画素材；当前视觉只承担状态插槽和静态演示。

## 发布与数据边界

- 公共静态 fixture 使用匿名合成内容，不包含真实任务正文、输入材料或运行产物。
- 模型凭据只从本地服务进程读取，不写入 SQLite、浏览器状态或 Git。
- 本地 SQLite 会保存任务字段和模型终态输出。文档示例使用已排除版本控制的 `.personal-ai-os/` 目录；其他数据库位置也必须明确排除版本控制，并按敏感工作数据管理。
- 第三方素材只有在来源、作者和公开许可证完整时才能进入仓库。
- PolyForm Noncommercial 仅授予许可证定义范围内的个人和非商业权利；商业使用需要单独书面许可并保留要求的署名。

## 下一道门槛

1. 为全部可见动作建立服务端 capability 状态，并让未接通动作明确禁用。
2. 把同步 Adapter 扩展为后台运行合同，再实现持久事件游标、SSE、取消与断线恢复。
3. 在同一 Broker 边界下增加 Codex App Server 和 VS Code Adapter，不新增第二套任务状态。
4. 增加模型发现、能力筛选和用户显式回退策略。
5. 把 Secretary 从快照简报扩展到可验证的停滞与证据新鲜度检测；主动通知继续由用户授权。
