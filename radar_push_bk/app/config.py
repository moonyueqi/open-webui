"""配置加载：从环境变量读取数据源、阈值、企业微信 webhook 等设置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


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


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _floats(name: str, default: List[float]) -> List[float]:
    raw = _env(name)
    if raw is None:
        return list(default)
    return [float(x) for x in raw.split(",") if x.strip()]


@dataclass(frozen=True)
class SftpSettings:
    host: str
    port: int
    user: str
    password: str
    nc_base_dir: str


@dataclass(frozen=True)
class FtpSettings:
    """推送结果（雷达图 + 文案）上传到 FTP 目录的配置。"""
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    remote_dir: str          # 远程目标目录，如 data/image/radar
    passive: bool            # 被动模式（多数防火墙环境需要）
    timeout: int
    encoding: str            # 控制连接编码，中文路径/文件名建议 utf-8
    tls: bool                # 是否使用 FTPS（显式 TLS）


@dataclass(frozen=True)
class Thresholds:
    strong_dbz: float = 35.0
    et_min_km: float = 7.0
    min_cluster_points: int = 4
    level_step_dbz: float = 5.0
    redalert_dbz: float = 45.0
    gale_cr_dbz: float = 45.0
    gale_et_km: float = 9.0
    hail_cr_dbz: float = 55.0
    hail_et_km: float = 12.0
    boundary_km_milestones: List[float] = field(
        default_factory=lambda: [25.0, 10.0, 5.0, 0.0]
    )
    buffer_km: float = 50.0
    push_window_minutes: int = 12   # 全局节流窗口：该时间内最多推送 1 次


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = 30
    temperature: float = 0.2
    enable_thinking: bool = False


@dataclass(frozen=True)
class Settings:
    data_source_kind: str
    sftp: Optional[SftpSettings]
    local_base_dir: str

    timezone: str
    scan_interval_sec: int
    future_frames: int
    nc_value_no_cover: float
    nc_value_no_echo: float

    wecom_webhook_url: str
    state_dir: str

    ftp: FtpSettings

    thresholds: Thresholds
    llm: LLMSettings = field(default_factory=LLMSettings)

    upstream_cities: List[str] = field(
        default_factory=lambda: ["无锡", "湖州", "泰州", "上海", "常州", "嘉兴", "南通"]
    )


def load_settings() -> Settings:
    kind = (_env("DATA_SOURCE", "sftp") or "sftp").lower()

    sftp: Optional[SftpSettings] = None
    if kind == "sftp":
        sftp = SftpSettings(
            host=_env("SFTP_HOST", "10.127.13.190") or "10.127.13.190",
            port=_int("SFTP_PORT", 22),
            user=_env("SFTP_USER", "root") or "root",
            password=_env("SFTP_PASSWORD", "") or "",
            nc_base_dir=_env(
                "SFTP_NC_BASE_DIR",
                "/space/duogee/data/runenv/product_data/Nc",
            ) or "/space/duogee/data/runenv/product_data/Nc",
        )

    thresholds = Thresholds(
        strong_dbz=_float("STRONG_DBZ", 35.0),
        et_min_km=_float("ET_MIN_KM", 7.0),
        min_cluster_points=_int("MIN_CLUSTER_POINTS", 4),
        level_step_dbz=_float("LEVEL_STEP_DBZ", 5.0),
        redalert_dbz=_float("REDALERT_DBZ", 45.0),
        gale_cr_dbz=_float("GALE_CR_DBZ", 45.0),
        gale_et_km=_float("GALE_ET_KM", 9.0),
        hail_cr_dbz=_float("HAIL_CR_DBZ", 55.0),
        hail_et_km=_float("HAIL_ET_KM", 12.0),
        boundary_km_milestones=_floats("BOUNDARY_KM_MILESTONES", [25.0, 10.0, 5.0, 0.0]),
        buffer_km=_float("BUFFER_KM", 50.0),
        push_window_minutes=_int("PUSH_WINDOW_MIN", 12),
    )

    ftp = FtpSettings(
        enabled=_bool("FTP_UPLOAD_ENABLED", False),
        host=_env("FTP_HOST", "") or "",
        port=_int("FTP_PORT", 21),
        user=_env("FTP_USER", "") or "",
        password=_env("FTP_PASSWORD", "") or "",
        remote_dir=_env("FTP_REMOTE_DIR", "data/image/radar") or "data/image/radar",
        passive=_bool("FTP_PASSIVE", True),
        timeout=_int("FTP_TIMEOUT_SEC", 30),
        encoding=_env("FTP_ENCODING", "utf-8") or "utf-8",
        tls=_bool("FTP_TLS", False),
    )

    llm = LLMSettings(
        enabled=_bool("LLM_POLISH_ENABLED", False),
        base_url=(_env("LLM_BASE_URL", "") or "").rstrip("/"),
        api_key=_env("LLM_API_KEY", "") or "",
        model=_env("LLM_MODEL", "") or "",
        timeout=_int("LLM_TIMEOUT_SEC", 30),
        temperature=_float("LLM_TEMPERATURE", 0.2),
        enable_thinking=_bool("LLM_ENABLE_THINKING", False),
    )

    return Settings(
        data_source_kind=kind,
        sftp=sftp,
        local_base_dir=_env("LOCAL_BASE_DIR", str(BASE_DIR / "data_samples"))
        or str(BASE_DIR / "data_samples"),
        timezone=_env("DEFAULT_TIMEZONE", "Asia/Shanghai") or "Asia/Shanghai",
        scan_interval_sec=_int("SCAN_INTERVAL_SEC", 60),
        future_frames=_int("FUTURE_FRAMES", 10),
        nc_value_no_cover=_float("NC_NO_COVER", -32768.0),
        nc_value_no_echo=_float("NC_NO_ECHO", -128.0),
        wecom_webhook_url=_env("WECOM_WEBHOOK_URL", "") or "",
        state_dir=_env("STATE_DIR", str(BASE_DIR / "state")) or str(BASE_DIR / "state"),
        ftp=ftp,
        thresholds=thresholds,
        llm=llm,
    )
