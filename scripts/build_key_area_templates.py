"""
基于示例模板（材料模板/未来三天气象服务专报-东城-121607.docx 及十天版本），
生成两份带 docxtpl 变量占位符的可渲染模板：
  - weather_templates/three_day_key_area/template.docx
  - weather_templates/ten_day_key_area/template.docx

保留原版的字体、字号、对齐、表格样式与第一列合并样式（合并由代码渲染后再做，
模板里第一列保持普通单元格即可，但每行的样式属性已从示例复制过来）。
"""
from __future__ import annotations

import copy
import os
from docx import Document
from docx.oxml.ns import qn


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_THREE_DAY = os.path.join(
    REPO_ROOT, "材料模板", "未来三天气象服务专报-东城-121607.docx"
)
SAMPLE_TEN_DAY = os.path.join(
    REPO_ROOT, "材料模板", "未来十天气象服务专报-东城-010311.docx"
)

OUT_THREE_DAY = os.path.join(
    REPO_ROOT, "weather_templates", "three_day_key_area", "template.docx"
)
OUT_TEN_DAY = os.path.join(
    REPO_ROOT, "weather_templates", "ten_day_key_area", "template.docx"
)


def _set_paragraph_text(p, new_text: str) -> None:
    """把段落的纯文本换成 new_text，但保留第一个 run 的格式。
    其余 run 会被删除。若段落里没有 run，则新建一个。"""
    runs = p.runs
    if not runs:
        run = p.add_run(new_text)
        return
    keep = runs[0]
    keep.text = new_text
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def _set_cell_text(cell, new_text: str) -> None:
    """把单元格内容替换成 new_text，保留第一个段落的第一个 run 的格式。"""
    # 删掉除第一个段落以外的全部段落
    paragraphs = cell.paragraphs
    for p in paragraphs[1:]:
        p._element.getparent().remove(p._element)
    p = cell.paragraphs[0]
    _set_paragraph_text(p, new_text)


def _clear_vmerge(tbl) -> None:
    """删除示例模板里所有 vMerge 标签：合并由工具代码在渲染后动态做。"""
    for tc in tbl.findall(".//" + qn("w:tc")):
        tcPr = tc.find(qn("w:tcPr"))
        if tcPr is None:
            continue
        for vm in tcPr.findall(qn("w:vMerge")):
            tcPr.remove(vm)


def _rewrite_table_with_loop(table) -> None:
    """把表格改造成：表头 1 行 + 「{%tr for row in table %}」标签行 +
    数据循环行 + 「{%tr endfor %}」标签行。
    标签行直接复用示例文件里的数据行作为骨架（保留字体/字号/单元格属性），
    只是单元格内文本被替换成 docxtpl 行级标签；表头行保持不动。
    """
    tbl = table._tbl
    trs = tbl.findall(qn("w:tr"))
    # 至少要有：表头 + 3 个数据行作为骨架（用于 tr_for / data_row / tr_endfor）
    assert len(trs) >= 4, f"示例模板数据行不足: rows={len(trs)}"

    _clear_vmerge(tbl)

    # 取前 3 个数据行作为「{%tr for%}」「实际循环体」「{%tr endfor%}」三行骨架
    tr_for = table.rows[1]
    tr_body = table.rows[2]
    tr_end = table.rows[3]

    # docxtpl 行级标签：标签必须独占整段（每个单元格的文本都设为该标签即可，
    # 实际处理时 docxtpl 只关心是否能找到该标签所在的 <w:tr>）
    _set_cell_text(tr_for.cells[0], "{%tr for row in table %}")
    for ci in range(1, len(tr_for.cells)):
        _set_cell_text(tr_for.cells[ci], "")

    _set_cell_text(tr_body.cells[0], "{{row.date}}")
    _set_cell_text(tr_body.cells[1], "{{row.period}}")
    _set_cell_text(tr_body.cells[2], "{{row.weather}}")
    _set_cell_text(tr_body.cells[3], "{{row.wdir_wspeed}}")
    _set_cell_text(tr_body.cells[4], "{{row.t}}")
    _set_cell_text(tr_body.cells[5], "{{row.vis}}")

    _set_cell_text(tr_end.cells[0], "{%tr endfor %}")
    for ci in range(1, len(tr_end.cells)):
        _set_cell_text(tr_end.cells[ci], "")

    # 删掉示例里多余的数据行（只保留表头 + tr_for + tr_body + tr_endfor）
    for extra_tr in trs[4:]:
        tbl.remove(extra_tr)


def _build_three_day_template() -> None:
    doc = Document(SAMPLE_THREE_DAY)

    # 段落替换（保留每段第一个 run 的字体/字号/加粗等）
    # P0: '天气预报'                                  -> 保持不变
    # P1: '首都关键区域气象服务保障中心  yyyy年mm月..'  -> 中间日期换占位
    # P2: '东城区天气预报'                             -> '{{district_title}}天气预报'
    # P3: '一、天气综述'                              -> 不变
    # P4: '未来三天...'                              -> '{{summary}}'
    # P5: '二、具体天气预报'                          -> 不变
    paragraphs = doc.paragraphs
    _set_paragraph_text(
        paragraphs[1],
        "首都关键区域气象服务保障中心                  {{report_datetime}}",
    )
    _set_paragraph_text(paragraphs[2], "{{district_title}}天气预报")
    _set_paragraph_text(paragraphs[4], "{{summary}}")

    _rewrite_table_with_loop(doc.tables[0])

    os.makedirs(os.path.dirname(OUT_THREE_DAY), exist_ok=True)
    doc.save(OUT_THREE_DAY)
    print(f"[OK] 三天模板已生成: {OUT_THREE_DAY}")


def _build_ten_day_template() -> None:
    doc = Document(SAMPLE_TEN_DAY)

    paragraphs = doc.paragraphs
    _set_paragraph_text(
        paragraphs[1],
        "首都关键区域气象服务保障中心                  {{report_datetime}}",
    )
    _set_paragraph_text(paragraphs[2], "{{district_title}}天气预报")
    _set_paragraph_text(paragraphs[4], "{{summary}}")

    _rewrite_table_with_loop(doc.tables[0])

    os.makedirs(os.path.dirname(OUT_TEN_DAY), exist_ok=True)
    doc.save(OUT_TEN_DAY)
    print(f"[OK] 十天模板已生成: {OUT_TEN_DAY}")


if __name__ == "__main__":
    _build_three_day_template()
    _build_ten_day_template()
