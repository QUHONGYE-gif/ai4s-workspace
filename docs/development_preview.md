# 个人开发预览与分析页面

本文件维护个人页面入口及运行方式；开户见 [成员说明](members.md)，分支与合并规则见 [协作约定](collaboration.md)，实际部署验证见 [当前状态](status.md)。

## 打开入口

登录 [Coder](https://coder.my-rustdesk.xyz)，进入自己的 `dev` 工作区，使用下面两个按钮。普通成员只能访问本人的页面；不要把链接当作面向其他成员的分享链接。服务器管理员仍具有管理权限。

| 按钮 | 容器内服务地址 | 用途 |
| --- | --- | --- |
| 开发预览 | `http://localhost:3000` | 个人网页、前端或应用开发服务 |
| 分析页面 | `http://localhost:8501` | 分析服务、交互图表或导出的 HTML 报告 |

四位成员可以同时使用相同端口，因为服务运行在不同容器内。入口使用现有 HTTPS 域名的路径代理；没有发布宿主机端口，也没有配置任意端口预览或通配子域名。配置唯一维护在 [个人模板](../coder/templates/server-personal/main.tf)。

入口只负责把浏览器连接到个人服务，不会自动启动应用。当前没有预装业务网页、Node.js、Streamlit 或 Jupyter；服务未启动时入口会提示无法连接，启动后重新打开即可。

## 在自己的代码上查看效果

1. 在个人工作区终端中执行 `cd ~/ai4s-workspace && git status -sb`，确认是自己的分支。
2. 使用项目实际的启动命令，将开发服务设为端口 `3000`，或将分析服务设为端口 `8501`。优先监听 `127.0.0.1`，由 Coder 代理访问。
3. 点击对应按钮。应用支持热更新时，保存后会自动更新；静态 HTML 刷新浏览器即可。需要重启才能加载代码的后端，重启自己启动的应用进程。
4. 验证后再按团队约定提交个人分支、创建 PR、汇总和开会。查看个人修改不需要先提交、推送或合并到 `main`。

本地 Codex 修改的是本地副本时，先将修改传到自己的工作区，或在个人分支推送后于工作区拉取。Coder 不会自动同步本地文件。操作前检查两端未提交修改，避免覆盖；通过远程编辑直接修改工作区文件时，无需另行同步。

## 不安装新依赖的页面示例

在工作区终端执行以下命令，使用已有 Python 展示独立报告目录。示例不修改仓库：

```bash
mkdir -p ~/preview-pages ~/analysis-pages
test -e ~/preview-pages/index.html || printf '%s\n' '<h1>我的开发预览</h1>' > ~/preview-pages/index.html
test -e ~/analysis-pages/index.html || printf '%s\n' '<h1>我的分析页面</h1>' > ~/analysis-pages/index.html
python -m http.server 3000 --bind 127.0.0.1 --directory "$HOME/preview-pages"
```

保持该终端运行，点击“开发预览”。另开一个工作区终端启动分析页面：

```bash
python -m http.server 8501 --bind 127.0.0.1 --directory "$HOME/analysis-pages"
```

把自己的 HTML、图片及相关静态文件放入相应目录，刷新即可查看；HTML 中使用相对链接，例如 `./figure.png`。不要将包含 `.env`、Git 凭据或私密配置的整个代码目录作为静态网站根目录。结束示例时在对应终端按 `Ctrl+C`，释放端口后再运行实际应用。

服务进程不随页面按钮自动启动，也不保证终端关闭后继续运行。需要后台运行时使用项目现有的进程管理方式并保存日志；工作区停止后应用需要重新启动。代码、报告及个人虚拟环境放在持久化的 `/home/coder` 中；容器系统目录内的临时安装不保证在重建后保留。

## 框架应用的路径适配

入口位于类似 `/@csr/dev.dev/apps/preview/` 的路径下，而不是独立域名的根路径。框架的资源地址、路由前缀、重定向及 WebSocket 地址需要支持这个前缀；直接写成 `/assets/...` 或 `/api/...` 的根路径可能跳到 Coder 自身。以按钮打开后的实际路径为准，并按所用框架配置 `base`、`root_path` 或相应选项。

当前静态页面及代理连通性验证不代表所有前端框架都已经适配。接入具体业务应用时，再验证其页面路由、资源和热更新。没有针对未选定的框架预装工具或占用固定端口的常驻示例服务。

## 管理员更新

发布模板不等于现有工作区自动更新。这个版本的 Coder 在普通工作区重新构建时会更换 agent 令牌，可能重建容器；不要将“只增加按钮”理解为必然无重启。

按 [模板发布流程](members.md#管理员准备种子与发布模板) 发布后，在 Coder 中逐个选择需要更新的个人工作区。更新前检查成员任务、端口、容器可写层、持久卷及代码状态；逐个更新并复核登录、页面权限和代码摘要。保留已有个人 checkout，不重新克隆、切分支或重置。新增成员会从当前模板直接获得两个入口。管理员 `prototype` 继续使用旧模板。

依据：[固定版本 coder_app 配置](https://github.com/coder/terraform-provider-coder/blob/v2.19.0/docs/resources/app.md) · [Coder 工作区应用](https://coder.com/docs/admin/templates/extending-templates/web-ides)。

相关文档：[成员说明](members.md) · [协作约定](collaboration.md) · [服务器说明](server_docker.md) · [当前状态](status.md) · [仓库入口](../README.md)。
