# PyMOL-Open-Source Web 容器部署文档
AI4S大创项目 | 计算生物学可视化工具模块

## 简介
本容器封装开源版 PyMOL (pymol-open-source)，搭配 noVNC 实现浏览器直接访问交互式蛋白结构可视化界面。
- 许可证：BSD-3-Clause，允许容器打包用于科研项目
- 用途：蛋白PDB结构查看、简单结构预处理、可视化出图
- 运行位置：组内Coder云工作区，本机不需要安装Docker/WSL

> 不使用商业版PyMOL，规避版权与分发限制。

## 仓库文件说明
| 文件 | 作用 |
| ---- | ---- |
| Dockerfile | 镜像构建描述文件，定义系统、依赖、PyMOL安装 |
| start.sh | 容器启动脚本，拉起VNC、窗口管理器、noVNC网页服务 |
| data/ | 数据挂载目录，存放PDB、CIF结构文件，PyMOL在容器内读取 `/data` |

## 部署流程（Coder云工作区）
### 前置条件
1. Coder服务正常可访问
2. 代码已推送到对应开发分支（如 `dev-wlh`）
3. Coder工作区内置Docker环境

### 步骤
```bash
# 进入项目工作目录
cd ~/ai4s-workspace

# 拉取最新分支代码
git pull origin dev-wlh

# 进入pymol-web目录
cd pymol-web

# 构建镜像
docker build -t pymol-open-web .

# 启动容器
docker run -d -p 6080:6080 -v $(pwd)/data:/data pymol-open-web