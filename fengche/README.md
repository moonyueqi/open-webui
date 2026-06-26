# fengche 子项目

苏州市气象局"风掣"短临预报系统的 OpenWebUI 工具侧实现。集中放在这个目录下，便于和 OpenWebUI 主程序源码隔离。

## 目录结构

```
fengche/
├── README.md               ← 本文件（顶层导读）
├── deploy/                 ← 部署套件（生产）
│   ├── docker-compose.yml
│   ├── .env.example
│   └── DEPLOY.md            完整的 Linux Docker 部署手册
├── tool_server/            ← 服务1：fengche-forecast（8765）
│   ├── app/                 业务代码（FastAPI）
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example         单服务本地开发用
│   └── README.md
├── warning_server/         ← 服务2：fengche-warning（8766）
│   ├── app/                 业务代码（FastAPI）
│   ├── data/                运行时只读：districts.geojson
│   ├── scripts/             离线脚本（build_geojson、smoke_test 等）
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── data_samples/           ← 本地 NetCDF 调试数据（不入库）
│   ├── 20260507/
│   ├── 20260508/
│   ├── 20260509/
│   └── 20260605/
└── shp_raw/                ← 地理底图原料（不入库，仅 build_geojson 时使用）
    ├── 县.shp / .dbf / .prj / ...
    └── ...
```

## 服务关系

```
                      ┌────────────────────────┐
                      │  OpenWebUI（主程序）    │
                      │  port 3000             │
                      └─────────┬──────────────┘
                                │  HTTP (OpenAPI)
              ┌─────────────────┴─────────────────┐
              │                                   │
              ▼                                   ▼
   ┌────────────────────┐              ┌──────────────────────┐
   │  fengche-forecast  │              │  fengche-warning     │
   │  port 8765         │              │  port 8766           │
   │  按经纬度查 24h    │              │  扫所有区，按阈值粗筛 │
   └────────┬───────────┘              └──────────┬───────────┘
            │                                     │
            │ FTP / 本地                          │ FTP / 本地
            ▼                                     ▼
   ┌────────────────────────────────────────────────────────┐
   │  风掣 NetCDF（FTP 10.127.13.197:2123 或 data_samples/）│
   └────────────────────────────────────────────────────────┘
```

> warning_server 依赖 tool_server 的 `datasource` / `forecast_finder`（共享 FTP/本地读取层），所以两个服务必须同时构建。

## 快速开始

### 本地开发

```bash
conda activate leadsee-webui
cd fengche/tool_server && cp .env.example .env       # 默认 DATA_SOURCE=local
cd ../warning_server   && cp .env.example .env
```

启动方式见各 server 的 `README.md`。

### 生产部署（Linux Docker）

完整流程见 [`deploy/DEPLOY.md`](deploy/DEPLOY.md)。简要：

```powershell
# 本地（仓库根目录）打包
powershell -ExecutionPolicy Bypass -File scripts\pack_fengche.ps1
# 输出：dist\fengche_deploy_<时间戳>.zip（~0.2 MB）
```

```bash
# 服务器
unzip fengche_deploy_*.zip
cd fengche_deploy
cp .env.fengche.example .env.fengche && vi .env.fengche   # 填 FTP 密码
docker compose -f docker-compose.fengche.yml --env-file .env.fengche up -d --build
```

## 重要约定

1. **容器内 import 路径保持 `fengche_tool_server` / `fengche_warning_server`**（带下划线前缀）。源码里的 `from fengche_tool_server.app... import ...` 是有意保留的，不要为了迁移而改 import；Dockerfile 在 COPY 时把 `tool_server/app` 重命名成 `/app/fengche_tool_server/app` 来对齐这一约定。
2. **`data_samples/` 与 `shp_raw/` 都不入 git**，但本地保留可用于 `DATA_SOURCE=local` 调试以及重新生成 `warning_server/data/districts.geojson`。
3. **打包后的 zip 内部保持老的命名**（`fengche_tool_server/`、`docker-compose.fengche.yml`、`.env.fengche.example`、`DEPLOY_FENGCHE.md`），这样服务器端历史命令完全不变。

## 阈值参考（warning_server）

| 等级 | 阵风 m/s | 1h 雨量 mm | 6h 雨量 mm | 24h 雨量 mm |
|------|---------|------------|------------|-------------|
| 蓝色 | —       | —          | ≥ 50       | —           |
| 黄色 | ≥ 17.2  | ≥ 50       | ≥ 100      | ≥ 150       |
| 橙色 | ≥ 24.5  | ≥ 75       | ≥ 150      | ≥ 200       |
| 红色 | ≥ 32.7  | ≥ 100      | ≥ 200      | ≥ 250       |

均按国标默认值，可在 `.env`（开发）或 `.env.fengche`（部署）覆盖。
