"""端到端真实测试：构造合成网格场景，跑真实算法管线并打印推送文本。

复用真实模块：
  - geo.GeoRegistry          真实苏州 geojson 掩膜
  - echo_detect.detect_clusters
  - extrapolation.analyze_extrapolation
  - templates.build_alert_text（含 CR/ET 对流类型判别、AI预报员短临提醒抬头）

不依赖 SFTP / nc 文件：反射率/顶高/外推帧均为本脚本合成，
目的在于验证“方向、趋势、对流类型话术、抬头”在真实掩膜上的输出。

运行：
  C:\\Users\\DELL\\.conda\\envs\\leadsee-webui\\python.exe radar_push/scripts/try_pipeline.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认 GBK，统一切到 UTF-8，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app.echo_detect import detect_clusters, level_floor  # noqa: E402
from app.extrapolation import analyze_extrapolation  # noqa: E402
from app.geo import GeoRegistry  # noqa: E402
from app.templates import build_alert_text  # noqa: E402


# 阈值（与 config 默认一致：CR≥35 且 ET≥7km 才推送；分级阈值见下）
STRONG_DBZ = 35.0
ET_MIN_KM = 7.0
MIN_PTS = 4
LEVEL_STEP = 5.0
GALE_CR, GALE_ET = 45.0, 9.0
HAIL_CR, HAIL_ET = 55.0, 12.0


def make_grid() -> Tuple[np.ndarray, np.ndarray]:
    """覆盖苏州及周边的规则经纬网格，约 1km 分辨率。"""
    lat = np.arange(30.3, 32.4, 0.01)   # 南->北
    lon = np.arange(119.3, 121.7, 0.01)  # 西->东
    return lat, lon


def _idx(arr: np.ndarray, val: float) -> int:
    return int(np.argmin(np.abs(arr - val)))


def blob(field: np.ndarray, lat, lon, clat, clon, peak, radius_deg=0.08):
    """在 (clat,clon) 处叠加一个高斯型回波团，峰值 peak。"""
    la = lat[:, None]
    lo = lon[None, :]
    r2 = ((la - clat) ** 2 + (lo - clon) ** 2) / (radius_deg ** 2)
    field += peak * np.exp(-r2)


def build_refl_et(lat, lon, blobs):
    """blobs: [(clat,clon,cr_peak,et_peak,radius), ...] -> (refl, et)。"""
    refl = np.full((lat.size, lon.size), np.nan)
    et = np.full((lat.size, lon.size), np.nan)
    base_r = np.zeros((lat.size, lon.size))
    base_e = np.zeros((lat.size, lon.size))
    for (clat, clon, crp, etp, rad) in blobs:
        blob(base_r, lat, lon, clat, clon, crp, rad)
        blob(base_e, lat, lon, clat, clon, etp, rad)
    # 只在有意义的回波处赋值，其余维持 NaN（模拟无回波/缺测）
    mask = base_r >= 10.0
    refl[mask] = base_r[mask]
    et[mask] = base_e[mask]
    return refl, et


def run_scenario(geo, name, observe_time, now_blobs, future_centers, future_peak_et):
    """跑单个场景：now_blobs 决定实况；future_centers 决定外推质心轨迹。

    future_centers: [(clat,clon,cr_peak,et_peak), ...] 未来帧主回波团中心序列。
    """
    lat, lon = make_grid()
    masks = geo.build_for_grid(lat, lon)
    th = dict(strong_dbz=STRONG_DBZ, min_points=MIN_PTS, level_step=LEVEL_STEP)

    # ---- 实况 ----
    refl, et = build_refl_et(lat, lon, now_blobs)
    refl_strong = refl.copy()
    low_top = ~(np.isfinite(et) & (et >= ET_MIN_KM))
    refl_strong[low_top] = np.nan

    det = detect_clusters(
        refl_strong, masks.buffer_full, lat, lon,
        dist_to_city_km=masks.dist_to_city_km, **th,
    )
    if not det.has_strong:
        print(f"\n===== {name} =====\n[无强回波满足 CR≥35 且 ET≥7km，不推送]")
        return

    strongest = det.clusters[0]
    et_in = et[strongest.rows, strongest.cols]
    et_in = et_in[np.isfinite(et_in)]
    strongest_et = float(et_in.max()) if et_in.size else 0.0

    city_vals = refl_strong[masks.city & np.isfinite(refl_strong)]
    city_max = float(city_vals.max()) if city_vals.size else float("nan")

    # ---- 外推帧序列（未来 10 帧）----
    frames = []
    vts = []
    for k, (clat, clon, crp, etp) in enumerate(future_centers):
        fr, fe = build_refl_et(lat, lon, [(clat, clon, crp, etp, 0.08)])
        fs = fr.copy()
        fs[~(np.isfinite(fe) & (fe >= ET_MIN_KM))] = np.nan
        frames.append(fs)
        vts.append(observe_time + timedelta(minutes=6 * (k + 1)))
    frames = np.stack(frames) if frames else np.empty((0, lat.size, lon.size))

    if frames.shape[0] >= 1:
        ex = analyze_extrapolation(
            frames, vts, masks, current_city_max_dbz=city_max,
            strong_dbz=STRONG_DBZ, min_points=MIN_PTS, level_step=LEVEL_STEP,
        )
        direction, trend, will_enter = ex.direction, ex.trend, ex.will_enter_city
        extrap_affected = ex.affected
    else:
        direction, trend, will_enter, extrap_affected = "少动", "维持", True, {}

    # ---- 来源 / 上游 / 本地 ----
    strong_grid = np.isfinite(refl_strong) & (refl_strong >= STRONG_DBZ)
    out_buffer = bool((strong_grid & masks.buffer_full & ~masks.city).any())
    upstream_hits: List[Tuple[str, int]] = []
    for cname, cmask in masks.upstream_cities:
        cnt = int((strong_grid & cmask).sum())
        if cnt > 0:
            upstream_hits.append((cname, cnt))
    upstream_hits.sort(key=lambda x: x[1], reverse=True)
    upstream_origin = [n for n, _ in upstream_hits]

    affected_now: Dict[str, Set[str]] = {}
    for code, dmask in masks.districts.items():
        sub = refl_strong[dmask & np.isfinite(refl_strong)]
        if sub.size == 0 or float(sub.max()) < STRONG_DBZ:
            continue
        tw: Set[str] = set()
        strong_d = strong_grid & dmask
        for tname, tcode, tmask in masks.townships:
            if tcode == code and (strong_d & tmask).any():
                tw.add(tname)
        affected_now[code] = tw

    merged: Dict[str, Set[str]] = {}
    for d in (affected_now, extrap_affected):
        for code, tws in d.items():
            merged.setdefault(code, set()).update(tws)

    local_origin = "、".join(
        masks.district_names.get(c, c) for c in affected_now.keys()
    )
    upstream_for_text = (upstream_origin or []) if out_buffer else []
    will_enter_final = will_enter or bool(affected_now)

    text = build_alert_text(
        observe_time=observe_time,
        level_dbz=strongest.level_dbz,
        max_dbz=strongest.max_dbz,
        max_et_km=strongest_et,
        gale_cr_dbz=GALE_CR, gale_et_km=GALE_ET,
        hail_cr_dbz=HAIL_CR, hail_et_km=HAIL_ET,
        upstream_names=upstream_for_text,
        local_origin_districts=local_origin,
        direction=direction,
        trend=trend,
        will_enter_city=will_enter_final,
        affected=merged,
        district_names=masks.district_names,
    )

    print(f"\n===== {name} =====")
    print(f"[算法判定] 最强块 CR={strongest.max_dbz:.1f}dBZ(等级{strongest.level_dbz}) "
          f"ET={strongest_et:.1f}km | 方向={direction} 趋势={trend} "
          f"影响本市={'是' if will_enter_final else '否'} "
          f"上游={upstream_for_text or '无'} 本地={local_origin or '无'}")
    print("[推送文本]")
    print(text)


def main():
    geo = GeoRegistry()
    OB = datetime(2026, 6, 13, 12, 48)

    # 苏州大致中心约 (31.3, 120.6)；上游湖州在西南(~30.9,120.0)、无锡西(~31.5,120.3)
    # 上海在东(~31.2,121.4)。市内高新区约(31.3,120.5)。

    # 场景1：上游湖州方向(西南)移入，向东北移动、增强；CR48 ET10 -> 含雷暴大风
    run_scenario(
        geo, "场景1 上游移入·东北移·增强·CR48/ET10", OB,
        now_blobs=[(30.95, 120.05, 48, 10.5, 0.09)],
        future_centers=[
            (30.95 + 0.04 * k, 120.05 + 0.05 * k, 48, 10.5) for k in range(10)
        ],
        future_peak_et=10.5,
    )

    # 场景2：市内局地生成，少动、维持；CR40 ET8 -> 仅短时强降水
    run_scenario(
        geo, "场景2 本地生成·少动·维持·CR40/ET8", OB,
        now_blobs=[(31.30, 120.55, 40, 8.0, 0.07)],
        future_centers=[(31.30, 120.55, 40, 8.0) for _ in range(10)],
        future_peak_et=8.0,
    )

    # 场景3：超强单体，向东南移动；CR58 ET13 -> 含局地小冰雹
    run_scenario(
        geo, "场景3 强单体·东南移·CR58/ET13(冰雹)", OB,
        now_blobs=[(31.55, 120.45, 58, 13.5, 0.08)],
        future_centers=[
            (31.55 - 0.03 * k, 120.45 + 0.04 * k, 58, 13.5) for k in range(10)
        ],
        future_peak_et=13.5,
    )

    # 场景4：缓冲区有强回波但外推不入市（向西北远离）-> 无明显影响
    run_scenario(
        geo, "场景4 上游强回波·向西北远离·无明显影响", OB,
        now_blobs=[(30.85, 119.95, 50, 11.0, 0.08)],
        future_centers=[
            (30.85 - 0.03 * k, 119.95 - 0.04 * k, 50, 11.0) for k in range(10)
        ],
        future_peak_et=11.0,
    )

    # 场景5：CR够强(58)但ET不足(10<12)->到雷暴大风为止，不报冰雹
    run_scenario(
        geo, "场景5 CR58但ET10·只到雷暴大风", OB,
        now_blobs=[(31.40, 120.40, 58, 10.0, 0.08)],
        future_centers=[(31.40, 120.40, 58, 10.0) for _ in range(10)],
        future_peak_et=10.0,
    )

    # 场景6：ET不足7km -> 不满足推送条件
    run_scenario(
        geo, "场景6 CR50但ET6·不满足ET≥7·不推送", OB,
        now_blobs=[(31.30, 120.55, 50, 6.0, 0.08)],
        future_centers=[(31.30, 120.55, 50, 6.0) for _ in range(10)],
        future_peak_et=6.0,
    )


if __name__ == "__main__":
    main()
