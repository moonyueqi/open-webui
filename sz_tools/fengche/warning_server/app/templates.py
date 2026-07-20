"""官方标准预报用语 + 防御指南文本。

文本严格按用户提供的版本，不擅自修改。运行时由 build_advisory() 填充
{time}（时段，带日期）与 {area}（区名）两个占位符。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ----------------------------------------------------------------------------
# 暴雨预报用语：同一级别下按触发窗口 (1h / 6h / 24h) 选不同描述词
# ----------------------------------------------------------------------------
RAIN_FORECAST_TEXT: Dict[str, Dict[str, str]] = {
    "blue": {
        "1h":  "预计{time}，{area}将出现短时强降水。",
        "6h":  "预计{time}，{area}将出现短时暴雨。",
        "24h": "预计{time}，{area}将出现暴雨。",
    },
    "yellow": {
        "1h":  "预计{time}，{area}将出现短时强降水，局地短时暴雨。",
        "6h":  "预计{time}，{area}将出现暴雨到大暴雨。",
        "24h": "预计{time}，{area}将出现暴雨到大暴雨。",
    },
    "orange": {
        "1h":  "预计{time}，{area}将出现短时大暴雨。",
        "6h":  "预计{time}，{area}将出现大暴雨。",
        "24h": "预计{time}，{area}将出现大暴雨。",
    },
    "red": {
        "1h":  "预计{time}，{area}将出现短时特大暴雨。",
        "6h":  "预计{time}，{area}将出现特大暴雨。",
        "24h": "预计{time}，{area}将出现特大暴雨。",
    },
}


# ----------------------------------------------------------------------------
# 强对流（阵风）预报用语：按级别分（不区分窗口）
# ----------------------------------------------------------------------------
WIND_FORECAST_TEXT: Dict[str, str] = {
    "yellow": "预计{time}，{area}将出现8级以上大风，阵风9级以上。",
    "orange": "预计{time}，{area}将出现10级以上大风，阵风11级以上。",
    "red":    "预计{time}，{area}将出现12级以上大风，阵风13级以上。",
}


# ----------------------------------------------------------------------------
# 防御指南（暴雨 4 级 + 强对流 3 级，按官方文本逐字录入）
# ----------------------------------------------------------------------------
DEFENSE_GUIDES: Dict[Tuple[str, str], List[str]] = {
    # ---- 暴雨 ----
    ("rainstorm", "blue"): [
        "请广大市民及时关注气象预报信息，出门携带雨具。",
        "不要在高楼或大型广告牌下躲雨、停留，以免被坠落物砸伤。",
        "注意道路湿滑和积水，确保驾驶安全。",
    ],
    ("rainstorm", "yellow"): [
        "请广大市民及时关注气象预警信息，降雨期间减少出行，确需外出尽量选乘公共交通。",
        "请勿前往地质灾害易发区，远离高压线和沟道河道，避开低洼区域。",
        "不参加各类室外活动；暂停户外高空作业，及时就近安全避雨。",
        "驾驶人员注意绕行积水较深区域，避免强行通过。",
        "检查室内插座、燃气用具等是否安全。",
    ],
    ("rainstorm", "orange"): [
        "请广大市民减少外出，及时关注气象预警和提示信息，确需外出尽量选乘公共交通。",
        "倡导企事业单位采取弹性工作方式或错峰上下班。",
        "学校视情停学，停止线下培训和野外教学活动。",
        "请勿前往涉山涉水类景区和地下经营性场所，远离地质灾害易发区和沟道河道等涉险区域。",
        "不参加各类室外活动，停止户外作业和施工。",
        "遇有积水路段，请勿涉水行车，不要在低洼路段和区域停放车辆。",
        "检查室内插座、燃气用具等是否安全。",
    ],
    ("rainstorm", "red"): [
        "请广大市民非必要不外出，遇有紧急情况请及时拨打110或119求助。",
        "企事业单位除保障城市运行、民生服务等外，非必要不要求员工到岗上班。",
        "学校停止线下教学和野外教学活动，培训机构停止线下培训活动。",
        "禁止前往涉山涉水区域和景区、公园、林场、民俗户游玩。",
        "平房、危旧房屋、低洼院落、地下（半地下）室居住人员密切关注降雨内涝风险，及时避险。",
        "所有地下经营场所停业，在建工地停工。",
        "受灾害风险威胁人员服从转移安排。",
    ],
    # ---- 强对流 ----
    ("strong_convection", "yellow"): [
        "停止户外有组织的体育或集会活动，中小学、幼儿园、相关培训机构停止户外活动。",
        "老、弱、病、幼减少户外活动。",
        "停止室外动火、露天烧烤等易引发火灾的行为。",
        "注意出行安全，车辆和人员避免在高大建筑物、广告牌、临时搭建物或大树的下方停留。",
        "停止高空、水上户外作业和游乐活动。",
    ],
    ("strong_convection", "orange"): [
        "停止户外有组织的体育或集会活动，中小学、幼儿园、相关培训机构停止户外活动。",
        "公众避免露天活动，严禁一切室外用火行为。",
        "非必要不出行，车辆和人员不在高大建筑物、广告牌、临时搭建物或大树的下方停留。",
        "停止一切室外施工作业和游乐活动。",
    ],
    ("strong_convection", "red"): [
        "非必要不外出，室外人员立即到防风安全位置躲避。",
        "停止一切露天活动，严禁一切室外用火行为，切断户外危险电源。",
        "驾驶人员要谨慎驾驶，风力较大时应在安全处停车。",
        "室内人员关好门窗，并远离窗口。",
    ],
}


# ----------------------------------------------------------------------------
# 区域名（区代码 → 中文展示名）。覆盖苏州市下属 10 个区/县级市。
# 兼容旧 code "gaoxin"（=虎丘区/高新区），如有调用方仍传 gaoxin 也能识别。
# ----------------------------------------------------------------------------
AREA_LABELS: Dict[str, str] = {
    "gusu":         "姑苏区",
    "huqiu":        "虎丘区（高新区）",
    "gaoxin":       "虎丘区（高新区）",  # 历史别名
    "wuzhong":      "吴中区",
    "xiangcheng":   "相城区",
    "wujiang":      "吴江区",
    "sip":          "苏州工业园区",
    "changshu":     "常熟市",
    "zhangjiagang": "张家港市",
    "kunshan":      "昆山市",
    "taicang":      "太仓市",
}


# ----------------------------------------------------------------------------
# 时间/起报展示函数
# ----------------------------------------------------------------------------
def format_time_range(start: datetime, end: datetime) -> str:
    """把一对 datetime 渲染为：
    - 同一小时（start==end）：'5月22日 18时前后'
    - 同一天跨小时：'5月22日 18时至20时'
    - 跨天：'5月22日 22时至5月23日 02时'
    """
    if start == end:
        return f"{start.month}月{start.day}日 {start.hour}时前后"
    if start.date() == end.date():
        return f"{start.month}月{start.day}日 {start.hour}时至{end.hour}时"
    return (
        f"{start.month}月{start.day}日 {start.hour}时至"
        f"{end.month}月{end.day}日 {end.hour}时"
    )


def format_issue_time_human(issue_time: datetime) -> str:
    """把起报时间渲染为 '5月22日 15时' 用于追加溯源标注。"""
    return f"{issue_time.month}月{issue_time.day}日 {issue_time.hour}时"


def issue_source_suffix(issue_time: datetime) -> str:
    """预报用语末尾的溯源标注。"""
    return f"（参考：风掣 AI {format_issue_time_human(issue_time)} 起报）"


# ----------------------------------------------------------------------------
# 拼装单个 advisory（预报用语 + 防御指南）
# ----------------------------------------------------------------------------
def build_advisory(
    warning_type: str,
    level: str,
    triggered_by: Optional[str],
    start: datetime,
    end: datetime,
    area_code: str,
    issue_time: datetime,
) -> Dict[str, object]:
    """根据预警类型/级别/触发窗口/时段/区/起报时间，组装出 forecast_text 与 defense_guide。"""
    area_name = AREA_LABELS.get(area_code, area_code)
    time_str = format_time_range(start, end)
    source_suffix = issue_source_suffix(issue_time)

    if warning_type == "rainstorm":
        # 蓝色无 1h/24h 阈值，triggered_by 理论上恒为 '6h'；做个 safety fallback
        window = triggered_by if triggered_by in ("1h", "6h", "24h") else "6h"
        template = (
            RAIN_FORECAST_TEXT.get(level, {}).get(window)
            or RAIN_FORECAST_TEXT.get(level, {}).get("6h", "{area} 在 {time} 触发暴雨预警。")
        )
    elif warning_type == "strong_convection":
        template = WIND_FORECAST_TEXT[level]
    else:
        template = "{area} 在 {time} 触发未知预警类型。"

    forecast_text = template.format(time=time_str, area=area_name) + source_suffix
    defense_guide = list(DEFENSE_GUIDES.get((warning_type, level), []))

    return {
        "forecast_text": forecast_text,
        "defense_guide": defense_guide,
    }
