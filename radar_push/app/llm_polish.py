"""大模型文案润色（可选）：数据由算法定，模型只重组措辞。

模板文本为唯一数据来源；LLM 输出经严格校验（数字/地名/落款必须保留、不得编造
带单位量值），任何异常/校验不通过/未配置都回退模板原文。接口为 OpenAI 兼容。
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Optional

import requests

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "你是气象台预警文案编辑。你的唯一任务是把给定的【预警初稿】改写得更自然、"
    "更符合气象播报口吻。这是用于公众发布的强对流天气预警，必须严谨。\n"
    "严格规则（违反任何一条都不可接受）：\n"
    "1. 不得新增、删除或修改任何数字、时间、方位（东/南/西/北等）、地名、单位；"
    "初稿里的所有数值与专有名词必须原样保留。\n"
    "2. 不得编造初稿中没有的任何具体量值（如降水量毫米数、风力级数、温度等）。\n"
    "3. 不得改变结论（是否影响本市、增强/减弱/维持、来源方向）；"
    "也不得增删对流天气现象（短时强降水、雷暴大风、局地小冰雹等），初稿列出哪些就保留哪些。\n"
    "3b. 雷达监测中的来源只能中性描述为相关区域\"有对流云团正在发展/活动\"，"
    "严禁出现\"移入\"\"移来\"\"自……方向移入\"\"局地生成\"等关于云团来向或生成方式的判断，初稿没写就绝不能加。\n"
    "3c. 「风掣预报：」整行必须原样保留、一字不改（该行已由系统定稿，含降水概况与各区县"
    "雨强明细），不得改写、不得调整其措辞或数值、不得增删其中任何文字。\n"
    "3d. 「实况提醒：」行：若为占位符原样保留；若为真实文案可润色措辞使其通顺，但数字/级数/"
    "地名一个都不得增删或改动。\n"
    "4. 只输出改写后的中文预警文本，不要解释、不要加引号、不要 Markdown。\n"
    "5. 保持简洁，长度与初稿相当（可±30%以内）。\n"
    "6. 标题行【…】（含其中的发布时间）必须原样保留在第一行，不得改动其中文字与时间。\n"
    "7. 保持初稿的分段结构：标题【…】、\"雷达监测：\"、\"实况提醒：\"、\"趋势预测：\"、\"风掣预报：\"各占一行；"
    "若初稿含\"具体影响乡镇如下\"段落，必须原样保留该段每一行（区县名与其乡镇列表不得改动），"
    "用换行分隔，不得合并成一段。"
)

# 数字紧跟降水/风力等单位，用于拦截模型擅自编造的量值
_DANGEROUS_VALUE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:毫米|mm|公里/小时|km/h|米/秒|m/s|级|摄氏度|℃|°C|百帕|hPa)",
    re.IGNORECASE,
)


def _extract_numbers(text: str) -> List[str]:
    return re.findall(r"\d+", text)


# 风掣预报行前缀：该行数字密集（各区县小时雨强），整段零容错校验易误杀，
# 故校验时把它单独剥离，用"宽松但仍要求数字不丢"的口径单独核对。
_FENGCHE_PREFIX = "风掣预报"


def _split_fengche(text: str) -> tuple[str, str]:
    """把文本按行拆成 (非风掣部分, 风掣行)。无风掣行则风掣部分为空串。

    兼容行首可能带的 emoji/符号前缀（如 "🌧 风掣预报：…"），按"该行是否包含
    风掣预报前缀"判断，而非严格以其开头。
    """
    others: List[str] = []
    fengche: List[str] = []
    for ln in text.splitlines():
        if _FENGCHE_PREFIX in ln:
            fengche.append(ln)
        else:
            others.append(ln)
    return "\n".join(others), "\n".join(fengche)


def _multiset_le(required: List[str], produced: List[str]) -> bool:
    """required 中每个数字按出现次数都应在 produced 中出现至少同样多次。"""
    rc, pc = Counter(required), Counter(produced)
    for tok, cnt in rc.items():
        if pc.get(tok, 0) < cnt:
            return False
    return True


def _enforce_tail(text: str, tail: str) -> Optional[str]:
    """确保落款 tail 固定在句尾：已在结尾则原样返回，出现一次则移到末尾，否则返回 None。"""
    if not tail:
        return text
    t = text.rstrip()
    if t.endswith(tail):
        return t
    cnt = t.count(tail)
    if cnt != 1:
        return None
    body = t.replace(tail, "", 1).strip()
    body = body.rstrip("：:，,。；; \u3000").strip()
    if not body:
        return None
    return f"{body}{tail}"


def _validate(
    template_text: str,
    candidate: str,
    must_keep: List[str],
    tail: str = "",
) -> Optional[str]:
    """校验 LLM 输出，通过返回清洗后的文本，否则返回 None。"""
    if not candidate:
        return None
    text = candidate.strip().strip("「」\"'`").strip()
    text = re.sub(r"[ \t\u3000]*\n[ \t\u3000]*", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)

    if tail:
        fixed = _enforce_tail(text, tail)
        if fixed is None:
            log.warning("LLM 润色未把落款保持在句尾且无法修复，回退模板\n输出=%s", text)
            return None
        text = fixed

    if len(text) < 10:
        log.warning("LLM 润色结果过短，回退模板")
        return None
    if len(text) > len(template_text) * 2:
        log.warning("LLM 润色结果过长(%d vs 模板%d)，回退模板", len(text), len(template_text))
        return None

    # 校验拆分：风掣预报行数字密集（各区县小时雨强），整段做"危险量值零容错"会被
    # 范围表达（如 10-25毫米 改写）频繁误杀，进而连累整段回退。故按行剥离：
    #   · 非风掣部分：沿用严格口径（数字不丢 + 不得多出任何"数字+单位"量值）；
    #   · 风掣行：放宽——允许改写措辞与范围表达，但仍要求其中数字一个都不少
    #     （尽量保留数字），不再做危险量值零容错。
    tmpl_others, tmpl_fengche = _split_fengche(template_text)
    out_others, out_fengche = _split_fengche(text)

    # 数字不丢：非风掣部分与风掣行分别核对，避免一处多出的数字掩盖另一处的缺失。
    if not _multiset_le(_extract_numbers(tmpl_others), _extract_numbers(out_others)):
        log.warning("LLM 润色丢失/改动了数字（正文），回退模板\n初稿=%s\n输出=%s",
                    template_text, text)
        return None
    if tmpl_fengche and not _multiset_le(
        _extract_numbers(tmpl_fengche), _extract_numbers(out_fengche)
    ):
        log.warning("LLM 润色丢失/改动了风掣预报行数字，回退模板\n初稿=%s\n输出=%s",
                    tmpl_fengche, out_fengche)
        return None

    # 危险量值零容错：仅对非风掣部分（风掣行豁免，允许范围措辞改写）。
    tmpl_dangerous = set(_DANGEROUS_VALUE_RE.findall(tmpl_others))
    out_dangerous = set(_DANGEROUS_VALUE_RE.findall(out_others))
    extra = out_dangerous - tmpl_dangerous
    if extra:
        log.warning("LLM 润色引入了模板没有的量值 %s（正文），回退模板", extra)
        return None

    for kw in must_keep:
        if kw and kw not in text:
            log.warning("LLM 润色缺失关键信息 '%s'，回退模板", kw)
            return None

    return text


def _build_facts_block(facts: Dict[str, object]) -> str:
    lines = ["【结构化事实，仅供参考，不得改动其中任何数值/地名】"]
    for k, v in facts.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def polish_text(
    llm,
    template_text: str,
    facts: Dict[str, object],
    must_keep: List[str],
    tail: str = "",
) -> str:
    """调用 OpenAI 兼容接口润色；失败/校验不过则返回模板原文。"""
    if not getattr(llm, "enabled", False):
        return template_text
    if not (llm.base_url and llm.model):
        log.warning("LLM 已启用但 base_url/model 未配置完整，使用模板")
        return template_text

    user_prompt = (
        f"{_build_facts_block(facts)}\n\n"
        f"【预警初稿】\n{template_text}\n\n"
        f"请在不改变任何数据的前提下，改写为更自然的气象预警文本。只输出文本本身。"
    )
    payload = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(getattr(llm, "temperature", 0.2)),
        "stream": False,
        "enable_thinking": bool(getattr(llm, "enable_thinking", False)),
    }
    headers = {"Content-Type": "application/json"}
    if llm.api_key:
        headers["Authorization"] = f"Bearer {llm.api_key}"

    url = f"{llm.base_url}/chat/completions"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=llm.timeout)
        data = resp.json()
        candidate = data["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning("LLM 润色请求失败(%s)，回退模板", e)
        return template_text

    validated = _validate(template_text, str(candidate), must_keep, tail=tail)
    if validated is None:
        return template_text
    log.info("LLM 润色成功并通过校验")
    return validated
