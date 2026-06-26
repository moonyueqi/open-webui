"""
title: 苏州一周天气预报
author: leadsee-webui-sz
version: 1.0.0
description: 调用苏州市气象局 7DaysForecast 接口，返回未来一周（白天/夜晚分时段）天气预报结构化数据。
"""

import re
import json
import requests
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        api_url: str = Field(
            default="http://10.127.13.163:8080/wms/productInter/getWebContent.action?code=7DaysForecast",
            description="苏州市气象局一周预报接口 URL",
        )
        timeout_seconds: int = Field(default=10, description="HTTP 请求超时（秒）")

    def __init__(self):
        self.valves = self.Valves()
        self.citation = True

    def get_suzhou_weekly_forecast(self) -> str:
        """
        查询苏州市气象局官方发布的未来一周天气预报（按日×白天/夜晚分时段）。
        当用户询问"苏州未来一周天气"、"苏州七天天气预报"、"苏州这周天气怎么样"、
        "苏州市气象局发布的天气预报"、"苏州周末天气"等问题时调用本工具。
        无需任何参数，直接调用即可。
        """
        try:
            resp = requests.get(
                self.valves.api_url,
                timeout=self.valves.timeout_seconds,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return json.dumps(
                {"error": f"请求气象局接口失败：{e}"},
                ensure_ascii=False,
            )

        try:
            payload = resp.json()
        except ValueError:
            return json.dumps(
                {
                    "error": "气象局接口返回的不是有效 JSON",
                    "raw_preview": resp.text[:500],
                },
                ensure_ascii=False,
            )

        if payload.get("status") != "0":
            return json.dumps(
                {
                    "error": f"气象局接口返回异常状态：{payload.get('message', '未知错误')}",
                    "raw_payload": payload,
                },
                ensure_ascii=False,
            )

        data = payload.get("data", {})
        content: str = data.get("content", "")
        if not content.strip():
            return json.dumps(
                {"error": "气象局接口返回的 content 为空"},
                ensure_ascii=False,
            )

        days = _parse_weekly_content(content)
        if not days:
            return json.dumps(
                {
                    "error": "无法解析天气预报内容，返回原文供参考",
                    "raw_content": content,
                },
                ensure_ascii=False,
            )

        summary = _build_summary(data, days)

        result = {
            "source": "苏州市气象局",
            "issued_at": data.get("time", ""),
            "issue_no": data.get("issue", ""),
            "doc_filename": data.get("filename", ""),
            "doc_url": data.get("word", ""),
            "days": days,
            "summary": summary,
            "disclaimer": "数据来源：苏州市气象局官方发布（7DaysForecast 接口）。",
        }
        return json.dumps(result, ensure_ascii=False)


def _parse_weekly_content(content: str) -> List[Dict[str, Any]]:
    """
    解析content 文本为结构化 days 列表。

    文本格式（每天两个时段）：
      DD日
      白天
      天气现象
      降水概率
      风向风力
      气温范围

      夜晚
      天气现象
      降水概率
      风向风力
    """
    lines = [ln.strip() for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]

    days: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        # 寻找 "DD日" 开头的行（日期标记）
        if not re.match(r"^\d{1,2}日$", lines[i]):
            i += 1
            continue

        date_label = lines[i]

        # 白天块：日期行之后依次是 "白天" / 现象 / 概率 / 风 / 气温
        if i + 5 >= len(lines) or lines[i + 1] != "白天":
            i += 1
            continue

        day_info = {
            "phenomenon": lines[i + 2],
            "precip_prob": lines[i + 3],
            "wind": lines[i + 4],
            "temp_range": lines[i + 5],
        }
        i += 6

        # 夜晚块：接下来找 "夜晚" 行，后跟 现象 / 概率 / 风
        night_info: Optional[Dict[str, str]] = None
        if i < len(lines) and lines[i] == "夜晚":
            if i + 3 < len(lines):
                night_info = {
                    "phenomenon": lines[i + 1],
                    "precip_prob": lines[i + 2],
                    "wind": lines[i + 3],
                }
                i += 4

        entry: Dict[str, Any] = {"date": date_label, "day": day_info}
        if night_info:
            entry["night"] = night_info
        days.append(entry)

    return days


def _build_summary(data: Dict[str, Any], days: List[Dict[str, Any]]) -> str:
    """根据解析好的 days 自动生成中文天气概述。"""
    issued_at = data.get("time", "未知时间")

    if not days:
        return f"苏州市气象局 {issued_at} 发布的未来一周天气预报。"

    date_range = f"{days[0]['date']}~{days[-1]['date']}"

    # 提取所有气温数值
    temps: List[int] = []
    for d in days:
        temp_str = d["day"].get("temp_range", "")
        nums = re.findall(r"(\d+)", temp_str)
        temps.extend(int(n) for n in nums)

    temp_summary = ""
    if temps:
        temp_summary = f"气温区间 {min(temps)}~{max(temps)}℃"

    # 找出降水概率 >= 50% 的天气（需要关注的雨天）
    rain_days: List[str] = []
    for d in days:
        for period_key, period_name in [("day", "白天"), ("night", "夜晚")]:
            period = d.get(period_key)
            if not period:
                continue
            prob_str = period.get("precip_prob", "0%")
            prob_num = int(re.search(r"\d+", prob_str).group()) if re.search(r"\d+", prob_str) else 0
            if prob_num >= 50:
                rain_days.append(
                    f"{d['date']}{period_name}{period['phenomenon']}（概率{prob_str}）"
                )

    rain_summary = ""
    if rain_days:
        rain_summary = "；需关注降水：" + "、".join(rain_days)

    parts = [
        f"苏州市气象局 {issued_at} 发布的未来一周（{date_range}）天气预报",
    ]
    if temp_summary:
        parts[0] += f"：{temp_summary}"
    if rain_summary:
        parts[0] += rain_summary
    parts[0] += "。"

    return parts[0]
