"""FastAPI 应用：暴露 /fengche_forecast 端点供 Open WebUI Tool Server 调用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import build_datasource, load_settings
from .datasource import DataSource
from .forecast_finder import find_latest_forecast
from .nc_reader import read_forecast
from .summary import build_summary
from .var_meta import (
    convert_value,
    conversions_applied,
    labels_for,
    unknown_variables,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("fengche_tool_server")


SETTINGS = load_settings()
DATASOURCE: DataSource = build_datasource(SETTINGS)


API_DESCRIPTION = """
风掣（Fengche）AI 天气预报查询工具。返回指定经纬度未来 24 小时（逐 1 小时）的多要素预报，
包括 2 米气温、10 米风速 / 风向分量、阵风、逐小时降水、雷达回波等。

**重要：本工具不做地理编码**。调用前请先用地理编码工具（例如高德地图 MCP）将地名解析为
WGS84 经纬度（lat / lon），再把数值传给本工具。**不要自己猜测坐标。**

**覆盖范围有限**：本预报仅覆盖江苏-上海一带（约 30.7~32.2°N, 119.7~121.5°E）。
查询超出范围的地点会收到 `out_of_coverage` 错误，请告知用户。

**预报时效仅 24 小时**：风掣 AI 模型按整点逐小时起报，每份文件覆盖未来 1~24 小时。

- 用户若问「未来 N 小时 / 一天 / 今晚 / 明早」之类，落在 24 小时内 → 正常返回。
- 用户若问「后天 / 大后天 / 未来 36 小时」之类，**调用方应通过 `target_time_iso` 或
  `target_lead_hours` 把目标时刻明确传过来**；超出 24 小时时效，工具会返回
  `error=out_of_horizon` + summary "超过预报时效"，请如实告知用户："本工具仅提供未来
  24 小时预报，超过部分超过预报时效，建议改用其它中长期预报产品。"
- 不要试图自己外推或编造 24 小时之外的预报。

典型调用流程：
1. 用户问「查询苏州未来 24 小时天气」
2. 模型先调用地理编码工具：geocode("苏州") -> { lat: 31.30, lon: 120.58 }
3. 模型再调用本工具：/fengche_forecast?lat=31.30&lon=120.58&location_name=苏州
4. 拿到结构化预报后，按 summary 文案与 forecast 表整理成中文回复给用户。

如果用户问的是某个具体时刻（如「苏州明天上午 8 点天气」），先把目标时刻转成
ISO8601（含本地时区，例 `2026-06-06T08:00:00+08:00`），随 `target_time_iso` 传入。
""".strip()


app = FastAPI(
    title="Fengche Forecast Tool Server",
    version=__version__,
    description=API_DESCRIPTION,
)


# -----------------------------
# Schemas
# -----------------------------
class ForecastRequest(BaseModel):
    lat: Optional[float] = Field(
        None,
        description="WGS84 纬度（必填）。例如 上海 31.2304。请先用地理编码工具获取。",
        ge=-90,
        le=90,
    )
    lon: Optional[float] = Field(
        None,
        description="WGS84 经度（必填）。例如 上海 121.4737。请先用地理编码工具获取。",
        ge=-180,
        le=180,
    )
    location_name: Optional[str] = Field(
        None,
        description="可选地名（仅用于结果展示与摘要文案，例如 \"上海\"）。",
    )
    variables: Optional[List[str]] = Field(
        None,
        description="可选要素筛选；省略则返回 t2m/q2m/u10m/v10m/ws/gs/cr/tp 全部 8 个要素。",
    )
    hours: Optional[int] = Field(
        None,
        ge=1,
        le=24,
        description="可选返回的预报小时数（1~24），省略则返回全部可用时效（默认 24 小时）。",
    )
    target_time_iso: Optional[str] = Field(
        None,
        description=(
            "可选；用户问到「具体某个时刻 / 某天某时」的天气时填这里（ISO8601 本地时间）。"
            "工具会判断该时刻是否在风掣预报时效内（起报时间 + 1~24 小时）："
            "在范围内 → 返回该时刻所在小时的预报；"
            "完全超出 → 返回 error=out_of_horizon 与友好的「超过预报时效」提示。"
            "示例：2026-06-06T08:00:00+08:00。"
        ),
    )
    target_lead_hours: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "可选；与 target_time_iso 二选一。表示「未来第几小时」（≥1）。"
            "≥25 时直接返回超出预报时效错误。"
        ),
    )
    request_time_iso: Optional[str] = Field(
        None,
        description="可选 ISO8601 本地时间，仅用于复现/调试；省略则用服务器当前时间。例如 2026-05-07T15:38:00+08:00。",
    )


# -----------------------------
# Helpers
# -----------------------------
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


def _missing_coords_response(req: ForecastRequest) -> Dict[str, Any]:
    return {
        "error": "missing_coordinates",
        "hint": (
            "缺少必要的经纬度参数。本工具不做地理编码，请先调用地理编码工具"
            "（例如高德地图 MCP）将地名解析为 WGS84 lat/lon 后再传入。"
        ),
        "query": {
            "lat": req.lat,
            "lon": req.lon,
            "location_name": req.location_name,
        },
    }


# 风掣时效上限（小时）
FORECAST_HORIZON_HOURS = 24


def _resolve_target_lead_hour(
    req: ForecastRequest,
    issue_time: datetime,
    tz_name: str,
) -> Optional[int]:
    """根据请求里的 target_time_iso / target_lead_hours 计算 lead hour（≥1 的整数）。

    返回值：
      - None：用户没指定 target，按默认逐小时返回处理；
      - int：1~∞ 的 lead hour（caller 自行检查是否 > FORECAST_HORIZON_HOURS）。
      - 0 / 负数：caller 自行处理（已是过去时刻）。

    注意：本函数不抛 HTTPException，超时效的判定交给上层统一组装结构化响应。
    """
    if req.target_lead_hours is not None:
        return int(req.target_lead_hours)

    if req.target_time_iso:
        try:
            t = datetime.fromisoformat(req.target_time_iso)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"target_time_iso 不是合法的 ISO8601 字符串：{e}",
            )
        if t.tzinfo is None:
            t = t.replace(tzinfo=ZoneInfo(tz_name))
        else:
            t = t.astimezone(ZoneInfo(tz_name))
        # 风掣按整点起报、整点 lead；把分钟数四舍五入到整点
        delta_seconds = (t - issue_time).total_seconds()
        lead = int(round(delta_seconds / 3600))
        return lead

    return None


def _out_of_horizon_response(
    req: ForecastRequest,
    now_local: datetime,
    issue_time_iso: str,
    target_lead: int,
    source_uri: str,
    fallback_steps_back: int,
) -> Dict[str, Any]:
    """目标时刻超出 24 小时预报时效，返回结构化 + 友好 summary。"""
    if target_lead <= 0:
        hint = (
            f"查询时刻已是起报时刻（{issue_time_iso}）之前，本工具仅提供未来 1~"
            f"{FORECAST_HORIZON_HOURS} 小时预报，请查询未来时刻。"
        )
        summary_msg = "查询时刻早于起报时刻，超过预报时效。本工具仅提供未来 1~24 小时预报。"
    else:
        hint = (
            f"查询时刻超出风掣 AI 模型 {FORECAST_HORIZON_HOURS} 小时预报时效"
            f"（请求 lead = {target_lead} 小时）。请改查未来 1~{FORECAST_HORIZON_HOURS} "
            "小时内的时刻；如需更长时效，请使用其它中长期预报产品。"
        )
        summary_msg = (
            f"超过预报时效。风掣 AI 仅提供未来 {FORECAST_HORIZON_HOURS} 小时预报，"
            f"查询时刻位于第 {target_lead} 小时，已超出范围。"
        )

    return {
        "error": "out_of_horizon",
        "hint": hint,
        "horizon_hours": FORECAST_HORIZON_HOURS,
        "requested_lead_hour": target_lead,
        "query": {
            "lat": req.lat,
            "lon": req.lon,
            "location_name": req.location_name,
            "target_time_iso": req.target_time_iso,
            "target_lead_hours": req.target_lead_hours,
            "request_time": now_local.isoformat(),
        },
        "forecast_source": {
            "issue_time": issue_time_iso,
            "file_uri": source_uri,
            "fallback_steps_back": fallback_steps_back,
            "data_source_kind": DATASOURCE.kind,
        },
        "summary": summary_msg,
    }


def _apply_unit_conversions(returned_vars: List[str], forecast: List[Dict[str, Any]]) -> None:
    """就地把每行 values 里的原始数值转成展示用单位。"""
    for row in forecast:
        values = row.get("values", {})
        for v in returned_vars:
            if v in values:
                values[v] = convert_value(v, values[v])


def _do_forecast(req: ForecastRequest) -> Dict[str, Any]:
    if req.lat is None or req.lon is None:
        return _missing_coords_response(req)

    now_local = _parse_now(req.request_time_iso, SETTINGS.timezone)
    log.info(
        "forecast request lat=%s lon=%s loc=%s now=%s",
        req.lat, req.lon, req.location_name, now_local.isoformat(),
    )

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
                    f"请稍后重试或检查上游数据是否就绪。"
                ),
                "search_window_hours": SETTINGS.max_lookback_hours,
                "now": now_local.isoformat(),
            },
        )

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
        parsed = read_forecast(
            nc_bytes,
            lat=req.lat,
            lon=req.lon,
            variables=req.variables,
            tz=SETTINGS.timezone,
            max_hours=req.hours,
        )
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

    source_uri = DATASOURCE.describe(found.relative_path)

    # 越界：模型友好的结构化错误
    if parsed.get("out_of_coverage"):
        coverage = parsed["coverage"]
        return {
            "error": "out_of_coverage",
            "hint": (
                "查询点超出预报覆盖范围。本预报仅覆盖江苏-上海一带"
                f"（{coverage['lat'][0]:.2f}~{coverage['lat'][1]:.2f}°N, "
                f"{coverage['lon'][0]:.2f}~{coverage['lon'][1]:.2f}°E）。"
                "请改查覆盖范围内的地点（如上海、苏州、无锡、常州、南通、嘉兴等）。"
            ),
            "coverage": coverage,
            "query": {
                "lat": req.lat,
                "lon": req.lon,
                "location_name": req.location_name,
            },
            "forecast_source": {
                "issue_time": None,
                "file_uri": source_uri,
                "fallback_steps_back": found.steps_back,
            },
        }

    returned_vars: List[str] = parsed["returned_variables"]
    forecast: List[Dict[str, Any]] = parsed["forecast"]

    _apply_unit_conversions(returned_vars, forecast)

    # 解析「目标时刻」（用户问到具体某个时间的天气）；超出 24 小时直接返回结构化错误
    issue_time_dt = datetime.fromisoformat(parsed["issue_time"])
    target_lead = _resolve_target_lead_hour(req, issue_time_dt, SETTINGS.timezone)
    target_row: Optional[Dict[str, Any]] = None
    if target_lead is not None:
        if target_lead <= 0 or target_lead > FORECAST_HORIZON_HOURS:
            return _out_of_horizon_response(
                req=req,
                now_local=now_local,
                issue_time_iso=parsed["issue_time"],
                target_lead=target_lead,
                source_uri=source_uri,
                fallback_steps_back=found.steps_back,
            )
        # 在 forecast 里找到 lead_hour == target_lead 的行
        for row in forecast:
            if int(row.get("lead_hour", -1)) == target_lead:
                target_row = row
                break

    summary = build_summary(
        location_name=req.location_name,
        grid_point=parsed["grid_point"],
        issue_time_iso=parsed["issue_time"],
        source_uri=source_uri,
        forecast=forecast,
        coverage=parsed["coverage"],
        target_row=target_row,
        horizon_hours=FORECAST_HORIZON_HOURS,
    )

    resp: Dict[str, Any] = {
        "query": {
            "lat": req.lat,
            "lon": req.lon,
            "location_name": req.location_name,
            "request_time": now_local.isoformat(),
            "target_time_iso": req.target_time_iso,
            "target_lead_hours": req.target_lead_hours,
        },
        "forecast_source": {
            "issue_time": parsed["issue_time"],
            "file_uri": source_uri,
            "fallback_steps_back": found.steps_back,
            "data_source_kind": DATASOURCE.kind,
            "horizon_hours": FORECAST_HORIZON_HOURS,
        },
        "grid_point": parsed["grid_point"],
        "coverage": parsed["coverage"],
        "available_variables": parsed["available_variables"],
        "returned_variables": returned_vars,
        "labels": labels_for(returned_vars),
        "unit_conversions": conversions_applied(returned_vars),
        "unknown_variables": unknown_variables(returned_vars),
        "step_interpretation": parsed["step_interpretation"],
        "forecast": forecast,
        "summary": summary,
    }
    if target_row is not None:
        resp["target_forecast"] = target_row
    return resp


# -----------------------------
# Routes
# -----------------------------
@app.get("/health", summary="健康检查", tags=["fengche_meta"])
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "data_source": DATASOURCE.kind,
        "timezone": SETTINGS.timezone,
    }


@app.post(
    "/fengche_forecast",
    summary="查询指定经纬度的风掣 AI 未来 24 小时逐时预报",
    description=(
        "传入 WGS84 经纬度，返回风掣 AI 模型最近一次起报的 24 小时逐 1 小时多要素预报。"
        "风掣按整点逐小时起报，本工具会自动查找最近一份就绪文件。"
        "若坐标缺失或越界，会返回带 hint 的结构化错误，便于上游模型自动纠正。"
    ),
    tags=["fengche_forecast"],
)
def forecast_post(req: ForecastRequest) -> JSONResponse:
    return JSONResponse(_do_forecast(req))


@app.get(
    "/fengche_forecast",
    summary="查询指定经纬度的风掣 AI 未来 24 小时逐时预报（GET 形式）",
    description="GET 形式，便于浏览器或 curl 测试。语义同 POST /fengche_forecast。",
    tags=["fengche_forecast"],
)
def forecast_get(
    lat: Optional[float] = Query(None, ge=-90, le=90, description="WGS84 纬度"),
    lon: Optional[float] = Query(None, ge=-180, le=180, description="WGS84 经度"),
    location_name: Optional[str] = Query(None, description="地名，仅用于展示"),
    variables: Optional[str] = Query(
        None,
        description="逗号分隔的要素列表，例如 t2m,ws,tp。省略则返回全部要素。",
    ),
    hours: Optional[int] = Query(
        None, ge=1, le=24,
        description="返回的预报小时数（1~24），省略则返回全部可用时效（默认 24 小时）。",
    ),
    target_time_iso: Optional[str] = Query(
        None,
        description=(
            "用户问到具体某时刻的天气时填这里（ISO8601 本地时间）。"
            "超过 24 小时预报时效会直接返回 out_of_horizon 错误。"
        ),
    ),
    target_lead_hours: Optional[int] = Query(
        None, ge=1,
        description="未来第几小时（≥1），与 target_time_iso 二选一。≥25 直接返回超时效。",
    ),
    request_time_iso: Optional[str] = Query(
        None, description="ISO8601 本地时间，调试用。"
    ),
) -> JSONResponse:
    var_list = (
        [v.strip() for v in variables.split(",") if v.strip()]
        if variables
        else None
    )
    req = ForecastRequest(
        lat=lat,
        lon=lon,
        location_name=location_name,
        variables=var_list,
        hours=hours,
        target_time_iso=target_time_iso,
        target_lead_hours=target_lead_hours,
        request_time_iso=request_time_iso,
    )
    return JSONResponse(_do_forecast(req))
