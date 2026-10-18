# 阿里云 Coder HTTPS 中转

当前入口为 `https://coder.my-rustdesk.xyz`，旧 Funnel 路由已撤下；实际验收结果见 [状态](status.md)。用户已确认根域名完成备案，使用范围为成员个人开发；该信息为用户确认，不冒充平台备案审查结果。

## 访问路径与配置职责

```text
成员浏览器 → coder.my-rustdesk.xyz:443 → 阿里云 Nginx
  → 云服务器 127.0.0.1:27080 → 常驻 SSH 反向转发
  → lab-gpu 127.0.0.1:17080 → Docker 中的 Coder
```

成员无需 SSH、Tailscale 或 Cloudflare 客户端，仍使用个人 Coder 邮箱和密码。账号和代码隔离见 [成员说明](members.md)，分支与合并规则见 [协作约定](collaboration.md)。

| 配置 | 维护内容 |
| --- | --- |
| 阿里云 DNS | `coder` 的 A 记录为 `47.109.63.27`，TTL 600 秒；根域名记录保留 |
| [Nginx 虚拟主机](../configs/nginx-coder.conf) | 独立子域名、HTTPS、ACME 路径、WebSocket 转发；原网站虚拟主机不改动 |
| [中转账号 SSH 限制](../configs/ai4s-tunnel-sshd.conf) | 仅允许 `ai4s-tunnel` 远程转发到云服务器回环端口 27080，禁止会话及其他转发方式 |
| [常驻通道服务](../configs/ai4s-coder-relay.service) | 在科研服务器由 `qhy` 运行，固定中转机主机公钥，掉线自动重连 |
| [证书续期钩子](../configs/ai4s-certbot-reload.sh) | 新证书续期后校验并平滑 reload Nginx |
| [共用 HTTPS 覆盖配置](../compose.funnel.yaml) | Coder 对外 URL、Secure Cookie、DERP WebSocket；文件名为兼容既有部署保留 |

## 两端位置

云服务器仅作接入中转，不承载模型计算：`ssh root@47.109.63.27`，阿里云成都 `cn-chengdu`，Ubuntu 26.04。管理权限只用于本次已授权配置，科研服务器不保存该机 root 凭据。

- 专用账号：`ai4s-tunnel`，home 为 `/var/lib/ai4s-tunnel`，shell 为 `nologin`。其 `.ssh/authorized_keys` 还限制 `permitlisten="127.0.0.1:27080"`。
- SSH 限制：`/etc/ssh/sshd_config.d/60-ai4s-tunnel.conf`。
- Nginx 配置：`/etc/nginx/sites-available/coder.my-rustdesk.xyz`，经 `sites-enabled` 中同名链接启用。
- ACME webroot：`/var/lib/ai4s-coder/acme`；它及父目录须允许 Nginx 遍历，使用 `755`。仅存放公开挑战文件，不存凭据。
- 证书：`/etc/letsencrypt/live/coder.my-rustdesk.xyz/`；沿用既有 `certbot.timer`，部署钩子为 `/etc/letsencrypt/renewal-hooks/deploy/ai4s-coder-reload`。私钥只留云服务器。
- 中转配置准备副本：`/opt/ai4s-coder/preparation`；Nginx 的 ACME 初始配置备份为 `/opt/ai4s-coder/nginx-http.before`。

科研服务器仍为 `ssh lab-gpu`，项目和 Docker 位置见 [环境说明](environment.md)。

- 通道密钥与已核验主机公钥：`/data1/qhy/coder-relay/`，目录 `700`、私钥 `600`；新建独立密钥，私钥不出科研服务器。主机公钥通过已认证的云服务器 SSH 会话取得。
- 用户服务：`~/.config/systemd/user/ai4s-coder-relay.service`，归入 `ai4s.slice`，自身上限 0.25 核、128 MiB；使用现有 linger，无新增系统级服务。
- Coder 切换前私有配置：项目副本 `.local/aliyun-relay/env.before`。切换只修改 `.env` 中 `AI4S_PUBLIC_URL`，然后 `up -d --no-deps coder`，不重建工作区和数据库。

## 复现与检查

部署前确认两端目标文件不存在或与仓库一致，已有不同配置先核对，不整份覆盖 Nginx、SSH 或 `.env`。专用账号和公钥按上述限制配置后，执行 `sshd -t`，平滑 reload SSH；安装科研服务器用户服务后执行 `systemd-analyze --user verify`、`daemon-reload` 和 `enable --now ai4s-coder-relay.service`。

首次证书签发先建立仅含 HTTP ACME location 的独立虚拟主机，确认公网挑战文件可读，再执行：

```bash
# 云服务器
certbot certonly --non-interactive --webroot -w /var/lib/ai4s-coder/acme \
  --cert-name coder.my-rustdesk.xyz -d coder.my-rustdesk.xyz --keep-until-expiring
```

证书存在后才安装完整 Nginx 配置，执行 `nginx -t && systemctl reload nginx`；不停止原网站。证书首次到期时间及实测结果保存在私有验收记录中，以实际续期结果为准。

```bash
# 云服务器：端口应只监听回环；两个健康检查均应成功
ss -lnt | grep 27080
curl -fsS http://127.0.0.1:27080/healthz
nginx -t
systemctl status certbot.timer

# 科研服务器：显式进入项目目录
cd /data1/qhy/projects/ai4s-workbench/repo
systemctl --user status ai4s-coder-relay.service
journalctl --user -u ai4s-coder-relay.service -n 30 --no-pager
curl -fsS http://127.0.0.1:17080/healthz
```

公网验收须包括真实证书、四人登录、Secure Cookie、本人工作区、跨成员拒绝及 WebSocket PTY 执行个人分支查询；登录页 200 或 SSH 服务 active 都不等于完整通过。Nginx 接入日志为 `/var/log/nginx/ai4s-coder-access.log`，仅记路径不记查询参数；错误日志同目录 `ai4s-coder-error.log`。私有基线和验收证据在本地 `.local/remote/aliyun/`，不进 Git。

## 回退

先将科研服务器 `.env` 的 `AI4S_PUBLIC_URL` 恢复为备份值，仅重建 Coder 控制面。若旧 Funnel 路由已撤下，可按 [原入口步骤](server_docker.md#免成员隧道的-https-入口) 恢复，但其既有公网稳定性限制仍在。

需撤下本项目新入口时，移除本项目 Nginx 启用链接，`nginx -t` 后平滑 reload，再停止科研服务器 `ai4s-coder-relay.service`。不删除原网站配置、数据库、成员卷或 SSH 管理账号。仅停用服务时保留密钥和配置用于恢复。

依据：[Coder Nginx 指南](https://coder.com/docs/tutorials/reverse-proxy-nginx) · [OpenSSH 转发](https://man.openbsd.org/ssh#R)。返回：[服务器运行说明](server_docker.md) · [状态](status.md) · [Cloudflare 备用方案](cloudflare_tunnel.md)。
