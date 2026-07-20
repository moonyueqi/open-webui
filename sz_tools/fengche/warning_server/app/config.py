"""配置加载：从环境变量读取阈值、数据源等设置。

数据源（DataSource）直接复用 fengche_tool_server.app.datasource，避免重复维护。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# 复用风掣预报工具的数据源实现
from fengche_tool_server.app.datasource import DataSource, FtpDataSource, LocalDataSource


load_dotenv()


@dataclass(frozen=True)
class Thresholds:
    """阵风（强对流）与降水（暴雨）阈值。

    暴雨判定按国标三窗口 OR 触发：
      - 蓝色：仅 6h ≥ 50
      - 黄色：1h ≥ 50 或 6h ≥ 100 或 24h ≥ 150
      - 橙色：1h ≥ 75 或 6h ≥ 150 或 24h ≥ 200
      - 红色：1h ≥ 100 或 6h ≥ 200 或 24h ≥ 250
    """

    gs_yellow_ms: float
    gs_orange_ms: float
    gs_red_ms: float

    rain_1h_yellow_mm: float
    rain_1h_orange_mm: float
    rain_1h_red_mm: float

    rain_6h_blue_mm: float
    rain_6h_yellow_mm: float
    rain_6h_orange_mm: float
    rain_6h_red_mm: float

    rain_24h_yellow_mm: float
    rain_24h_orange_mm: float
    rain_24h_red_mm: float


@dataclass(frozen=True)
class Settings:
    data_source_kind: str
    timezone: str
    max_lookback_hours: int
    host: str
    port: int
    path_template: str

    thresholds: Thresholds


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw is not None else default


def _int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw is not None else default


def load_settings() -> Settings:
    kind = (_env("DATA_SOURCE", "local") or "local").lower()
    default_template = (
        "{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc"
        if kind == "ftp"
        else "{ymd}/{ymd}T{HH}.nc"
    )

    thresholds = Thresholds(
        gs_yellow_ms=_float("GS_YELLOW_MS", 17.2),
        gs_orange_ms=_float("GS_ORANGE_MS", 24.5),
        gs_red_ms=_float("GS_RED_MS", 32.7),
        rain_1h_yellow_mm=_float("RAIN_1H_YELLOW", 50.0),
        rain_1h_orange_mm=_float("RAIN_1H_ORANGE", 75.0),
        rain_1h_red_mm=_float("RAIN_1H_RED", 100.0),
        rain_6h_blue_mm=_float("RAIN_6H_BLUE", 50.0),
        rain_6h_yellow_mm=_float("RAIN_6H_YELLOW", 100.0),
        rain_6h_orange_mm=_float("RAIN_6H_ORANGE", 150.0),
        rain_6h_red_mm=_float("RAIN_6H_RED", 200.0),
        rain_24h_yellow_mm=_float("RAIN_24H_YELLOW", 150.0),
        rain_24h_orange_mm=_float("RAIN_24H_ORANGE", 200.0),
        rain_24h_red_mm=_float("RAIN_24H_RED", 250.0),
    )

    return Settings(
        data_source_kind=kind,
        timezone=_env("DEFAULT_TIMEZONE", "Asia/Shanghai") or "Asia/Shanghai",
        max_lookback_hours=_int("MAX_LOOKBACK_HOURS", 24),
        host=_env("HOST", "0.0.0.0") or "0.0.0.0",
        port=_int("PORT", 8766),
        path_template=_env("PATH_TEMPLATE", default_template) or default_template,
        thresholds=thresholds,
    )


def build_datasource(settings: Optional[Settings] = None) -> DataSource:
    """根据环境变量构造 DataSource 实例（直接复用 fengche_tool_server 的实现）。"""
    s = settings or load_settings()
    if s.data_source_kind == "ftp":
        host = _env("FTP_HOST")
        if not host:
            raise RuntimeError("DATA_SOURCE=ftp 但 FTP_HOST 未配置")
        return FtpDataSource(
            host=host,
            port=_int("FTP_PORT", 21),
            user=_env("FTP_USER", "anonymous") or "anonymous",
            password=_env("FTP_PASSWORD", "") or "",
            base_dir=_env("FTP_BASE_DIR", "/fengche") or "/fengche",
        )
    _default_base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data_samples",
    )
    base_dir = _env("LOCAL_BASE_DIR", _default_base) or _default_base
    return LocalDataSource(base_dir=base_dir)
