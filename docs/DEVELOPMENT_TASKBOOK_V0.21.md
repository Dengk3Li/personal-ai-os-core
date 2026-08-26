# Personal AI OS v0.21 模板绑定门验收

状态：`CANDIDATE / 公开 feature branch`

## 本轮目标

让任务在进入 `ExecutionBroker` 的运行边界前，先核对可选的
`TemplateSelection/v1`。模板正文、文件路径和凭据继续由私有适配器持有；公开核心
只接收经过校验的模板绑定元数据。

## 任务声明

任务可以在 `context.template_selection` 中声明模板选择。该字段未出现时，沿用没有
模板绑定的历史任务形状；字段一旦出现，就视为本任务必须具备一个有效的
`TemplateSelection/v1` 记录。

Broker 只接受 `source_ref` 等不透明引用、版本、任务类型和 SHA-256 摘要。选择缺失或
校验失败时返回固定原因码，任务保持 `QUEUED`，不会创建 run、探测 Adapter、记录
运行事件或调用模型。

## 运行边界

有效选择经过一次规范化后，作为 `context_pack.template_selection` 传给 Adapter。
它仍然只包含绑定元数据；公开核心不读取模板正文、不验证私有文件路径、不保存凭据，
也不代替私有适配器执行模板。

`resolve_task_template_selection` 是无副作用的纯边界函数。它返回
`NOT_REQUIRED`、`RESOLVED` 或带固定原因码的 `BLOCKED`，拒绝值不会进入错误信息或
运行记录。

## 验收不变量

1. 无效声明：任务为 `QUEUED`，运行记录数为零，Adapter 的 `probe` 与 `start` 均不
   被调用。
2. 缺失声明值：任务为 `QUEUED`，返回 `TEMPLATE_SELECTION_REQUIRED`，不产生运行
   或 Adapter 调用。
3. 有效声明：Adapter 只收到规范化的模板选择元数据，哈希统一为小写，正文、路径
   与凭据不进入选择记录。
4. 模板是否存在、是否有权读取以及如何加载正文，仍由私有适配器在本地完成；该门
   不把模板绑定误报为任务完成或人工验收。

## 验证

- `tests/test_template_selection.py`：`TemplateSelection/v1` 字段和隐私边界。
- `tests/test_template_selection_gate.py`：Broker 派发前的缺失/无效/有效选择路径，
  以及零 run、零 Adapter 调用和规范化元数据交接。
