"""阈值定义、级别标签、严重度比较。

阈值的实际数值由 config.Thresholds 在运行时提供（支持环境变量覆盖）；
本模块仅负责：基于给定阈值，构造"从低到高"的级别梯度，以及级别标签查询。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .config import Thresholds


# 级别严重度排序（数字越大越严重）
LEVEL_SEVERITY = {
    "blue":   1,
    "yellow": 2,
    "orange": 3,
    "red":    4,
}


# 级别中文标签
LEVEL_LABELS = {
    ("strong_convection", "yellow"): "强对流黄色预警",
    ("strong_convection", "orange"): "强对流橙色预警",
    ("strong_convection", "red"):    "强对流红色预警",
    ("rainstorm", "blue"):   "暴雨蓝色预警",
    ("rainstorm", "yellow"): "暴雨黄色预警",
    ("rainstorm", "orange"): "暴雨橙色预警",
    ("rainstorm", "red"):    "暴雨红色预警",
}


def gs_thresholds(t: Thresholds) -> List[Tuple[str, float]]:
    """阵风阈值（从低到高排）。

    返回 (level, threshold_ms)，便于上层用 `reversed(...)` 从高到低遍历定级。
    """
    return [
        ("yellow", t.gs_yellow_ms),
        ("orange", t.gs_orange_ms),
        ("red",    t.gs_red_ms),
    ]


def rain_thresholds(
    t: Thresholds,
) -> List[Tuple[str, Optional[float], Optional[float], Optional[float]]]:
    """暴雨阈值（从低到高排）。

    返回 (level, threshold_1h_mm, threshold_6h_mm, threshold_24h_mm)；
    每级是 OR 条件（任一窗口达标即触发），None 表示该窗口该级别不参与判定。

    国标：
    - 蓝色：仅 6h ≥ 50
    - 黄色：1h ≥ 50 或 6h ≥ 100 或 24h ≥ 150
    - 橙色：1h ≥ 75 或 6h ≥ 150 或 24h ≥ 200
    - 红色：1h ≥ 100 或 6h ≥ 200 或 24h ≥ 250
    """
    return [
        ("blue",   None,                  t.rain_6h_blue_mm,   None),
        ("yellow", t.rain_1h_yellow_mm,   t.rain_6h_yellow_mm, t.rain_24h_yellow_mm),
        ("orange", t.rain_1h_orange_mm,   t.rain_6h_orange_mm, t.rain_24h_orange_mm),
        ("red",    t.rain_1h_red_mm,      t.rain_6h_red_mm,    t.rain_24h_red_mm),
    ]


def level_label(warning_type: str, level: str) -> str:
    """返回 '强对流黄色预警' / '暴雨橙色预警' 这样的中文标签。"""
    return LEVEL_LABELS.get((warning_type, level), f"{warning_type}-{level}")


def severity(level: Optional[str]) -> int:
    if level is None:
        return 0
    return LEVEL_SEVERITY.get(level, 0)
