"""基于风掣 AI 预报，按苏州各区县统计目标时段的小时雨强范围，生成「风掣预报」行。

流程：
1. 由观测时刻按「逐小时为界」(boundary_minute) 算出目标时段 [start, start+1h)。
2. 回退查找能覆盖该时段的最近一份风掣 nc，取该 lead_hour 的 tp 网格。
3. 用 radar_push 现有的区县掩膜（GeoRegistry.build_for_grid）统计每个区县内 tp 范围。
4. 区县按雨量从大到小排列；无降水的区县不提及；全市无降水则给「以无明显降水为主」。
5. 拼成确定性的中文「风掣预报」行（数据源即真值）；可选用 LLM 归纳分组措辞，
   但严禁改动任何数值/地名（沿用 llm_polish 的零风险校验思路）。
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
# 区县代表雨强用的高分位（抗单格噪声）：取区县内有降水格点 tp 的该分位作为「最大值」。
HIGH_PCT = 90.0
# 区县内最少有降水格点数：低于此值认为是零星噪声，不计该区县降水。
MIN_RAIN_POINTS = 3
# 区间收窄：当某区县雨强区间跨度（hi-lo）>= 该阈值(mm)时触发收窄，
# 把下界抬到 max(0, hi - WIDE_RANGE_NARROW_MM)，避免「0-50」这类过宽区间。
WIDE_RANGE_TRIGGER_MM = 15.0
WIDE_RANGE_NARROW_MM = 10.0


@dataclass(frozen=True)
class DistrictRain:
    code: str
    name: str
    lo_mm: float          # 区县内雨强范围下界（取整后）
    hi_mm: float          # 区县内雨强范围上界（取整后）
    raw_max_mm: float     # 原始高分位雨强（用于排序）


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
        # 单档：上下界相同。>0 用「左右」；都为 0 的兜底写法。
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
    high_pct: float = HIGH_PCT,
    min_rain_points: int = MIN_RAIN_POINTS,
) -> List[DistrictRain]:
    """统计每个区县内的小时雨强范围，返回按雨量从大到小排序、仅含有降水的区县。"""
    out: List[DistrictRain] = []
    for code, mask in district_masks.items():
        vals = tp[mask]
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            continue
        rain_vals = vals[vals >= no_rain_mm]
        if rain_vals.size < min_rain_points:
            continue
        hi_raw = float(np.percentile(rain_vals, high_pct))
        lo_raw = float(np.percentile(rain_vals, 100.0 - high_pct))
        if hi_raw < no_rain_mm:
            continue
        lo = max(0.0, _round_down(lo_raw, round_step_mm))
        hi = _round_up(hi_raw, round_step_mm)
        if hi <= 0:
            hi = round_step_mm
        # 区间收窄：跨度过大（hi-lo>=阈值）时，下界抬到「上界-收窄量」，
        #   避免出现「0-50」这类跨度过宽、参考性差的区间（如 0-50 -> 40-50）。
        #   上界本身较小（hi<收窄量）时下界夹到 0，且此时跨度通常 < 阈值不会触发。
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


def _group_consecutive_same_range(items: List[DistrictRain]) -> List[Tuple[List[str], float, float]]:
    """把相邻且雨强区间相同的区县合并为一组，返回 [(区县名列表, lo, hi), ...]。"""
    groups: List[Tuple[List[str], float, float]] = []
    for d in items:
        if groups and groups[-1][1] == d.lo_mm and groups[-1][2] == d.hi_mm:
            groups[-1][0].append(d.name)
        else:
            groups.append(([d.name], d.lo_mm, d.hi_mm))
    return groups


def build_rainfall_line_template(
    start_hour: int,
    end_hour: int,
    districts: List[DistrictRain],
    overview: str = "",
) -> str:
    """生成确定性的「风掣预报」行（数值明细为数据真值，不可改）。

    start_hour / end_hour 为目标时段的本地整点（如 9, 10 表示 9-10 时）。
    overview 为可选的"降水概况"定性短语（由 LLM 生成、不含具体数值）：
      · 非空时插入为：预计{span}苏州{overview}，小时降水量{明细}。
      · 空时退回原样：  预计{span}苏州小时雨强{明细}。
    """
    span = f"{start_hour}-{end_hour}时"
    if not districts:
        return f"▶ 风掣预报：预计{span}苏州各区无明显降水。"

    groups = _group_consecutive_same_range(districts)
    parts: List[str] = []
    for names, lo, hi in groups:
        parts.append(f"{ '、'.join(names) }{_range_text(lo, hi)}")
    body = "，".join(parts)
    if overview:
        return f"▶ 风掣预报：预计{span}苏州{overview}，小时降水量{body}。"
    return f"▶ 风掣预报：预计{span}苏州小时降水量{body}。"


def build_overview_phrase(llm, districts: List[DistrictRain]) -> str:
    """用 LLM 生成"降水概况"定性短语（仅定性、不含任何数字），失败/无数据返回空串。

    概况只描述区域方位与量级倾向（如"中南部地区降水较为明显，局地可达暴雨量级"），
    供 build_rainfall_line_template 插入到固定明细之前。严禁出现任何数字/毫米数，
    出现即判为不合格、返回空串（退回无概况版本）。
    """
    if not getattr(llm, "enabled", False):
        return ""
    if not (getattr(llm, "base_url", "") and getattr(llm, "model", "")):
        return ""
    if not districts:
        return ""

    import re

    import requests

    # 给模型的事实：各区县雨强等级（按从大到小），仅供它判断"哪边强、整体量级"。
    facts = "、".join(
        f"{d.name}{int(round(d.lo_mm))}-{int(round(d.hi_mm))}mm" for d in districts
    )
    system = (
        "你是气象台预报员。根据给定的【各区县未来1小时雨强数据】，写一句简短的"
        "「降水概况」短语，它将被嵌入到这样的句子中：\n"
        "    预计X-Y时苏州【你写的概况】，小时降水量某区**毫米、某区**毫米……\n"
        "因此你写的内容要能紧接在「苏州」二字之后、自然衔接，并能接「，小时降水量…」。要求：\n"
        "1. 只做定性概括：降水主要落区（用'北部/中部/南部/中北部/中南部'等方位，不要再写"
        "'苏州'二字，因为前面已有'苏州'）、整体或局地量级倾向（如降水明显、局地雨势较强、"
        "局地可达暴雨量级 等）。\n"
        "2. 严禁出现任何阿拉伯数字、毫米数、时间、百分比等具体数值——数值会在本句之后单独"
        "罗列，本句只做文字概括。\n"
        "3. 一句话，10~28 字，读起来通顺；句内若有两个分句要用逗号隔开（如'降水主要"
        "集中在北部和中部，局地雨势较强'）；结尾不要加任何标点（句号/逗号都不要），"
        "不要引号，不要解释。\n"
        "4. 可以出现区县名或方位词，但不得编造数据里没有体现的结论。\n"
        "示例（仅供格式参考，请据实际数据写）：'中南部降水较为明显，局地雨势较强'。"
    )
    user = (
        f"【各区县未来1小时雨强数据】\n{facts}\n\n"
        "请只输出那一句降水概况短语（不带'苏州'、不带数字、结尾无标点），不要其他内容。"
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
    # 后处理清洗（兜底，纠正模型未完全遵循指令的情况）：
    #   1) 去掉开头多余的"苏州/苏州市"（模板已含"苏州"，避免"苏州…苏州北部"重复）；
    #   2) 去掉结尾标点（模板会自己接"，小时降水量…"，结尾带标点会重复/不通顺）；
    #   3) 去掉开头可能多带的连接词"预计""为"等。
    text = re.sub(r"^(预计)?苏州市?", "", text)
    text = text.lstrip("，,。.、；; ")
    text = text.rstrip("，,。.、；;：: ")
    # 安全闸：概况里绝不能出现数字（避免与后面明细冲突或编造量值）。
    if re.search(r"\d", text):
        log.warning("降水概况含数字，判为不合格、退回无概况：%s", text)
        return ""
    if not (4 <= len(text) <= 40):
        log.warning("降水概况长度异常(%d)，退回无概况：%s", len(text), text)
        return ""
    log.info("降水概况生成：%s", text)
    return text


def polish_rainfall_line(llm, template_line: str, districts: List[DistrictRain]) -> str:
    """可选：用 LLM 把风掣预报行归纳得更自然（严禁改数值/地名），失败回退模板。"""
    if not getattr(llm, "enabled", False):
        return template_line
    if not (getattr(llm, "base_url", "") and getattr(llm, "model", "")):
        return template_line
    if not districts:
        return template_line

    import re

    import requests

    system = (
        "你是气象台预警文案编辑。把给定的【风掣降水预报初稿】改写得更通顺自然，"
        "用于公众发布，必须严谨。严格规则：\n"
        "1. 不得新增、删除或修改任何数字、毫米数、时间、地名、单位。\n"
        "2. 不得编造初稿中没有的任何量值。\n"
        "3. 必须保留每个区县名及其对应的雨强范围，可适当用「等地」「其余区市」归纳措辞，"
        "但已出现的区县名和数字一个都不能少。\n"
        "4. 必须以「风掣预报：」开头，只输出一行中文，不要解释、不要引号、不要 Markdown。"
    )
    user = (
        f"【风掣降水预报初稿】\n{template_line}\n\n"
        "请在不改变任何数字与地名的前提下改写为更自然的一行文本，仍以「风掣预报：」开头。"
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
        log.warning("风掣预报行 LLM 润色失败(%s)，回退模板", e)
        return template_line

    text = (candidate or "").strip().strip("「」\"'`").strip()
    text = re.sub(r"\s*\n\s*", " ", text)
    if not text.startswith("风掣预报"):
        log.warning("风掣预报行润色未以「风掣预报」开头，回退模板")
        return template_line

    # 数值多重集合校验：模板里每个数字都必须在输出里出现至少同样多次
    def _nums(s: str) -> List[str]:
        return re.findall(r"\d+", s)

    from collections import Counter

    rc, pc = Counter(_nums(template_line)), Counter(_nums(text))
    for tok, cnt in rc.items():
        if pc.get(tok, 0) < cnt:
            log.warning("风掣预报行润色丢失/改动数字，回退模板\n初稿=%s\n输出=%s", template_line, text)
            return template_line

    # 区县名必须全部保留
    for d in districts:
        if d.name not in text:
            log.warning("风掣预报行润色缺失区县 '%s'，回退模板", d.name)
            return template_line

    log.info("风掣预报行 LLM 润色成功并通过校验")
    return text


def build_rainfall_forecast_line(
    *,
    tp_grid,
    masks,
    start_hour: int,
    end_hour: int,
    llm=None,
) -> Tuple[str, List[DistrictRain]]:
    """统计 + 生成「风掣预报」行的总入口。返回 (文案行, 区县雨强明细)。

    若传入 llm（已启用），仅在固定明细之前插入一句"降水概况"定性短语（不含数值），
    使文案更贴近预报员口吻；数值明细部分始终由代码原样拼接、不经 LLM 改写。
    概况生成失败/含数字时自动退回无概况版本，零数据风险。
    """
    districts = aggregate_district_rain(
        tp_grid.tp, masks.districts, masks.district_names
    )
    overview = build_overview_phrase(llm, districts) if llm is not None else ""
    line = build_rainfall_line_template(start_hour, end_hour, districts, overview)
    return line, districts
