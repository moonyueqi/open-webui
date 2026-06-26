"""
本地测试 sz_weekly_weather_tool.py 的解析逻辑。
用用户给的示例 JSON mock 掉 HTTP 请求，验证 days 和 summary 输出。

运行方式（在仓库根目录或 tools_python/ 目录下）：

    python tools_python/tests/test_weekly_tool.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 让 `from sz_weekly_weather_tool import Tools` 能找到上一级目录里的同名文件
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOCK_RESPONSE = {
    "status": "0",
    "message": "查询成功。",
    "data": {
        "code": "7DaysForecast",
        "name": "一周天气预报",
        "creator": "张祎",
        "issue": "475",
        "time": "2026-05-06 09:07:24",
        "filename": "一周天气预报-20260506.doc",
        "word": "http://10.127.13.163:8080/wmsfile//word//history//2026//0506//9b262efae1414b8bafde7b2fb40caa6a_20260506090715441.doc",
        "content": (
            "未来一周天气预测\n"
            "苏州市气象局\n"
            "2026年05月06日发布\n"
            "\n\n"
            "日期\n时段\n天气现象\n降水概率\n风向风力\n气温\n"
            "06日\n白天\n晴到多云\n20%\n东南风4～5级\n18～27℃\n"
            "\n夜晚\n晴到多云\n20%\n东南风4～5级\n"
            "\n07日\n白天\n上午多云，下午转阴有阵雨或雷雨\n70%\n南风3～4级转北风4～5级阵风6级、水面阵风7级\n17～28℃\n"
            "\n夜晚\n阵雨渐止转阴到多云\n60%\n北风4～5级阵风6级、水面阵风7级\n"
            "\n08日\n白天\n多云\n30%\n东北风4～5级阵风6级\n16～24℃\n"
            "\n夜晚\n多云\n30%\n东风转南风，风力都是3～4级\n"
            "\n09日\n白天\n多云\n30%\n东南风4～5级阵风6级\n13～25℃\n"
            "\n夜晚\n多云\n30%\n东南风4～5级\n"
            "\n10日\n白天\n多云\n30%\n南风4～5级\n16～27℃\n"
            "\n夜晚\n多云\n30%\n南风3～4级\n"
            "\n11日\n白天\n多云到晴\n20%\n南风4级左右\n18～31℃\n"
            "\n夜晚\n多云到晴\n20%\n南风4级左右\n"
            "\n12日\n白天\n晴到多云\n20%\n南风3～4级\n21～33℃\n"
            "\n夜晚\n晴到多云\n20%\n东南风4级左右\n"
            "\n13日\n白天\n多云\n20%\n东南风4～5级阵风6级\n22～33℃\n"
            "\n夜晚\n多云转阴\n40%\n东南风4～5级阵风6级\n"
            "\n\n"
        ),
    },
}


def make_mock_response():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status.return_value = None
    mock_resp.status_code = 200
    return mock_resp


def test_parse():
    from sz_weekly_weather_tool import Tools

    tool = Tools()

    with patch("sz_weekly_weather_tool.requests.get", return_value=make_mock_response()):
        result_str = tool.get_suzhou_weekly_forecast()

    result = json.loads(result_str)

    assert "error" not in result, f"Unexpected error: {result}"

    days = result["days"]
    print(f"Parsed {len(days)} days:")
    for d in days:
        print(f"  {d['date']}: day={d['day']['phenomenon']}, "
              f"temp={d['day'].get('temp_range', 'N/A')}, "
              f"night={d.get('night', {}).get('phenomenon', 'N/A')}")

    assert len(days) == 8, f"Expected 8 days, got {len(days)}"

    assert days[0]["date"] == "06日"
    assert days[0]["day"]["phenomenon"] == "晴到多云"
    assert days[0]["day"]["temp_range"] == "18～27℃"
    assert days[0]["night"]["phenomenon"] == "晴到多云"

    assert days[1]["date"] == "07日"
    assert "阵雨" in days[1]["day"]["phenomenon"]
    assert days[1]["day"]["precip_prob"] == "70%"

    assert days[7]["date"] == "13日"
    assert days[7]["night"]["phenomenon"] == "多云转阴"

    assert result["source"] == "苏州市气象局"
    assert result["issued_at"] == "2026-05-06 09:07:24"

    summary = result["summary"]
    print(f"\nSummary: {summary}")
    assert "苏州市气象局" in summary
    assert "06日" in summary
    assert "13日" in summary
    assert "disclaimer" in result

    print("\n--- Full JSON output ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n[OK] All assertions passed!")


if __name__ == "__main__":
    test_parse()
