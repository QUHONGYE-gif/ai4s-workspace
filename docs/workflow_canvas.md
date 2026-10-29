# 工作流画布与 Agent 操作协议

入口：**工作流 → 接入自定义流程 → AI 辅助生成**。当前是三模型配置与设计画布，不代表科学任务已经执行。参数、输入引用、依赖和状态由原有后端管理；画布不单独维护一份科学配置。

## 看图和交互

- 模型卡片左侧列输入，右侧列主输出和辅助产物。RFdiffusion 的 TRB、ProteinMPNN 的 NPZ 评分、Boltz 的 JSON 置信度分别作为辅助输出声明展示，不意味着文件已经产生。
- 实线表示已配置的输入绑定，虚线表示需要格式转换；点线表示反馈／参考设计关系。连线标注实际来源格式及已选记录。空 MSA 时 A3M 显示为当前不用，切为已有 MSA 时该输入变为必需。
- 拖动卡片顶部移动节点；拖动空白平移镜头。用工具栏或 Ctrl／Command＋滚轮缩放；可适应整个图、聚焦所选、展开画布。选中卡片按钮后，方向键移动节点，Shift 加大步长；聚焦画布空白后方向键平移、`+`／`-` 缩放、`0` 适应。Escape 收起展开画布。
- 「分层布局」按科学依赖分列，支持一个输出分支到多个下游节点；「环形布局」只改变排列。手动位置保存到服务端草稿 `visual.positions`；重新布局会清除手动位置，可用已有「撤销」恢复。镜头是按工作流保存在当前浏览器的个人偏好，不进入科学登记快照。
- 「连接步骤」可指定实际输出端口。科学绑定继续检查模型兼容性；反馈／参考关系可以从辅助输出关联其他节点，允许交叉和成环。关系可在「图结构 / 操作」中删除；输入绑定在对应节点的输入详情中断开。

## 三种关系的边界

| 关系 | 保存位置 | 能否构成环 | 是否作为科学输入 |
| --- | --- | --- | --- |
| 输入绑定 | `draft.edges` 与目标 `inputs` | 不允许 | 是，仍待适配层物化、检查并执行 |
| 反馈设计关系 | `draft.visual.relations`，`kind=feedback` | 允许 | 否，尚无循环条件／停止条件／迭代执行语义 |
| 产物参考关系 | 同上，`kind=reference` | 允许 | 否，仅说明哪个输出被哪个节点参考 |

例如 Boltz 的置信度反馈到 RFdiffusion，可以画成环，但本版不会把 JSON 当成 RFdiffusion 输入，也不会启动新一轮设计。重复循环执行仍需后续定义迭代状态、条件及 AiiDA 适配。现有「应用到接入草稿」只接受串行链：分支或设计关系不会被偷偷展平，而是提示保留在 AI 草稿。节点登记和生成请求会保留涉及的设计关系并标记 `design_relations_not_executable`，请求不可提交。

## 让 Agent 操作图

复用既有 HTTP 变更接口，无新增 MCP 服务或独立画图模型。API 前缀相对于工作台：

- `GET agent/api/graph-contract`：返回实际 Pydantic JSON Schema、模型端口与布局能力。
- `GET agent/api/workflows/{id}`：读取草稿和当前修订号。
- `POST agent/api/workflows/{id}/changes/preview`：只校验并给出摘要，不写入。
- `POST agent/api/workflows/{id}/changes`：按预期修订号整批写入，失败不部分保存；已有幂等和冲突机制继续适用。

请求包仍是 `expected_revision`、唯一 `operation_id`、`operations`（1–20 项）和 `confirmed`。未知字段会拒绝，坐标必须为有限数且在 ±100000 内。预览成功后也必须携带原修订号保存，期间的并发修改会返回冲突。

```json
{
  "expected_revision": 0,
  "operation_id": "diagram-edit-unique-001",
  "operations": [
    {"type": "move_node", "node_id": "rfd-1", "x": 0, "y": 100},
    {"type": "add_relation", "relation_id": "confidence-review",
     "source": "boltz-1", "source_port": "confidence", "target": "rfd-1",
     "kind": "feedback", "label": "评估后重新设计"}
  ]
}
```

新增高层操作为 `move_node`、`set_layout`、`add_relation`、`remove_relation`，与现有 `add_node`、`connect`、参数及输入操作共用一个类型契约。Agent 从实际草稿和模型定义读取端口，提出结构化操作并经服务端验证；它无需生成 HTML、SVG 路径或拖动像素。普通问答不能顺带写图。

在「图结构 / 操作」可查看或下载 `ai4s-graph-1` JSON，含稳定 ID、位置、输入所需格式和引用、各输出的消费者、辅助产物及设计关系。这是可视化投影；完整参数、来源和原始草稿仍通过「导出 AI 草稿」保留，不能把投影当作完整运行配置导入。批量操作框接收操作数组，预览摘要并确认后保存，不执行代码。

[分支与反馈操作样例](../configs/agent_graph_branch.json) 应用于**新建的三节点示例**：得到五节点分支和两条设计关系。样例中的 `0`／`sample=1` 仅是待实际上游输出验证的记录选择意图。已有同名节点或关系时会明确拒绝，不覆盖用户数据。

## 实现与参考

- [graph-model.js](../src/ai4s_demo/web/graph-model.js)：纯数据投影、分层／环形布局及边界计算；不依赖 DOM。
- [graph.js](../src/ai4s_demo/web/graph.js)：原生 DOM／SVG 画布、镜头、拖动、端口连线。沿用现有技术栈，不引入 React 或运行时 CDN。
- [类型契约](../src/ai4s_demo/models.py) 和 [服务端操作](../src/ai4s_demo/service.py)：验证、保存和登记语义。

参考了 [Mindmap Builder API](https://github.com/zsviczian/obsidian-excalidraw-plugin/blob/master/docs/ea-script-docs/MindMapBuilderAPI.md) 的能力发现、结构查询、高层操作与独立布局设计，以及 [Mindmap Builder](https://github.com/zsviczian/ea-scripts/tree/main/src/scripts/mindmap-builder) 的节点编辑形式。对比了 [React Flow](https://reactflow.dev/learn/concepts/terms-and-definitions) 的节点、连接点与镜头划分，以及 [Cytoscape.js](https://js.cytoscape.org/) 的图布局能力。本次是设计参考，没有复制其源代码、安装 Obsidian 插件或宣称使用 Excalidraw 渲染引擎。当前轻量布局不提供自动避障、子图折叠或大规模图性能保证。

验证与当前部署情况见 [Agent 运行说明](agent_demo_run.md)；整体限制见 [当前状态](status.md)。
