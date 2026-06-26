"""一次性脚本：检查三个区在所有 .nc 样本里的 gs / tp 极值，
帮助判断「为什么没出预警」是逻辑 bug 还是数据本身就没达阈值。

用法：
    python -m fengche_warning_server.scripts.inspect_district_values
"""

from __future__ import annotations

import glob
import io
import os
import sys


def main() -> int:
    from fengche_warning_server.app.district_mask import DistrictMaskRegistry
    from fengche_warning_server.app.nc_reader_grid import read_forecast_grid

    pattern = os.path.join("fengche", "20260507", "*.nc")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"no nc files under {pattern}")
        return 1

    registry = DistrictMaskRegistry()
    masks_cache = None

    print(f"{'file':32s}  {'code':8s}  {'gs_max':>8s}  {'tp_max':>8s}  {'tp_sum_max_pt':>14s}")
    print("-" * 80)

    for path in files:
        with open(path, "rb") as f:
            grid = read_forecast_grid(io.BytesIO(f.read()))
        if masks_cache is None:
            masks_cache = registry.build_for_grid(grid.lat_arr, grid.lon_arr)
        for code, dm in masks_cache.items():
            gs_max = float(grid.gs[:, dm.mask].max()) if dm.n_points else float("nan")
            tp_max = float(grid.tp[:, dm.mask].max()) if dm.n_points else float("nan")
            tp_sum_per_pt = grid.tp[:, dm.mask].sum(axis=0) if dm.n_points else None
            tp_sum_max = float(tp_sum_per_pt.max()) if tp_sum_per_pt is not None else float("nan")
            print(
                f"{os.path.basename(path):32s}  {code:8s}  "
                f"{gs_max:8.2f}  {tp_max:8.3f}  {tp_sum_max:14.3f}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
