# Personal AI OS v0.11 开发任务书

## 交付目标

v0.11 收口工作进度的信息层级、模块连接说明和本地运行投影边界。页面聚焦当前工作线，模块详情能够解释系统连接，私人本地使用与公共安全展示使用不同且明确的服务模式。

## 已交付范围

### Domain 与工作线双层分页

- Domain 是一级分页，工作线是二级分页。
- 工作线的 Domain 归属写入运行库；空工作线在刷新和重启后仍保留原 Domain。
- 当前 Domain 只显示自己的工作线。
- 当前工作线只显示自己的任务、结构和运行轨迹。
- 两级分页均支持方向键、Home 和 End。
- 切换分页只更新投影，不写入任务状态。

### 运行设置收敛

- 工作线级和任务级执行设置默认收起。
- 无可用 Adapter 时，选择框显示“暂无可用执行适配器”。
- 服务端投影固定运行或自动路由的真实就绪状态；模型或 Adapter 未就绪时，固定运行按钮保持禁用，自动路由配置完整时无需伪造默认模型。
- 禁用状态使用低强调样式，不伪装成可执行主动作。

### 模块连接说明

- 结构上下游不再混入 feedback 回边。
- 模块详情分别显示外部输入、内部处理、主要输出、接口协议和反馈关系。
- 复合模块继续使用同一画布下钻和面包屑返回。
- 模块批注仍只生成一项有边界的任务候选。

### 本地投影模式

`runtime serve` 支持两种显式模式：

- `private-local`：保留真实本地任务文案，只允许绑定 `127.0.0.1`、`localhost` 或 `::1`；
- `public-safe`：要求 `personal-ai-os.presentation/v1` 展示包，并输出安全浏览器投影。

两种模式都只返回固定字段的 Adapter 目录，并对外使用稳定错误原因。`public-safe` 还会匿名化模型、Adapter、路由和既有分配标签，并在操作时由服务端还原。`private-local` 仍由当前操作系统用户承担本机信任边界；它不是安全沙箱，也不能用于局域网或公网发布。

## 设计参考

- [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)：客户端不持有执行权，后台运行与恢复由独立执行层负责。
- [LangGraph](https://github.com/langchain-ai/langgraph)：持久工作流、明确 interrupt 和节点边界恢复。
- [OpenHands](https://github.com/OpenHands/OpenHands)：控制中心、Agent Server 和自动化服务分层。
- [Letta Code](https://github.com/letta-ai/letta-code)：常驻上下文与按需记忆分层；本版本不引入自动记忆改写。
- [LoopX](https://github.com/huangruiteng/loopx)：私人运行状态与公共通用合同分离。

这些项目用于校验工程边界。v0.11 不复制其会话运行时、图引擎、记忆系统或控制平面。

## 验收

- 134 个 Python 用例通过。
- 55 个 Workbench 用例通过。
- 真实浏览器可切换 Domain 和工作线，并只显示当前工作线节点。
- 模块地图可下钻，详情包含输入、处理、输出、协议和反馈。
- 无 Adapter 时，工作线和任务两个运行入口均禁用。
- `private-local` 绑定非 loopback 地址时在创建服务前失败。
- 私人任务、路径、项目名称、对话和运行库不进入公共仓。

## 未交付边界

- 工作流结构求值结果尚未直接驱动 RuntimeStore 与 AutoAdvance。
- 没有后台 daemon、持久调度队列、Worker lease 或跨机器恢复。
- 没有流式 Token、运行取消、外部运行状态对账或多机 Adapter。
- 没有自动领域识别、自动人格学习或未经人工确认的记忆晋升。
- 模块启用/禁用和依赖传播仍属于后续版本。
