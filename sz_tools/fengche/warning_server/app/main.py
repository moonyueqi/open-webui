"""FastAPI 应用：暴露 /fengche_warning 端点供 Open WebUI Tool Server 调用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 复用风掣预报工具的最近预报检索器
from fengche_tool_server.app.forecast_finder import find_latest_forecast

from . import __version__
from .config import build_datasource, load_settings
from .district_mask import DistrictMaskRegistry
from .nc_reader_grid import read_forecast_grid
from .summary import build_summary
from .warning_engine import evaluate_all


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("fengche_warning_server")


SETTINGS = load_settings()
DATASOURCE = build_datasource(SETTINGS)
REGISTRY = DistrictMaskRegistry()


API_DESCRIPTION = """
苏州市气象预警信号**粗筛**工具。基于风掣 AI 模型未来 24 小时预报，对苏州市下属
全部 10 个区/县级市（姑苏区 / 虎丘区[高新区] / 吴中区 / 相城区 / 吴江区 / 苏州工业园区 /
常熟市 / 张家港市 / 昆山市 / 太仓市）做强对流（阵风阈值）与暴雨（国标 1h/6h/24h 三窗口）
的**任意格点触发**判定（只要某区内有任一格点达到某等级阈值，即提示该区可能需要发布
对应级别的预警信号；最终是否发布以预报员研判为准）。

**模型回复用户时请遵循以下输出规范：**

1. **直接复用响应中的 `summary` 字段**——它已经把 10 个区的发布建议拼成一张
   Markdown 表格 + 每段预报用语清单 + 一句话免责声明，模型不要再额外铺陈"重要提醒"
   "不确定性说明"等冗余文本。
2. 表述统一使用「发布预警信号」，不要说成「发预警」或「发布预警」。
3. 用户追问某个区/某段的细节（防御指南、量化指标）时，再去 `districts.<code>.<warning_type>.segments[*]`
   里取 `advisory.defense_guide`、`hour_metrics` 复述。
4. 是否真正发布预警信号以预报员研判为准（`summary` 末尾已包含此声明，复用即可）。

可选参数：
- `districts`：仅评估指定区，逗号分隔。可用值：`gusu` / `huqiu`（兼容历史 `gaoxin`）/
  `wuzhong` / `xiangcheng` / `wujiang` / `sip` / `changshu` / `zhangjiagang` / `kunshan` /
  `taicang`；省略则评估全部 10 个区。
- `request_time_iso`：调试/复现用，ISO8601 本地时间。

> 历史版本支持的 `gs_coverage_ratio` / `rain_coverage_ratio` 覆盖率门槛参数已弃用：
> 现版本统一按"任意格点达标即提示"，传入也会被忽略。
""".strip()


app = FastAPI(
    title="Fengche Warning Tool Server",
    version=__version__,
    description=API_DESCRIPTION,
)


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class WarningRequest(BaseModel):
    districts: Optional[List[str]] = Field(
        None,
        description=(
            "待评估的区代码列表，省略则评估苏州全部 10 个区。可选值："
            "gusu / huqiu(兼容历史 gaoxin) / wuzhong / xiangcheng / wujiang / sip / "
            "changshu / zhangjiagang / kunshan / taicang"
        ),
    )
    gs_coverage_ratio: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description=(
            "[已弃用] 阵风覆盖率门槛。当前版本按『任意格点达标即触发』判定，"
            "传入会被忽略，仅为向后兼容保留字段。"
        ),
    )
    rain_coverage_ratio: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description=(
            "[已弃用] 降水覆盖率门槛。当前版本按『任意格点达标即触发』判定，"
            "传入会被忽略，仅为向后兼容保留字段。"
        ),
    )
    request_time_iso: Optional[str] = Field(
        None,
        description="ISO8601 本地时间，仅用于复现/调试；省略则用服务器当前时间。",
    )


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _parse_now(request_time_iso: Optional[str], tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    if request_time_iso:
        try:
            dt = datetime.fromisoformat(request_time_iso)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"request_time_iso 不是合法的 ISO8601 字符串：{e}",
            )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        return dt
    return datetime.now(tz)


def _do_warning(req: WarningRequest) -> Dict[str, Any]:
    now_local = _parse_now(req.request_time_iso, SETTINGS.timezone)
    # 覆盖率门槛参数已弃用：当前版本固定按"任意格点达标即触发"判定，
    # 仍透传 0.0 给评估函数，仅作为占位（评估函数已忽略该值）。
    gs_ratio = 0.0
    rain_ratio = 0.0
    if req.gs_coverage_ratio is not None or req.rain_coverage_ratio is not None:
        log.info(
            "client supplied deprecated coverage_ratio "
            "(gs=%s, rain=%s); ignored.",
            req.gs_coverage_ratio, req.rain_coverage_ratio,
        )
    log.info(
        "warning request now=%s mode=any-point-hit districts=%s",
        now_local.isoformat(), req.districts,
    )

    # 1) 找最近一份预报
    found = find_latest_forecast(
        DATASOURCE,
        now_local,
        SETTINGS.max_lookback_hours,
        path_template=SETTINGS.path_template,
    )
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_forecast_available",
                "hint": (
                    f"在最近 {SETTINGS.max_lookback_hours} 小时内未找到任何预报文件。"
                ),
                "search_window_hours": SETTINGS.max_lookback_hours,
                "now": now_local.isoformat(),
            },
        )

    # 2) 读 .nc 全网格
    try:
        nc_bytes = DATASOURCE.open_binary(found.relative_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("datasource read failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "datasource_read_failed",
                "hint": "数据源读取失败，请稍后重试。",
                "detail": str(e),
            },
        )

    try:
        grid = read_forecast_grid(nc_bytes, tz=SETTINGS.timezone)
    except Exception as e:
        log.exception(".nc parse failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "nc_parse_failed",
                "hint": "NetCDF 文件解析失败。",
                "detail": str(e),
            },
        )

    # 3) 生成（或取缓存）各区掩膜
    masks = REGISTRY.build_for_grid(grid.lat_arr, grid.lon_arr)

    # 4) 区域评估（先把别名 code 解析为主 code，并去重保序）
    requested_codes: Optional[List[str]] = None
    if req.districts:
        seen = set()
        requested_codes = []
        for c in req.districts:
            primary = REGISTRY.resolve_code(c)
            if primary not in seen:
                seen.add(primary)
                requested_codes.append(primary)
    districts_out = evaluate_all(
        grid=grid,
        masks=masks,
        thresholds=SETTINGS.thresholds,
        gs_coverage_ratio=gs_ratio,
        rain_coverage_ratio=rain_ratio,
        districts=requested_codes,
    )

    # 5) 摘要
    forecast_hours = int(grid.gs.shape[0])
    summary = build_summary(
        issue_time=grid.issue_time,
        districts=districts_out,
        forecast_hours=forecast_hours,
    )

    return {
        "query": {
            "request_time": now_local.isoformat(),
            "trigger_mode": "any_point_hit",
            "trigger_mode_desc": "区内任意格点达到阈值即提示发布对应级别预警信号",
            "districts": list(districts_out.keys()),
        },
        "forecast_source": {
            "issue_time": grid.issue_time.isoformat(),
            "file_uri": DATASOURCE.describe(found.relative_path),
            "fallback_steps_back": found.steps_back,
            "data_source_kind": DATASOURCE.kind,
        },
        "coverage": {
            "lat": list(grid.coverage_lat),
            "lon": list(grid.coverage_lon),
        },
        "districts": districts_out,
        "summary": summary,
    }


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.get("/health", summary="健康检查", tags=["fengche_warning_meta"])
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "data_source": DATASOURCE.kind,
        "timezone": SETTINGS.timezone,
        "geojson_path": REGISTRY.geojson_path,
        "district_source": REGISTRY.overall_source,
        "per_district_source": REGISTRY.per_district_source(),
        "districts_known": REGISTRY.district_codes(),
        "trigger_mode": "any_point_hit",
        "trigger_mode_desc": "区内任意格点达到阈值即提示发布对应级别预警信号",
        "thresholds": {
            "gs_yellow_ms": SETTINGS.thresholds.gs_yellow_ms,
            "gs_orange_ms": SETTINGS.thresholds.gs_orange_ms,
            "gs_red_ms":    SETTINGS.thresholds.gs_red_ms,
            "rain_1h_yellow_mm":  SETTINGS.thresholds.rain_1h_yellow_mm,
            "rain_1h_orange_mm":  SETTINGS.thresholds.rain_1h_orange_mm,
            "rain_1h_red_mm":     SETTINGS.thresholds.rain_1h_red_mm,
            "rain_6h_blue_mm":    SETTINGS.thresholds.rain_6h_blue_mm,
            "rain_6h_yellow_mm":  SETTINGS.thresholds.rain_6h_yellow_mm,
            "rain_6h_orange_mm":  SETTINGS.thresholds.rain_6h_orange_mm,
            "rain_6h_red_mm":     SETTINGS.thresholds.rain_6h_red_mm,
            "rain_24h_yellow_mm": SETTINGS.thresholds.rain_24h_yellow_mm,
            "rain_24h_orange_mm": SETTINGS.thresholds.rain_24h_orange_mm,
            "rain_24h_red_mm":    SETTINGS.thresholds.rain_24h_red_mm,
        },
    }


@app.post(
    "/fengche_warning",
    summary="苏州市全部 10 个区/县级市未来 24h 强对流与暴雨预警粗筛",
    description=(
        "对苏州市下属全部 10 个区/县级市（姑苏、虎丘[高新]、吴中、相城、吴江、苏州工业园区、"
        "常熟、张家港、昆山、太仓）做强对流（阵风阈值）与暴雨（1h/6h/24h 三窗口阈值）的"
        "任意格点触发判定（只要区内有任一格点达到阈值即提示），返回按级别合并的连续时段，"
        "每段都附带自动拼装的预报用语与防御指南。"
    ),
    tags=["fengche_warning"],
)
def warning_post(req: WarningRequest) -> JSONResponse:
    return JSONResponse(_do_warning(req))


@app.get(
    "/fengche_warning",
    summary="GET 形式",
    description="语义同 POST /fengche_warning，便于浏览器或 curl 测试。",
    tags=["fengche_warning"],
)
def warning_get(
    districts: Optional[str] = Query(
        None,
        description=(
            "逗号分隔的区代码列表，例如 gusu,huqiu,sip,kunshan。省略则评估全部 10 个区。"
        ),
    ),
    gs_coverage_ratio: Optional[float] = Query(
        None, ge=0.0, le=1.0,
        description="[已弃用] 阵风覆盖率门槛，传入会被忽略。",
    ),
    rain_coverage_ratio: Optional[float] = Query(
        None, ge=0.0, le=1.0,
        description="[已弃用] 降水覆盖率门槛，传入会被忽略。",
    ),
    request_time_iso: Optional[str] = Query(
        None, description="ISO8601 本地时间，调试用。"
    ),
) -> JSONResponse:
    district_list = (
        [d.strip() for d in districts.split(",") if d.strip()]
        if districts
        else None
    )
    req = WarningRequest(
        districts=district_list,
        gs_coverage_ratio=gs_coverage_ratio,
        rain_coverage_ratio=rain_coverage_ratio,
        request_time_iso=request_time_iso,
    )
    return JSONResponse(_do_warning(req))
