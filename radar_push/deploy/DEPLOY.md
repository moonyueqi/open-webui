# radar-push 部署操作手册

部署在一台能访问雷达数据服务器(10.127.13.190:22)、且装了 Docker 的 Linux 服务器上。
数据走 SFTP 远程拉取，推送走企业微信群机器人 Webhook。整个服务与 fengche / OpenWebUI 互不影响。

---

## 一、前置条件（部署机需满足）

1. 已装 Docker 与 Docker Compose 插件
   ```bash
   docker --version
   docker compose version
   ```
2. 能从部署机访问雷达数据服务器的 22 端口（SFTP）
   ```bash
   nc -vz 10.127.13.190 22        # 显示 succeeded 即通
   ```
3. 能访问外网 `qyapi.weixin.qq.com`（企业微信 webhook 走 HTTPS）
   ```bash
   curl -I https://qyapi.weixin.qq.com
   ```
4. 已拿到两样东西：
   - 雷达服务器 SFTP 的 **root 密码**
   - 企业微信群机器人的 **Webhook URL**

---

## 二、上传代码到服务器

把整个 `radar_push/` 目录拷到部署机，例如 `/opt/radar_push/`。

方式 A：用 git（若仓库可达）
```bash
cd /opt
git clone <你的仓库地址>
# 进入仓库内的 radar_push 目录
```

方式 B：用 scp 直接拷本地目录
```bash
# 在本地 Windows（PowerShell）执行，把 radar_push 拷到部署机
scp -r "d:/Dev Project/open-webui-sz/radar_push" user@<部署机IP>:/opt/
```

> 注意：`data/` 下的 geojson 必须一起拷过去（已随源码生成好，运行时直接用）。
> `state/` `data_samples/` `.env` 不需要拷（会在服务器上生成/挂载）。

---

## 三、配置环境变量

```bash
cd /opt/radar_push/deploy
cp .env.example .env
vi .env
```

至少填这两项：
```ini
SFTP_PASSWORD=<雷达服务器root密码>
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<实际key>
```

其余默认值通常不用改（SFTP_HOST/PORT/USER、数据目录、阈值等已按实测填好）。

---

## 四、构建并启动

```bash
cd /opt/radar_push/deploy
docker compose --env-file .env up -d --build
```

首次构建会装依赖+中文字体，约几分钟。完成后容器会常驻后台运行。

---

## 五、验证运行

1. 看健康检查（在部署机本机）
   ```bash
   curl http://localhost:8770/health
   ```
   返回 JSON 里 `webhook_configured: true`、`data_source: "sftp"`、
   `runtime.scans` 在递增，即为正常。

2. 看实时日志
   ```bash
   docker logs -f radar-push
   ```
   - 正常无强对流：会周期性打印 `no strong echo ... in buffer`
   - 有强对流：打印 `PUSH at <时间戳> reasons=[...]` 和生成的文本，
     并向企业微信群发出文字+图片
   - SFTP 连不上 / TreRef 缺失等会有 WARNING/ERROR，据此排查

3. 确认企业微信群收到测试消息
   - 可临时等一次真实强对流，或先用一条手动 curl 测 webhook：
     ```bash
     curl 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=585baafc-c117-41c6-9217-ea71b48a5b2d' \
       -H 'Content-Type: application/json' \
       -d '{"msgtype":"text","text":{"content":"测试消息"}}'
     ```

---

## 六、日常运维

```bash
# 查看状态
docker ps | grep radar-push

# 重启
cd /opt/radar_push/deploy && docker compose restart

# 停止
docker compose down

# 改了 .env 后重新生效
docker compose --env-file .env up -d

# 改了代码后重建
docker compose --env-file .env up -d --build

# 看去重状态（容器重启不丢，挂在宿主机）
cat /opt/radar_push/state/dedup_state.json
```

---

## 七、常见问题

| 现象 | 排查 |
|------|------|
| `/health` 打不开 | `docker logs radar-push` 看启动报错；确认 8770 端口未被占用 |
| 日志报 SFTP 失败 | 核对 `.env` 的 SFTP_PASSWORD；`nc -vz 10.127.13.190 22` 测连通 |
| 找不到 nc 文件 | 确认 `SFTP_NC_BASE_DIR` 正确、当天 `{YYYYMMDD}/Cr/` 下有文件 |
| 企业微信不收消息 | 用上面的 curl 单测 webhook；检查群机器人是否被移除/key 是否失效 |
| 图片发不出 | 日志若报"超过2MB"则需调低 plotter dpi；正常实况图约 160KB 不会触发 |
| 推送太频繁/太少 | 调 `.env` 的阈值（STRONG_DBZ / 里程碑 / REDALERT_DBZ）后重启 |

---

## 八、端口说明

服务在容器内监听 8770，compose 映射到宿主机 8770。
仅用于 `/health` 探活，不对外提供业务接口。如需改端口，改 compose 的 `ports` 和
Dockerfile 的 `EXPOSE`/`CMD` 端口即可（或加 `PORT` 环境变量后同步改 CMD）。
