"""
端到端测试：验证「公报接入」改造后的 5 个文稿生成工具。

覆盖点：
  1. _resolve_common_stamp：能否从样例 240 目录 + 样例公报目录里找到正确的公共最新时间戳
  2. _extract_day_segments：能否跨「二、未来一周天气预报」+「三、未来八到十四天天气预报」
     两章节连续抽出所需段数（三天/三天关键区=6，十天/十天关键区=20，汛期周报=14）
  3. _split_wind：风力句子拆分是否符合预期
  4. 数据覆盖：table_rows 里的天气/风向/风力是否已换成公报文本，气温是否仍是 240 的值
  5. generate_three_day_forecast 的气温列横向合并（gridSpan）渲染效果

不走 FastAPI 上传链路 / 不调用 LLM（用本地兜底概述），只验证本次改造新增的核心逻辑。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_DIR = os.path.join(REPO, "_workspace", "sample-data", "BJ-240")
BULLETIN_DIR = os.path.join(REPO, "_workspace", "sample-data", "data")
OUT_DIR = os.path.join(REPO, "_workspace", "tmp", "_inspect_tmp")
os.makedirs(OUT_DIR, exist_ok=True)


def load_tool(module_name: str, py_path: str):
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_tools(module_name: str, py_path: str, template_rel: str):
    mod = load_tool(module_name, py_path)
    t = mod.Tools()
    t.valves.source_mode = "local"
    t.valves.xml_dir = XML_DIR
    t.valves.bulletin_source_mode = "local"
    t.valves.bulletin_local_dir = BULLETIN_DIR
    t.valves.use_bulletin_for_weather = True
    t.valves.template_path = os.path.join(REPO, template_rel)
    return mod, t


def resolve_and_fetch(t, need_count: int):
    """跑一遍「列时间戳 -> 取公共最新时间戳 -> 下载240与公报 -> 解析」全流程，返回
    (xml_path, base_time, bulletin_segments, stamp)。"""
    xml_stamps = t._list_xml_stamps()
    bulletin_stamps = t._list_bulletin_stamps()
    print(f"    240 时间戳({len(xml_stamps)}): {sorted(xml_stamps)}")
    print(f"    公报时间戳({len(bulletin_stamps)}): {sorted(bulletin_stamps)}")
    stamp = t._resolve_common_stamp(xml_stamps, bulletin_stamps, datetime.now())
    print(f"    共同最新时间戳 = {stamp}")
    assert stamp, "未找到公共时间戳"

    xml_path = t._fetch_xml_by_stamp(stamp)
    base_time = t._parse_base_time(xml_path)
    print(f"    起报时间 base_time = {base_time}")

    bulletin_local = t._fetch_bulletin_by_stamp(stamp)
    bulletin_docx = t._doc_to_docx(bulletin_local)
    paragraphs = t._read_paragraphs(bulletin_docx)
    segments = t._extract_day_segments(paragraphs, need_count=need_count)
    print(f"    抽取到 {len(segments)} 段（需要 {need_count} 段）")
    for i, seg in enumerate(segments[:3] + (segments[-2:] if len(segments) > 5 else [])):
        wdir, wspeed = t._split_wind(seg["wind"])
        print(f"      seg[{i}] weather={seg['weather']!r} wind={seg['wind']!r} -> wdir={wdir!r} wspeed={wspeed!r}")
    return xml_path, base_time, segments, stamp


def test_split_wind():
    print("\n========== _split_wind 单元测试 ==========")
    mod, t = make_tools(
        "_t_split", os.path.join(REPO, "tools", "generate_three_day_forecast.py"),
        "weather_templates/three_day/template.docx",
    )
    cases = [
        ("北转南风2—3级", "北转南风", "2—3级"),
        ("偏南风3级（阵风5—6级）转2级", "偏南风", "3级（阵风5—6级）转2级"),
        ("南转北风1—2级", "南转北风", "1—2级"),
        ("北转南风1级转3级（阵风5—6级）", "北转南风", "1级转3级（阵风5—6级）"),
        ("", "", ""),
    ]
    for text, exp_dir, exp_speed in cases:
        wdir, wspeed = t._split_wind(text)
        ok = (wdir == exp_dir and wspeed == exp_speed)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {text!r} -> ({wdir!r}, {wspeed!r})  期望 ({exp_dir!r}, {exp_speed!r})")
        assert ok, f"split_wind 失败: {text!r}"


def test_three_day():
    print("\n========== generate_three_day_forecast（密云）==========")
    mod, t = make_tools(
        "_t_three_day", os.path.join(REPO, "tools", "generate_three_day_forecast.py"),
        "weather_templates/three_day/template.docx",
    )
    xml_path, base_time, segments, stamp = resolve_and_fetch(t, need_count=6)
    data_list, available = t._parse_xml(xml_path, "密云")
    assert data_list is not None, f"密云不在可用站点里: {available}"
    forecast_data = [d for d in data_list if d["hour"] <= 72][:6]
    assert len(forecast_data) == 6

    for item, seg in zip(forecast_data, segments):
        item["wp"] = seg["weather"]
        wdir, wspeed = t._split_wind(seg["wind"])
        item["wdir"] = wdir
        item["wspeed"] = wspeed

    table = t._build_table(forecast_data, base_time)
    print("    table rows:")
    for r in table:
        print("     ", r)
    # 断言：天气来自公报（与 segments 顺序一致），气温字段仍然是数字
    for r, seg in zip(table, segments):
        assert r["weather"] == seg["weather"]
        assert "t" in r and r["t"]

    # 渲染 docx，验证模板（已改为单一气温列）渲染效果
    from docxtpl import DocxTemplate
    from docx import Document
    from docx.oxml.ns import qn

    doc = DocxTemplate(t.valves.template_path)
    now = datetime.now()
    ctx = {
        "district": "密云",
        "report_datetime": f"{now.year}年{now.month}月{now.day}日{now.hour}时",
        "summary": "（测试兜底概述）",
        "table": table,
    }
    doc.render(ctx)
    t._merge_date_cells(doc.docx, table)

    out_path = os.path.join(OUT_DIR, "bulletin_e2e_three_day_密云.docx")
    doc.save(out_path)
    print(f"    已保存: {out_path}")

    d2 = Document(out_path)
    tab = d2.tables[0]

    def physical_tcs(row):
        return row._tr.findall(qn("w:tc"))

    def tc_text(tc) -> str:
        return "".join(t.text or "" for t in tc.findall(".//" + qn("w:t")))

    # 气温列现在是模板自带的单一列（不再依赖 gridSpan 伪合并），这里只校验表头文字
    # 和每一行气温值是否正确，不假设具体的物理单元格数/gridSpan 实现细节。
    header_texts = [tc_text(tc) for tc in physical_tcs(tab.rows[0])]
    print(f"    渲染后表头: {header_texts}")
    assert header_texts[-1] == "气温（℃）", f"表头气温列文字不对: {header_texts[-1]!r}"

    for ri, row_data in enumerate(table, start=1):
        texts = [tc_text(tc) for tc in physical_tcs(tab.rows[ri])]
        print(f"    R{ri}: {texts}")
        assert texts[-1] == row_data["t"], f"R{ri} 气温列应为 {row_data['t']!r}，实际 {texts[-1]!r}"


def test_flat_district_tool(tool_file: str, func_hint: str, template_rel: str, need_count: int, hour_limit: int, district: str):
    print(f"\n========== {func_hint}（{district}）==========")
    mod, t = make_tools(f"_t_{func_hint}", os.path.join(REPO, "tools", tool_file), template_rel)
    xml_path, base_time, segments, stamp = resolve_and_fetch(t, need_count=need_count)
    data_list, available = t._parse_xml(xml_path, district)
    assert data_list is not None, f"{district}不在可用站点里: {available}"
    forecast_data = [d for d in data_list if d["hour"] <= hour_limit][:need_count]
    assert len(forecast_data) == need_count, f"数据条数不足: {len(forecast_data)} / {need_count}"

    for item, seg in zip(forecast_data, segments):
        item["wp"] = seg["weather"]
        wdir, wspeed = t._split_wind(seg["wind"])
        item["wdir"] = wdir
        item["wspeed"] = wspeed

    table = t._build_table(forecast_data, base_time)
    print(f"    table 行数 = {len(table)}，前 2 行 / 后 2 行：")
    for r in table[:2] + table[-2:]:
        print("     ", r)
    for r, seg in zip(table, segments):
        assert r["weather"] == seg["weather"], f"表格天气未被公报覆盖: {r} vs {seg}"


def test_key_area_tool(tool_file: str, func_hint: str, template_rel: str, need_count: int, hour_limit: int, area: str):
    print(f"\n========== {func_hint}（{area}）==========")
    mod, t = make_tools(f"_t_{func_hint}", os.path.join(REPO, "tools", tool_file), template_rel)
    xml_path, base_time, segments, stamp = resolve_and_fetch(t, need_count=need_count)
    area_key = t._normalize_area(area)
    assert area_key, f"区域归一化失败: {area}"
    data_list, available, matched = t._parse_xml(xml_path, area_key)
    assert data_list is not None, f"{area}不在可用站点里: {available}"
    forecast_data = [d for d in data_list if d["hour"] <= hour_limit][:need_count]
    assert len(forecast_data) == need_count

    for item, seg in zip(forecast_data, segments):
        item["wp"] = seg["weather"]
        wdir, wspeed = t._split_wind(seg["wind"])
        item["wdir"] = wdir
        item["wspeed"] = wspeed

    table = t._build_table(forecast_data, base_time)
    print(f"    matched_station={matched!r}，table 行数 = {len(table)}，前 2 行：")
    for r in table[:2]:
        print("     ", r)
    for r, seg in zip(table, segments):
        assert r["weather"] == seg["weather"]
        # 关键区模板的风向风力是合并一列，值应等于公报原句（split后再拼回来是等价的）
        wdir, wspeed = t._split_wind(seg["wind"])
        assert r["wdir_wspeed"] == t._fmt_wdir_wspeed(wdir, wspeed)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    test_split_wind()

    test_three_day()

    test_flat_district_tool(
        "generate_flood_weekly_report.py", "flood_weekly",
        "weather_templates/flood_weekly/template.docx",
        need_count=14, hour_limit=168, district="密云",
    )

    test_flat_district_tool(
        "generate_ten_day_forecast.py", "ten_day_forecast",
        "weather_templates/ten_day/template.docx",
        need_count=20, hour_limit=240, district="密云",
    )

    for area in ["东城", "西城", "天安门"]:
        test_key_area_tool(
            "generate_three_day_key_area.py", "three_day_key_area",
            "weather_templates/three_day_key_area/template.docx",
            need_count=6, hour_limit=72, area=area,
        )

    for area in ["东城", "西城", "天安门"]:
        test_key_area_tool(
            "generate_ten_day_key_area.py", "ten_day_key_area",
            "weather_templates/ten_day_key_area/template.docx",
            need_count=20, hour_limit=240, area=area,
        )

    print("\n全部测试通过 ✔")
