"""演示脚本：用人造的天气场触发多区多级预警，打印一份完整的工具响应。

构造逻辑：
- 在最近一份真实风掣文件（覆盖范围、坐标轴、起报时间均真实）的基础上
- 用 numpy 替换 gs / tp 场，让东半部（昆山/工业园区/吴中等）出现强对流大风、
  西部（吴江/虎丘）出现持续暴雨过程，覆盖 1h / 6h / 24h 三种触发窗口。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

import numpy as np


def main() -> int:
    ROOT = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DATA_SOURCE", "local")
    os.environ.setdefault("LOCAL_BASE_DIR", str(ROOT / "fengche"))

    from fengche_tool_server.app.forecast_finder import find_latest_forecast
    from fengche_warning_server.app.config import build_datasource, load_settings
    from fengche_warning_server.app.district_mask import DistrictMaskRegistry
    from fengche_warning_server.app.nc_reader_grid import (
        ForecastGrid,
        read_forecast_grid,
    )
    from fengche_warning_server.app.summary import build_summary
    from fengche_warning_server.app.warning_engine import evaluate_all

    s = load_settings()
    ds = build_datasource(s)
    now = datetime(2026, 6, 5, 13, 38, tzinfo=ZoneInfo("Asia/Shanghai"))
    found = find_latest_forecast(
        ds, now, s.max_lookback_hours, path_template=s.path_template
    )
    if found is None:
        print("[ERROR] no forecast file found")
        return 1
    grid = read_forecast_grid(ds.open_binary(found.relative_path), tz=s.timezone)

    n_step, n_lat, n_lon = grid.gs.shape
    lat_arr = grid.lat_arr
    lon_arr = grid.lon_arr

    # ----- 构造 gs：东部 lon>120.9 区域第 3~5 步出现 26 m/s 阵风（橙色级） -----
    fake_gs = np.full((n_step, n_lat, n_lon), 1.5, dtype=np.float32)
    east_mask = lon_arr >= 120.9
    fake_gs[3:6, :, east_mask] = 26.0
    # 东部第 6~7 步降到 18 m/s（黄色级），让段合并能演示「橙→黄」过渡
    fake_gs[6:8, :, east_mask] = 18.5

    # ----- 构造 tp：西部 lon<120.6 区域 3 种窗口都触发 -----
    fake_tp = np.zeros((n_step, n_lat, n_lon), dtype=np.float32)
    west_mask = lon_arr <= 120.6
    # (1) 第 4 步：1h 局地强降水 60mm/h（→ 1h 黄色）
    fake_tp[4, :, west_mask] = 60.0
    # (2) 第 8~13 步：每小时 18mm，连续 6 小时 = 108mm → 6h 黄
    fake_tp[8:14, :, west_mask] = 18.0
    # (3) 第 14~23 步：每小时 9mm，让 24h 累计达约 222mm → 24h 橙
    fake_tp[14:24, :, west_mask] = 9.0

    g2 = ForecastGrid(
        issue_time=grid.issue_time,
        lat_arr=lat_arr,
        lon_arr=lon_arr,
        step_arr=grid.step_arr,
        valid_times=grid.valid_times,
        gs=fake_gs,
        tp=fake_tp,
        coverage_lat=grid.coverage_lat,
        coverage_lon=grid.coverage_lon,
    )

    reg = DistrictMaskRegistry()
    masks = reg.build_for_grid(g2.lat_arr, g2.lon_arr)
    out = evaluate_all(
        grid=g2,
        masks=masks,
        thresholds=s.thresholds,
        gs_coverage_ratio=0.0,
        rain_coverage_ratio=0.0,
    )

    summary = build_summary(
        issue_time=g2.issue_time,
        districts=out,
        forecast_hours=int(g2.gs.shape[0]),
    )

    response: Dict[str, Any] = {
        "query": {
            "request_time": now.isoformat(),
            "trigger_mode": "any_point_hit",
            "trigger_mode_desc": "区内任意格点达到阈值即提示发布对应级别预警信号",
            "districts": list(out.keys()),
        },
        "forecast_source": {
            "issue_time": g2.issue_time.isoformat(),
            "file_uri": ds.describe(found.relative_path) + "  [DEMO 数据：gs/tp 已替换]",
            "fallback_steps_back": found.steps_back,
            "data_source_kind": ds.kind,
        },
        "coverage": {
            "lat": list(g2.coverage_lat),
            "lon": list(g2.coverage_lon),
        },
        "districts": out,
        "summary": summary,
    }

    out_path = ROOT / "fengche_warning_server" / "scripts" / "demo_sample_output.json"
    out_path.write_text(
        json.dumps(response, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    summary_path = ROOT / "fengche_warning_server" / "scripts" / "demo_sample_output.txt"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"wrote: {out_path}")
    print(f"wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
