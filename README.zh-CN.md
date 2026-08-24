# Personal AI OS

Personal AI OS 是一个面向长期 AI 工作的本地操作层。它把长期目标拆成可执行的短任务，为任务分配合适的模型或工具，保存共享状态，并把需要判断的节点交还给人。

单个 AI 对话适合处理边界清楚的小任务。任务一旦跨越多次对话，新的对话需要重新核验旧内容；计划生成后缺少稳定的推进方式；多个执行分支也很快变得难以检查。Personal AI OS 补上长期目标和单次 AI 运行之间的操作层。

[English](README.md) · [v0.6 开发任务书](docs/DEVELOPMENT_TASKBOOK_V0.6.md) · [产品研究](docs/PRODUCT_RESEARCH_V0.6.zh-CN.md)

它不打算重复做一套通用 Agent 工具箱。浏览器、终端、定时任务、记忆、子 Agent 和远程运行已经有成熟产品。Personal AI OS 处理这些执行器之上的问题：工作区结构、可移交的任务现场、证据验收、人工决定和跨执行器连续性。

## v0.6 工作流演示

公开工作台使用匿名合成数据。页面保留工作流结构、任务数量、分配关系、运行轮次和事件轨迹，不包含任务标题、验收原文、输入材料和私人路径。

默认演示有 18 项任务，分布在三类工作流中：

- 科研线由科学假设、Protocol 设计、自主实验执行、数据分析和反馈优化五类 Agent 协作，多条实验路径可以并行推进；
- 会议纪要线从录音、演示材料和项目资料进入信息抽取、Draft、审核和定稿；
- 行业研究 / 专业报告线从广泛检索和 Data pool 进入论证规划、章节写作、排版与配图。

其中 11 项已分配，3 项正在运行，2 项待验收，6 项已收口，另有 4 次重复运行保留在轨迹中。点击任一节点，可以查看 Agent、模型、执行适配器、Attempt 次数、心跳和产物事件。运行中的节点会按模型显示工作宠物。

```bash
make workbench
```

打开 [http://127.0.0.1:8787](http://127.0.0.1:8787)。静态模式只使用浏览器内存，不读取本地工作区。

## 可持久化运行 MVP

v0.6 已加入一个只依赖 Python 标准库和 SQLite 的本地运行时。它保存工作流、任务、运行、事件、产物和决定，并通过有限 API 驱动同一个工作台。首个真实模型 Adapter 使用 OpenAI-compatible Chat Completions 协议，可以接入 DeepSeek 等兼容服务；凭据不进入仓库和 SQLite。每次运行都会接收当前任务的本地上下文，以及各项已完成依赖的当前验收产物；上下文总量受到明确限制。

```bash
python3 -m pip install --no-deps -e .
personal-ai-os runtime init \
  --store .personal-ai-os/runtime.db \
  --preset science

export PERSONAL_AI_OS_API_BASE="https://你的兼容接口.example/v1"
export PERSONAL_AI_OS_API_KEY="只保存在本机环境变量中的密钥"
personal-ai-os runtime serve \
  --store .personal-ai-os/runtime.db \
  --model "你的模型 ID"
```

打开 [http://127.0.0.1:8787](http://127.0.0.1:8787)。API 可用时，页面会从合成演示切换到本地运行库。创建工作线和任务、启动模型、接受结果、记录裁决都会写入 SQLite。服务重启后，任务、运行轨迹和决定仍可读回。

当前 Adapter 会登记模型的终态输出并送入验收。同一个 runtime 服务进程会拒绝同一任务的并发派发；一个 SQLite 运行库只允许一个 runtime 写入进程。新任务不能伪造完成证据，本地写接口只接受同源 JSON 请求。跨进程派发租约、流式事件、心跳、取消、后台执行、Codex / VS Code 控制、远程机器适配和具备公开许可的动画宠物素材仍在后续工作中；静态演示只展示这些事件的结构，不把它们说成实时能力。

## 操作闭环

```mermaid
flowchart LR
    I[检查工作区] --> M[识别能力]
    M --> P[提出短任务]
    P --> H[人确认]
    H --> R[路由与分配]
    R --> E[执行短任务]
    E --> V[验收结果]
    V --> D{需要判断?}
    D -->|是| G[待我决定]
    G --> R
    D -->|否| A[归档状态]
    A --> R
```

检查和规划只生成候选。确认之后，系统才允许在已接受的任务边界内执行。执行器返回运行标识和事件后，任务才能进入运行状态；只修改界面标签不算执行。

## 三个固定入口

| 入口 | 负责什么 |
|---|---|
| 模块地图 | 在可拖动、可缩放的全局拓扑中查看模块层级、真实依赖、上下游关系、可用状态和可替换插槽；模块批注可转成当前工作流中的修正任务。 |
| 工作进度 | 查看任务数量、分配情况、Loop、并行分支、重复运行和节点轨迹。 |
| 待我决定 | 集中处理计划确认、阻塞和 Human Gate。 |

这是一套操作界面，不是管理大屏。系统用状态转换、运行事件、产物和人工验收证明任务确实在运转。功能数量和页面包装不能替代可运行的闭环。

## 即插即用模块

模块通过 capability 名称连接，不直接引用其他模块。每个模块提供一个带版本的 manifest：

```json
{
  "contract_version": "personal-ai-os.module/v1",
  "module_id": "local-exporter",
  "name": "Local Exporter",
  "layer": "output",
  "summary": "Exports an artifact reference.",
  "provides": ["artifact.export"],
  "requires": ["execution.result"],
  "availability": "READY",
  "optional": true,
  "entrypoint": "local_exporter:activate"
}
```

`discover_module_manifests()` 读取模块目录下一层的 `module.json`，不会导入或执行插件代码。`build_module_graph()` 负责解析能力提供者，报告缺失或重复接口，并拒绝模块之间的直接引用。新增或移除合法 manifest 时，工作台布局不需要跟着修改。

```bash
personal-ai-os modules --directory examples/modules
```

内置模块包括有边界的工作区摄取、Cognitive Intake、工作流状态、动态路由、执行适配、连续性，以及规划中的 Token Manager 插槽。

## 本地 CLI

```bash
personal-ai-os inspect ./workspace
personal-ai-os modules
personal-ai-os plan ./workspace
personal-ai-os spec
```

命令统一输出机器可读 JSON。`inspect` 和 `plan` 保持只读；Git 工作区存在未提交改动时，系统会建立明确的人类确认边界，不会静默吸收这些内容。

## 内核能力

| 能力 | 行为 |
|---|---|
| 长任务拆解 | 检查父子层级、依赖、验收条件、缺失引用和循环依赖。 |
| 人类确认 | AI 生成的计划保持候选状态，人确认后才能执行。 |
| 依赖调度 | 只开放前置任务和 Human Gate 均满足的短任务。 |
| 动态路由 | 按能力和上下文要求选择满足条件的最小执行层。 |
| 任务分配 | 选择能力兼容且仍有容量的执行者。 |
| 模块组合 | 解析带版本的 capability manifest，组合断裂时停止。 |
| 模块问题交接 | 把选中模块的批注转成可持久、可分派的任务，不建立第二套任务系统。 |
| 只读摄取 | 读取本地结构并提出工作地图，不写入目标项目。 |
| 连续接续 | 保存下一次运行恢复和核验所需的状态。 |
| 持久化运行时 | 用 SQLite 保存任务、运行、事件、产物和决定，并支持重启后重放。 |
| 秘书简报 | 从同一状态生成进行中、待验收、阻塞和下一动作摘要，不复制私人记忆正文。 |
| 兼容模型适配 | 通过已配置的 Chat Completions-compatible 接口执行一个有边界的短任务。 |

## 安装与测试

内核需要 Python 3.10 或更高版本；工作台行为测试使用 Node.js。

```bash
python3 -m pip install --no-deps -e .
make demo
make test
```

## 仓库结构

```text
src/personal_ai_os/   计划、路由、运行时、Adapter、秘书层、模块、状态与恢复合同
workbench/            可连接本地运行库的工作台，并保留匿名静态演示
tests/                Python 与工作台行为测试
examples/             合成状态记录和示例模块 manifest
.github/workflows/    Python 3.10-3.12 安装与测试矩阵
PRODUCT.md            稳定的产品边界
docs/DEVELOPMENT_TASKBOOK_V0.6.md  运行时、工作流、宠物与适配器规格
docs/REPOSITORY_ACCEPTANCE_V0.6.zh-CN.md  v0.6 封包验收边界
docs/PRODUCT_RESEARCH_V0.6.zh-CN.md  产品空缺、证据和可证伪的 MVP 验收
```

## 公开边界与许可证

这个仓库只包含可复用的产品骨架和合成演示。私人 Memory、输入材料、个人路径、运行回执、模型账号、凭据和本地适配器不会进入仓库。

代码以 [PolyForm Noncommercial 1.0.0](LICENSE) 提供：许可证定义范围内的个人与非商业用途可以使用、修改和分发，并须保留版权声明。商业用途需要取得 Dengk3Li 单独签署的付费许可并署名；当前不提供公开商业联系入口，未签署商业许可前不授予商业使用权。详见[商业使用说明](COMMERCIAL_USE.md)。
