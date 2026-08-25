# Personal AI OS v0.15 开发任务书

状态：`CANDIDATE / 尚未封包`

## 本轮目标

把模型与路由配置从工作页面移入右上角设置，并让私人本地运行库可以从浏览器真实绑定 Codex 或兼容 API。绑定完成后，当前工作线沿既有 Broker、Human Gate、预算和恢复边界执行有界自动推进。

## 已交付

- 私人本地模式新增 `/api/settings/execution`，只接受同源 loopback JSON 请求。
- Codex 自动配置读取本机 `codex` 可执行文件、登录状态和默认模型，通过 app-server 完成真实 thread/turn。
- 兼容 API 密钥只保存在当前服务进程，不进入运行投影、SQLite、事件或错误回包。
- 任务路由在整包校验通过后原子替换；无效 Adapter、模型、能力或上下文上限不会改变旧设置。
- 设置页提供 Codex 自动绑定、兼容 API 绑定和路由编辑；工作进度页只保留开始、继续、验收与裁决。
- 同一 Broker 持有的活跃运行显示为“进行中”；其他实例或重启后读到的遗留运行进入恢复确认。
- 运行中的模型任务不能被页面提前提交验收。

## 验收

- 190 个 Python 用例通过。
- 72 个 Workbench 用例通过。
- 本机 Codex app-server 只读探测返回真实 thread/turn 回执。
- 私人 LongTask 浏览器完成 Codex 与自动路由绑定，并启动第一项有界任务。
- Codex 最终消息探测只把 `phase=final` 的内容登记为任务产物，过程性消息不进入交付结果。

## 仍未交付

- 设置持久化、API 密钥钥匙串集成、后台 daemon、流式 token、取消与远端运行对账。
- 自动接受 `REVIEW`、自动批准 Human Gate、自动解除阻塞和自动提交 Git。
- 公开封包与版本标签；需先用真实科研任务完成一篇研究报告并验收。
