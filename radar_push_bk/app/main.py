"""主入口：后台定时扫描调度循环 + FastAPI /health。"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import FastAPI

from . import __version__
from .config import load_settings
from .datasource import build_datasource
from .dedup import DedupManager
from .echo_detect import detect_clusters, level_floor, strong_connected_mask
from .extrapolation import analyze_extrapolation
from .ftp_uploader import FtpUploader
from .geo import GeoRegistry
from .llm_polish import polish_text
from .nc_reader import read_cr, read_et, read_treref
from .notifier import WecomNotifier
from .plotter import render_radar_png
from .radar_finder import find_latest_cr, has_et, has_treref
from .templates import _convective_phrase, _fmt_time, build_alert_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("radar_push")


SETTINGS = load_settings()
app = FastAPI(title="Radar Push Service", version=__version__)

_runtime: Dict[str, object] = {
    "last_scan": None,
    "last_processed_ts": None,
    "last_push": None,
    "last_error": None,
    "scans": 0,
    "pushes": 0,
    "throttled": 0,            # 命中节流窗口被抑制的次数
    "dedup_suppressed": 0,     # 有强回波但被去重抑制的次数
    "last_throttled": None,    # 最近一次被节流抑制的时间戳
    "ftp_uploads": 0,          # FTP 上传成功次数
    "last_ftp": None,          # 最近一次 FTP 上传结果
}


class RadarPushWorker:
    def __init__(self):
        self.settings = SETTINGS
        self.ds = build_datasource(self.settings)
        self.geo = GeoRegistry()
        self.notifier = WecomNotifier(self.settings.wecom_webhook_url)
        self.ftp = FtpUploader(self.settings.ftp)
        self.dedup = DedupManager(
            self.settings.state_dir,
            level_step=self.settings.thresholds.level_step_dbz,
            redalert_dbz=self.settings.thresholds.redalert_dbz,
            strong_dbz=self.settings.thresholds.strong_dbz,
            boundary_milestones_km=self.settings.thresholds.boundary_km_milestones,
            push_window_minutes=self.settings.thresholds.push_window_minutes,
        )
        self.tz = ZoneInfo(self.settings.timezone)
        self._last_ts: Optional[str] = None
        self._stop = threading.Event()

    def run_forever(self):
        log.info("RadarPushWorker started (interval=%ds, source=%s)",
                 self.settings.scan_interval_sec, self.ds.kind)
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as e:
                log.exception("scan_once failed: %s", e)
                _runtime["last_error"] = f"{datetime.now(self.tz).isoformat()}: {e}"
            self._stop.wait(self.settings.scan_interval_sec)

    def stop(self):
        self._stop.set()

    def scan_once(self):
        _runtime["scans"] = int(_runtime["scans"]) + 1
        _runtime["last_scan"] = datetime.now(self.tz).isoformat()

        rf = find_latest_cr(self.ds)
        if rf is None:
            return
        if rf.timestamp == self._last_ts:
            return

        observe_time = rf.dt_utc.astimezone(self.tz)
        log.info("processing Cr ts=%s observe=%s", rf.timestamp, observe_time.isoformat())

        cr_bytes = self.ds.open_binary(rf.cr_rel_path)
        grid = read_cr(
            cr_bytes,
            observe_time=observe_time,
            no_cover=self.settings.nc_value_no_cover,
            no_echo=self.settings.nc_value_no_echo,
            tz=self.settings.timezone,
        )

        th = self.settings.thresholds

        # CR≥35 且顶高 ET≥7km 同时满足才推送；Et 缺失时不推进 _last_ts，待落盘后重试
        if not has_et(self.ds, rf):
            log.info("Et 缺失：%s，等待顶高数据，本轮跳过（不推送）", rf.et_rel_path)
            return

        et_bytes = self.ds.open_binary(rf.et_rel_path)
        et = read_et(
            et_bytes,
            no_cover=self.settings.nc_value_no_cover,
            no_echo=self.settings.nc_value_no_echo,
        )
        if et.shape != grid.refl.shape:
            log.warning(
                "Et 网格形状 %s 与 Cr %s 不一致，本轮跳过（不推送）",
                et.shape, grid.refl.shape,
            )
            return

        # 外推产品 TreRef 缺失时，与 Et 同样处理：不推进 _last_ts，待落盘后重试。
        # 没有外推无法判断移动/趋势/是否入市，宁可等待也不发"默认占位"的预报文案。
        if not has_treref(self.ds, rf):
            log.info("TreRef 缺失：%s，等待外推数据，本轮跳过（不推送）", rf.treref_rel_path)
            return

        refl_strong = grid.refl.copy()
        low_top = ~(np.isfinite(et) & (et >= th.et_min_km))
        refl_strong[low_top] = np.nan

        masks = self.geo.build_for_grid(grid.lat_arr, grid.lon_arr)

        det = detect_clusters(
            refl_strong, masks.buffer_full, grid.lat_arr, grid.lon_arr,
            strong_dbz=th.strong_dbz, min_points=th.min_cluster_points,
            level_step=th.level_step_dbz, dist_to_city_km=masks.dist_to_city_km,
        )

        # 全网格"有效强回波"掩膜：仅保留四连通且≥min_points 的连片格点，
        # 所有实况判断（市内最大值/区县/乡镇/上游/缓冲区）统一基于此，
        # 不再以单个格点达标作为依据。
        valid_strong = strong_connected_mask(
            refl_strong,
            strong_dbz=th.strong_dbz,
            min_points=th.min_cluster_points,
        )

        self._last_ts = rf.timestamp
        _runtime["last_processed_ts"] = rf.timestamp

        if not det.has_strong:
            log.info("no strong echo (>=%.0fdBZ, >=%d pts) in buffer at %s",
                     th.strong_dbz, th.min_cluster_points, rf.timestamp)
            return

        city_vals = refl_strong[masks.city & valid_strong]
        city_max = float(city_vals.max()) if city_vals.size else float("nan")
        strongest = det.clusters[0]
        min_dist = strongest.min_dist_to_city_km
        if min_dist is None:
            min_dist = 9999.0

        et_in_cluster = et[strongest.rows, strongest.cols]
        et_in_cluster = et_in_cluster[np.isfinite(et_in_cluster)]
        strongest_et_km = float(et_in_cluster.max()) if et_in_cluster.size else 0.0

        # 最强回波峰值格点所在位置：苏州市内定位到区县；市外定位到上游城市；都不命中则留空。
        peak_idx = int(np.argmax(refl_strong[strongest.rows, strongest.cols]))
        peak_r = int(strongest.rows[peak_idx])
        peak_c = int(strongest.cols[peak_idx])
        strongest_location = ""
        for _code, _dmask in masks.districts.items():
            if _dmask[peak_r, peak_c]:
                strongest_location = masks.district_names.get(_code, _code)
                break
        if not strongest_location:
            for _cname, _cmask in masks.upstream_cities:
                if _cmask[peak_r, peak_c]:
                    strongest_location = _cname
                    break

        # 对流类型判别用"市内 ET 最大值"，与"未来影响本市"语义一致（不取可能在市外的最强块）。
        # 市内暂无有效 ET（回波尚未进市）时回退到实况最强块 ET。
        et_city = et[masks.city & np.isfinite(et)]
        city_et_max = float(et_city.max()) if et_city.size else strongest_et_km

        # 此处 TreRef 必然存在（缺失已在前面提前 return）。
        # will_enter 默认 False：仅当外推算出入市、或实况已影响区县时才判定"会影响本市"。
        will_enter = False
        direction = "少动"
        trend = "维持"
        extrap_affected: Dict[str, Set[str]] = {}
        tre_bytes = self.ds.open_binary(rf.treref_rel_path)
        seq = read_treref(
            tre_bytes,
            max_frames=self.settings.future_frames,
            skip_first=True,
            no_cover=self.settings.nc_value_no_cover,
            no_echo=self.settings.nc_value_no_echo,
            tz=self.settings.timezone,
        )
        ex = analyze_extrapolation(
            seq.frames, seq.valid_times, masks,
            current_city_max_dbz=city_max,
            strong_dbz=th.strong_dbz, min_points=th.min_cluster_points,
            level_step=th.level_step_dbz,
        )
        direction = ex.direction
        trend = ex.trend
        will_enter = ex.will_enter_city
        extrap_affected = ex.affected

        strong_grid = valid_strong
        out_buffer_now = bool((strong_grid & masks.buffer_full & ~masks.city).any())

        upstream_hits: list[tuple[str, int]] = []
        for cname, cmask in masks.upstream_cities:
            cnt = int((strong_grid & cmask).sum())
            if cnt > 0:
                upstream_hits.append((cname, cnt))
        upstream_hits.sort(key=lambda x: x[1], reverse=True)
        upstream_origin = [name for name, _ in upstream_hits]

        now_ts = time.time()
        decisions = []
        ap = self.dedup.decide_approach(
            observed_level=strongest.level_dbz,
            observed_max_dbz=strongest.max_dbz,
            min_dist_to_city_km=float(min_dist),
            now_ts=now_ts,
        )
        if ap.should_push:
            decisions.append(("approach", ap))

        affected_now: Dict[str, Set[str]] = {}
        for code, dmask in masks.districts.items():
            # 区县内"有效强回波"格点（已满足四连通≥min_points）
            strong_d = valid_strong & dmask
            if not strong_d.any():
                continue
            sub = refl_strong[strong_d]
            dmax = float(sub.max())
            dlevel = level_floor(dmax, th.level_step_dbz, th.strong_dbz)
            tw: Set[str] = set()
            for tname, tcode, tmask in masks.townships:
                if tcode == code and (strong_d & tmask).any():
                    tw.add(tname)
            affected_now[code] = tw
            dd = self.dedup.decide_district(code, dlevel, dmax, now_ts)
            if dd.should_push:
                decisions.append((code, dd))

        if not decisions:
            log.info("strong echo present but suppressed by dedup at %s", rf.timestamp)
            _runtime["dedup_suppressed"] = int(_runtime["dedup_suppressed"]) + 1
            self.dedup.save()
            return

        # 全局节流：距上次推送不足窗口期则本轮不推（去重等级状态已在上面更新，不丢失）。
        if self.dedup.in_throttle_window(now_ts):
            wait_min = self.settings.thresholds.push_window_minutes
            log.info("命中节流窗口（%d 分钟内已推过），本轮不推 at %s", wait_min, rf.timestamp)
            _runtime["throttled"] = int(_runtime["throttled"]) + 1
            _runtime["last_throttled"] = datetime.now(self.tz).isoformat()
            self.dedup.save()
            return

        merged: Dict[str, Set[str]] = {}
        for d in (affected_now, extrap_affected):
            for code, tws in d.items():
                merged.setdefault(code, set()).update(tws)

        local_origin = self._origin_districts_text(affected_now, masks.district_names)
        if out_buffer_now:
            upstream_for_text = upstream_origin or self.settings.upstream_cities
        else:
            upstream_for_text = []
        will_enter_final = will_enter or bool(affected_now)

        # 预报段对流类型用"外推未来市内最大 CR + 实况 ET"判别：
        # 外推产品无 ET，故顶高沿用实况；未来 CR 缺测（市内无强回波）时回退到实况 CR。
        forecast_cr = ex.max_dbz_in_city
        if not np.isfinite(forecast_cr):
            forecast_cr = strongest.max_dbz

        # 各区县乡镇（街道）总数：受影响占比≥阈值时文案折叠为"大部分乡镇（街道）"。
        district_township_total: Dict[str, int] = {}
        for _tname, _tcode, _tmask in masks.townships:
            district_township_total[_tcode] = district_township_total.get(_tcode, 0) + 1

        template_text = build_alert_text(
            observe_time=observe_time,
            level_dbz=strongest.level_dbz,
            strongest_location=strongest_location,
            max_dbz=forecast_cr,
            max_et_km=city_et_max,
            gale_cr_dbz=th.gale_cr_dbz,
            gale_et_km=th.gale_et_km,
            hail_cr_dbz=th.hail_cr_dbz,
            hail_et_km=th.hail_et_km,
            upstream_names=upstream_for_text,
            local_origin_districts=local_origin,
            direction=direction,
            trend=trend,
            will_enter_city=will_enter_final,
            affected=merged,
            district_names=masks.district_names,
            district_township_total=district_township_total,
        )

        text = self._maybe_polish(
            template_text,
            observe_time=observe_time,
            level_dbz=strongest.level_dbz,
            strongest_location=strongest_location,
            max_dbz=forecast_cr,
            max_et_km=city_et_max,
            upstream_for_text=upstream_for_text,
            local_origin=local_origin,
            direction=direction,
            trend=trend,
            will_enter_final=will_enter_final,
            merged=merged,
            district_names=masks.district_names,
        )

        reasons = "; ".join(
            f"{k}:{','.join(dec.reasons)}" for k, dec in decisions
        )
        log.info("PUSH at %s reasons=[%s]\n%s", rf.timestamp, reasons, text)

        png = None
        try:
            png = render_radar_png(grid, title_time=observe_time)
        except Exception as e:
            log.exception("render png failed: %s", e)

        ok = self.notifier.send_alert(text, png)
        if ok:
            self.dedup.mark_pushed(now_ts)
        self.dedup.save()
        if ok:
            _runtime["pushes"] = int(_runtime["pushes"]) + 1
            _runtime["last_push"] = {
                "ts": rf.timestamp,
                "time": observe_time.isoformat(),
                "text": text,
            }

        # 同步把本次推送结果（雷达图 + 文案）上传到 FTP 目录。
        # 与企业微信推送解耦：无论企业微信是否成功都尝试上传，且上传失败只记日志、
        # 不影响主流程（不抛异常、不回滚去重状态）。
        if self.ftp.enabled:
            base_name = f"radar_{observe_time.strftime('%Y%m%d_%H%M')}"
            try:
                up_ok = self.ftp.upload_alert(
                    base_name=base_name, text=text, png_bytes=png,
                )
                _runtime["last_ftp"] = {
                    "ts": rf.timestamp,
                    "base_name": base_name,
                    "ok": up_ok,
                    "time": datetime.now(self.tz).isoformat(),
                }
                if up_ok:
                    _runtime["ftp_uploads"] = int(_runtime["ftp_uploads"]) + 1
            except Exception as e:
                log.exception("FTP 上传异常（已忽略，不影响推送）: %s", e)

    @staticmethod
    def _origin_districts_text(affected_now, district_names) -> str:
        names = [district_names.get(c, c) for c in affected_now.keys()]
        return "、".join(names) if names else ""

    def _maybe_polish(
        self,
        template_text: str,
        *,
        observe_time: datetime,
        level_dbz: float,
        strongest_location: str = "",
        max_dbz: float,
        max_et_km: float,
        upstream_for_text: List[str],
        local_origin: str,
        direction: str,
        trend: str,
        will_enter_final: bool,
        merged: Dict[str, Set[str]],
        district_names: Dict[str, str],
    ) -> str:
        if not self.settings.llm.enabled:
            return template_text

        affected_names = [district_names.get(c, c) for c in merged.keys()]
        src_parts: List[str] = []
        src_parts.extend([n for n in upstream_for_text if n])
        if local_origin:
            src_parts.append(f"苏州{local_origin}")
        source = "、".join(src_parts) if src_parts else "本市"
        time_str = _fmt_time(observe_time)

        th = self.settings.thresholds
        convective = _convective_phrase(
            max_dbz, max_et_km,
            gale_cr_dbz=th.gale_cr_dbz, gale_et_km=th.gale_et_km,
            hail_cr_dbz=th.hail_cr_dbz, hail_et_km=th.hail_et_km,
        )

        facts: Dict[str, object] = {
            "发布时间": time_str,
            "强度等级": f"{level_dbz:.0f}dBZ",
            "最强回波位置": strongest_location or "（未定位）",
            "来源": source,
            "移动方向": direction,
            "趋势": trend,
            "是否影响本市": "是" if will_enter_final else "否",
            "受影响区县乡镇": "、".join(affected_names) if affected_names else "无",
            "对流天气现象（不得增删）": convective if will_enter_final else "无",
        }

        must_keep: List[str] = [time_str]
        if strongest_location:
            must_keep.append(strongest_location)
        must_keep.extend(affected_names)
        must_keep.extend(upstream_for_text)
        if local_origin:
            must_keep.append(local_origin)
        if will_enter_final:
            must_keep.extend(convective.split("、"))

        # 落款已并入标题、正文无独立落款，不再强制句尾落款。
        return polish_text(self.settings.llm, template_text, facts, must_keep, tail="")


_worker: Optional[RadarPushWorker] = None
_thread: Optional[threading.Thread] = None


@app.on_event("startup")
def _startup():
    global _worker, _thread
    _worker = RadarPushWorker()
    _thread = threading.Thread(target=_worker.run_forever, daemon=True)
    _thread.start()
    log.info("startup complete; worker thread running")


@app.on_event("shutdown")
def _shutdown():
    if _worker is not None:
        _worker.stop()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "data_source": SETTINGS.data_source_kind,
        "timezone": SETTINGS.timezone,
        "scan_interval_sec": SETTINGS.scan_interval_sec,
        "push_window_minutes": SETTINGS.thresholds.push_window_minutes,
        "webhook_configured": bool(SETTINGS.wecom_webhook_url),
        "ftp_upload_enabled": SETTINGS.ftp.enabled,
        "ftp_remote_dir": SETTINGS.ftp.remote_dir if SETTINGS.ftp.enabled else None,
        "runtime": _runtime,
    }
