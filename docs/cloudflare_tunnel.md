# Cloudflare Tunnel 固定域名接入

当前已采用 [阿里云中转入口](aliyun_relay.md)，Cloudflare 服务保持未启用。本文件维护备用方案的准备、启用与回退步骤；实际进度见 [状态](status.md)，现有服务和维护入口见 [服务器说明](server_docker.md)。域名示例 `coder.example.com` 不能直接用于部署。

## 管理员需要准备什么

1. 注册并验证自己的 [Cloudflare 账号](https://dash.cloudflare.com/)。成员不需要注册 Cloudflare，继续使用各自的 Coder 账号。
2. 注册一个自己持有、可修改 Nameserver 的域名。可在 Cloudflare Registrar 或其他注册商购买；比较首年和续费价格即可，当前不需要额外购买 VPS、网站主机或 SSL 证书。
3. 将域名添加到 Cloudflare，选择适用的 Free 网站计划，在注册商处将 Nameserver 改为 Cloudflare 为该域名分配的地址，等状态变为 Active。Cloudflare 注册的域名按其控制台流程完成即可。不要将服务器内网地址写成公网 A 记录。
4. 选定一级子域名，如 `coder.你购买的域名`。此处只发布 Coder，既有成员、工作区与 GitHub 分支继续使用。

官方要求账号、接入 Cloudflare 的域名和能出站联网的服务器，详见 [建立隧道](https://developers.cloudflare.com/tunnel/get-started/)。域名是否可注册、价格和续费按注册商结算页面为准。

## 已准备的服务器组件

- 独立目录：`/data1/qhy/cloudflared-ai4s`；二进制在 `bin/cloudflared`，凭据在 `tunnel-token`，日志在 `logs/`。所有目录均属于 `qhy`，凭据文件权限为 `600`。
- 固定版本：官方 [cloudflared 2026.10.1](https://github.com/cloudflare/cloudflared/releases/tag/2026.10.1)，Linux AMD64；SHA-256 为 `3bfc539f45d2620c71debb7a86be0efa737ed5ccbad9eb85c787116900e5c586`。下载可经本地中转，安装前后均须校验；不覆盖不同的既有二进制。
- [用户服务](../configs/ai4s-cloudflared.service) 归入现有 `ai4s.slice`，自身上限 0.25 核、256 MiB；使用 TCP HTTP/2 出站端口 7844，指标仅监听 `127.0.0.1:20241`。禁用自动升级，日志使用组件自带轮转。
- 使用宿主机用户服务，使接入组件可以直接访问宿主机回环端口；Coder 与成员开发环境仍运行于现有 Docker。无需挂载 Docker socket 或改动共享 Docker。
- [配置脚本](../scripts/setup_coder_cloudflare.sh) 默认只安装服务声明，不启动、不启用开机启动，也不改 Coder URL。没有 Token 时 `--start` 会拒绝启动。

```bash
cd /data1/qhy/projects/ai4s-workbench/repo
sh scripts/setup_coder_cloudflare.sh --prepare
```

版本和 Token 文件参数依据：[运行参数](https://developers.cloudflare.com/tunnel/reference/run-parameters/)。启动前检查服务器到 Cloudflare 的 7844/TCP 出站；普通 TCP 接通或收到证书不代表认证隧道已成功，参考 [连通性预检](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/troubleshoot-tunnels/connectivity-prechecks/)。

## 域名就绪后的启用顺序

1. 在 Cloudflare 的 Networking → Tunnels（部分界面在 Zero Trust → Networks → Connectors）创建名为 `ai4s-coder` 的 Cloudflared 隧道。只需该隧道的 connector Token，不需要给服务器保存全局 API Key。
2. 将 Token 保存为本地忽略文件 `.local/remote/cloudflare/tunnel-token`，权限 `600`；也可由管理员直接保存到上述服务器凭据路径。不要粘贴到聊天、Git、共享文档或命令行参数中。可在本机终端运行下面的交互命令，粘贴时不会回显，且拒绝覆盖已有文件：

   ```bash
   cd /Users/quhongye/Documents/ChatGPT/大创
   python3 -c 'import getpass,os; from pathlib import Path; p=Path(".local/remote/cloudflare/tunnel-token"); p.parent.mkdir(parents=True,exist_ok=True); token=getpass.getpass("Cloudflare Tunnel Token: ").strip(); assert token; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,(token+"\n").encode()); os.close(fd)'
   ```

   后续仅将这个文件传到服务器 `tunnel-token`，保持权限 `600`；不要整体同步 `.local/`。

3. 在隧道的 Published application route / Public Hostname 中配置：

   | 字段 | 值 |
   | --- | --- |
   | 子域名 | `coder` |
   | 域名 | 实际购买并已 Active 的域名 |
   | Path | 留空，覆盖 Coder 全站 |
   | Service 类型 | HTTP |
   | Service URL | `127.0.0.1:17080` |

   控制台通常自动创建对应隧道的 DNS 记录。原型沿用 Coder 自身账号认证；不额外套 Cloudflare Access 登录页，以免拦截 API、agent 或 WebSocket。仅连接本机回环 Coder，不添加服务器网段、SSH、数据库或 Docker API 路由。用户到 Cloudflare 使用 HTTPS，Cloudflare 到接入组件使用加密隧道，组件到 Coder 是本机回环 HTTP。

4. 域名、流量范围和凭据就绪后，在服务器项目目录执行 `sh scripts/setup_coder_cloudflare.sh --start`。核对控制台 Healthy、连接日志及回环健康检查；进程 active 本身不等于隧道可用。
5. 私有备份既有服务器 `.env`，只将 `AI4S_PUBLIC_URL` 改为真实 `https://coder.你的域名`。复用 [HTTPS 覆盖配置](../compose.funnel.yaml)：文件名为兼容现有部署保留，对 Cloudflare 同样适用。仅重建控制面：

   ```bash
   export DOCKER_HOST=unix:///data1/qhy/docker-ai4s/run/docker.sock
   docker compose -f compose.yaml -f compose.server.yaml -f compose.funnel.yaml up -d --no-deps coder
   ```

6. 从不依赖 Tailscale 的成员网络验证 DNS、证书、成员登录、本人工作区和跨成员拒绝、网页终端执行命令及断线重连。核对数据库及成员容器身份、代码卷保持不变，再分发新网址并更新本地私有成员凭据文件中的 URL。Cloudflare 支持 [WebSocket](https://developers.cloudflare.com/network/websockets/)，仍需真实 Coder 测试，不能以登录页 200 代替验收。
7. 新入口验收通过后，按 [服务器说明](server_docker.md#免成员隧道的-https-入口) 撤下旧 Funnel 公网路由；保留恢复所需状态。当前未执行该切换。

## 日常检查与回退

```bash
systemctl --user status ai4s-cloudflared.service
journalctl --user -u ai4s-cloudflared.service -n 30 --no-pager
tail -n 30 /data1/qhy/cloudflared-ai4s/logs/cloudflared.log
curl -fsS http://127.0.0.1:20241/ready
curl -fsS http://127.0.0.1:17080/healthz
```

诊断日志仅保存在服务器，不公开 Token、Cookie 或认证头；日常不启用 debug。指标 `/ready` 只表示连接状态，仍需公网业务验证。

若新入口失败，先恢复备份中的 `AI4S_PUBLIC_URL` 并仅重建 Coder 控制面；若旧 Funnel 已撤下，再恢复其路由。随后 `systemctl --user disable --now ai4s-cloudflared.service` 停止新接入组件，必要时在 Cloudflare 停用本项目 hostname 路由。旧入口本身存在网络限制，因此回退只是恢复原配置，不代表修复旧入口。不得删除数据库、个人卷或重建成员工作区来处理入口问题。

相关文档：[服务器说明](server_docker.md) · [环境](environment.md) · [成员操作](members.md) · [状态](status.md)。
