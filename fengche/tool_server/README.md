# Fengche Forecast Tool Server

风掣（Fengche）AI 天气预报查询的 OpenAPI Tool Server。配合 Open WebUI 的「Tool Server」机制和已配置的高德地图 MCP，让大模型用一句话完成「地名 → 经纬度 → 24 小时逐时预报」。

## 功能

- 暴露 `POST /fengche_forecast` 与 `GET /fengche_forecast`，输入 WGS84 经纬度，返回最近一次起报的未来 24 小时逐 1 小时多要素预报。
- 数据源支持本地路径（`DATA_SOURCE=local`，开发/测试）或风掣 FTP（`DATA_SOURCE=ftp`，生产），通过环境变量切换，业务代码完全相同。
- 风掣按整点逐小时起报；本工具自动从「现在时刻」回退查找最近一份就绪文件（最多 24 小时），跳过尚未生成的整点。
- 对查询点做越界严格检查（覆盖范围仅江苏-上海一带），越界返回结构化提示。
- 自动单位换算：`t2m` 由 K 转 ℃，输出中说明哪些转换被应用。
- 支持 `hours` 参数把返回结果截断到前 N 小时（1~24，默认全 24 小时）。
- 输出含中文摘要文案，模型可直接转给用户。

## 接口

### `POST /fengche_forecast`

请求体：

```json
{
  "lat": 31.2304,
  "lon": 121.4737,
  "location_name": "上海",
  "variables": ["t2m", "ws", "tp"],
  "hours": 24,
  "request_time_iso": "2026-06-05T13:38:00+08:00"
}
```

- `lat` / `lon`：必填。请由上游地理编码工具（如高德 MCP）提供，**不要让模型自己编**。
- `location_name`：可选，仅用于摘要文案。
- `variables`：可选。省略则返回全部 8 个要素：`t2m`（2米气温, ℃，已 K→℃）、`q2m`（2米比湿, kg/kg）、`u10m` / `v10m`（10米 U/V 风, m/s）、`ws`（10米风速, m/s）、`gs`（阵风, m/s）、`cr`（雷达回波, dBZ）、`tp`（逐小时降水, mm；每个时次的当小时降水量）。
- `hours`：可选，1~24。省略则返回全部 24 小时。
- `request_time_iso`：可选，仅用于复现/调试；省略则用服务器当前时间。

### 成功响应（节选）

```json
{
  "query": { "lat": 31.2304, "lon": 121.4737, "location_name": "上海", "request_time": "2026-05-07T15:38:00+08:00" },
  "forecast_source": {
    "issue_time": "2026-06-05T13:00:00+08:00",
    "file_uri": "file:///.../fengche/data_samples/20260605/20260605T13.nc",
    "fallback_steps_back": 0,
    "data_source_kind": "local"
  },
  "grid_point": { "lat": 31.23, "lon": 121.47, "distance_km": 0.45 },
  "coverage": { "lat": [30.7, 32.2], "lon": [119.7, 121.5] },
  "labels": {
    "t2m": { "label": "2米气温", "unit": "℃" },
    "ws":  { "label": "10米风速", "unit": "m/s" },
    "tp":  { "label": "逐小时降水", "unit": "mm" }
  },
  "unit_conversions": ["t2m: K → ℃"],
  "step_interpretation": "lead hours after issue time (e.g. step=1 means issue+1h)",
  "forecast": [
    { "lead_hour": 1, "valid_time": "2026-06-05T14:00:00+08:00", "values": { "t2m": 22.3, "ws": 3.2, "tp": 0.0 } }
  ],
  "summary": "上海（最近格点 31.23°N, 121.47°E，距查询点约 0.45 km）未来 24 小时逐小时预报：起报时刻 2026-06-05T13:00:00+08:00。气温区间 18.5~28.4℃。…"
}
```

### 错误形式（结构化，便于模型自行纠正）

- 缺坐标：

```json
{ "error": "missing_coordinates", "hint": "缺少必要的经纬度参数。本工具不做地理编码，请先调用地理编码工具…" }
```

- 越界：

```json
{ "error": "out_of_coverage", "hint": "查询点超出预报覆盖范围。本预报仅覆盖江苏-上海一带 …", "coverage": { "lat": [30.7, 32.2], "lon": [119.7, 121.5] } }
```

- 找不到预报：HTTP 404 + `{"error": "no_forecast_available", ...}`
- 数据源读取失败：HTTP 502 + `{"error": "datasource_read_failed", ...}`

### `GET /health`

```json
{ "status": "ok", "version": "0.1.0", "data_source": "local", "timezone": "Asia/Shanghai" }
```

## 本地运行（开发/测试）

推荐用 `leadsee-webui` 这个 conda 环境，里面已经装好 `netCDF4`：

```bash
conda activate leadsee-webui
cd fengche/tool_server

# 复制环境文件，按需修改（默认 DATA_SOURCE=local，LOCAL_BASE_DIR=./fengche/data_samples）
cp .env.example .env

# 安装其余依赖（netCDF4 已通过 conda 装好，剩余包用 pip）
pip install fastapi==0.115.5 "uvicorn[standard]==0.32.1" python-dotenv==1.0.1 pydantic==2.10.3

# 启动服务（在仓库根目录运行；LOCAL_BASE_DIR 默认相对当前工作目录）
cd ../..
# 注意：容器内/import 路径仍是 fengche_tool_server.app.main，本地开发期同名 package 需要让 Python 找到。
# 简单做法是先把代码放到 PYTHONPATH，比如：
PYTHONPATH=fengche/tool_server python -m uvicorn app.main:app --host 0.0.0.0 --port 8765
```

测试：

```bash
# 上海（覆盖范围内，返回 24 小时）
curl "http://localhost:8765/fengche_forecast?lat=31.2304&lon=121.4737&location_name=上海&request_time_iso=2026-06-05T13:38:00%2B08:00"

# 上海，仅取前 12 小时
curl "http://localhost:8765/fengche_forecast?lat=31.2304&lon=121.4737&location_name=上海&hours=12"

# 北京（越界）
curl "http://localhost:8765/fengche_forecast?lat=39.9042&lon=116.4074&location_name=北京&request_time_iso=2026-06-05T13:38:00%2B08:00"

# OpenAPI 描述
curl "http://localhost:8765/openapi.json" | head -c 500
```

## Docker 部署

推荐使用统一的部署 stack（包含 forecast + warning 两个服务），见 [`fengche/deploy/DEPLOY.md`](../deploy/DEPLOY.md)，里面有完整的打包/上传/起服务流程，本节略。

如果只想单独起 forecast 服务，编辑 `.env`：

   生产场景使用 FTP：

   ```
   DATA_SOURCE=ftp
   FTP_HOST=10.127.13.197
   FTP_PORT=2123
   FTP_USER=fengche
   FTP_PASSWORD=填写实际密码
   # fengche 账号登录后所看到的根目录就是数据根，无需再指定子目录
   FTP_BASE_DIR=/
   # 路径模板可省略，DATA_SOURCE=ftp 时默认就是下面这个：
   # PATH_TEMPLATE={Y}/{Ym}/{ymd}/{ymd}T{HH}.nc
   ```

   FTP 上的实际目录结构形如：
   `/2026/202605/20260509/20260509T08.nc`（按 年 / 年月 / 年月日 三层分目录）。
   服务会用模板 `{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc` 自动构造路径。

   或用本地挂载路径调试：

   ```
   DATA_SOURCE=local
   LOCAL_BASE_DIR=/data/fengche
   ```

2. 起服务（沿用统一 stack）：

   ```bash
   cd fengche/deploy
   docker compose up -d --build fengche-forecast
   docker compose logs -f fengche-forecast
   ```

   `open-webui` 容器和镜像**完全不动、不需要重启**。

3. 在 Open WebUI 管理员页 → Settings → Tools → Add Tool Server，URL 填：
   - 同 docker network：`http://fengche-forecast:8765/openapi.json`
   - 跨主机或调试：`http://<宿主IP>:8765/openapi.json`

   命名「风掣天气预报」，保存。

## 在 Open WebUI 中使用

**关键**：用户在聊天框中需**同时勾选**两个工具——

1. 「高德地图 MCP」（已由管理员配置好，负责地理编码）
2. 「风掣天气预报」（本工具）

然后一句话即可：

> 查询苏州未来 24 小时天气

模型会自动两步调用：

1. `geocode("苏州")` → `{ lat: 31.30, lon: 120.58 }`
2. `/fengche_forecast(lat=31.30, lon=120.58, location_name="苏州")` → 24 行表格 + summary

模型再把表格 + summary 整理成中文回复发给用户。

如果用户问的是覆盖范围之外的城市（如北京），模型会收到 `out_of_coverage` 错误，自动告诉用户「本预报仅覆盖江苏-上海一带」。

## 覆盖范围参考

预报网格仅覆盖：

- 纬度：30.7°N ~ 32.2°N
- 经度：119.7°E ~ 121.5°E
- 分辨率：约 0.01°（≈1 km）

范围内典型城市：上海、苏州、无锡、常州、南通、嘉兴、昆山、张家港 等。

范围外城市（会被拒绝）：北京、广州、杭州、南京、深圳、成都 等。

## 数据结构说明

每个 `.nc` 文件包含：

- 维度：`time=1`（起报时刻）、`step=24`（预报时效，1~24 小时）、`lat=151`、`lon=181`
- 起报频率：整点逐小时（每小时一份新文件）
- 变量（全部 4D `(time, step, lat, lon)`，dtype float32）：
  - `t2m`（2米气温, K，自动转 ℃）
  - `q2m`（2米比湿, kg/kg）
  - `u10m`、`v10m`（10米 U/V 风, m/s）
  - `ws`（10米风速, m/s）
  - `gs`（阵风, m/s）
  - `cr`（雷达回波, dBZ）
  - `tp`（逐小时降水, mm；每个时次的当小时降水量，已通过样本数据验证：非累积值）

文件命名按起报时刻，路径布局通过 `PATH_TEMPLATE` 环境变量配置：

- 本地默认：`{ymd}/{ymd}T{HH}.nc`，例 `20260509/20260509T08.nc`
- FTP 默认：`{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc`，例 `2026/202605/20260509/20260509T08.nc`

## 故障排查

- **`/health` 返回 `data_source: local` 但找不到文件**：检查 `LOCAL_BASE_DIR` 是否为相对当前工作目录的正确路径，或改成绝对路径。
- **FTP 模式连不上**：先用 `python -c "from ftplib import FTP; FTP().connect('IP', PORT, 30); print('ok')"` 确认网络可达。
- **OWUI 看不到工具**：在 OWUI Tool Server 列表里看是否成功拉到了 `/openapi.json`；网络问题时 try `http://<宿主IP>:8765/openapi.json`。
- **模型不调用本工具或乱编坐标**：在聊天框确认两个工具都勾上了；若仍不调用，可在系统提示词里强调"查天气先调地理编码、再调风掣天气预报"。
