# 风掣两个工具部署手册（Linux Docker）

把 `fengche-forecast`（预报查询）+ `fengche-warning`（苏州市气象预警粗筛）作为一个独立的
Docker stack 部署到已经在跑 OpenWebUI 的 Linux 服务器上，**不影响现有的 OpenWebUI 容器**。

> 服务器：Linux + Docker；本地打包：Windows PowerShell。
> OpenWebUI 已经在跑（之前用离线 tar 起的），这次部署**只新增两个 sidecar 容器，不动 OWUI**。

> 仓库内源码位置（开发期参考）：`fengche/tool_server/`、`fengche/warning_server/`、本部署目录 `fengche/deploy/`。
> 服务器端解压后 zip 内部仍叫 `fengche_deploy/{docker-compose.fengche.yml, .env.fengche.example, fengche_tool_server/, fengche_warning_server/}`——下面命令完全按 zip 内布局来。

---

## 0. 前提

服务器上需要：

- Linux + Docker Engine ≥ 20.10（`docker --version`）
- Docker Compose v2（`docker compose version` 能输出版本号；老的 `docker-compose` 命令不支持下面的命令格式）
- 服务器**能联网**访问 docker hub / pip 清华源（Dockerfile 已经把 apt 与 pip 都换成清华源；如果连清华源也不通，请改用公司内部镜像或离线方案，见 §9）
- 防火墙开放 **8765 / 8766** 两个端口（OpenWebUI 容器要通过宿主机回调访问）
- 风掣 FTP 服务器可达，并已拿到 FTP 账号密码

---

## 1. 本地打包（Windows）

在仓库根目录（PowerShell）执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pack_fengche.ps1
```

输出在 `dist\fengche_deploy_<时间戳>.zip`，约 0.2 MB。

---

## 2. 上传 + 解压（Linux）

把 zip 上传到服务器任意目录，例如 `/opt/fengche/`：

```bash
mkdir -p /opt/fengche
cd /opt/fengche
unzip fengche_deploy_<时间戳>.zip
cd fengche_deploy
ls
# DEPLOY_FENGCHE.md  docker-compose.fengche.yml  .env.fengche.example
# fengche_tool_server/   fengche_warning_server/
```

> 如果 `unzip` 没装：`apt-get install unzip -y`（Debian/Ubuntu）或 `yum install -y unzip`（RHEL/CentOS）。

---

## 3. 配置 FTP 账号

```bash
cp .env.fengche.example .env.fengche
vi .env.fengche
```

主要要填的就是这几行：

```env
DATA_SOURCE=ftp
FTP_HOST=10.127.13.197
FTP_PORT=2123
FTP_USER=fengche
FTP_PASSWORD=填写实际密码
FTP_BASE_DIR=/
```

阈值（强对流阵风、暴雨 1h/6h/24h）、覆盖率门槛、时区都按苏州气象局国标默认值填好，**通常不用动**。

---

## 4. 起服务

```bash
cd /opt/fengche/fengche_deploy
docker compose -f docker-compose.fengche.yml --env-file .env.fengche up -d --build
```

第一次 build 会拉 `python:3.11-slim`、装 `libnetcdf-dev / libhdf5-dev / libgeos-dev` 与 Python 依赖（FastAPI / netCDF4 / shapely 等），大约 3~8 分钟。

完成后查看状态：

```bash
docker compose -f docker-compose.fengche.yml ps
docker compose -f docker-compose.fengche.yml logs -f
```

正常应能看到两个容器 `fengche-forecast` / `fengche-warning` 都是 `Up (healthy)`。

---

## 5. 防火墙开端口

确保 OpenWebUI 容器能从内部回调访问宿主机的 8765/8766。

**firewalld（RHEL / CentOS / Rocky）：**

```bash
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --permanent --add-port=8766/tcp
sudo firewall-cmd --reload
```

**ufw（Ubuntu）：**

```bash
sudo ufw allow 8765/tcp
sudo ufw allow 8766/tcp
sudo ufw reload
```

**iptables（手动）：**

```bash
sudo iptables -I INPUT -p tcp --dport 8765 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8766 -j ACCEPT
```

> 仅对内网开即可，对外网（公网 IP）无需开放。

---

## 6. 健康检查

服务器本地：

```bash
curl http://localhost:8765/health
curl http://localhost:8766/health
```

两个都应返回 `{"status":"ok",...}`。

从其它机器或 OpenWebUI 容器内访问，把 `localhost` 换成宿主机的内网 IP：

```bash
curl http://<宿主机内网IP>:8765/health
curl http://<宿主机内网IP>:8766/health
```

---

## 7. 在 OpenWebUI 接入

OpenWebUI 不需要重启、不需要改它的 compose / tar 镜像。

打开 OWUI 管理员界面：

> Admin Settings → Settings → Tools → **+ Add Tool Server**

依次添加两个：

| 名称（自定） | OpenAPI URL |
|---|---|
| 风掣预报查询 | `http://<宿主机内网IP>:8765/openapi.json` |
| 苏州市气象预警粗筛 | `http://<宿主机内网IP>:8766/openapi.json` |

> **不要写 `http://localhost:8765/...`**——OWUI 容器里的 `localhost` 是它自己。
> 必须用宿主机的内网 IP，或者 docker bridge 网关 IP（一般是 `172.17.0.1`）。

保存后两个 Tool Server 列表里会出现端点；聊天框底部「工具」勾选后即可触发调用。

---

## 8. 升级（替换代码后重 build）

仓库代码有更新时，本地重新打包：

```powershell
# Windows 本地
powershell -ExecutionPolicy Bypass -File scripts\pack_fengche.ps1
```

把新 zip 传到服务器后：

```bash
cd /opt/fengche

# 备份旧目录（含已经填好密码的 .env.fengche）
mv fengche_deploy fengche_deploy.bak.$(date +%Y%m%d_%H%M%S)

unzip fengche_deploy_<新时间戳>.zip
cd fengche_deploy

# 把上次的 .env.fengche 复制过来，避免重新填密码
cp ../fengche_deploy.bak.*/.env.fengche . 2>/dev/null || cp .env.fengche.example .env.fengche

docker compose -f docker-compose.fengche.yml --env-file .env.fengche up -d --build
```

只改 `.env.fengche` 里的阈值或密码、不需要重 build：

```bash
docker compose -f docker-compose.fengche.yml --env-file .env.fengche restart
```

---

## 9. 离线 / 内网环境（清华源也不通）

如果服务器连清华源都不通：

**方案 A：换公司内部镜像源**

编辑两个 Dockerfile：

```bash
sed -i 's|mirrors.tuna.tsinghua.edu.cn|你的内部apt镜像主机|g' fengche_tool_server/Dockerfile fengche_warning_server/Dockerfile
sed -i 's|https://pypi.tuna.tsinghua.edu.cn/simple|https://你的内部pypi/simple|g' fengche_tool_server/Dockerfile fengche_warning_server/Dockerfile
```

然后重 build。

**方案 B：在能联网的机器上 build 完镜像后导出 tar，离线传上去**

能联网的 Linux 机器上：

```bash
docker compose -f docker-compose.fengche.yml --env-file .env.fengche build
docker save fengche-forecast:latest fengche-warning:latest -o fengche_images.tar
```

把 `fengche_images.tar` + 整个 `fengche_deploy/` 目录传到目标服务器：

```bash
docker load -i fengche_images.tar
cd /opt/fengche/fengche_deploy
# 不再 --build，直接用 image 启动
docker compose -f docker-compose.fengche.yml --env-file .env.fengche up -d
```

> 注意：`docker-compose.fengche.yml` 里的 `build:` 段在 image 已经存在时会被跳过，不重新构建。

---

## 10. 卸载

```bash
cd /opt/fengche/fengche_deploy
docker compose -f docker-compose.fengche.yml --env-file .env.fengche down
docker image rm fengche-forecast:latest fengche-warning:latest
```

---

## 11. 常见问题

| 现象 | 处理 |
|---|---|
| `docker compose` 报 `unknown command` | 老版本 Docker，没有 v2 compose 插件。装 `docker-compose-plugin`（Debian/Ubuntu：`apt-get install docker-compose-plugin`）或升级 Docker Engine。 |
| `unzip: cannot find or open ...` | 用错文件名了，`ls` 一下确认；或者没装 unzip：`apt install -y unzip` / `yum install -y unzip`。 |
| build 时 apt 下载卡死 | Dockerfile 已配清华镜像，但服务器仍连不上时，把 Dockerfile 里 `mirrors.tuna.tsinghua.edu.cn` 换成 `mirrors.aliyun.com` 或公司内部镜像。 |
| build 时 pip 卡死 | 同上，`https://pypi.tuna.tsinghua.edu.cn/simple` 换成 `https://mirrors.aliyun.com/pypi/simple/`。 |
| `/health` 返回正常但 OWUI 添加 Tool Server 时超时 | 1) 防火墙没开 8765/8766，参考 §5；2) URL 用了 `localhost`——必须用宿主机内网 IP 或 `172.17.0.1`；3) 容器隔离严重时，让两个新服务进入 OWUI 的 docker network，参考末尾「进阶」。 |
| 容器起来后日志一直报 `FTP RETR failed` 之类 | `.env.fengche` 里 FTP 账号密码或 BASE_DIR 不对；改完执行 `docker compose -f docker-compose.fengche.yml --env-file .env.fengche restart`。 |
| 阈值要调 / 报得太多太少 | 改 `.env.fengche` 里 `GS_YELLOW_MS` / `GS_ORANGE_MS` / `GS_RED_MS` 或 `RAIN_*` 阈值，然后 `restart`，无需重 build。（当前判定按"区内任意格点达标即触发"，不再有覆盖率门槛可调。）|
| 想直接看一次输出长什么样 | 浏览器打开 `http://<宿主IP>:8766/docs`（Swagger UI），点 `/fengche_warning` → Try it out → Execute。 |
| SELinux 报 `permission denied`（很少见） | 我们这套 compose 没挂载宿主机目录，理论上不触发。如果你额外 volume 挂载了路径，给挂载源打 `:Z` 标签，或临时 `setenforce 0` 验证。 |

---

## 进阶：让两个新服务进入 OWUI 的 docker network

默认方案下两个新服务通过宿主机内网 IP + 8765/8766 暴露，OWUI 通过宿主机回调访问，**不动 OWUI**。

如果想让 OWUI 容器直接通过容器名（如 `http://fengche-warning:8766`）访问：

1. 找到 OWUI 用的网络名：

   ```bash
   docker inspect <owui 容器名> --format '{{json .NetworkSettings.Networks}}'
   ```

   假设输出里看到的网络名是 `open-webui_default`。

2. 在 `docker-compose.fengche.yml` 末尾追加：

   ```yaml
   networks:
     default:
       external: true
       name: open-webui_default
   ```

3. 重启：

   ```bash
   docker compose -f docker-compose.fengche.yml --env-file .env.fengche up -d
   ```

4. 在 OWUI 里把 Tool Server URL 改成：

   ```
   http://fengche-forecast:8765/openapi.json
   http://fengche-warning:8766/openapi.json
   ```

> 这种方式下 `ports:` 仍然保留，便于外部调试；如果不想暴露端口，把 `ports:` 那两行注释掉即可。
