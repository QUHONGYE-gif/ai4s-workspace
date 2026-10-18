# 成员账号与个人工作区

本文件维护开户和代码隔离操作；分支及会议合并规则统一见 [团队协作约定](collaboration.md)，实际成员接入与验证状态见 [当前状态](status.md)。只按用户确认的身份开户，登录邮箱和初始凭据保存在私密记录中，不发布到公开仓库。

## 已配置的个人模板

服务器新增 [server-personal](../coder/templates/server-personal/main.tf) 模板，与原型使用的 `server-docker` 并存。新成员使用个人模板；现有管理员 `prototype` 仍保留原来的宿主机代码挂载，不在本轮迁移。

旧 `server-docker` 已通过 `templates edit server-docker --private --yes` 取消默认全员访问，保留管理员权限。当前版本的详细模板 ACL 接口属于 Premium 功能，但这个私有模板开关可用；不得重新向普通成员开放挂载部署目录的旧模板。

| 项目 | 个人工作区行为 |
| --- | --- |
| 账号 | Coder 用户名为姓名三字的小写拼音首字母，普通成员权限，无管理员角色 |
| 代码目录 | `/home/coder/ai4s-workspace`，随该工作区的独立 home 卷持久化 |
| 初始分支 | 从账号名生成 `dev-abc`；种子已有对应分支则使用它，否则从种子 `origin/main` 创建 |
| 首次克隆 | 只读 `/opt/ai4s-seed/repository.bundle`，仅含公开 Git 仓库内容 |
| 重启 | 保留已有 checkout、当前分支和未提交修改，不自动 fetch、切分支或 reset |
| 共享目录 | `/shared` 仍用于团队共享产物，不保存个人代码或凭据 |
| 单工作区资源 | 1 核、1 GiB；所有实例仍受项目合计资源限制，见 [环境](environment.md) |

个人工作区不挂载部署仓库、服务器 `.env` 或 Docker socket；种子目录只读。独立卷解决代码和 Git 状态相互覆盖的问题；共享服务器管理员仍可管理这些卷，不把它描述为对管理员或恶意租户的强安全隔离。

停止工作区保留 home 卷；删除工作区会销毁该工作区管理的卷，因此删除前先推送代码并另存需要保留的文件。

## 管理员开户

取得成员首字母和登录邮箱后，在服务器项目目录执行；显示名称可先使用已确认的首字母，真实姓名后续由成员自行补充：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
python3 scripts/configure_members.py add \
  --initials abc --name 'abc' --email 'member@example.com'
```

将示例替换为确认后的信息。也可在本地已打开服务器 SSH 隧道时执行同一脚本，在 `add` 前添加 `--env-file .local/remote/.env`。该选项只供管理员读取既有登录配置，不向成员分发管理员 `.env`。

[开户脚本](../scripts/configure_members.py) 生成独立随机密码，私密记录写入执行机器的 `.local/members/abc.json`（权限 600），终端仅输出路径。同名同邮箱账号已存在时保持原密码和角色；同名不同邮箱时停止，先协调姓名首字母冲突。请求中断后若留下 `pending` 记录，先查询实际创建结果再处理，不覆盖记录或自动重置已有密码。

管理员单独交付该成员自己的初始密码；成员首次登录后修改密码。当前没有发送邮件、设置 GitHub 协作者权限或代配成员 GitHub 凭据。

## 成员首次使用

1. 按 [服务器访问说明](server_docker.md#访问) 连接个人 SSH 隧道，使用自己的 Coder 邮箱与密码登录。
2. 打开已分配的个人 `dev` 工作区；尚未分配时从 `server-personal` 创建，等待仓库初始化完成。
3. 在终端检查 `cd ~/ai4s-workspace && git status -sb`，确认分支为自己的 `dev-abc`。后续需要最新代码时自行 `git fetch origin`，按协作约定同步 `main`。
4. 成员使用自己的 GitHub 凭据，并在获得目标仓库写入权限后执行首次 `git push -u origin dev-abc`。模板只初始化本地分支，不使用管理员 GitHub 身份替成员推送。

Coder 账号与 GitHub 账号是两套身份；创建前者不自动授予后者的仓库权限。服务器网络不通时，由管理员通过本地中转更新公开种子；已有个人 checkout 不会被更新种子覆盖。

## 管理员准备种子与发布模板

当前服务器种子目录：`/data1/qhy/projects/ai4s-workbench/member-seed`。种子从公开 GitHub 仓库生成，不能对包含私有配置或未公开提交的本地工作目录直接打包。首次准备可在本地仓库运行：

```bash
git clone --mirror https://github.com/QUHONGYE-gif/ai4s-workspace.git .local/remote/member-seed.git
git -C .local/remote/member-seed.git bundle create ../repository.bundle --all
git -C .local/remote/member-seed.git bundle verify ../repository.bundle
```

已有镜像仓库时先 `git -C .local/remote/member-seed.git fetch --prune origin`，再生成新 bundle；经 SSH 传至服务器临时文件，验证成功后原子替换种子 `repository.bundle`。仅影响后来创建的 checkout；既有工作区继续保留个人代码。种子记录的是制作时的 Git 快照，不保证始终等于最新 `main`。

将本仓库的个人模板目录（含锁文件、启动脚本）及开户脚本同步到服务器后，执行：

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
python3 scripts/configure_members.py publish-template \
  --seed-path /data1/qhy/projects/ai4s-workbench/member-seed
```

该命令向 Coder 发布个人模板，并将旧原型模板设为私有；不更新或重启已有工作区。服务端继续使用已校验的 provider 缓存和 AMD64 工作区镜像；准备方式见 [服务器说明](server_docker.md)。

接口依据：[Coder 用户 API](https://coder.com/docs/reference/api/users) · [Coder 启动脚本资源](https://registry.terraform.io/providers/coder/coder/2.19.0/docs/resources/script)。

相关文档：[协作约定](collaboration.md) · [CI/CD 计划](cicd.md) · [状态](status.md) · [环境](environment.md) · [仓库入口](../README.md)。
