---
name: "Personal AI OS · Long Work"
description: "一套从 Cognitive Intake 延伸而来的浅色、克制、高密度长期工作操作界面。"
colors:
  ink: "#16211f"
  muted: "#515d59"
  paper: "#f3f1e9"
  surface: "#fffdf7"
  surface-strong: "#e9e7dc"
  accent: "#245c4c"
  accent-dark: "#173f35"
  accent-soft: "#dcebe3"
  signal: "#d7ff6b"
  danger: "#914a40"
  warning: "#8a641b"
  white: "#ffffff"
typography:
  display:
    fontFamily: "ui-serif, Georgia, serif"
    fontSize: "clamp(2.6rem, 5vw, 4.8rem)"
    fontWeight: 500
    lineHeight: 0.98
    letterSpacing: "-0.045em"
  headline:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif"
    fontSize: "1.7rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  title:
    fontFamily: "ui-serif, Georgia, serif"
    fontSize: "clamp(1.8rem, 3vw, 2.8rem)"
    fontWeight: 500
    lineHeight: 1.08
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif"
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif"
    fontSize: "0.66rem"
    fontWeight: 850
    lineHeight: 1.2
    letterSpacing: "0.15em"
rounded:
  field: "0.7rem"
  module: "0.75rem"
  navigation: "0.9rem"
  card: "1.25rem"
  panel: "1.3rem"
  pill: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.55rem"
  md: "0.9rem"
  lg: "1.25rem"
  xl: "2rem"
components:
  button-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.pill}"
    padding: "0.72rem 1rem"
  button-accent:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.pill}"
    padding: "0.72rem 1rem"
  button-signal:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.72rem 1rem"
  navigation-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.navigation}"
    padding: "0.78rem 0.9rem"
  module-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.module}"
    padding: "1rem 1rem 1rem 1.15rem"
  task-input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "0.82rem 0.95rem"
  signal-pill:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.5rem"
---

# Design System: Personal AI OS · Long Work

## Overview

**Creative North Star: "荧光批注的工作纸面"**

Long Work 延续 Cognitive Intake 已建立的视觉世界：浅暖纸面承载密集信息，深色墨迹建立层级，墨绿把模块、路径和当前状态组织成一个可操作的系统，荧光黄绿像真实纸面上的批注，只标记需要立即注意的节点。它的气质克制、理性、安静，但不是无差别的灰色管理后台。

界面首先帮助用户建立系统结构，再进入具体工作。固定的三个一级入口、可横向浏览的模块画布、分业务线展开的任务工作区和集中出现的人工决策，共同构成可继承的操作骨架。后续页面可以改变内容密度和业务线内部排版，但应保留这套颜色分工、空间层级与交互反馈。

科研工作流使用与其他业务线相同的 workflow reader、任务状态、运行轨迹与裁决表现，通过 Loop、迭代分组和并行分支表达非线性协作；它不另设一级入口或专属占位视图。

**Key Characteristics:**

- 暖白纸面与轻微荧光环境光，而非纯白应用画布。
- 墨绿承担结构、选中态与主要行动，荧光信号保持稀缺。
- 高密度信息通过网格、细线、色块和字号层级组织。
- 模块节点呈现可组合积木，工作进度以可切换业务线的 workflow reader 展开。
- 桌面端强调并列扫描，窄屏端按决策顺序纵向展开。

## Colors

色彩以暖纸中性色为底，墨绿建立系统结构，荧光黄绿只承担强信号；危险与警告色只出现在相应状态中。

### Primary

- **结构墨绿**：用于当前一级入口、主要业务行动、阶段选中态与模块激活态。
- **深墨绿**：用于系统建议、操作链等需要形成明确边界的深色结构面。
- **淡墨绿**：用于隐私说明、路由标签、弱选中背景与连接件。

### Secondary

- **荧光批注**：用于 Human Gate、确认步骤、计数信号、扫描行动与焦点外环。它是注意力标记，不是大面积品牌底色。

### Tertiary

- **阻塞陶红**：用于阻塞、退回与风险边界。
- **待定赭黄**：用于规划中、开放决策与需要谨慎理解的状态。

### Neutral

- **主墨色**：用于正文、强标题、主按钮与最深操作面。
- **次级墨灰**：用于说明、元数据、辅助标签和非当前状态。
- **暖纸底色**：用于全页背景与输入区，让长时间阅读保持柔和。
- **卡片纸白**：用于任务、模块和决策卡的主要内容面。
- **压实纸灰**：用于详情区、说明条与较低层级的分组面。
- **纯白**：仅用于深色表面上的高对比文字与透明叠层。

### Named Rules

**The 荧光稀缺 Rule.** 荧光信号只标记需要注意、确认或人工裁决的节点；常规导航和装饰不使用荧光填满。

**The 纸面分层 Rule.** 页面层级先由暖纸底、卡片纸白、压实纸灰和墨绿色块形成，颜色不脱离状态与结构单独装饰。

## Typography

**Display Font:** `ui-serif`（后备为 `Georgia, serif`）

**Body Font:** `ui-sans-serif`（后备为系统 UI 字体、`PingFang SC, sans-serif`）

**Label/Mono Font:** 标签继续使用系统无衬线；终端命令使用浏览器等宽默认字体。

**Character:** 衬线标题给长期目标、业务线和操作契约带来编辑感与思考空间；紧凑的系统无衬线承担高频操作、状态和密集说明。两种声音同时存在，但不在同一层级争夺注意力。

### Hierarchy

- **Display**（500，流体大字号，紧凑行高与负字距）：用于页面主命题和首屏长期目标，保持短行并控制在约 10–12 个汉字宽度。
- **Headline**（700，紧凑负字距）：用于一级面板标题，快速划分模块地图、工作进度和待我决定。
- **Title**（500，衬线流体字号）：用于业务线名称、首次运行主张和操作契约标题。
- **Body**（400，舒展行高）：用于目标说明、验收条件、模块摘要和帮助文案；正文保持可扫读的短段落。
- **Label**（850，高字距）：用于英文眉题、系统层级、步骤和状态提示，采用短词组而非长句。

### Named Rules

**The 双声部 Rule.** 衬线字体只承担长期目标与结构性标题；任务、状态、操作和说明统一使用系统无衬线。

## Layout

页面外边距使用流体水平留白，桌面端主视图由 `15rem` 导航轨与弹性内容区组成。首屏概览使用两列：左侧建立目标，右侧四格指标完成快速扫描。导航轨在桌面端保持粘性，顶栏同样保持粘性；内容区只承载当前一级入口的工作面板。

模块地图是设计系统的标志性画布。版本化 manifest 通过 capability 解析为“输入、理解、编排、执行、记忆与观测”分层拓扑；每层节点数量随模块集合增长，并按拓扑顺序排布，不使用固定卡位。真实 DOM 按钮承担节点文本、选择、拖动和无障碍语义，SVG 只绘制带方向的依赖边。`24px` 方格纸视口支持节点拖动、空白区平移、缩放、Fit、Reset 与完整上下游聚焦；右键节点会选择该模块并把焦点送入批注表单，表单提交后生成修正任务。宽屏中画布与模块详情并列，`1320px` 以下上下排列。

工作进度是 workflow reader，不是管理表。浏览器式工作线标签横向切换科研、会议纪要、分析报告或用户新建工作线；深墨绿运行摘要集中显示任务总数、已分配、运行中、重复次数和完成比例。主阅读区左侧按迭代组织非线性 Loop 与并行分支节点，右侧显示当前节点的模型、Adapter、Attempt、分支、验收条件和事件轨迹。业务线可以改变分组与节点组合，但状态、运行记录、决策和行动仍来自同一个工作源。

在 `980px` 以下，概览与主工作区改为单列，导航轨解除粘性并进入内容流，workflow reader 的运行结构与节点详情上下排列。模块拓扑仍保留完整世界坐标，通过平移、缩放和 Fit 阅读，不压缩成失真的卡片栅格；视口高度依次调整为 `31rem` 与 `28rem`。在 `680px` 以下，三个一级入口和表单纵向重排，指标与运行摘要采用两列，工作流节点改为单列；浏览器式工作线标签继续横向滚动。按钮与粗指针环境中的可点击控件保持至少 `44px` 高。

### Named Rules

**The 三入口 Rule.** 后续一级页面始终从“模块地图、工作进度、待我决定”进入；业务线和模块属于入口内部，不新增平级主导航。

**The 同源异形 Rule.** 业务线可以采用适合自身工作的阶段与详情排版，但必须复用同一套任务状态、决策信号和主要行动层级。

## Elevation & Depth

系统以色调分层、细边框和网格结构为主，常规容器保持扁平。模块节点使用轻柔环境阴影表达可拖动实体，默认阴影为 `0 5px 14px rgba(22, 33, 31, .08)`，悬停时增强为 `0 8px 18px rgba(22, 33, 31, .12)`。顶栏使用半透明纸面和 `18px` 背景模糊，在滚动中维持位置关系。键盘焦点由 `3px` 主墨色轮廓、`3px` 偏移和 `5px` 荧光外环共同形成。

### Shadow Vocabulary

- **积木静置**（`0 5px 14px rgba(22, 33, 31, .08)`）：只用于模块节点，暗示可拖动的实体边缘。
- **积木悬停**（`0 8px 18px rgba(22, 33, 31, .12)`）：配合墨绿边框反馈可交互性。
- **阻塞内标**（`inset 0 1px 0`）：使用阻塞陶红标识需要处理的决策卡，不制造整卡浮起。

### Named Rules

**The 结构先于阴影 Rule.** 默认使用色块、边框、网格和留白建立深度；阴影只用于模块实体、焦点或明确状态反馈。

## Shapes

形状由“工作纸面”和“可组合积木”两套几何共同构成。按钮、计数、标签和状态采用全圆胶囊；导航项使用中等圆角；关键引导卡和指标组使用更大的柔和圆角。模块画布、workflow reader、迭代分组、运行详情和操作契约保持接近纸张与图表的直角结构，避免所有容器都变成漂浮圆角卡。

模块节点使用轻圆角矩形，右侧以淡墨绿接头表达 capability 输出；当前节点转为墨绿，接头转为荧光信号。连接件是模块可组合性的视觉语法，只用于真实模块节点。

### Named Rules

**The 积木接口 Rule.** 只有具备模块输入、输出或依赖含义的卡片使用连接件轮廓；普通任务卡和信息卡保持纸面几何。

## Components

### Buttons

- **Shape:** 主要与次要按钮使用完整胶囊轮廓；节点详情中的任务行动占满详情栏宽度，地图工具按钮保持紧凑胶囊。
- **Primary:** 顶栏全局动作使用主墨色底与白字；工作流内主要行动使用结构墨绿底与白字。
- **Signal:** 首次扫描等高注意力但低风险的启动动作使用荧光底与主墨色字。
- **Hover / Focus:** 可用按钮悬停上移 `1px`；所有按钮、输入和链接共享高对比墨色轮廓与荧光焦点外环。
- **Ghost / Reject:** 次要按钮使用半透明纸白或卡片纸白；退回动作只把文字改为阻塞陶红，保留轻表面。

### Chips

- **Style:** 状态和路由胶囊使用压实纸灰或淡墨绿；Human Gate 使用荧光批注；警告与阻塞使用各自的浅色状态底。
- **State:** 胶囊只表达简短状态、能力或路由，不承载句子，也不替代主行动按钮。

### Cards / Containers

- **Module Node:** 卡片纸白、细边框、柔和环境影与右侧连接件组成可拖动积木；激活时整节点转为墨绿，层级标签弱化，右侧接头转为荧光。
- **Workflow Node:** 在迭代分组中呈现任务 ID、状态、Agent、阶段、模型路由和 Attempt；选中时整节点转为墨绿，状态与 Agent 使用荧光或白色层级。
- **Iteration Group:** 使用直角纸面边界包住同一轮任务；组标题同时说明节点数和并行分支数，Loop 的返回关系以明确标记连接到下一轮。
- **Run Detail:** 使用压实纸灰承载当前节点的元数据、验收条件、事件时间线、模型/Adapter 选择和主要行动；在窄屏移到运行结构下方。
- **Decision Card:** 使用纸白平面和明确行动区；阻塞状态在卡片内顶部加入陶红标记，Human Gate 用荧光胶囊定位。
- **Metric Group:** 四个指标共享同一圆角容器和分隔线，不拆成四张独立浮卡。

### Inputs / Fields

- **Style:** 输入框使用暖纸底、细边框和轻圆角，放在纸白任务生成器内；提交按钮使用结构墨绿。
- **Focus:** 与所有交互元素共享墨色轮廓和荧光外环，不能只依赖颜色变化。
- **Responsive:** 在窄屏中输入与提交按钮垂直排列，按钮占满可用宽度。

### Navigation

- **Primary Navigation:** 三个一级入口在桌面端位于左侧导航轨，默认透明、次级墨灰文字；悬停出现浅纸白底，当前入口使用墨绿底和白字，待决策计数使用荧光胶囊。
- **Business-Line Navigation:** 浏览器式工作线标签横向连接 workflow reader，每个标签显示名称、说明与完成计数；当前工作线使用墨绿整面，新建入口使用压实纸灰。窄屏保持横向滚动，不把多条业务线挤成不可读的等宽列。
- **Keyboard Behavior:** 一级入口采用 tab 语义，当前项可聚焦，方向键切换时同步更新选择与焦点。

### Module Canvas

方格纸背景、五层语义泳道、DOM 模块节点、SVG capability 边和相邻详情区共同组成模块地图。拓扑由 manifest 动态生成，节点在各层内随数量纵向增长；新增模块不依赖固定行列或选择器卡位。用户可拖动节点、平移视口、缩放、Fit、Reset，并聚焦当前模块的完整上下游；非关联节点在聚焦时降低透明度，但保持原位置。右键是打开当前模块批注的快捷方式，可见表单提供同等入口，批注提交后进入任务候选或 runtime 任务。

### Business-Line Workspace

业务线工作台复用统一的浏览器式标签、运行摘要、迭代分组、workflow node 与 run detail。科研工作流以通用 Loop、并行分支、依赖和 Human Gate 语法呈现；会议纪要、分析报告和自定义工作线使用同一 reader，不建立专属管理表或第二套状态视觉。

## Do's and Don'ts

### Do:

- **Do** 保留三个稳定一级入口，并把模块、业务线和人工裁决放回各自入口。
- **Do** 使用暖纸、纸白、压实纸灰和墨绿形成密度层级，让荧光只承担关键批注。
- **Do** 让桌面视图并列呈现拓扑/详情与运行结构/轨迹，让移动视图按阅读顺序上下排列，同时保留地图世界坐标。
- **Do** 为所有可交互控件提供清晰的 `:focus-visible` 反馈，并尊重 `prefers-reduced-motion`。
- **Do** 为右键批注保留可见表单等价入口，确保键盘和触屏用户都能把模块问题转成任务。
- **Do** 让不同业务线继承同一任务状态和操作层级，同时保留适合自身工作的详情排版。

### Don't:

- **Don't** 把荧光黄绿当作常规大面积背景、装饰渐变或无意义强调色。
- **Don't** 把每个信息块都做成圆角浮卡；workflow reader、画布、运行详情和操作契约依靠结构边界表达层级。
- **Don't** 在窄屏把模块拓扑重排成无关卡片墙；使用平移、缩放和 Fit 保留完整关系。
- **Don't** 新增与“模块地图、工作进度、待我决定”平级的业务线入口。
- **Don't** 为科研工作流建立独立占位页、专属状态源或与通用 workflow reader 冲突的视觉语法。
