"""在服务器上预览一张雷达实况图（不推送、不依赖 Et/TreRef）。

复用主程序的数据源与绘图逻辑：拉取"当前最新一帧 Cr 实况"，渲染成 PNG 落盘到
state/ 目录（compose 已把 state 挂载到宿主机，便于直接查看/下载）。

用法（容器内）：
    docker exec -it radar-push python scripts/preview_image.py
    # 生成 /app/state/preview_radar.png -> 宿主机 radar_push/state/preview_radar.png

可选参数：
    --out <path>   指定输出文件路径（默认 state/preview_radar.png）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402
from app.datasource import build_datasource  # noqa: E402
from app.nc_reader import read_cr  # noqa: E402
from app.plotter import render_radar_png  # noqa: E402
from app.radar_finder import find_latest_cr  # noqa: E402


def main() -> int:
    out = ROOT / "state" / "preview_radar.png"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])

    settings = load_settings()
    print(f"数据源：{settings.data_source_kind}")
    ds = build_datasource(settings)

    rf = find_latest_cr(ds)
    if rf is None:
        print("！未找到任何 Cr 实况文件，请检查数据源/目录/当天是否有数据。")
        return 1
    observe_time = rf.dt_utc.astimezone(__import__("zoneinfo").ZoneInfo(settings.timezone))
    print(f"最新实况：{rf.cr_rel_path}")
    print(f"观测时刻（{settings.timezone}）：{observe_time.strftime('%Y-%m-%d %H:%M')}")

    cr_bytes = ds.open_binary(rf.cr_rel_path)
    grid = read_cr(
        cr_bytes,
        observe_time=observe_time,
        no_cover=settings.nc_value_no_cover,
        no_echo=settings.nc_value_no_echo,
        tz=settings.timezone,
    )

    png = render_radar_png(grid, title_time=observe_time)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"已生成预览图：{out}  ({len(png)/1024:.0f} KB)")
    print("（容器内路径 /app/state/... 对应宿主机 radar_push/state/...，可直接打开查看）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
