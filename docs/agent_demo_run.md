# Agent 工作流接入

Agent 用于 RFdiffusion、ProteinMPNN 和 Boltz 的资料参数提取、对话配置、确认登记与请求生成。科学执行与 AiiDA 尚未连接；生成请求明确标为 `not_submitted`，不能直接提交计算。

## 安装和启动

在个人工作区仓库根目录安装项目专用依赖，需要 Python 3.12+ 和 uv：

```bash
uv sync --frozen
bash tools/pymol_web/start-workspace.sh
```

继续使用原有联合启动入口和 Coder 的“开发预览”：工作台、PyMOL 和 Agent 共用 3000 端口，左侧“智能体接入”进入 `./agent/`。启动前按原方式停止本人已有的应用。PyMOL 系统依赖及原入口见 [PyMOL 说明](../tools/pymol_web/README.md)。不需要重建容器或新增 Coder 应用。

普通的 `python scripts/serve_workbench.py` 入口仍保留；它仅运行原工作台，不自动启动 PyMOL 或 Agent。排错时可单独运行内部 Agent：

```bash
.venv/bin/python scripts/run_agent_demo.py --port 3002 --root-path /agent
```

上述内部服务只监听回环地址，由工作台代理。直接打开独立 Agent 页面时使用 `--port 3000 --root-path ''`，并先确认端口空闲。

## 模型 API 与使用

1. 进入“模型 API 设置”，填写 DeepSeek 模型名和自己的 API key，再测试已保存配置。模型名可改；默认值只是界面初始配置，不保证账号可用。
2. 选择模型节点，通过表单或对话修改参数；资料导入先核对原文、参数分类和旧值→新值，再确认应用。
3. 上传自己的 PDB、FASTA 或 A3M，选择输入绑定和设计链，保存草稿后确认登记。
4. 查看或导出请求；后续改参会令旧请求过期。适配层、环境身份、输入物化与科学运行仍需另行接通。

密钥仅保存在服务端私有文件或环境中，页面不回显，也不随 Git 部署。可使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 或忽略于 Git 的 `.local/agent-demo.env`。新工作区须配置自己的密钥；留空表示保留，删除需显式操作。

Agent 默认数据在仓库 `.local/agent-demo/`，可用 `--data-dir` 或 `AI4S_DEMO_DATA` 指定。原工作台的 `api-state/`、PyMOL 上传及日志继续按 [原运行目录](../tools/pymol_web/README.md#维护) 保存，彼此不自动转换。

该版限个人单用户、单服务进程、单 worker；有版本冲突检查、原子 JSON 保存和启动锁，没有正式多人鉴权。文件检查只覆盖有限格式、链和记录，不替代科学输入验证。

## 验证

```bash
uv run pytest -q
node --test tests/test_demo_logic.cjs tests/test_api_client.cjs tests/test_agent_messages.cjs
```

`tests/fixtures/backbone.pdb` 是手写的三条 CA 记录，仅用于格式、链和 API 检查，不是实验产物或可用于科学推理的结构。测试和验收入口不依赖历史实验归档。

需要真实语言验收时，先启动服务并配置可用密钥，再显式执行以下命令；会消耗 API 额度：

```bash
uv run python scripts/verify_agent_demo.py --live \
  --url http://127.0.0.1:3000/agent \
  --output .local/agent-demo-live-report.json
```

确定性测试中的 TestModel 只检查集成机制，不能证明真实语言理解效果。实际部署和验证状态见 [当前状态](status.md)。

## 文件职责

- `src/ai4s_demo/`：API、受限 Agent 工具、模型定义、输入检查、工作流状态及页面。
- `scripts/run_agent_demo.py`：内部服务启动；联合启动仍由原 PyMOL 入口管理。
- `scripts/verify_agent_demo.py`：显式启用的真实 API 验收。
- `pyproject.toml`、`uv.lock`：业务依赖，不包含科学模型环境或权重。

返回：[前后端开发](../web/README.md) · [PyMOL](../tools/pymol_web/README.md) · [仓库入口](../README.md)。
