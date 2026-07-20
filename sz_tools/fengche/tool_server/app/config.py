"""配置加载：从环境变量构造 DataSource 和服务参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from .datasource import DataSource, LocalDataSource, FtpDataSource


load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_source_kind: str
    timezone: str
    max_lookback_hours: int
    host: str
    port: int
    path_template: str


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def load_settings() -> Settings:
    kind = _env("DATA_SOURCE", "local").lower()
    # 默认路径模板：本地是平铺 {ymd}/...；FTP 是分层 {Y}/{Ym}/{ymd}/...
    default_template = (
        "{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc"
        if kind == "ftp"
        else "{ymd}/{ymd}T{HH}.nc"
    )
    return Settings(
        data_source_kind=kind,
        timezone=_env("DEFAULT_TIMEZONE", "Asia/Shanghai"),
        max_lookback_hours=int(_env("MAX_LOOKBACK_HOURS", "24")),
        host=_env("HOST", "0.0.0.0"),
        port=int(_env("PORT", "8765")),
        path_template=_env("PATH_TEMPLATE", default_template),
    )


def build_datasource(settings: Optional[Settings] = None) -> DataSource:
    """根据环境变量构造 DataSource 实例。"""
    s = settings or load_settings()
    if s.data_source_kind == "ftp":
        host = _env("FTP_HOST")
        if not host:
            raise RuntimeError("DATA_SOURCE=ftp 但 FTP_HOST 未配置")
        return FtpDataSource(
            host=host,
            port=int(_env("FTP_PORT", "21")),
            user=_env("FTP_USER", "anonymous"),
            password=_env("FTP_PASSWORD", ""),
            base_dir=_env("FTP_BASE_DIR", "/fengche"),
        )
    _default_base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data_samples",
    )
    base_dir = _env("LOCAL_BASE_DIR", _default_base)
    return LocalDataSource(base_dir=base_dir)
