# 工作台前后端开发

工作流与实验闭环采用模拟数据，PyMOL 提供真实结构查看与命令执行。具体能力见 [当前状态](../docs/status.md)。

## 启动

从仓库根目录启动演示前后端：

```bash
python scripts/serve_workbench.py --host 127.0.0.1 --port 3000
```

然后打开工作区已有“开发预览”。需要真实 PyMOL 时，改用 [联合启动器](../tools/pymol_web/README.md)，不同时启动两个占用 3000 端口的服务。

## 修改哪里

| 文件 | 职责 |
| --- | --- |
| [index.html](demo/index.html) | 页面外壳与资源引用 |
| [app.js](demo/assets/app.js)、[styles.css](demo/assets/styles.css) | 页面交互、模拟规则与样式 |
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

## 验证

```bash
python -m unittest discover -s tests -p 'test_workbench_api.py' -v
node tests/test_demo_logic.cjs
node tests/test_api_client.cjs
```

界面改动按需验证真实预览中的资源、路由、刷新、交互与 WebSocket。Node.js 仅用于上述逻辑检查。

返回 [仓库入口](../README.md) · [成员协作](../docs/collaboration.md)。
