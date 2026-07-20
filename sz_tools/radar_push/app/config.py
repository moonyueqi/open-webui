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
class FengcheSettings:
    """风掣 AI 降水预报数据源配置。

    风掣按整点逐小时起报，文件覆盖未来 1~24 小时逐时多要素（含 tp 逐小时降水）；
    数据源 local（本地目录）或 ftp（独立 FTP 服务器）。
    """
    enabled: bool
    # 数据源类型：local（部署服务器本地目录）或 ftp（独立 FTP 服务器）
    source_kind: str
    # local 模式根目录，按 path_template 的 {Y}/{Ym}/{ymd}/ 分层
    local_base_dir: str
    host: str
    port: int
    user: str
    password: str
    base_dir: str
    # 路径模板，占位符 {Y} {Ym} {ymd} {HH}；与 fengche/tool_server 默认一致
    path_template: str
    # 起报回退上限（小时）：从能覆盖目标时段的整点起逐小时回退查找首个就绪文件
    max_lookback_hours: int
    timeout: int
    encoding: str
    # 「逐小时为界」的分界分钟数：观测分钟 <= 该值，目标时段取当前整点起；否则取下一整点起
    boundary_minute: int
    # 风掣等待超时（分钟）：文件未就绪则该时次延后重试，超过此值仍未就绪才放弃；0 表示不等待
    wait_minutes: int
    # 阵风上报门槛（蒲福风级）：区县最大阵风 >= 此级才在「最大阵风…」段列出，避免罗列弱风
    gust_report_min_level: int


@dataclass(frozen=True)
class ObsSettings:
    """地面站点实况数据源配置（小时雨强 + 阵风的 xlsx 快照）。

    实况文件为某一时刻的全省站点快照，文件名时间戳为 UTC，「小时降水量」为过去 1 小时累计雨量。
    """
    enabled: bool
    # 数据源类型：local（开发/测试本地目录）或 sftp（生产，与雷达同机）
    source_kind: str
    local_base_dir: str
    # 路径模板，占位符 {Y} {Ym} {ymd} {HH} {MM} {ymdHM}（基于 UTC 时刻渲染）
    path_template: str
    # 窗口结束对齐：True=向下对齐到 :00/:30（半点边界），False=整点
    half_hour_boundary: bool
    # 实况逐文件时间间隔（分钟）与回退查找上限（分钟）
    step_minutes: int
    max_lookback_minutes: int
    # 风用列关键字（覆盖默认优先级），空则用 obs_reader 默认（最大瞬时风速优先）
    gust_column: str
    # 触发「实况提醒」行的门槛
    rain_threshold_mm: float
    gust_threshold_level: int
    # 上游侧判定的半张角（度）：站点相对市质心方位与「来向」夹角 <= 此值即上游侧
    upstream_half_angle_deg: float


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
    z_layer_index: int
    nc_value_no_cover: float
    nc_value_no_echo: float

    wecom_webhook_url: str
    state_dir: str

    ftp: FtpSettings
    fengche: FengcheSettings
    obs: ObsSettings

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

    fengche = FengcheSettings(
        enabled=_bool("FENGCHE_ENABLED", False),
        # 现行默认改为本地目录读取；设 FENGCHE_SOURCE=ftp 可切回旧的 FTP 服务器。
        source_kind=(_env("FENGCHE_SOURCE", "local") or "local").lower(),
        local_base_dir=_env("FENGCHE_LOCAL_BASE_DIR", "/bigdata/fengche-suzhou")
        or "/bigdata/fengche-suzhou",
        host=_env("FENGCHE_FTP_HOST", "10.127.13.197") or "10.127.13.197",
        port=_int("FENGCHE_FTP_PORT", 2123),
        user=_env("FENGCHE_FTP_USER", "fengche") or "fengche",
        password=_env("FENGCHE_FTP_PASSWORD", "") or "",
        base_dir=_env("FENGCHE_FTP_BASE_DIR", "/") or "/",
        path_template=_env("FENGCHE_PATH_TEMPLATE", "{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc")
        or "{Y}/{Ym}/{ymd}/{ymd}T{HH}.nc",
        max_lookback_hours=_int("FENGCHE_MAX_LOOKBACK_HOURS", 24),
        timeout=_int("FENGCHE_FTP_TIMEOUT_SEC", 30),
        encoding=_env("FENGCHE_FTP_ENCODING", "utf-8") or "utf-8",
        boundary_minute=_int("FENGCHE_BOUNDARY_MINUTE", 30),
        wait_minutes=_int("FENGCHE_WAIT_MINUTES", 15),
        gust_report_min_level=_int("FENGCHE_GUST_REPORT_MIN_LEVEL", 6),
    )

    obs = ObsSettings(
        enabled=_bool("OBS_ENABLED", False),
        # 实况数据在部署服务器本地（非 FTP），默认 local。
        source_kind=(_env("OBS_SOURCE", "local") or "local").lower(),
        # 生产根目录形如 /bigdata/data/aws/processed，目录按 UTC 年/月/日 分层。
        local_base_dir=_env("OBS_LOCAL_BASE_DIR", str(BASE_DIR / "data_samples" / "processed"))
        or str(BASE_DIR / "data_samples" / "processed"),
        path_template=_env("OBS_PATH_TEMPLATE", "{Y}/{m}/{d}/PROCESSED_{ymdHM}.xlsx")
        or "{Y}/{m}/{d}/PROCESSED_{ymdHM}.xlsx",
        half_hour_boundary=_bool("OBS_HALF_HOUR_BOUNDARY", False),
        step_minutes=_int("OBS_STEP_MINUTES", 10),
        max_lookback_minutes=_int("OBS_MAX_LOOKBACK_MINUTES", 60),
        gust_column=_env("OBS_GUST_COLUMN", "") or "",
        rain_threshold_mm=_float("OBS_RAIN_THRESHOLD_MM", 20.0),
        gust_threshold_level=_int("OBS_GUST_THRESHOLD_LEVEL", 7),
        upstream_half_angle_deg=_float("OBS_UPSTREAM_HALF_ANGLE_DEG", 90.0),
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
        z_layer_index=_int("Z_LAYER_INDEX", 3),
        nc_value_no_cover=_float("NC_NO_COVER", -32768.0),
        nc_value_no_echo=_float("NC_NO_ECHO", -128.0),
        wecom_webhook_url=_env("WECOM_WEBHOOK_URL", "") or "",
        state_dir=_env("STATE_DIR", str(BASE_DIR / "state")) or str(BASE_DIR / "state"),
        ftp=ftp,
        fengche=fengche,
        obs=obs,
        thresholds=thresholds,
        llm=llm,
    )
