# Fengche Warning Tool Server

苏州市气象**强对流 / 暴雨预警粗筛**工具，作为 苏州市气象预报智能助手 的 Tool Server 运行，**覆盖苏州市下属全部 10 个区/县级市**：姑苏区、虎丘区（高新区）、吴中区、相城区、吴江区、苏州工业园区、常熟市、张家港市、昆山市、太仓市。

基于风掣 AI 模型未来 24 小时预报数据（按整点逐小时起报），对每个区做格点阈值判定 + 时段合并，并**自动拼装标准预报用语与官方防御指南**，供苏州市气象台预报员人工研判时参考。

> **触发规则**：只要区内**任意一个**格点达到某等级阈值，即提示该区可能需要发布对应级别的预警信号——纯提示性质，是否真正发布以预报员研判为准。

> 仅做粗筛，不替代预报员判断。强对流定级仅基于阵风阈值，未结合雷电监测，可能将"大风过程"误标为"强对流"。最终是否发布**预警信号**以预报员研判为准。

---

## 功能

- 数据源复用 `fengche_tool_server` 的本地/FTP 双模式（`DATA_SOURCE=local|ftp`）。
- 风掣 AI 按整点逐小时起报，每份文件覆盖未来 24 小时；本工具自动检索最近一份就绪文件。
- 覆盖**苏州全部 10 个区/县级市**，行政边界来自离线 shp（`shp/县.shp`，WGS84 区县级），通过 `scripts/build_geojson_from_shp.py` 一次性生成 `data/districts.geojson`，运行时不依赖任何外部 API。
- 每个区逐小时**任意格点触发**：区内只要有 1 个格点 ≥ 某等级阈值即定级；从高级别向低级别测试，取首个达标的最高级。响应里附 `hit_points` / `hit_ratio` 供人工复核参考。
- 强对流（黄/橙/红）按阵风 8/10/12 级阈值粗筛；冰雹、龙卷、雷电不参与定级，仅以 `note` 字段提醒人工复核。
- 暴雨（蓝/黄/橙/红）按国标 **1h / 6h / 24h 三窗口 OR 触发**：
  - 蓝色：6h ≥ 50
  - 黄色：1h ≥ 50 或 6h ≥ 100 或 24h ≥ 150
  - 橙色：1h ≥ 75 或 6h ≥ 150 或 24h ≥ 200
  - 红色：1h ≥ 100 或 6h ≥ 200 或 24h ≥ 250
  - 每段附 `triggered_by`（`1h`/`6h`/`24h`）指明主触发窗口；rain_6h 在第 1~5 小时、rain_24h 在第 1~23 小时数据不足，对应窗口在前期不参与判定。
- 连续同级小时自动合并为时段（如 `6月5日 18时至20时`），含 `hour_metrics` 逐小时明细。
- 每个达标时段自动生成 `advisory.forecast_text`（已填好时段、区名、起报时间溯源）与 `advisory.defense_guide`（官方防御指南条目数组）。
- 中文 `summary` 一次性输出全部 10 区评估，首行带起报时间。

## 区代码（`districts` 参数取值）

| code | 名称 | adcode |
|---|---|---|
| `gusu` | 姑苏区 | 320508 |
| `huqiu`（兼容历史 `gaoxin`） | 虎丘区（高新区） | 320505 |
| `wuzhong` | 吴中区 | 320506 |
| `xiangcheng` | 相城区 | 320507 |
| `wujiang` | 吴江区 | 320509 |
| `sip` | 苏州工业园区 | 320571 |
| `changshu` | 常熟市 | 320581 |
| `zhangjiagang` | 张家港市 | 320582 |
| `kunshan` | 昆山市 | 320583 |
| `taicang` | 太仓市 | 320585 |

## 接口

### `POST /fengche_warning` / `GET /fengche_warning`

请求体（POST）：

```json
{
  "districts": ["gusu", "huqiu", "sip", "kunshan"],
  "request_time_iso": "2026-06-05T13:00:00+08:00"
}
```

所有字段都可省略，省略 `districts` 时评估全部 10 个区。GET 形式用同名 query 参数（`districts` 用逗号分隔），便于浏览器测试：

```
GET /fengche_warning?districts=gusu,huqiu,sip
```

> 历史版本支持的 `gs_coverage_ratio` / `rain_coverage_ratio` 覆盖率门槛参数已弃用：
> 现版本统一按"任意格点达标即提示"，传入会被忽略，但为兼容旧客户端仍可传入。

### 成功响应（节选）

```json
{
  "query": {
    "request_time": "2026-06-05T13:00:00+08:00",
    "trigger_mode": "any_point_hit",
    "trigger_mode_desc": "区内任意格点达到阈值即提示发布对应级别预警信号",
    "districts": ["gusu", "huqiu", "wuzhong", "xiangcheng", "wujiang",
                  "sip", "changshu", "zhangjiagang", "kunshan", "taicang"]
  },
  "forecast_source": {
    "issue_time": "2026-06-05T13:00:00+08:00",
    "file_uri": "file:///.../20260605/20260605T13.nc",
    "fallback_steps_back": 0,
    "data_source_kind": "local"
  },
  "coverage": { "lat": [30.7, 32.2], "lon": [119.7, 121.5] },
  "districts": {
    "huqiu": {
      "name": "虎丘区（高新区）",
      "grid_points_in_district": 1120,
      "boundary_source": "shp_china_county",
      "strong_convection": {
        "segments": [
          {
            "level": "orange",
            "level_label": "强对流橙色预警",
            "start_time": "2026-06-05T18:00:00+08:00",
            "end_time":   "2026-06-05T19:00:00+08:00",
            "triggered_by": null,
            "hour_metrics": [
              { "valid_time": "...T18:00...", "max_gs_ms": 25.0, "hit_points": 3, "hit_ratio": 0.003, "threshold_ms": 24.5 }
            ],
            "advisory": {
              "forecast_text": "预计6月5日 18时至19时，虎丘区（高新区）将出现10级以上大风，阵风11级以上。（参考：风掣 AI 6月5日 13时 起报）",
              "defense_guide": [
                "停止户外有组织的体育或集会活动，中小学、幼儿园、相关培训机构停止户外活动。",
                "公众避免露天活动，严禁一切室外用火行为。",
                "非必要不出行，车辆和人员不在高大建筑物、广告牌、临时搭建物或大树的下方停留。",
                "停止一切室外施工作业和游乐活动。"
              ]
            }
          }
        ],
        "note": "本判定仅基于阵风阈值，未结合雷达回波/雷电监测，可能将大风过程误标为强对流，需人工核实。"
      },
      "rainstorm": { "segments": [] }
    }
  },
  "summary": "数据来源：风掣 AI 模型，起报时刻 6月5日 13时（北京时间）。\n..."
}
```

### `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "data_source": "local",
  "geojson_path": "...",
  "district_source": "shp_china_county",
  "per_district_source": {
    "huqiu": "shp_china_county", "wuzhong": "shp_china_county",
    "xiangcheng": "shp_china_county", "gusu": "shp_china_county",
    "wujiang": "shp_china_county", "sip": "shp_china_county",
    "changshu": "shp_china_county", "zhangjiagang": "shp_china_county",
    "kunshan": "shp_china_county", "taicang": "shp_china_county"
  },
  "districts_known": ["huqiu", "wuzhong", "xiangcheng", "gusu", "wujiang",
                      "sip", "changshu", "zhangjiagang", "kunshan", "taicang"],
  "trigger_mode": "any_point_hit",
  "trigger_mode_desc": "区内任意格点达到阈值即提示发布对应级别预警信号",
  "thresholds": { "...": "..." }
}
```

`district_source` 为 `shp_china_county` 表示边界来自 `shp/县.shp`（区县级行政区划，WGS84），由 `scripts/build_geojson_from_shp.py` 一次性生成。

---

## 本地运行（开发/测试）

推荐用 `leadsee-webui` conda 环境（已装好 `netCDF4`、`shapely`）：

```bash
conda activate leadsee-webui
cd fengche/warning_server
cp .env.example .env

pip install fastapi==0.115.5 "uvicorn[standard]==0.32.1" python-dotenv==1.0.1 pydantic==2.10.3 shapely

# 启动（在仓库根目录跑，LOCAL_BASE_DIR=./fengche/data_samples 默认相对当前目录）
cd ../..
# 容器内 import 路径仍是 fengche_tool_server / fengche_warning_server。本地开发期同名 package 需要 PYTHONPATH：
PYTHONPATH=fengche/tool_server:fengche/warning_server python -m uvicorn app.main:app --host 0.0.0.0 --port 8766
```

冒烟测试（绕开 uvicorn，直接调业务函数）：

```bash
PYTHONPATH=fengche/tool_server:fengche/warning_server python -m scripts.smoke_test
```

可以临时降低阈值来验证管线（先设环境变量再跑）：

```powershell
$env:GS_YELLOW_MS = "10.0"; $env:GS_ORANGE_MS = "13.0"; $env:GS_RED_MS = "16.0"
$env:PYTHONPATH = "fengche/tool_server;fengche/warning_server"
python -m scripts.smoke_test
```

---

## 行政边界数据（`data/districts.geojson`）

仓库自带的 `data/districts.geojson` 由 `scripts/build_geojson_from_shp.py` 从离线 shp（`fengche/shp_raw/县.shp`，区县级，WGS84）一次性抽取生成，已经包含苏州市下属全部 10 个区/县级市的精确多边形（含苏州工业园区，adcode 320571）。

如果 shp 数据更新或路径变化，重新生成：

```bash
# 在 fengche/warning_server/ 目录下
python -m scripts.build_geojson_from_shp
```

可选环境变量：

- `COUNTY_SHP_PATH`：shp 路径，默认 `fengche/shp_raw/县.shp`
- `SHP_ENCODING`：dbf 编码，默认 `gbk`

脚本依赖纯 Python 的 `pyshp`（`pip install pyshp`），**不需要 GDAL/geopandas**。
运行时（FastAPI 服务）只读 `data/districts.geojson`，不依赖 shp 文件本身，因此 Docker 镜像里不需要带 shp。

> 旧的 `scripts/fetch_districts.py` 是基于高德 District API 的版本，仅覆盖 3 个属地区，已被标记为废弃。
> 服务启动时通过 `_source` 字段识别边界来源（新版会显示 `shp_china_county`）。

---

## Docker 部署

推荐使用统一的部署 stack（包含 forecast + warning 两个服务），见 [`fengche/deploy/DEPLOY.md`](../deploy/DEPLOY.md)，里面有完整的打包/上传/起服务流程。

如果只想单独起 warning 服务：

```bash
cd fengche/deploy
docker compose up -d --build fengche-warning
docker compose logs -f fengche-warning
```

在 Open WebUI 管理员页 → Settings → Tools → Add Tool Server，URL 填：
- 同 docker network：`http://fengche-warning:8766/openapi.json`
- 跨主机或调试：`http://<宿主IP>:8766/openapi.json`

命名「苏州市气象预警粗筛」，保存。

---

## 在 Open WebUI 中使用

聊天框里仅勾选「苏州市气象预警粗筛」即可。**不需要再勾「高德地图 MCP」**——本工具完全不依赖坐标输入。

典型对话：

> 用户：今天会不会有预警？
>
> 模型：调用 `/fengche_warning` → 把每个达标 segment 的 `advisory.forecast_text` 与 `advisory.defense_guide` 复述给用户，并把 `summary` 首行的起报时间一并报出来。

---

## 调参建议

当前判定规则是「区内任意格点达到阈值即触发」（提示性质），不再使用覆盖率门槛，因此调参只剩阈值本身：

| 现象 | 调什么 |
|---|---|
| 觉得阵风偏强（模式系统性偏大），报得太多 | 调高 `GS_YELLOW_MS` / `GS_ORANGE_MS` / `GS_RED_MS` |
| 觉得阵风偏弱，漏报 | 调低对应的阵风阈值 |
| 降水报得太多 / 太少 | 调整 `RAIN_1H_*` / `RAIN_6H_*` / `RAIN_24H_*` |

所有阈值参数都从环境变量读，**不需要改代码**。

> 历史的 `GS_MIN_COVERAGE_RATIO` / `RAIN_MIN_COVERAGE_RATIO` 已彻底移除，旧 `.env` 中若残留这两行不会报错（被自动忽略）。

---

## 已知约束

- **强对流不结合雷电**：可能把大风过程误标为强对流，每段都带 `note` 字段提醒；最终发布以预报员研判为准。
- **滚动窗口前期数据不足**：rain_6h 在未来第 1~5 小时、rain_24h 在未来第 1~23 小时数据不足，前期对应窗口不参与判定（仅由已就绪窗口触发）。
- **覆盖范围边界外行政区**：风掣预报覆盖约 30.7~32.2°N、119.7~121.5°E；常熟、张家港、太仓的最北端，少量格点可能落在覆盖范围之外（这些点不参与判定，区内剩余格点正常评估）。
- **苏州工业园区行政归属特殊**：苏州工业园区不是一级行政区，shp 中 adcode=320571，区划上仍属吴中区，本工具按 shp 中独立多边形单独评估。

---

## 数据结构说明

每个 `.nc` 文件结构与 `fengche_tool_server` 一致：

- 维度：`time=1`（起报时刻）、`step=24`（预报时效，1~24 小时）、`lat=151`、`lon=181`
- 起报频率：整点逐小时（每小时一份新文件）
- 关键变量：
  - `gs`（阵风, m/s）— 强对流判级用
  - `tp`（**逐小时降水**, mm；经实测验证非累积量）— 暴雨判级用

路径模板与 `fengche_tool_server` 共用 `PATH_TEMPLATE` 环境变量。
