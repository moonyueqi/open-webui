"""根据各区评估结果生成中文摘要文案。

输出包含三部分：
1. 起报时间溯源行；
2. 10 个区 × {强对流, 暴雨} 的发布建议表格（Markdown）；
3. 紧凑的预报用语清单（每段一行）；
末尾一句话免责声明。

详细的 hour_metrics、防御指南等仍保留在响应 JSON 的 `districts.*.advisory` 字段中，
模型在用户追问时可按需检索复述，无须在 summary 里铺陈。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .templates import format_issue_time_human, format_time_range


LEVEL_CN = {"blue": "蓝色", "yellow": "黄色", "orange": "橙色", "red": "红色"}

# 表格里每段简写
TYPE_LABEL = {
    "strong_convection": "强对流",
    "rainstorm": "暴雨",
}


def _trigger_str(triggered_by: Optional[str]) -> str:
    if triggered_by in ("1h", "6h", "24h"):
        return f"，{triggered_by} 触发"
    return ""


def _segs_cell(segs: List[Dict[str, Any]]) -> str:
    """把若干 segment 渲染成单个表格单元格里的内容。

    无达标段：'否'；
    有段：'是 / 黄色 6月5日 18时至19时；橙色 ...'。
    """
    if not segs:
        return "否"
    parts: List[str] = []
    for seg in segs:
        level_cn = LEVEL_CN.get(seg.get("level"), str(seg.get("level")))
        start = datetime.fromisoformat(seg["start_time"])
        end = datetime.fromisoformat(seg["end_time"])
        time_str = format_time_range(start, end)
        tb_suffix = _trigger_str(seg.get("triggered_by"))
        parts.append(f"{level_cn} {time_str}{tb_suffix}")
    return "是 / " + "；".join(parts)


def _build_table(districts: Dict[str, Dict[str, Any]]) -> List[str]:
    """生成 Markdown 表格：一行一个区，三列（区名 / 强对流 / 暴雨）。"""
    lines: List[str] = []
    lines.append("| 区/县级市 | 强对流预警信号 | 暴雨预警信号 |")
    lines.append("|---|---|---|")
    for _code, block in districts.items():
        name = block.get("name", _code)
        sc_segs = block.get("strong_convection", {}).get("segments", []) or []
        rs_segs = block.get("rainstorm", {}).get("segments", []) or []
        lines.append(
            f"| {name} | {_segs_cell(sc_segs)} | {_segs_cell(rs_segs)} |"
        )
    return lines


def _build_advisory_lines(districts: Dict[str, Dict[str, Any]]) -> List[str]:
    """对每个达标段输出一行预报用语；无达标时段的区不列出。"""
    lines: List[str] = []
    for _code, block in districts.items():
        name = block.get("name", _code)
        for warning_type in ("strong_convection", "rainstorm"):
            segs = block.get(warning_type, {}).get("segments", []) or []
            for seg in segs:
                level_cn = LEVEL_CN.get(seg.get("level"), str(seg.get("level")))
                type_label = TYPE_LABEL.get(warning_type, warning_type)
                advisory = seg.get("advisory") or {}
                forecast_text = advisory.get("forecast_text", "")
                lines.append(
                    f"- {name} · {type_label}{level_cn}预警信号：{forecast_text}"
                )
    return lines


def build_summary(
    issue_time: datetime,
    districts: Dict[str, Dict[str, Any]],
    forecast_hours: int = 24,
) -> str:
    issue_human = format_issue_time_human(issue_time)

    lines: List[str] = [
        f"风掣 AI 起报时刻 {issue_human}（北京时间），未来 {forecast_hours} 小时苏州各区"
        "强对流 / 暴雨预警信号研判建议（区内任意格点达到阈值即提示）：",
        "",
    ]

    lines.extend(_build_table(districts))
    lines.append("")

    advisory_lines = _build_advisory_lines(districts)
    if advisory_lines:
        lines.append("各达标时段预报用语（按官方模板拼装，可直接复用）：")
        lines.extend(advisory_lines)
    else:
        lines.append("各区未来 24 小时内均无达标时段，暂无需发布预警信号。")

    lines.append("")
    lines.append("以上为 AI 工具判别结果，不能替代预报员专业研判。")
    return "\n".join(lines).rstrip() + "\n"
