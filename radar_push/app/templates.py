"""推送文本拼装。"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Set

# 风掣预报 / 实况提醒：均按「空串则整行省略、不回退占位符」处理。
#   · 风掣行空：本时次风掣未就绪并已超时放弃（或未启用）——见 main._build_fengche_line；
#   · 实况行空：本时刻无达标风雨实况——见 main._build_realtime_line。


def _fmt_time(dt: datetime) -> str:
    return f"{dt.year}年{dt.month}月{dt.day}日{dt.strftime('%H:%M')}"


def build_tail(observe_time: datetime) -> str:
    """保留兼容：落款已并入标题，正文不再使用落款。"""
    return f"苏州市气象台{_fmt_time(observe_time)}发布"


def _level_text(level_dbz: int) -> str:
    return f"{int(level_dbz)}dBZ"


def _district_list_text(
    affected: Dict[str, Set[str]],
    district_names: Dict[str, str],
) -> str:
    """仅区县名罗列（不含乡镇），用于"……将出现雷电活动"主句。"""
    names = [district_names.get(code, code) for code in affected.keys()]
    return "、".join(names) if names else "苏州市"


def _township_block(
    affected: Dict[str, Set[str]],
    district_names: Dict[str, str],
    district_township_total: Dict[str, int] | None = None,
    full_ratio: float = 0.7,
) -> str:
    """生成"具体影响乡镇（街道）如下"明细段；无任何具体乡镇时返回空串。

    若某区受影响乡镇（街道）数占该区总数的比例 >= full_ratio，则折叠为
    "大部分乡镇（街道）"，不再逐个罗列，避免大范围过程时清单过长。
    """
    totals = district_township_total or {}
    lines: List[str] = []
    for code, townships in affected.items():
        tw = [t for t in sorted(townships) if t]
        if not tw:
            continue
        dname = district_names.get(code, code)
        total = totals.get(code, 0)
        if total > 0 and len(tw) >= full_ratio * total:
            lines.append(f"{dname}：大部分乡镇（街道）")
        else:
            lines.append(f"{dname}：{ '、'.join(tw) }")
    if not lines:
        return ""
    return "▶ 具体影响乡镇（街道）如下\n" + "\n".join(lines)


def _convective_phrase(
    max_dbz: float,
    max_et_km: float,
    *,
    gale_cr_dbz: float = 45.0,
    gale_et_km: float = 9.0,
    hail_cr_dbz: float = 55.0,
    hail_et_km: float = 12.0,
) -> str:
    """按 CR 与 ET 判别对流类型，逐档叠加：短时强降水 / 雷暴大风 / 局地小冰雹。"""
    phenomena: List[str] = ["短时强降水"]
    if max_dbz >= gale_cr_dbz and max_et_km >= gale_et_km:
        phenomena.append("雷暴大风")
    if max_dbz >= hail_cr_dbz and max_et_km >= hail_et_km:
        phenomena.append("局地小冰雹")
    return "、".join(phenomena)


def _origin_text(upstream_names: List[str], local_districts: str) -> str:
    """来源话术：中性罗列检测到对流云团的区域（周边城市与本地区县并列），不做"移入/生成"判断。"""
    parts: List[str] = []
    parts.extend([n for n in upstream_names if n])
    if local_districts:
        parts.append(f"苏州{local_districts}")
    return "、".join(parts) if parts else "苏州市"


def build_alert_text(
    *,
    observe_time: datetime,
    level_dbz: int,
    strongest_location: str = "",
    max_dbz: float = 0.0,
    max_et_km: float = 0.0,
    gale_cr_dbz: float = 45.0,
    gale_et_km: float = 9.0,
    hail_cr_dbz: float = 55.0,
    hail_et_km: float = 12.0,
    upstream_names: List[str],
    local_origin_districts: str,
    direction: str,
    trend: str,
    will_enter_city: bool,
    affected: Dict[str, Set[str]],
    district_names: Dict[str, str],
    district_township_total: Dict[str, int] | None = None,
    realtime_line: str = "",
    rainfall_forecast_line: str = "",
) -> str:
    """生成完整推送文本；will_enter_city=False 时走"无明显影响"变体。

    格式：发布时间并入标题；删除落款与防范语；"将出现雷电活动"主句只列区县，
    具体乡镇另起"具体影响乡镇如下"段落逐行罗列（无具体乡镇的区县不出现在该段）。

    realtime_line / rainfall_forecast_line 分别为"实况提醒""风掣预报"两行；
    二者为空均表示本时次该行无内容（实况无达标 / 风掣超时未就绪），整行省略
    （不渲染、不占位）。
    """
    origin = _origin_text(upstream_names, local_origin_districts)
    level = _level_text(level_dbz)
    move = f"回波向{direction}移动" if direction != "少动" else "回波移动缓慢"
    trend_text = {
        "增强": "强度逐渐增强",
        "减弱": "强度逐渐减弱",
        "维持": "强度基本维持",
    }.get(trend, "强度基本维持")

    if strongest_location:
        strength_clause = f"最强回波位于{strongest_location}，强度达{level}"
    else:
        strength_clause = f"雷达回波强度达{level}"
    # 风掣预报：仅当有就绪的风掣文案（非空）时才渲染该行；为空表示本时次风掣
    #   未就绪并已超时放弃（或未启用），整行省略、不再回退占位符。
    # 实况提醒：仅当有达标风雨实况（realtime_line 非空）时才渲染该行，否则整行省略。
    realtime_block = f"{realtime_line}\n" if realtime_line else ""
    observe = (
        f"【AI预报员短临提醒{_fmt_time(observe_time)}】\n"
        f"▶ 雷达监测：{origin}有对流云团正在发展，{strength_clause}。\n"
        f"{realtime_block}"
    )

    # 风掣行尾块：非空才作为独立一行附加在文末（前置换行），为空则整段不含该行。
    forecast_tail = f"\n{rainfall_forecast_line}" if rainfall_forecast_line else ""

    if not will_enter_city:
        return (
            f"{observe}"
            f"▶ 趋势预测：预计未来一小时{move}，{trend_text}，移动路径对我市无明显影响。"
            f"{forecast_tail}"
        )

    convective = _convective_phrase(
        max_dbz, max_et_km,
        gale_cr_dbz=gale_cr_dbz, gale_et_km=gale_et_km,
        hail_cr_dbz=hail_cr_dbz, hail_et_km=hail_et_km,
    )
    district_text = _district_list_text(affected, district_names)
    forecast = (
        f"▶ 趋势预测：预计未来一小时{move}，{trend_text}。"
        f"{district_text}将出现雷电活动，"
        f"部分地区可能伴有{convective}等强对流天气。"
    )
    township_block = _township_block(affected, district_names, district_township_total)
    if township_block:
        return f"{observe}{forecast}\n{township_block}{forecast_tail}"
    return f"{observe}{forecast}{forecast_tail}"
