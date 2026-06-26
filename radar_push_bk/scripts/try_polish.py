"""本地试跑大模型文案润色效果（不依赖雷达数据、不发企业微信）。

它复用真实的算法模板（templates.build_alert_text）与 LLM 润色逻辑
（llm_polish.polish_text，含严格校验），用几组典型场景打印对比：
    模板原文  vs  LLM 润色结果  vs  是否通过校验（不通过会自动回退模板）。

用法（PowerShell）：
    # 1) 先配好 deploy/.env 里的 LLM_*（或在命令行临时设环境变量）
    #    至少需要：LLM_POLISH_ENABLED=true、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
    # 2) 运行：
    cd radar_push
    & "C:\\Users\\DELL\\.conda\\envs\\leadsee-webui\\python.exe" scripts\\try_polish.py

说明：
  - 脚本会从 deploy/.env 读取 LLM 配置（python-dotenv），也可用真实环境变量覆盖。
  - 即便 LLM_POLISH_ENABLED=false，脚本也会临时强制启用以便看效果（仅本地试跑）。
  - 任何异常/校验不过都会回退模板，属于预期的安全行为。
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# 让 `from app...` 可用
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 显式从 deploy/.env 加载（覆盖默认 .env 查找）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "deploy" / ".env")
load_dotenv(ROOT / ".env")  # 若根目录也放了 .env，做兜底

from app.config import load_settings  # noqa: E402
from app.llm_polish import polish_text  # noqa: E402
from app.templates import _fmt_time, build_alert_text, build_tail  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
OBSERVE = datetime(2026, 6, 12, 17, 0, tzinfo=TZ)
TIME_STR = _fmt_time(OBSERVE)

DISTRICT_NAMES = {
    "320509": "相城区",
    "320506": "吴中区",
    "320508": "吴江区",
}


# 每个场景：(标题, build_alert_text 入参, facts, must_keep)
def _scenarios():
    s = []

    # 场景1：上游移入，会影响本市，多区县乡镇
    affected1 = {
        "320509": {"元和街道", "黄桥街道"},
        "320508": {"盛泽镇"},
    }
    merged_names1 = ["相城区", "吴江区"]
    s.append((
        "上游移入·影响本市·45dBZ·东南移·增强",
        dict(
            observe_time=OBSERVE, level_dbz=45,
            upstream_names=["无锡", "常州"], local_origin_districts="",
            direction="东南", trend="增强", will_enter_city=True,
            affected=affected1, district_names=DISTRICT_NAMES,
        ),
        {
            "发布时间": TIME_STR, "强度等级": "45dBZ", "来源": "无锡、常州方向移入",
            "移动方向": "东南", "趋势": "增强", "是否影响本市": "是",
            "受影响区县乡镇": "、".join(merged_names1),
        },
        [TIME_STR, *merged_names1, "无锡", "常州"],
    ))

    # 场景2：局地生成，会影响本市
    affected2 = {"320506": {"木渎镇"}}
    s.append((
        "局地生成·影响本市·40dBZ·少动·维持",
        dict(
            observe_time=OBSERVE, level_dbz=40,
            upstream_names=[], local_origin_districts="吴中区",
            direction="少动", trend="维持", will_enter_city=True,
            affected=affected2, district_names=DISTRICT_NAMES,
        ),
        {
            "发布时间": TIME_STR, "强度等级": "40dBZ", "来源": "吴中区局地生成",
            "移动方向": "少动", "趋势": "维持", "是否影响本市": "是",
            "受影响区县乡镇": "吴中区",
        },
        [TIME_STR, "吴中区"],
    ))

    # 场景3：缓冲区有回波但不入市（无明显影响变体）
    s.append((
        "上游·对本市无明显影响·35dBZ·西北移·减弱",
        dict(
            observe_time=OBSERVE, level_dbz=35,
            upstream_names=["湖州"], local_origin_districts="",
            direction="西北", trend="减弱", will_enter_city=False,
            affected={}, district_names=DISTRICT_NAMES,
        ),
        {
            "发布时间": TIME_STR, "强度等级": "35dBZ", "来源": "湖州方向移入",
            "移动方向": "西北", "趋势": "减弱", "是否影响本市": "否",
            "受影响区县乡镇": "无",
        },
        [TIME_STR, "湖州"],
    ))

    # 场景4：上游(市外)与苏州本地同时有强回波 -> 来源并列同报
    affected4 = {
        "320509": {"元和街道"},   # 相城区（本地已有）
        "320508": {"盛泽镇"},     # 吴江区（外推将影响）
    }
    merged_names4 = ["相城区", "吴江区"]
    s.append((
        "上游+本地同时有·影响本市·45dBZ·东南移·增强",
        dict(
            observe_time=OBSERVE, level_dbz=45,
            upstream_names=["无锡"], local_origin_districts="相城区",
            direction="东南", trend="增强", will_enter_city=True,
            affected=affected4, district_names=DISTRICT_NAMES,
        ),
        {
            "发布时间": TIME_STR, "强度等级": "45dBZ",
            "来源": "无锡方向移入；相城区局地生成",
            "移动方向": "东南", "趋势": "增强", "是否影响本市": "是",
            "受影响区县乡镇": "、".join(merged_names4),
        },
        [TIME_STR, *merged_names4, "无锡"],
    ))

    return s


def _list_models(llm) -> int:
    """调用 OpenAI 兼容的 GET /models 列出当前 key 可用的模型名。"""
    import requests

    if not llm.base_url or not llm.api_key:
        print("！缺少 LLM_BASE_URL / LLM_API_KEY，无法查询模型列表。请先在 .env 配好。")
        return 2
    url = f"{llm.base_url}/models"
    headers = {"Authorization": f"Bearer {llm.api_key}"}
    print(f"GET {url}  (timeout=30s)")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"请求失败：{e}")
        print("  多半是网络/代理问题（连不上 dashscope），与模型名无关。")
        return 1
    print(f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        print(resp.text[:2000])
        return 0 if resp.ok else 1
    if not resp.ok:
        print("接口返回错误：")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
        return 1
    ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
    if ids:
        print(f"可用模型（共 {len(ids)} 个）：")
        for mid in sorted(filter(None, ids)):
            print(f"  - {mid}")
    else:
        print("返回成功但未解析到模型列表，原始返回：")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    return 0


def main() -> int:
    settings = load_settings()
    llm = settings.llm

    print("=" * 72)
    print(f"LLM 配置：enabled={llm.enabled} base_url={llm.base_url or '(空)'} "
          f"model={llm.model or '(空)'} key={'已配置' if llm.api_key else '(空)'}")
    print("=" * 72)

    # --list-models：仅查询可用模型名后退出
    if "--list-models" in sys.argv:
        return _list_models(llm)

    if not llm.api_key or not llm.base_url or not llm.model:
        print("！缺少 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，将只能看到模板原文（润色会回退）。")
        print("  请先在 radar_push/deploy/.env 配好后重试。")
    # 本地试跑：强制启用，便于看真实调用效果（不改磁盘配置）
    llm = dataclasses.replace(llm, enabled=True)
    print("=" * 72)

    for title, kwargs, facts, must_keep in _scenarios():
        template_text = build_alert_text(**kwargs)
        tail = build_tail(kwargs["observe_time"])
        polished = polish_text(llm, template_text, facts, must_keep, tail=tail)
        changed = polished != template_text
        print(f"\n■ 场景：{title}")
        print(f"  must_keep: {must_keep}")
        print(f"  【模板原文】\n    {template_text}")
        print(f"  【润色结果】（{'已改写并通过校验' if changed else '回退模板/未改动'}）\n    {polished}")

    print("\n" + "=" * 72)
    print("提示：润色结果若与模板一致，可能是未配置/请求失败/校验未通过（均自动回退，属安全行为）。")
    print("查看回退原因可临时把日志级别调到 WARNING 及以上观察 llm_polish 的告警。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
