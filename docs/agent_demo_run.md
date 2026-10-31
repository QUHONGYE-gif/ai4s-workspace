# Agent 工作流接入

Agent 用于 RFdiffusion、ProteinMPNN 和 Boltz 的资料参数提取、对话配置、确认登记与请求生成。科学执行与 AiiDA 尚未连接；请求标为 `not_submitted`，不能直接提交计算。

## 安装和启动

在个人工作区仓库根目录安装项目专用依赖，需要 Python 3.12+ 和 uv：

```bash
uv sync --frozen
bash tools/pymol_web/start-workspace.sh
```

沿用原 PyMOL 联合入口和 Coder 开发预览，工作台、PyMOL 与 Agent 共用 3000 端口。入口为 **工作流 → 接入自定义流程 → AI 辅助生成**，手动填写与 AI 共用同一份接入草稿。不需要重建容器或新增 Coder 应用。

普通的 `python scripts/serve_workbench.py` 仍只运行工作台。排错时可单独启动内部 Agent，再由工作台代理：

```bash
.venv/bin/python scripts/run_agent_demo.py --port 3002 --root-path /agent
```

`/agent/` 现在跳转到工作台的 AI 接入页；内部服务本身不启动工作台或 PyMOL。停止与运行目录见 [PyMOL 维护说明](../tools/pymol_web/README.md#维护)。

## 配置、画布与回填

1. 在“模型 API 设置”填写 DeepSeek 模型名和自己的 API key；默认模型名只是初始值，需用自己的账号测试。
2. 通过表单或对话修改节点；资料提取后先核对原文、参数分类和旧值→新值，再确认应用。上传 PDB、FASTA 或 A3M 后，仍需选择输入绑定和设计链。
3. 拖动卡片顶部移动节点，拖动空白平移；Ctrl／Command＋滚轮缩放。分层／环形布局仅改变排列，节点位置保存在草稿，镜头保存在当前浏览器。选中卡片可用方向键移动，布局与图操作可撤销。
4. “连接步骤”支持从同一输出分支到多个节点。实线表示输入绑定，虚线表示需要格式转换，点线表示反馈／参考设计关系；辅助产物端口只是输出声明，不代表文件已生成。
5. “应用到接入草稿”保留已填项目信息和明确的参数、输入与来源；调用指令仍需人工核对。参数变化会清空关联旧指令。当前接入表单只接受串行链，分支及反馈关系会明确拒绝回填，继续保留在 AI 草稿中。
6. 保存并确认登记后可查看或导出请求；相关配置变化会令登记／请求过期。反馈关系没有循环条件、停止条件或执行语义，生成请求会标记 `design_relations_not_executable`。

“图结构 / 操作”可下载带端口、位置、输入引用和消费者的 `ai4s-graph-1` 投影。它不含全部参数与来源；保留完整配置请使用“导出 AI 草稿”。批量操作复用现有变更接口，最多 20 项，一次校验并保存，失败不部分写入。

| 相对 `agent/` 的接口 | 内容 |
| --- | --- |
| `GET api/graph-contract` | 操作 Schema、模型端口与布局能力 |
| `GET api/workflows/{id}` | 完整草稿和当前修订号 |
| `POST api/workflows/{id}/changes/preview` | 只读校验和修改摘要 |
| `POST api/workflows/{id}/changes` | 按 `expected_revision`、`operation_id` 和 `operations` 保存；破坏性操作须 `confirmed` |

图操作包括 `move_node`、`set_layout`、`add_relation`、`remove_relation`，与原有节点、连接及参数操作共用类型和版本检查，不执行任意代码。

## 数据与边界

密钥仅保存在服务端私有文件或环境中，页面不回显，也不随 Git 部署。支持 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 或忽略于 Git 的 `.local/agent-demo.env`。留空表示保留已存密钥，删除须显式操作。

Agent 默认数据为仓库 `.local/agent-demo/`，可用 `--data-dir` 或 `AI4S_DEMO_DATA` 指定。原工作台快照、PyMOL 上传及日志继续使用原运行目录，彼此不自动转换。

该版限个人单用户、单进程、单 worker；有修订冲突检查、原子 JSON 保存和进程锁，没有正式多人鉴权。文件检查只覆盖有限格式、链和记录，不能替代科学验证；环境身份、输入物化、格式转换与真正提交仍待引擎适配层接通。

## 验证与文件职责

```bash
uv run pytest -q
node --test tests/test*.cjs
```

`tests/fixtures/backbone.pdb` 是手写的三条 CA 记录，仅用于格式、链和 API 检查。测试和验收入口不依赖历史实验归档；TestModel 不证明真实语言理解效果。

真实语言验收须先启动服务并配置密钥，再显式执行以下命令，会消耗 API 额度：

```bash
uv run python scripts/verify_agent_demo.py --live \
  --url http://127.0.0.1:3000/agent \
  --output .local/agent-demo-live-report.json
```

- `src/ai4s_demo/`：API、受限 Agent 工具、模型定义、输入检查与工作流状态。
- `src/ai4s_demo/web/`：嵌入界面；`graph-model.js` 负责数据投影与布局，`graph.js` 负责画布交互。
- `scripts/run_agent_demo.py`：内部服务；联合启动继续由原 PyMOL 入口管理。
- `scripts/verify_agent_demo.py`：显式启用的真实 API 验收。
- `pyproject.toml`、`uv.lock`：业务依赖，不包含科学模型环境或权重。

实际验证与部署状态见 [当前状态](status.md)。返回 [前后端开发](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [仓库入口](../README.md)。
