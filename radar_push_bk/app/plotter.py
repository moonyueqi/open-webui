"""渲染雷达组合反射率实况图为 PNG 字节，边界取自 data/ 下的 geojson。"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from .nc_reader import RadarGrid  # noqa: E402

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_LEVELS = [-10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
_COLORS = [
    "#FFFFFF", "#9DFAFF", "#00BFFF", "#0000FF",
    "#00FF00", "#00CC00", "#009900", "#FFFF00",
    "#FFD700", "#FF8C00", "#FF4500", "#FF0000",
    "#CC0000", "#990000", "#FF00FF",
]

# 从 matplotlib 已安装字体里匹配可用的中文字体，避免中文显示为方块
def _setup_cjk_font() -> None:
    from matplotlib import font_manager

    candidates = (
        "WenQuanYi Zen Hei",
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans CN",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Heiti SC",
        "Sarasa Gothic SC",
    )
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = [name for name in candidates if name in available]
    if chosen:
        plt.rcParams["font.sans-serif"] = chosen + ["DejaVu Sans"]
        plt.rcParams["font.family"] = "sans-serif"
        log.info("CJK font for plotting: %s", chosen[0])
    else:
        log.warning(
            "未找到可用中文字体，图中中文可能显示为方块；"
            "请在运行环境安装如 fonts-wqy-zenhei / Noto Sans CJK。"
        )


_setup_cjk_font()
plt.rcParams["axes.unicode_minus"] = False


def _load_geoms(name: str):
    p = DATA_DIR / name
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        fc = json.load(f)
    return [(feat.get("properties", {}), shape(feat["geometry"])) for feat in fc["features"]]


def _plot_boundary(ax, geom, **kw):
    try:
        gt = geom.geom_type
        if gt == "Polygon":
            xs, ys = geom.exterior.xy
            ax.plot(xs, ys, **kw)
        elif gt == "LineString":
            xs, ys = geom.xy
            ax.plot(xs, ys, **kw)
        elif gt in ("MultiPolygon", "MultiLineString", "GeometryCollection"):
            for g in geom.geoms:
                _plot_boundary(ax, g, **kw)
    except Exception as e:
        log.debug("plot boundary failed: %s", e)


def _fill_poly(ax, geom, **kw):
    try:
        gt = geom.geom_type
        if gt == "Polygon":
            xs, ys = geom.exterior.xy
            ax.fill(xs, ys, **kw)
        elif gt in ("MultiPolygon", "GeometryCollection"):
            for g in geom.geoms:
                _fill_poly(ax, g, **kw)
    except Exception as e:
        log.debug("fill poly failed: %s", e)


def render_radar_png(
    grid: RadarGrid,
    *,
    title_time: Optional[datetime] = None,
    dpi: int = 130,
) -> bytes:
    lat = grid.lat_arr
    lon = grid.lon_arr
    refl = grid.refl

    cmap = mcolors.ListedColormap(_COLORS)
    norm = BoundaryNorm(_LEVELS, ncolors=cmap.N)
    lon2d, lat2d = np.meshgrid(lon, lat)

    city = _load_geoms("suzhou_city.geojson")
    districts = _load_geoms("districts.geojson")
    townships = _load_geoms("townships.geojson")
    buffers = _load_geoms("suzhou_buffer.geojson")
    background = _load_geoms("background.geojson")

    # 画布范围：在 50km 缓冲区 bbox 基础上外扩约 0.35°
    extent = None
    full = [g for props, g in buffers if props.get("kind") == "full"]
    if full:
        minx, miny, maxx, maxy = full[0].bounds
        margin = 0.35
        extent = [minx - margin, maxx + margin, miny - margin, maxy + margin]

    fig, ax = plt.subplots(figsize=(10, 9))
    if extent:
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])

    # 周边省界黑实线、市界灰虚线
    for props, g in background:
        if props.get("kind") == "province":
            _plot_boundary(ax, g, color="black", linewidth=1.0, zorder=1)
        else:
            _plot_boundary(ax, g, color="#666666", linewidth=0.6, linestyle="--", zorder=1)

    # 50km 缓冲区浅红填充
    for props, g in buffers:
        if props.get("kind") == "full":
            _fill_poly(ax, g, facecolor="red", alpha=0.04, edgecolor="none", zorder=2)

    plot_data = np.ma.masked_invalid(refl)
    ax.pcolormesh(lon2d, lat2d, plot_data, cmap=cmap, norm=norm, shading="auto", zorder=3)

    # 乡镇界（黑点线）
    for _, g in townships:
        _plot_boundary(ax, g, color="black", linewidth=0.4, linestyle=":", zorder=4)
    # 区县界（黑细实线）
    for _, g in districts:
        _plot_boundary(ax, g, color="black", linewidth=0.8, linestyle="-", zorder=4)
    # 市界（黑粗实线）
    for _, g in city:
        _plot_boundary(ax, g, color="black", linewidth=2.0, zorder=5)
    # 50km 缓冲区（红虚线边界）
    for props, g in buffers:
        if props.get("kind") == "full":
            _plot_boundary(ax, g, color="red", linewidth=1.8, linestyle="--", zorder=6)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", pad=0.02, shrink=0.85, extend="both")
    cbar.set_label("反射率 (dBZ)", fontsize=13)
    cbar.set_ticks(_LEVELS)
    cbar.ax.tick_params(labelsize=12)

    legend_elements = [
        Line2D([0], [0], color="black", linewidth=2, label="苏州市界"),
        Line2D([0], [0], color="black", linewidth=0.8, linestyle="-", label="苏州县界"),
        Line2D([0], [0], color="black", linewidth=0.5, linestyle=":", label="苏州乡镇界"),
        Line2D([0], [0], color="red", linewidth=1.8, linestyle="--", label="苏州市外50km缓冲区"),
        Patch(facecolor="red", alpha=0.1, label="缓冲区范围"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", framealpha=0.7, facecolor="white", fontsize=9)

    # 坐标加 °E / °N，去掉末尾多余的 .0，用 mathtext 渲染度符号
    def _fmt(v: float) -> str:
        return f"{v:.1f}".rstrip("0").rstrip(".")

    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: rf"${_fmt(v)}^{{\circ}}$E"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: rf"${_fmt(v)}^{{\circ}}$N"))
    ax.tick_params(labelsize=11)
    ax.grid(True, linewidth=0.4, color="gray", alpha=0.5, linestyle="--")

    tt = title_time or grid.valid_time
    ax.set_title(f"雷达组合反射率  {tt.strftime('%Y-%m-%d %H:%M')} CST", fontsize=15, pad=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
