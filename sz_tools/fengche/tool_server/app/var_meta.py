"""要素元数据：中文名、单位、单位换算函数。"""

from __future__ import annotations

from typing import Any, Dict


VAR_LABELS: Dict[str, Dict[str, Any]] = {
    "t2m":  {"label": "2米气温",     "unit": "℃",     "convert": "K_to_C"},
    "q2m":  {"label": "2米比湿",     "unit": "kg/kg", "convert": None},
    "u10m": {"label": "10米U风",     "unit": "m/s",   "convert": None},
    "v10m": {"label": "10米V风",     "unit": "m/s",   "convert": None},
    "ws":   {"label": "10米风速",    "unit": "m/s",   "convert": None},
    "gs":   {"label": "阵风",        "unit": "m/s",   "convert": None},
    "cr":   {"label": "雷达回波",    "unit": "dBZ",   "convert": None},
    "tp":   {"label": "逐小时降水",  "unit": "mm",    "convert": None},
}


def convert_value(var_name: str, value: float | None) -> float | None:
    """对原始数值做单位换算，返回展示用值。NaN/None 透传。"""
    if value is None:
        return None
    meta = VAR_LABELS.get(var_name)
    if not meta:
        return value
    conv = meta.get("convert")
    if conv == "K_to_C":
        return round(value - 273.15, 2)
    return round(value, 4)


def labels_for(returned_variables: list[str]) -> Dict[str, Dict[str, str]]:
    """生成给客户端的 labels 映射（不含 convert 内部字段）。未识别的变量原样兜底。"""
    out: Dict[str, Dict[str, str]] = {}
    for v in returned_variables:
        meta = VAR_LABELS.get(v)
        if meta:
            out[v] = {"label": meta["label"], "unit": meta["unit"]}
        else:
            out[v] = {"label": v, "unit": ""}
    return out


def conversions_applied(returned_variables: list[str]) -> list[str]:
    """生成 unit_conversions 字段，仅包含真正发生过单位换算的项。"""
    notes = []
    for v in returned_variables:
        meta = VAR_LABELS.get(v)
        if meta and meta.get("convert") == "K_to_C":
            notes.append(f"{v}: K → ℃")
    return notes


def unknown_variables(returned_variables: list[str]) -> list[str]:
    return [v for v in returned_variables if v not in VAR_LABELS]
