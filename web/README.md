# 工作台前后端开发

本版本保留原有 UI 和模拟实验闭环，拆分静态资源、浏览器交互与 Python API。启动、个人预览和 CLI 转发见 [成员指南](../docs/collaboration.md#工作台模拟网页)，实际部署位置见 [环境说明](../docs/environment.md#工作台模拟网页与本地-coder-cli)。[返回仓库入口](../README.md)。

## 修改哪里

| 内容 | 文件 | 当前职责 |
| --- | --- | --- |
| 页面外壳 | [demo/index.html](demo/index.html) | 导航、主内容容器、弹窗及资源引用 |
| 视觉样式 | [styles.css](demo/assets/styles.css) | 保留原配色、组件、响应式布局 |
| 页面与模拟规则 | [app.js](demo/assets/app.js) | 按显示辅助、流程定义、模拟决策、运行、页面模板及事件分区；不再保留旧版本覆盖层 |
| API 客户端 | [api.js](demo/assets/api.js) | 相对路径请求、异步快照保存、修订冲突及恢复 |
| HTTP 服务 | [server.py](../src/workbench/server.py) | 同源静态资源、示例配置、健康及状态 API |
| 快照存储 | [storage.py](../src/workbench/storage.py) | 浏览器命名空间、原子写入及修订号检查 |
| 演示配置 | [workbench-demo.json](../configs/workbench-demo.json) | 蛋白质／小分子示例步骤、依赖、模型版本和策略 |
| 启动入口 | [serve_workbench.py](../scripts/serve_workbench.py) | 使用已有 Python 3.10+，无需第三方运行依赖 |

## 已接通的接口

接口相对页面所在目录访问，例如开发预览前缀下的 `api/demo/state`；不硬编码域名根路径。

| 方法与路径 | 内容 |
| --- | --- |
| `GET /api/health` | 返回服务状态和 `simulation` 模式 |
| `GET /api/demo/bootstrap` | 返回演示流程与策略配置 |
| `GET /api/demo/state` | 返回当前浏览器命名空间的 `{revision, state}`；首次为 `0, null` |
| `PUT /api/demo/state` | 提交 `{revision, state}`，成功返回递增修订号；旧修订返回 `409` |

状态接口要求 `X-Demo-Session`，由前端生成并保存不含身份信息的随机标识。它仅隔离模拟快照，**不是实际成员鉴权或共享权限**。当前服务依赖既有个人 Coder 访问边界，仅绑定回环；未建立独立对外部署或真实多人后端。

快照保存目录由启动参数 `--data-dir` 决定，默认在仓库 `.local/workbench-api`，不进入 Git。浏览器继续保留备份；从旧单文件页面迁移时，若服务端尚无该命名空间的快照，会采用同一 origin 下已有浏览器记录，也可显式导入原导出文件。服务端已有记录时优先恢复它；存在未同步的本地修改时保留本地副本并提示处理，避免静默覆盖。

页面显示后端保存状态。并发冲突或网络失败后，先导出当前记录，再通过“体验说明 → 恢复服务端记录”选择恢复，或确认导入备份。不同 origin（文件页面、个人 HTTPS 预览、本机转发）的浏览器标识不同，不会自动共用同一份记录。

## 当前边界

- 模拟的身份计算、候选匹配、保留策略及运行推进仍在前端；服务端存储的是完整体验快照，不是可信科研任务数据库。
- 后端不执行表单里的模型命令，不读取登记的服务器数据路径，不调用 GPU、AI、PyMOL 或 ChimeraX。
- 随机生成意图、种子与依赖含义维持原演示约定；不能将界面示例作为科学方法或性能结论。
- 本次没有引入前端构建工具、数据库、作业调度器或第三方运行库。需要迁移模拟计算到服务端时，可沿现有 API 边界推进。

## 验证

在仓库根目录执行：

```bash
python3 -m unittest discover -s tests -p 'test_workbench_api.py' -v
node tests/test_demo_logic.cjs
node tests/test_api_client.cjs
```

Python 检查使用临时目录与随机回环端口，覆盖状态隔离、服务重建后读取、版本冲突、输入限制和静态文件边界；Node 仅用于本地前端逻辑检查，不是服务器运行依赖。部署到个人工作区后，再验证静态资源、相对 API 路径、实验与产物跳转、刷新恢复和控制台。
