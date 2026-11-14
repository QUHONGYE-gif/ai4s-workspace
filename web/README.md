# 工作台前后端开发

工作流与实验闭环采用模拟数据，PyMOL 提供真实结构查看与命令执行。具体能力见 [当前状态](../docs/status.md)。

## 启动

从仓库根目录启动演示前后端：

```bash
workbench_state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/ai4s-workbench-demo/api-state"
python scripts/serve_workbench.py --host 127.0.0.1 --port 3000 \
  --data-dir "$workbench_state_dir"
```

然后打开工作区已有“开发预览”：根路径为项目介绍页，经“进入工作台”进入 `workbench.html`。入口只在浏览器保存显示名称，不校验账号或密码。需要真实 PyMOL 时，改用 [联合启动器](../tools/pymol_web/README.md)，不同时启动两个占用 3000 端口的服务。

## Agent 工作流接入

安装 `uv sync --frozen` 后，继续通过原 [PyMOL 联合启动入口](../tools/pymol_web/README.md) 运行；通过“工作流 → 接入自定义流程 → AI 辅助生成”编辑并回填；`./agent/` 兼容旧链接并跳转到该页。普通服务入口保留，仅运行原工作台。模型 API、数据目录和验证边界见 [最小说明](../docs/agent_demo_run.md)。

已登记流程可直接交接到创建实验页；实验助手复用接入页模型配置，创建后确认概述再检查候选。操作与模拟限制见 [登记交接说明](../docs/agent_demo_run.md#登记交接与实验配置)。

## 状态目录与启动切换

上述普通启动示例显式使用与 PyMOL 联合启动相同的状态目录，因此以后可在两种方式之间切换并继续读取同一份模拟快照。

| 启动方式 | 状态目录 |
| --- | --- |
| 普通服务，不传 `--data-dir` | 仓库中的 `.local/workbench-api` |
| 普通服务，使用上方示例 | 用户状态目录下的 `ai4s-workbench-demo/api-state` |
| PyMOL 联合启动器 | 同上，具体运行目录见 [PyMOL 维护说明](../tools/pymol_web/README.md#维护) |

以前未传 `--data-dir` 启动过的记录不会自动迁移；目录不同导致页面记录不同，不表示原文件已被删除。切换前先导出当前浏览器记录，并按原管理方式停止本人服务，再启动目标方式，避免同时占用 3000 端口。需要迁移时，通过页面显式导入或恢复，不直接覆盖或合并已有快照文件。

继续使用同一预览地址和浏览器；不同浏览器或不同 origin 不会自动共用模拟快照命名空间。

## 修改哪里

| 文件 | 职责 |
| --- | --- |
| [index.html](demo/index.html)、[landing.css](demo/assets/landing.css)、[landing.js](demo/assets/landing.js) | 项目介绍与成员入口；旧的 `./#/…` 链接自动转到工作台 |
| [workbench.html](demo/workbench.html) | 工作台页面外壳与资源引用 |
| [app.js](demo/assets/app.js)、[styles.css](demo/assets/styles.css) | 页面交互、模拟规则与样式；`styles.css` 顶部为工作台与 Agent 页面共用的设计变量（颜色、字号、间距、圆角、动效），新样式只取其中的值 |
| [motion.js](demo/assets/motion.js) | 页面进入、计数和卡片高光等纯界面动效，遵循系统“减少动态效果”设置 |
| [yanxu/](demo/assets/yanxu/README.md) | 流程封面、空状态插图、图标与分享图 |
| [api.js](demo/assets/api.js) | 相对路径请求、快照保存与冲突恢复 |
| [pymol.html](demo/pymol.html) | 无工具栏的嵌入式 noVNC 查看器 |
| [server.py](../src/workbench/server.py) | 同源静态资源与 HTTP API |
| [storage.py](../src/workbench/storage.py) | 模拟快照的原子写入及修订检查 |
| [pymol.py](../src/workbench/pymol.py) | 连接已有 PyMOL 会话 |
| [workbench-demo.json](../configs/workbench-demo.json) | 演示流程、步骤与策略 |

## API

前端按页面前缀访问相对地址，兼容 Coder 开发预览。

| 方法与路径 | 内容 |
| --- | --- |
| `GET /api/health` | 服务状态 |
| `GET /api/demo/bootstrap` | 演示配置 |
| `GET /api/demo/state`、`PUT /api/demo/state` | 读取或保存 `{revision, state}`，旧修订返回 409 |
| `GET /api/tools/pymol` | 会话、结构和界面模式 |
| `POST /api/tools/pymol/load` | 加载上传结构 |
| `POST /api/tools/pymol/style`、`POST /api/tools/pymol/mode` | 切换显示方式或完整界面 |
| `POST /api/tools/pymol/command` | 执行原生 PyMOL 命令并返回反馈 |

状态 API 使用 `X-Demo-Session` 隔离模拟快照，不代表成员鉴权或共享权限。保存位置由 `--data-dir` 决定。遇到修订冲突或保存失败，先导出浏览器记录，再显式恢复或导入，避免覆盖未同步内容。

工作流执行、候选匹配和复用决策仍在前端模拟；后端不会执行表单中的模型命令。PyMOL 接口只操作已有个人工具会话，不能作为蛋白质流程或科学效果验证。

## 复用画布与 AiiDA 查询快照

“复用与存储”新增产物关系、复用计划和存储位置三个视图，支持选点、拖动、缩放及模拟整理。画布使用独立示例，不执行模型、不清理实际文件。

[B 查询模块](../src/ai4s_query/README.md)可导出 AiiDA 原生记录，再由页面“导入”读取。此路径是只读离线快照；运行中状态不会被页面改成模拟中断，也不能通过模拟启动／取消／复制配置操作修改真实记录。刷新网页不更新引擎状态，需重新导出。文件仍在来源 Repository，导入 JSON 不授予文件访问或团队共享权限。

## 验证

```bash
python -m unittest discover -s tests -p 'test_workbench_api.py' -v
node tests/test_demo_logic.cjs
node tests/test_api_client.cjs
```

界面改动按需验证真实预览中的资源、路由、刷新、交互与 WebSocket。Node.js 仅用于上述逻辑检查。

返回 [仓库入口](../README.md) · [成员协作](../docs/collaboration.md)。

## 真实实验入口

`web/demo/engine.html` 使用已发布声明生成参数表单，并通过标准库工作台后端调用独立引擎。接口、启动与范围统一见 [引擎说明](../docs/engine_service.md)；最新跨成员证据见 [R007](../experiments/R007-member-reuse/record.md)，历史单成员证据见 [R006](../experiments/R006-aiida-engine/record.md)。原模拟实验流程继续保留。

任务注册中心与工作流编辑器使用独立入口，声明草稿的提案、确认、导出及恢复见[登记说明](../docs/task_declaration_run.md)。
