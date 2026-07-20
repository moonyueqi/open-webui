"""基于风掣 AI 预报，按苏州各区县统计目标时段的小时雨强范围与最大阵风，生成「风掣预报」行。

流程：
1. 由观测时刻按「逐小时为界」(boundary_minute) 算出目标时段 [start, start+1h)。
2. 回退查找能覆盖该时段的最近一份风掣 nc，取该 lead_hour 的 tp（降水）、gs（阵风）网格。
3. 用 radar_push 现有的区县掩膜（GeoRegistry.build_for_grid）分别统计每个区县内的
   tp 雨强范围与 gs 最大阵风等级——两者相互独立，阵风不再以「该区有降水」为前提。
4. 降水按雨量从大到小排列、仅列有降水的区县；阵风按风级从大到小排列、仅列达到
   上报门槛（gust_report_min_level）的区县。全市无降水/无强阵风则对应段省略。
5. 拼成确定性的中文「风掣预报」文案：首行给一句定性概况（含雨与风，可选 LLM，只写
   定性、不含数值）；随后「最大小时雨强…」一段按雨强归纳各区、「最大阵风…」一段按
   风级归纳各区（相同数值的区县用顿号合并），数据源即真值、不经 LLM 改写。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


# 无降水阈值（mm）：区县代表雨强 < 此值视为无明显降水，不在文案中提及。
NO_RAIN_MM = 0.1
# 雨强取整刻度（mm）：把 min/max 向下/向上取整到该刻度，形成「整十/整五」区间。
ROUND_STEP_MM = 5.0
# 区县内最少有降水格点数：低于此值认为是零星噪声，不计该区县降水。
MIN_RAIN_POINTS = 3
# 区间收窄：当某区县雨强区间跨度（hi-lo）>= 该阈值(mm)时触发收窄，
# 把下界抬到 max(0, hi - WIDE_RANGE_NARROW_MM)，避免「0-50」这类过宽区间。
WIDE_RANGE_TRIGGER_MM = 15.0
WIDE_RANGE_NARROW_MM = 10.0

# 阵风上报门槛（蒲福风级）：区县最大阵风 >= 此级才在「最大阵风…」段列出，
# 避免把风力很小的区县全部罗列。可由调用方（config）覆盖。
GUST_REPORT_MIN_LEVEL = 6
# 区县内最少有效阵风格点数：低于此值认为是零星噪声，不计该区县阵风。
MIN_GUST_POINTS = 3

# 蒲福风级下界（m/s）：风速 >= 第 i 档下界即为该风级，索引即风级（与 obs_realtime 一致）。
_BEAUFORT_MIN_MS = [
    0.0, 0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7,
]


def wind_to_level(ms: float) -> int:
    """阵风(m/s) -> 蒲福风级（整数）。缺测/非有限值返回 0，超过 12 级按 12 计。"""
    if not np.isfinite(ms):
        return 0
    lvl = 0
    for i, lo in enumerate(_BEAUFORT_MIN_MS):
        if ms >= lo:
            lvl = i
    return lvl


@dataclass(frozen=True)
class DistrictRain:
    code: str
    name: str
    lo_mm: float          # 区县内雨强范围下界（取整后）
    hi_mm: float          # 区县内雨强范围上界（取整后）
    raw_max_mm: float     # 原始高分位雨强（用于排序）


@dataclass(frozen=True)
class DistrictGust:
    code: str
    name: str
    gust_level: int       # 区内最大阵风等级（蒲福风级）
    gust_ms: float        # 区内最大阵风代表值 m/s（用于排序/参考）


def _round_down(x: float, step: float) -> float:
    return float(np.floor(x / step) * step)


def _round_up(x: float, step: float) -> float:
    return float(np.ceil(x / step) * step)


def _range_text(lo: float, hi: float) -> str:
    """把 [lo, hi] 渲染成中文雨强短语，统一用「lo-hi毫米」区间句式。

    · 下界为 0 时显示「0-hi毫米」（不再用「hi毫米以下」，避免同一行句式混排）；
    · 上下界相等（单档）时用「X毫米左右」更自然，避免「X-X毫米」。
    """
    lo_i, hi_i = int(round(lo)), int(round(hi))
    if hi_i <= lo_i:
        if hi_i <= 0:
            return "0-5毫米"
        return f"{hi_i}毫米左右"
    return f"{lo_i}-{hi_i}毫米"


def aggregate_district_rain(
    tp: np.ndarray,
    district_masks: Dict[str, np.ndarray],
    district_names: Dict[str, str],
    *,
    no_rain_mm: float = NO_RAIN_MM,
    round_step_mm: float = ROUND_STEP_MM,
    min_rain_points: int = MIN_RAIN_POINTS,
) -> List[DistrictRain]:
    """统计每个区县内的小时雨强范围，返回按雨量从大到小排序、仅含有降水的区县。

    雨强区间用区内有降水格点的最小~最大值（按取整刻度归档）。
    """
    out: List[DistrictRain] = []
    for code, mask in district_masks.items():
        vals = tp[mask]
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            continue
        rain_vals = vals[vals >= no_rain_mm]
        if rain_vals.size < min_rain_points:
            continue
        hi_raw = float(np.max(rain_vals))
        lo_raw = float(np.min(rain_vals))
        if hi_raw < no_rain_mm:
            continue
        lo = max(0.0, _round_down(lo_raw, round_step_mm))
        hi = _round_up(hi_raw, round_step_mm)
        if hi <= 0:
            hi = round_step_mm
        # 区间收窄：跨度过大时下界抬到「上界-收窄量」，避免「0-50」这类过宽区间
        if hi - lo >= WIDE_RANGE_TRIGGER_MM:
            lo = max(0.0, hi - WIDE_RANGE_NARROW_MM)
        out.append(
            DistrictRain(
                code=code,
                name=district_names.get(code, code),
                lo_mm=lo,
                hi_mm=hi,
                raw_max_mm=hi_raw,
            )
        )
    out.sort(key=lambda d: d.raw_max_mm, reverse=True)
    return out


def aggregate_district_gust(
    gs: Optional[np.ndarray],
    district_masks: Dict[str, np.ndarray],
    district_names: Dict[str, str],
    *,
    min_report_level: int = GUST_REPORT_MIN_LEVEL,
    min_gust_points: int = MIN_GUST_POINTS,
) -> List[DistrictGust]:
    """独立统计每个区县内的最大阵风，返回按风级从大到小排序、达到上报门槛的区县。

    与降水无关：无论该区是否有降水，都用区内 gs 格点最大值换算风级。
    gs 为 None 或整帧缺测时返回空列表（文案里省略阵风段）。
    """
    if gs is None:
        return []
    out: List[DistrictGust] = []
    for code, mask in district_masks.items():
        gvals = gs[mask]
        gvals = gvals[np.isfinite(gvals)]
        if gvals.size < min_gust_points:
            continue
        gust_ms = float(np.max(gvals))
        level = wind_to_level(gust_ms)
        if level < min_report_level:
            continue
        out.append(
            DistrictGust(
                code=code,
                name=district_names.get(code, code),
                gust_level=level,
                gust_ms=gust_ms,
            )
        )
    out.sort(key=lambda d: (d.gust_level, d.gust_ms), reverse=True)
    return out


def _rain_section(districts: List[DistrictRain]) -> str:
    """把有降水的区县按「雨强区间」归纳成一段：相同区间的区县用顿号合并。

    形如：「最大小时雨强吴江区0-10毫米，昆山市、吴中区0-5毫米。」（按雨量从大到小）
    """
    if not districts:
        return ""
    # 保持既有的「雨量从大到小」顺序，同一雨强区间的区县合并到一组
    groups: List[Tuple[str, List[str]]] = []
    index: Dict[str, int] = {}
    for d in districts:
        key = _range_text(d.lo_mm, d.hi_mm)
        if key not in index:
            index[key] = len(groups)
            groups.append((key, []))
        groups[index[key]][1].append(d.name)
    parts = [f"{'、'.join(names)}{rng}" for rng, names in groups]
    return f"最大小时雨强{'，'.join(parts)}。"


def _gust_section(districts: List[DistrictGust]) -> str:
    """把达到门槛的区县按「风级」归纳成一段：相同风级的区县用顿号合并。

    形如：「最大阵风某某区、某某区11级，某某区10级。」（按风级从大到小）
    """
    if not districts:
        return ""
    groups: List[Tuple[int, List[str]]] = []
    index: Dict[int, int] = {}
    for d in districts:
        if d.gust_level not in index:
            index[d.gust_level] = len(groups)
            groups.append((d.gust_level, []))
        groups[index[d.gust_level]][1].append(d.name)
    parts = [f"{'、'.join(names)}{lvl}级" for lvl, names in groups]
    return f"最大阵风{'，'.join(parts)}。"


def build_rainfall_line_template(
    start_hour: int,
    end_hour: int,
    rain_districts: List[DistrictRain],
    gust_districts: List[DistrictGust],
    overview: str = "",
) -> str:
    """生成确定性的「风掣预报」文案（数值明细为数据真值，不可改）。

    首行为一句定性概况（含雨与风，可由 LLM 生成，不含数值）；随后把降水与阵风
    分成两段各占一行：「最大小时雨强…」按雨强归纳、「最大阵风…」按风级归纳。
    start_hour / end_hour 为目标时段的本地整点（如 9,10 表示 9-10 时）。
    """
    span = f"{start_hour}-{end_hour}时"
    # 无强阵风时统一在首行补一句「无明显强阵风」总结（不依赖 LLM，保证确定性）。
    no_gust = not gust_districts
    gust_suffix = "，无明显强阵风" if no_gust else ""
    if not rain_districts and not gust_districts:
        return f"▶ 风掣预报：预计{span}苏州各区无明显降水{gust_suffix}。"

    if overview:
        head = f"▶ 风掣预报：预计{span}苏州{overview}{gust_suffix}。"
    elif rain_districts:
        head = f"▶ 风掣预报：预计{span}苏州部分地区有降水{gust_suffix}。"
    else:
        head = f"▶ 风掣预报：预计{span}苏州无明显降水，部分地区有较强阵风。"

    lines = [head]
    rain_seg = _rain_section(rain_districts)
    if rain_seg:
        lines.append(rain_seg)
    gust_seg = _gust_section(gust_districts)
    if gust_seg:
        lines.append(gust_seg)
    return "\n".join(lines)


def build_overview_phrase(
    llm,
    rain_districts: List[DistrictRain],
    gust_districts: List[DistrictGust],
) -> str:
    """用 LLM 生成"降水+大风概况"定性短语（仅定性、不含任何数字），失败/无数据返回空串。

    概况只描述区域方位、雨势与风势倾向，含数字即判为不合格、退回无概况版本。
    """
    if not getattr(llm, "enabled", False):
        return ""
    if not (getattr(llm, "base_url", "") and getattr(llm, "model", "")):
        return ""
    if not rain_districts and not gust_districts:
        return ""

    import re

    import requests

    # 给模型的事实：各区县雨强（从大到小）与达到门槛的区县阵风（从大到小），
    # 供其判断哪边强、整体量级与风力
    rain_facts = "、".join(
        f"{d.name}雨强{int(round(d.lo_mm))}-{int(round(d.hi_mm))}mm"
        for d in rain_districts
    ) or "无明显降水"
    gust_facts = "、".join(
        f"{d.name}最大阵风{d.gust_level}级" for d in gust_districts
    ) or "无明显强阵风"
    max_level = max((d.gust_level for d in gust_districts), default=0)
    system = (
        "你是气象台预报员。根据给定的【各区县未来1小时雨强与最大阵风数据】，写一句简短的"
        "「天气概况」短语，它将被嵌入到这样的句子中：\n"
        "    预计X-Y时苏州【你写的概况】。\n"
        "随后另起两行分别罗列各区具体雨强与阵风数值。因此你写的内容要能紧接在「苏州」二字"
        "之后、自然衔接，并能以句号收尾。要求：\n"
        "1. 只做定性概括：降水主要落区（用'北部/中部/南部/中北部/中南部'等方位，不要再写"
        "'苏州'二字，因为前面已有'苏州'）、整体或局地雨势倾向（如降水明显、雨势平缓、局地"
        "雨势较强 等），并简要带上风势（如伴有阵风、局地风力较强、风力总体不大 等）。\n"
        "2. 严禁出现任何阿拉伯数字、毫米数、风级数、时间、百分比等具体数值——数值会在本句"
        "之后逐区单独罗列，本句只做文字概括。\n"
        "3. 一句话，12~30 字，读起来通顺，用逗号分隔分句（如'南部有弱降水，雨势平缓，"
        "局地伴有较强阵风'）；结尾不要加任何标点，不要引号，不要解释。\n"
        "4. 可以出现区县名或方位词，但不得编造数据里没有体现的结论；若风力普遍很小则如实"
        "写风力不大或不必强调风。\n"
        "示例（仅供格式参考，请据实际数据写）：'南部有弱降水，雨势平缓，局地伴有较强阵风'。"
    )
    hint = "整体风力偏弱" if max_level < 6 else "局地伴有较强阵风"
    # 有风没雨：要求概况先点明「无明显降水」、再描述风势，避免只报风让人误解
    if not rain_districts and gust_districts:
        constraint = (
            "\n【硬性约束】本时段全市无明显降水。请以'无明显降水'开头，随后只描述风势"
            "（如'无明显降水，局地伴有较强阵风'）；不得写出任何'有雨/雨势/阵雨/降水明显'"
            "等表示确有降水的措辞。"
        )
    elif rain_districts and not gust_districts:
        # 有降水但无强阵风：概况只写降水与雨势，不要提风——句尾会由代码统一补「无明显强阵风」，
        # 避免概况再写风造成重复或矛盾。
        constraint = (
            "\n【硬性约束】本时段全市无明显强阵风。请只描述降水落区与雨势，"
            "不要提及风、阵风、大风或风力（如'南部有弱降水，雨势平缓'）；"
            "不得写出'伴有阵风/风力较强'等表示有明显风力的措辞。"
        )
    else:
        constraint = ""
    user = (
        f"【各区县未来1小时雨强与最大阵风数据】\n降水：{rain_facts}\n阵风：{gust_facts}\n"
        f"（参考：{hint}）{constraint}\n\n"
        "请只输出那一句天气概况短语（不带'苏州'、不带数字、结尾无标点），不要其他内容。"
    )
    payload = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": float(getattr(llm, "temperature", 0.2)),
        "stream": False,
        "enable_thinking": bool(getattr(llm, "enable_thinking", False)),
    }
    headers = {"Content-Type": "application/json"}
    if getattr(llm, "api_key", ""):
        headers["Authorization"] = f"Bearer {llm.api_key}"
    url = f"{llm.base_url}/chat/completions"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=llm.timeout)
        candidate = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("降水概况 LLM 生成失败(%s)，退回无概况", e)
        return ""

    text = (candidate or "").strip().strip("「」\"'`：: \n\u3000")
    text = re.sub(r"\s+", "", text)
    # 兜底清洗：去掉开头多余的「预计/苏州」和首尾标点（模板已含「苏州」并自接「，小时降水量…」）
    text = re.sub(r"^(预计)?苏州市?", "", text)
    text = text.lstrip("，,。.、；; ")
    text = text.rstrip("，,。.、；;：: ")
    # 概况里绝不能出现数字（避免与后面明细冲突或编造量值）
    if re.search(r"\d", text):
        log.warning("降水概况含数字，判为不合格、退回无概况：%s", text)
        return ""
    # 有风没雨时兜底校验：允许「无明显降水/无降水」这类否定表述，但若出现表示确有降水的
    # 措辞则判为不合格、退回无概况。先剥掉否定短语，再看是否仍残留降水字样。
    if not rain_districts and gust_districts:
        residual = re.sub(r"无(明显)?(降水|雨)", "", text)
        if re.search(r"[雨降]|阵雨|雨势", residual):
            log.warning("无降水时概况却提及降水，判为不合格、退回无概况：%s", text)
            return ""
    if not (4 <= len(text) <= 40):
        log.warning("降水概况长度异常(%d)，退回无概况：%s", len(text), text)
        return ""
    log.info("降水概况生成：%s", text)
    return text


def build_rainfall_forecast_line(
    *,
    tp_grid,
    masks,
    start_hour: int,
    end_hour: int,
    llm=None,
    gust_report_min_level: int = GUST_REPORT_MIN_LEVEL,
) -> Tuple[str, List[DistrictRain], List[DistrictGust]]:
    """统计 + 生成「风掣预报」文案的总入口。返回 (文案, 降水明细, 阵风明细)。

    降水与阵风分别独立统计：降水段仅列有降水的区县、阵风段仅列达到门槛的区县，
    二者相互不影响。传入 llm 时仅在首行插入一句定性概况（含雨与风）；两段数值明细
    始终由代码原样拼接、不经 LLM 改写。阵风取自 tp_grid.gs（缺则阵风段省略）。
    """
    rain_districts = aggregate_district_rain(
        tp_grid.tp,
        masks.districts,
        masks.district_names,
    )
    gust_districts = aggregate_district_gust(
        getattr(tp_grid, "gs", None),
        masks.districts,
        masks.district_names,
        min_report_level=gust_report_min_level,
    )
    overview = (
        build_overview_phrase(llm, rain_districts, gust_districts)
        if llm is not None
        else ""
    )
    line = build_rainfall_line_template(
        start_hour, end_hour, rain_districts, gust_districts, overview
    )
    return line, rain_districts, gust_districts
