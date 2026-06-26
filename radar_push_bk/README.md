# radar_push — 雷达实况+外推 → 企业微信自动推送

独立的后台守护服务（与 fengche / OpenWebUI 完全解耦）。定时扫描雷达组合反射率
实况 nc，检测苏州市外 50km 缓冲区内的强回波块，结合外推产品推断未来 1 小时的
移动方向 / 受影响区县乡镇 / 强度等级，按预设话术生成文本 + 实况图，去重后推送到
企业微信群机器人。

## 工作流程

```
每 60s 扫描
  └─ 找最新实况 Cr (Mosaic{UTC时间戳}_Cr.nc)
       └─ 缓冲区内强回波块检测 (>=35dBZ 且四连通>=4格点)
            └─ 命中 → 读同名 TreRef (单文件 21 帧，取未来 1h 的 tick1~10)
                 └─ 外推: 方向 / 影响区县乡镇 / 强度极值 / 增强减弱 / 是否入市
                      └─ 去重判定 (首次/升级/跨边界25-10-5km-入市/>=45持续/新区县)
                           └─ 命中 → 渲染实况图 + 拼文本 → 企业微信推送
```

## 目录结构

```
radar_push/
├── app/
│   ├── config.py          配置（SFTP / 阈值 / webhook）
│   ├── datasource.py      SFTP（生产）+ 本地（测试）数据源
│   ├── radar_finder.py    定位最新 Cr 与同名 TreRef
│   ├── nc_reader.py       解析 data/lat/lon/tss，屏蔽缺测(-32768/-128)
│   ├── geo.py             加载 geojson，生成网格掩膜 + 到市界距离
│   ├── echo_detect.py     强回波块检测（scipy 连通域）
│   ├── extrapolation.py   外推方向/影响/强度/趋势
│   ├── templates.py       推送话术文本
│   ├── plotter.py         渲染实况图 PNG
│   ├── notifier.py        企业微信群机器人 webhook
│   ├── dedup.py           去重状态机（state/dedup_state.json）
│   └── main.py            调度循环 + /health (FastAPI)
├── data/                  预生成 geojson（市界/缓冲区/区县/乡镇）
├── scripts/build_geojson.py  从 shp 离线生成 data/*.geojson
├── deploy/                docker-compose.yml + .env.example
├── Dockerfile
├── requirements.txt       运行时依赖（无 geopandas/GDAL）
└── requirements-build.txt 离线生成 geojson 用
```

## 部署

```bash
cd radar_push/deploy
cp .env.example .env
# 编辑 .env：填 SFTP_PASSWORD 和 WECOM_WEBHOOK_URL
docker compose --env-file .env up -d --build
```

健康检查：`curl http://<宿主IP>:8770/health`

## 重新生成边界 geojson（仅当 shp 变化时）

需要 geopandas/GDAL 环境（如 conda）：

```bash
pip install -r requirements-build.txt
python scripts/build_geojson.py
```

源 shp 路径可用环境变量覆盖：`COUNTY_SHP` / `TOWNSHIP_SHP` / `RADAR_SHP_BASE`。

## 关键数据结构（实测）

- 文件名 `Mosaic{YYYYMMDDHHMMSS}_Cr.nc` / `_TreRef.nc`，时间戳为 UTC。
- 反射率变量 `data`：Cr 为 `(layer,lat,lon)` 取 `data[0]`；
  TreRef 为 `(tss=21,layer,lat,lon)` 单文件含 21 帧（6min/帧，tick 0~120min）。
- 网格 1000×1250、约 0.005°（≈500m）；缺测 `-32768`(超范围)/`-128`(无回波)。

## 待补充 / 已知简化

- 实况产品（≥20mm/h 短时强降水、≥7级雷暴大风）占位符暂未拼入文本（按文档要求）。
- 去重轨迹按"接近轨迹 + 各区县"建模，未做多回波团的独立 ID 追踪。
- 上游/局地来源判定按"当前市内是否已有强回波"近似。
