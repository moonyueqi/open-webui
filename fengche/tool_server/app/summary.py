"""根据预报数据生成中文摘要文案 + 简要天气提示。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_values(forecast: List[Dict[str, Any]], var: str) -> List[float]:
    out = []
    for row in forecast:
        v = row.get("values", {}).get(var)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _radar_hint(cr_max: float) -> str:
    if cr_max < 20:
        return "雷达回波较弱，无明显降水"
    if cr_max < 35:
        return "存在中等强度回波，可能有阵性降水"
    if cr_max < 45:
        return "存在较强回波，注意短时强降水"
    return "存在强对流回波，可能伴随强降水或冰雹，请关注预警"


def _wind_hint(ws_max: float, gs_max: Optional[float]) -> str:
    peak = max(ws_max, gs_max or 0.0)
    if peak < 3.4:
        return "风力较弱"
    if peak < 8.0:
        return "风力适中"
    if peak < 13.9:
        return "风力较大，注意防风"
    return "风力强劲，请注意防范大风影响"


def _precip_hint(tp_total: float) -> str:
    if tp_total < 0.1:
        return "几乎无降水"
    if tp_total < 5:
        return "有少量降水"
    if tp_total < 15:
        return "有中等降水"
    if tp_total < 50:
        return "有较强降水"
    return "有强降水，注意防范"


def _target_row_phrase(row: Dict[str, Any]) -> str:
    """把命中的 lead 行渲染成一句话的天气短语。"""
    values = row.get("values", {}) or {}
    lead = row.get("lead_hour")
    valid_time = row.get("valid_time", "")
    parts: List[str] = []
    if isinstance(values.get("t2m"), (int, float)):
        parts.append(f"气温约 {values['t2m']:.1f}℃")
    ws = values.get("ws")
    gs = values.get("gs")
    if isinstance(ws, (int, float)):
        s = f"10米风速 {ws:.1f} m/s"
        if isinstance(gs, (int, float)):
            s += f"（阵风 {gs:.1f} m/s）"
        parts.append(s)
    tp = values.get("tp")
    if isinstance(tp, (int, float)):
        if tp < 0.1:
            parts.append("基本无降水")
        else:
            parts.append(f"小时降水 {tp:.1f} mm")
    cr = values.get("cr")
    if isinstance(cr, (int, float)) and cr >= 20:
        parts.append(f"雷达回波 {cr:.1f} dBZ")
    detail = "，".join(parts) if parts else "无可用要素"
    return f"目标时刻（lead={lead}h，{valid_time}）：{detail}。"


def build_summary(
    location_name: Optional[str],
    grid_point: Dict[str, Any],
    issue_time_iso: str,
    source_uri: str,
    forecast: List[Dict[str, Any]],
    coverage: Dict[str, list],
    target_row: Optional[Dict[str, Any]] = None,
    horizon_hours: int = 24,
) -> str:
    """生成可读的中文摘要文案。所有数值假定已经过单位换算（t2m 已 K→℃）。

    若调用方传入了 target_row（命中具体某个 lead），会在摘要开头加一句目标时刻的短语，
    便于模型直接复述给用户。
    """
    place = location_name or "查询点"
    glat = grid_point.get("lat")
    glon = grid_point.get("lon")
    dist = grid_point.get("distance_km")

    lines: List[str] = []
    if target_row is not None:
        lines.append(f"{place}（{_target_row_phrase(target_row)}）")
    lines.append(
        f"{place}（最近格点 {glat:.2f}°N, {glon:.2f}°E，距查询点约 {dist:.2f} km）"
        f"未来 {len(forecast)} 小时逐小时预报：起报时刻 {issue_time_iso}，"
        f"风掣预报时效 {horizon_hours} 小时。"
    )

    t2m_vals = _safe_values(forecast, "t2m")
    if t2m_vals:
        lines.append(
            f"气温区间 {min(t2m_vals):.1f}~{max(t2m_vals):.1f}℃。"
        )

    ws_vals = _safe_values(forecast, "ws")
    gs_vals = _safe_values(forecast, "gs")
    if ws_vals:
        lines.append(
            f"10米风速最大 {max(ws_vals):.1f} m/s"
            + (f"，阵风最大 {max(gs_vals):.1f} m/s" if gs_vals else "")
            + f"。{_wind_hint(max(ws_vals), max(gs_vals) if gs_vals else None)}。"
        )

    tp_vals = _safe_values(forecast, "tp")
    if tp_vals:
        # tp 是每个 step 的逐小时降水增量（已通过 fengche/20260507/*.nc 实测验证：
        # 序列中出现 0→1.013→0 这样的回退，累积量物理上不可能回退），
        # 因此累计降水 = 各时次直接求和。
        total = sum(tp_vals)
        n_hours = len(forecast)
        lines.append(
            f"未来 {n_hours} 小时累计降水约 {total:.1f} mm。{_precip_hint(total)}。"
        )

    cr_vals = _safe_values(forecast, "cr")
    if cr_vals:
        lines.append(f"雷达回波峰值 {max(cr_vals):.1f} dBZ。{_radar_hint(max(cr_vals))}。")

    lines.append(f"数据来源：风掣 AI 模型（{source_uri}）。")
    return " ".join(lines)
