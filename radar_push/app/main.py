"""主入口：后台定时扫描调度循环 + FastAPI /health。"""

from __future__ import annotations

import io
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
from .datasource import (
    build_datasource,
    build_fengche_datasource,
    build_obs_datasource,
)
from .dedup import DedupManager
from .echo_detect import (
    detect_clusters,
    level_floor,
    robust_value,
    strong_connected_mask,
)
from .extrapolation import analyze_extrapolation, threat_score
from .fengche_finder import find_forecast_for_target, resolve_target_start
from .fengche_rain import build_rainfall_forecast_line
from .fengche_reader import read_tp_at_lead
from .ftp_uploader import FtpUploader
from .geo import GeoRegistry
from .llm_polish import polish_text
from .nc_reader import read_et, read_treref, read_z
from .notifier import WecomNotifier
from .obs_finder import find_obs_for_observe_time
from .obs_reader import read_obs_xlsx
from .obs_realtime import build_realtime_line
from .plotter import render_radar_png
from .radar_finder import find_latest_z, has_et, has_treref
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
    "fengche_hits": 0,         # 风掣预报成功生成（命中文件并产出文案）的次数
    "fengche_misses": 0,       # 风掣启用但未命中文件/解析失败、回退占位符的次数
    "last_fengche": None,      # 最近一次风掣预报结果摘要
    "obs_hits": 0,             # 实况提醒成功生成（命中文件并产出达标文案）的次数
    "obs_misses": 0,           # 实况启用但未命中文件/无达标/解析失败的次数
    "last_obs": None,          # 最近一次实况提醒结果摘要
}


class RadarPushWorker:
    def __init__(self):
        self.settings = SETTINGS
        self.ds = build_datasource(self.settings)
        self.fengche_ds = (
            build_fengche_datasource(self.settings.fengche)
            if self.settings.fengche.enabled
            else None
        )
        self.obs_ds = (
            build_obs_datasource(self.settings)
            if self.settings.obs.enabled
            else None
        )
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
            full_coverage_ratio=self.settings.thresholds.full_coverage_ratio,
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

        rf = find_latest_z(self.ds)
        if rf is None:
            return
        if rf.timestamp == self._last_ts:
            return

        # 仅当本时次"完整处理结束"才标记为已处理：
        #   · 处理中抛异常 → 不标记，下一轮重试（避免中途报错漏掉整帧）；
        #   · 数据未就绪（Et/TreRef 缺失、网格不匹配，_process_timestamp 返回 False）
        #     → 不标记，待数据落盘后下一轮重试；
        #   · 正常处理完（含"无强回波""被去重/节流抑制"等正常 return，返回 True）
        #     → 标记为已处理，不再重复处理同一时次。
        try:
            processed = self._process_timestamp(rf)
        except Exception:
            log.exception("处理时次 %s 失败，本时次未标记，下轮将重试", rf.timestamp)
            raise
        if processed:
            self._last_ts = rf.timestamp
            _runtime["last_processed_ts"] = rf.timestamp

    def _process_timestamp(self, rf) -> bool:
        """处理单个时次。返回 True 表示已完整处理（可标记为已处理），
        返回 False 表示数据未就绪、本时次应在下一轮重试。"""
        observe_time = rf.dt_utc.astimezone(self.tz)
        log.info("processing Z ts=%s observe=%s", rf.timestamp, observe_time.isoformat())

        z_bytes = self.ds.open_binary(rf.z_rel_path)
        grid = read_z(
            z_bytes,
            observe_time=observe_time,
            layer_index=self.settings.z_layer_index,
            no_cover=self.settings.nc_value_no_cover,
            no_echo=self.settings.nc_value_no_echo,
            tz=self.settings.timezone,
        )

        th = self.settings.thresholds

        # CR≥35 且顶高 ET≥7km 同时满足才推送；Et 缺失时不推进 _last_ts，待落盘后重试
        if not has_et(self.ds, rf):
            log.info("Et 缺失：%s，等待顶高数据，本轮跳过（不推送）", rf.et_rel_path)
            return False

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
            return False

        # 外推产品 TreRef 缺失时，与 Et 同样处理：不推进 _last_ts，待落盘后重试。
        # 没有外推无法判断移动/趋势/是否入市，宁可等待也不发"默认占位"的预报文案。
        if not has_treref(self.ds, rf):
            log.info("TreRef 缺失：%s，等待外推数据，本轮跳过（不推送）", rf.treref_rel_path)
            return False

        # refl_raw：仅含强度信息的反射率（无 ET 过滤），用于"雷达监测"段——
        # 该段只描述实况强回波分布，不附加"对流顶高≥7km"的限定。
        refl_raw = grid.refl.copy()
        # refl_strong：在 refl_raw 基础上抹掉顶高不足（ET<et_min_km）的格点，
        # 用于推送决策、预报乡镇明细、强对流类型判别（"真对流"口径）。
        refl_strong = refl_raw.copy()
        low_top = ~(np.isfinite(et) & (et >= th.et_min_km))
        refl_strong[low_top] = np.nan

        masks = self.geo.build_for_grid(grid.lat_arr, grid.lon_arr)

        det = detect_clusters(
            refl_strong, masks.buffer_full, grid.lat_arr, grid.lon_arr,
            strong_dbz=th.strong_dbz, min_points=th.min_cluster_points,
            level_step=th.level_step_dbz, dist_to_city_km=masks.dist_to_city_km,
        )

        # 全网格"有效强回波"掩膜：仅保留四连通且≥min_points 的连片格点，
        # 推送/预报相关实况判断（市内最大值/区县/乡镇/上游/缓冲区）统一基于此。
        valid_strong = strong_connected_mask(
            refl_strong,
            strong_dbz=th.strong_dbz,
            min_points=th.min_cluster_points,
        )

        # "雷达监测"段专用：无 ET 过滤的强回波块与掩膜（仅 ≥strong_dbz + 连片）。
        det_mon = detect_clusters(
            refl_raw, masks.buffer_full, grid.lat_arr, grid.lon_arr,
            strong_dbz=th.strong_dbz, min_points=th.min_cluster_points,
            level_step=th.level_step_dbz, dist_to_city_km=masks.dist_to_city_km,
        )
        valid_strong_mon = strong_connected_mask(
            refl_raw,
            strong_dbz=th.strong_dbz,
            min_points=th.min_cluster_points,
        )

        if not det.has_strong:
            log.info("no strong echo (>=%.0fdBZ, >=%d pts) in buffer at %s",
                     th.strong_dbz, th.min_cluster_points, rf.timestamp)
            return True

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

        # ===== "雷达监测"段专用值（无 ET 过滤）=====
        # 最强回波等级与位置：取无 ET 过滤的全局最强块（即雷达上真正最强的回波，
        # 不受顶高限制）。det_mon 必非空（valid_strong 是其子集且已通过 has_strong）。
        mon_level_dbz = strongest.level_dbz
        mon_strongest_location = strongest_location
        if det_mon.clusters:
            mon_strongest = det_mon.clusters[0]
            mon_level_dbz = mon_strongest.level_dbz
            m_idx = int(np.argmax(refl_raw[mon_strongest.rows, mon_strongest.cols]))
            m_r = int(mon_strongest.rows[m_idx])
            m_c = int(mon_strongest.cols[m_idx])
            mon_strongest_location = ""
            for _code, _dmask in masks.districts.items():
                if _dmask[m_r, m_c]:
                    mon_strongest_location = masks.district_names.get(_code, _code)
                    break
            if not mon_strongest_location:
                for _cname, _cmask in masks.upstream_cities:
                    if _cmask[m_r, m_c]:
                        mon_strongest_location = _cname
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
        # 方向轨迹起点：用实况主威胁团（带 ET 过滤口径，威胁度=距市界近+强）的质心，
        # 把移动方向锚定到"实况正在盯的同一个团"，避免外推内部独立选团导致方向跳到别的团。
        current_centroid = None
        if det.clusters:
            cur = max(det.clusters, key=threat_score)
            current_centroid = (cur.centroid_lat, cur.centroid_lon)

        ex = analyze_extrapolation(
            seq.frames, seq.valid_times, masks,
            current_city_max_dbz=city_max,
            current_centroid=current_centroid,
            strong_dbz=th.strong_dbz, min_points=th.min_cluster_points,
            level_step=th.level_step_dbz,
        )
        direction = ex.direction
        trend = ex.trend
        will_enter = ex.will_enter_city
        extrap_affected = ex.affected

        # "雷达监测"段：无 ET 过滤的上游城市与本地区县（仅看强度+连片）。
        # 上游城市/区县均不再附加 ET 顶高条件——ET 只用于推送门槛与强对流类型判别。
        mon_out_buffer = bool((valid_strong_mon & masks.buffer_full & ~masks.city).any())
        mon_up_hits: list[tuple[str, int]] = []
        for cname, cmask in masks.upstream_cities:
            cnt = int((valid_strong_mon & cmask).sum())
            if cnt > 0:
                mon_up_hits.append((cname, cnt))
        mon_up_hits.sort(key=lambda x: x[1], reverse=True)
        mon_upstream_origin = [name for name, _ in mon_up_hits]
        mon_local_codes = [
            code for code, dmask in masks.districts.items()
            if (valid_strong_mon & dmask).any()
        ]
        mon_local_origin = "、".join(
            masks.district_names.get(c, c) for c in mon_local_codes
        )

        now_ts = time.time()

        # 风掣就绪门槛（与 Et/TreRef 同属"数据就绪"等待区，但置于此处——仅在已确认
        # 有强回波、可能要推送时才等待，避免"无强回波本就不推"的时次被风掣拖住）。
        # 关键：必须在任何去重决策（decide_approach/district/coverage）之前判断，
        #   未就绪时 return False 才不会推进去重状态，保证下一轮干净重试。
        rainfall_forecast_line, fengche_ready = self._build_fengche_line(observe_time)
        if not fengche_ready:
            log.info("风掣未就绪且未超时，本时次暂不推、下轮重试 at %s", rf.timestamp)
            return False

        decisions = []

        # 「市外逼近」推送须满足：外推判定会移入本市，或市内当前已有真对流强回波。
        # 否则即"强回波在缓冲区内、市外，且外推显示后续不会移入"——文案口径为
        # 「移动路径对我市无明显影响」，这类情况不应推送。
        # 注意：此时不调用 decide_approach，避免里程碑/等级状态被提前推进，
        #   以保证该团日后真正逼近入市时仍能正常触发首次/里程碑推送。
        city_has_strong_now = bool((valid_strong & masks.city).any())
        approach_affects_city = will_enter or city_has_strong_now

        if approach_affects_city:
            ap = self.dedup.decide_approach(
                observed_level=strongest.level_dbz,
                observed_max_dbz=strongest.robust_dbz,
                min_dist_to_city_km=float(min_dist),
                now_ts=now_ts,
            )
            if ap.should_push:
                decisions.append(("approach", ap))
        else:
            log.info(
                "市外缓冲区强回波但外推不入市（will_enter=False 且市内无强回波），"
                "approach 不推 at %s", rf.timestamp,
            )

        # affected_now：文案口径（无 ET 过滤）——决定预报段列出哪些区县/乡镇。
        # 推送决策（decide_district）单独用 ET 口径（valid_strong），二者解耦：
        #   · 列入文案：区县内有"无 ET 强回波"即可（与雷达监测段一致）
        #   · 触发推送：区县内有"ET≥7km 的真对流强回波"才计入 decisions
        affected_now: Dict[str, Set[str]] = {}
        for code, dmask in masks.districts.items():
            # 文案口径：无 ET 过滤的区县内强回波格点
            strong_d_mon = valid_strong_mon & dmask
            if strong_d_mon.any():
                tw: Set[str] = set()
                for tname, tcode, tmask in masks.townships:
                    if tcode == code and (strong_d_mon & tmask).any():
                        tw.add(tname)
                affected_now[code] = tw

            # 推送口径：ET 过滤后的区县内强回波，达标才参与去重/推送决策。
            # 区县代表强度取"第 min_points 高的格点值"（防单点杂波触发推送），
            # 而非区县内单点峰值。
            strong_d = valid_strong & dmask
            if strong_d.any():
                sub = refl_strong[strong_d]
                drobust = robust_value(sub, th.min_cluster_points)
                if not np.isfinite(drobust):
                    drobust = float(sub.max())
                dlevel = level_floor(drobust, th.level_step_dbz, th.strong_dbz)
                dd = self.dedup.decide_district(code, dlevel, drobust, now_ts)
                if dd.should_push:
                    decisions.append((code, dd))

        if not decisions:
            log.info("strong echo present but suppressed by dedup at %s", rf.timestamp)
            _runtime["dedup_suppressed"] = int(_runtime["dedup_suppressed"]) + 1
            self.dedup.save()
            return True

        merged: Dict[str, Set[str]] = {}
        for d in (affected_now, extrap_affected):
            for code, tws in d.items():
                merged.setdefault(code, set()).update(tws)

        will_enter_final = will_enter or bool(affected_now)

        # 各区县乡镇（街道）总数：供"大部分乡镇"折叠与覆盖范围抑制（规则7/8）判定共用。
        district_township_total: Dict[str, int] = {}
        for _tname, _tcode, _tmask in masks.townships:
            district_township_total[_tcode] = district_township_total.get(_tcode, 0) + 1

        # 覆盖维度（decide_coverage）：仅当"会影响本市"时纳入。
        # 注意：此处已确保 decisions 非空（前面强度/逼近/区县维度已命中要推），所以本帧
        #   必推；覆盖维度只作为"额外推送理由来源 + 状态维护"，绝不再一票否决整条推送
        #   ——避免出现"各区县仍≥45dBZ持续推、却因无新区县被覆盖抑制盖掉"的问题。
        # decide_coverage 始终调用以维护其内部状态（pushed_codes/last_push_level/
        #   full_coverage/last_seen_ts），否则全覆盖等判定会失准。
        if will_enter_final:
            affected_tw_counts = {
                code: len([t for t in tws if t])
                for code, tws in merged.items()
                if any(t for t in tws)
            }
            cov_dec = self.dedup.decide_coverage(
                affected_township_counts=affected_tw_counts,
                district_township_total=district_township_total,
                global_level=int(strongest.level_dbz),
                now_ts=now_ts,
            )
            if cov_dec.should_push:
                decisions.append(("coverage", cov_dec))

        # 全局节流：距上次推送不足窗口期则本轮不推（去重等级状态已在上面更新，不丢失）。
        if self.dedup.in_throttle_window(now_ts):
            wait_min = self.settings.thresholds.push_window_minutes
            log.info("命中节流窗口（%d 分钟内已推过），本轮不推 at %s", wait_min, rf.timestamp)
            _runtime["throttled"] = int(_runtime["throttled"]) + 1
            _runtime["last_throttled"] = datetime.now(self.tz).isoformat()
            self.dedup.save()
            return True

        # "雷达监测"段文案专用上游城市（无 ET 过滤口径）。
        if mon_out_buffer:
            mon_upstream_for_text = mon_upstream_origin or self.settings.upstream_cities
        else:
            mon_upstream_for_text = []

        # 预报段对流类型完全用实况 Z + 实况 ET 判别（不看外推 CR）：
        #   · 团已在市内（主威胁团有格点落入市界）→ 用整个市内的实况 Z/ET
        #   · 团尚未入市 → 用主威胁团（方向跟踪的同一团，带 ET 过滤口径）的实况 Z/ET
        # Z 取"代表值（第 min_points 高格点）"防单点杂波；ET 取范围内最大（顶高无尖峰问题）。
        cur_in_city = False
        if det.clusters:
            cur_in_city = bool(masks.city[cur.rows, cur.cols].any())

        if cur_in_city:
            # 市内实况 Z 稳健值 + 市内实况 ET 最大值。
            city_strong_vals = refl_strong[masks.city & valid_strong]
            convective_cr = robust_value(city_strong_vals, th.min_cluster_points)
            if not np.isfinite(convective_cr) and city_strong_vals.size:
                convective_cr = float(city_strong_vals.max())
            convective_et = city_et_max
        elif det.clusters:
            # 主威胁团（市外）的实况 Z 稳健值 + 团内实况 ET 最大值。
            convective_cr = cur.robust_dbz
            cur_et = et[cur.rows, cur.cols]
            cur_et = cur_et[np.isfinite(cur_et)]
            convective_et = float(cur_et.max()) if cur_et.size else strongest_et_km
        else:
            convective_cr = strongest.robust_dbz
            convective_et = city_et_max

        # 实况提醒行：按观测时刻取地面站点实况（市内/上游侧最大小时雨强 + 阵风）。
        # current_centroid 为实况主威胁团质心，供 direction=少动时按回波位置定上游侧。
        # 与雷达推送解耦，失败/无达标只记日志、返回空串（模板层整行不渲染）。
        realtime_line = self._build_realtime_line(
            observe_time, direction, current_centroid,
        )

        # 风掣 AI 降水预报行已在去重决策前生成（见上方"风掣就绪门槛"），此处直接使用。
        template_text = build_alert_text(
            observe_time=observe_time,
            level_dbz=mon_level_dbz,
            strongest_location=mon_strongest_location,
            max_dbz=convective_cr,
            max_et_km=convective_et,
            gale_cr_dbz=th.gale_cr_dbz,
            gale_et_km=th.gale_et_km,
            hail_cr_dbz=th.hail_cr_dbz,
            hail_et_km=th.hail_et_km,
            upstream_names=mon_upstream_for_text,
            local_origin_districts=mon_local_origin,
            direction=direction,
            trend=trend,
            will_enter_city=will_enter_final,
            affected=merged,
            district_names=masks.district_names,
            district_township_total=district_township_total,
            realtime_line=realtime_line,
            rainfall_forecast_line=rainfall_forecast_line,
        )

        # 正文（雷达监测/趋势预测/乡镇/实况）一律使用模板原文，不再做整段 LLM 润色——
        # AI 发挥仅限「风掣预报」行的"降水概况"短语（已在上游 build_rainfall_forecast_line
        # 内生成并嵌入模板）。如需恢复整段润色，调用 self._maybe_polish(...) 即可。
        text = template_text

        reasons = "; ".join(
            f"{k}:{','.join(dec.reasons)}" for k, dec in decisions
        )
        log.info("PUSH at %s reasons=[%s]\n%s", rf.timestamp, reasons, text)

        png = None
        try:
            move_arrow = None
            if ex.track_start is not None and ex.track_end is not None:
                move_arrow = (ex.track_start, ex.track_end)
            png = render_radar_png(
                grid,
                title_time=observe_time,
                move_arrow=move_arrow,
                move_direction=direction,
            )
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

        return True

    def _build_realtime_line(
        self,
        observe_time: datetime,
        direction: str,
        echo_centroid: Optional[tuple] = None,
    ) -> str:
        """生成「实况提醒」行。未启用/找不到文件/无达标实况/异常 → 返回空串。

        实况文件名时间为 UTC、记录过去 1 小时累计雨量；窗口由观测时刻对齐推出。
        echo_centroid 为回波主威胁团质心 (lat, lon)，用于 direction=少动时按回波位置定上游侧。
        与主推送解耦：任何异常只记日志、返回空串，模板层据此整行不渲染。
        """
        if self.obs_ds is None:
            return ""
        obs = self.settings.obs
        try:
            found = find_obs_for_observe_time(
                self.obs_ds,
                observe_time=observe_time,
                path_template=obs.path_template,
                half_hour_boundary=obs.half_hour_boundary,
                obs_step_minutes=obs.step_minutes,
                max_lookback_minutes=obs.max_lookback_minutes,
            )
            if found is None:
                self._record_obs(ok=False, reason="no_obs_file")
                return ""

            raw = self.obs_ds.open_binary(found.relative_path)
            stations = read_obs_xlsx(
                io.BytesIO(raw),
                gust_col_key=obs.gust_column or None,
            )
            line = build_realtime_line(
                stations=stations,
                geo=self.geo,
                direction=direction,
                echo_centroid=echo_centroid,
                window_start_local=found.window_start_local,
                window_end_local=found.window_end_local,
                rain_threshold_mm=obs.rain_threshold_mm,
                gust_threshold_level=obs.gust_threshold_level,
                upstream_half_angle_deg=obs.upstream_half_angle_deg,
            )
            if not line:
                self._record_obs(
                    ok=False, reason="no_qualifying_station",
                    file_uri=self.obs_ds.describe(found.relative_path),
                )
                return ""
            self._record_obs(
                ok=True,
                file_uri=self.obs_ds.describe(found.relative_path),
                window=f"{found.window_start_local.strftime('%H:%M')}-"
                       f"{found.window_end_local.strftime('%H:%M')}",
                line=line,
            )
            return line
        except Exception as e:
            log.exception("实况提醒行生成失败（已忽略，整行不显示）: %s", e)
            self._record_obs(ok=False, reason="exception", detail=str(e))
            return ""

    def _record_obs(self, *, ok: bool, **extra) -> None:
        """记录最近一次实况提醒结果到运行时状态，供 /health 暴露。"""
        if ok:
            _runtime["obs_hits"] = int(_runtime["obs_hits"]) + 1
        else:
            _runtime["obs_misses"] = int(_runtime["obs_misses"]) + 1
        entry: Dict[str, object] = {
            "ok": ok,
            "time": datetime.now(self.tz).isoformat(),
        }
        entry.update(extra)
        _runtime["last_obs"] = entry

    def _build_fengche_line(self, observe_time: datetime) -> tuple[str, bool]:
        """生成「风掣预报」行，返回 (line, ready)。

        ready=True  → 本时次风掣已"定稿"，可继续推送：
            · line 非空：找到文件并产出文案；
            · line 为空：放弃风掣（未启用 / 等待超时 / 解析异常），该行整行省略。
        ready=False → 风掣文件尚未就绪且未超过等待时限：调用方应 return False，
            本时次不推、下一轮重试（与外推/Et 的"待落盘"等待机制一致），
            以待风掣文件落盘后产出完整文案。

        等待判定：距观测时刻已过 fc.wait_minutes 分钟仍未找到文件即视为超时放弃。
        wait_minutes=0 表示不等待（找不到即放弃，行省略）。

        注：此处只生成确定性模板行；最终措辞润色统一交给全局 _maybe_polish 一次完成。
        """
        if self.fengche_ds is None:
            return "", True
        fc = self.settings.fengche
        target_start = resolve_target_start(observe_time, fc.boundary_minute)
        span = f"{target_start.hour}-{(target_start.hour + 1) % 24}时"
        try:
            found = find_forecast_for_target(
                self.fengche_ds,
                target_start=target_start,
                path_template=fc.path_template,
                max_lookback_hours=fc.max_lookback_hours,
            )
            if found is None:
                # 距观测时刻已等待的分钟数（用真实当前时刻；回放时 wait_minutes=0 直接放弃）。
                elapsed_min = (time.time() - observe_time.timestamp()) / 60.0
                if fc.wait_minutes > 0 and elapsed_min < fc.wait_minutes:
                    log.info(
                        "风掣预报：未找到覆盖 %s 的就绪文件，已等待 %.1f/%d 分钟，本时次暂不推、下轮重试",
                        target_start.isoformat(), elapsed_min, fc.wait_minutes,
                    )
                    self._record_fengche(
                        ok=False, target_span=span,
                        reason="waiting",
                        detail=f"等待风掣文件 {elapsed_min:.1f}/{fc.wait_minutes}min",
                    )
                    return "", False
                log.info(
                    "风掣预报：未找到覆盖 %s 的就绪文件且已超过等待时限（%.1f>=%dmin），放弃风掣行",
                    target_start.isoformat(), elapsed_min, fc.wait_minutes,
                )
                self._record_fengche(
                    ok=False, target_span=span,
                    reason="no_forecast_file_timeout",
                    detail=f"超时未就绪，放弃（{elapsed_min:.1f}/{fc.wait_minutes}min）",
                )
                return "", True

            nc_bytes = self.fengche_ds.open_binary(found.relative_path)
            tp_grid = read_tp_at_lead(nc_bytes, found.lead_hour)
            fc_masks = self.geo.build_for_grid(tp_grid.lat_arr, tp_grid.lon_arr)

            start_hour = target_start.hour
            end_hour = (start_hour + 1) % 24
            # 传入 LLM：仅在固定明细前插入一句"降水概况"定性短语（不含数值），
            #   数值明细仍由代码原样拼接。风掣行不再交给全局 _maybe_polish 改写
            #   （_maybe_polish 已约定保持风掣行原样），避免精心固定的明细被二次改动。
            line, districts = build_rainfall_forecast_line(
                tp_grid=tp_grid,
                masks=fc_masks,
                start_hour=start_hour,
                end_hour=end_hour,
                llm=self.settings.llm if self.settings.llm.enabled else None,
            )
            log.info("风掣预报行（lead=%dh, %d个区县有雨）：%s",
                     found.lead_hour, len(districts), line)
            self._record_fengche(
                ok=True, target_span=span,
                issue_time=found.issue_time.isoformat(),
                lead_hour=found.lead_hour,
                rain_districts=len(districts),
                file_uri=self.fengche_ds.describe(found.relative_path),
                line=line,
            )
            return line, True
        except Exception as e:
            # 文件找到了但解析/统计失败：不再无意义等待，放弃风掣行（ready=True）。
            log.exception("风掣预报行生成失败（已忽略，整行省略）: %s", e)
            self._record_fengche(
                ok=False, target_span=span,
                reason="exception", detail=str(e),
            )
            return "", True

    def _record_fengche(self, *, ok: bool, target_span: str, **extra) -> None:
        """记录最近一次风掣预报结果到运行时状态，供 /health 暴露。"""
        if ok:
            _runtime["fengche_hits"] = int(_runtime["fengche_hits"]) + 1
        else:
            _runtime["fengche_misses"] = int(_runtime["fengche_misses"]) + 1
        entry: Dict[str, object] = {
            "ok": ok,
            "target_span": target_span,
            "time": datetime.now(self.tz).isoformat(),
        }
        entry.update(extra)
        _runtime["last_fengche"] = entry

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
        realtime_line: str = "",
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
        # 实况提醒里的站点定位（括号内地点）必须原样保留，防止 LLM 改写地名。
        if realtime_line:
            import re as _re
            for loc in _re.findall(r"（([^（）]*?)）", realtime_line):
                # 括号里形如「N级，吴中区东山站」或「吴中区东山站」，取末段地点
                name = loc.split("，")[-1].strip()
                if name:
                    must_keep.append(name)

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
        "fengche_enabled": SETTINGS.fengche.enabled,
        "fengche_source": SETTINGS.fengche.source_kind if SETTINGS.fengche.enabled else None,
        "fengche_location": (
            (
                SETTINGS.fengche.local_base_dir
                if SETTINGS.fengche.source_kind == "local"
                else f"{SETTINGS.fengche.host}:{SETTINGS.fengche.port}"
            )
            if SETTINGS.fengche.enabled else None
        ),
        "fengche_boundary_minute": (
            SETTINGS.fengche.boundary_minute if SETTINGS.fengche.enabled else None
        ),
        "obs_enabled": SETTINGS.obs.enabled,
        "obs_source": SETTINGS.obs.source_kind if SETTINGS.obs.enabled else None,
        "obs_thresholds": (
            {
                "rain_mm": SETTINGS.obs.rain_threshold_mm,
                "gust_level": SETTINGS.obs.gust_threshold_level,
            }
            if SETTINGS.obs.enabled else None
        ),
        "runtime": _runtime,
    }
