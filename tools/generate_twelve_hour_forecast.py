"""
title: 未来12小时天气预报生成工具
description: 根据「北京市气象台未来12小时预报产品」自动生成某区未来12小时天气预报 Word 文档
author: lyq
version: 1.0.0
"""

WF12H_OFFICIAL_NAME = "北京市气象台未来12小时预报产品"

# 北京市（全市）版本：district 传入以下别名时，直接取 12h XML 里的「观象台」站，
# 标题/文件名/概述里的地名统一显示为「北京市」，不再拼「XX区」。
CITY_LEVEL_DISTRICT_ALIASES = {"北京市", "全市"}
CITY_LEVEL_STATION_NAME = "观象台"
CITY_LEVEL_DISPLAY_NAME = "北京市"

import os
import re
import io
import json
import glob
import asyncio
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET
from ftplib import FTP, error_perm

from pydantic import BaseModel, Field


XML_NAME_RE = re.compile(r"MSP2_BJ-MO_WF_ME_LNO_BJ_(\d{12})_00000-01201\.xml$")


class Tools:
    class Valves(BaseModel):
        source_mode: str = Field(
            default=os.environ.get("TWELVE_HOUR_SOURCE_MODE", "ftp"),
            description="12h XML 数据源：local=读本地目录(xml_dir)；ftp=登录 FTP 拉取",
        )
        xml_dir: str = Field(
            default=os.environ.get("TWELVE_HOUR_LOCAL_DIR", "/app/data/BJ-12h"),
            description="source_mode=local 时使用：12h XML 文件所在目录的绝对路径（本地模式不分月子目录）",
        )
        ftp_host: str = Field(
            default=os.environ.get("BJ240_FTP_HOST", "10.225.3.71"),
            description="source_mode=ftp 时使用：FTP 服务器地址（与240/公报复用同一台机器）",
        )
        ftp_port: int = Field(
            default=int(os.environ.get("BJ240_FTP_PORT", "21")),
            description="FTP 端口（默认 21）",
        )
        ftp_user: str = Field(
            default=os.environ.get("BJ240_FTP_USER", "FtpFiles"),
            description="FTP 用户名",
        )
        ftp_password: str = Field(
            default=os.environ.get("BJ240_FTP_PASSWORD", ""),
            description="FTP 密码（推荐通过环境变量 BJ240_FTP_PASSWORD 注入，不要写死在这里）",
        )
        ftp_base_dir: str = Field(
            default=os.environ.get("TWELVE_HOUR_FTP_BASE_DIR", "/FTPDATA/Product/STATION/逐1"),
            description="FTP 上按月分子目录的根路径，实际会拼接成 {ftp_base_dir}/{YYYYMM} 再去列文件",
        )
        ftp_timeout: int = Field(
            default=int(os.environ.get("BJ240_FTP_TIMEOUT", "30")),
            description="FTP 连接 / 操作超时（秒）",
        )
        template_path: str = Field(
            default=os.environ.get(
                "WEATHER_TEMPLATE_TWELVE_HOUR",
                "/app/weather_templates/12_hours/template.docx",
            ),
            description="未来12小时天气预报 docx 模板的绝对路径",
        )
        summary_model: str = Field(
            default="",
            description="用于生成天气概况文字的模型 ID（留空则自动使用当前对话模型 / 第一个可用模型）",
        )
        summary_timeout: int = Field(
            default=int(os.environ.get("TWELVE_HOUR_SUMMARY_TIMEOUT", "120")),
            description="调用模型生成天气概况的最大等待秒数，超时即用本地模板兜底，不阻塞文档生成",
        )
        debug: bool = Field(
            default=False,
            description="开启后，调用模型失败时会把错误信息写入概况文本，方便排查",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_twelve_hour_forecast(
        self,
        district: str,
        __user__: dict = None,
        __event_emitter__: Any = None,
        __request__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
    ) -> str:
        """
        生成某区未来12小时天气预报 Word 文档，并在聊天中提供下载。

        数据来源固定为「北京市气象台区级12小时精细化预报产品」，在向用户介绍数据来源时**必须**
        使用该全称，严禁简写为「12小时产品/逐小时数据」等。

        【对调用方/LLM 的回复守则】
        工具调用成功后会返回一个 JSON，里面的 `reply_to_user` 字段已经组装好了给用户看的回复
        （包含真实下载链接 markdown）。你应当**原样**把 `reply_to_user` 输出给用户，不要在
        其中添加/删除/编造任何文件名、链接、起报时间、预报时效等元信息。

        :param district: 行政区名称，如"密云"、"延庆"、"朝阳"等北京各区，或"观象台"等中心站；
            如需生成北京市整体版本，传入"北京市"（直接取"观象台"站数据，标题/文件名/概述里
            统一显示为"北京市"，不带"区"字）
        :return: JSON 字符串，包含 status / district / filename / download_url / reply_to_user 等字段
        """
        is_city_level = district.strip() in CITY_LEVEL_DISTRICT_ALIASES
        station_name = CITY_LEVEL_STATION_NAME if is_city_level else district
        display_name = CITY_LEVEL_DISPLAY_NAME if is_city_level else f"{district}区"
        narrative_name = CITY_LEVEL_DISPLAY_NAME if is_city_level else f"{district}地区"

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": f"正在读取{WF12H_OFFICIAL_NAME}...", "done": False},
                }
            )

        xml_path, cleanup_paths = self._find_latest_xml()
        try:
            if not xml_path:
                location = self._location_hint()
                return json.dumps(
                    {"error": f"在 {location} 未找到{WF12H_OFFICIAL_NAME} XML 文件"},
                    ensure_ascii=False,
                )

            base_time = self._parse_base_time(xml_path)
            data_list, available = self._parse_xml(xml_path, station_name)
            if data_list is None:
                hint = f"'{district}'（对应站点'{station_name}'）" if is_city_level else f"'{district}'"
                return json.dumps(
                    {
                        "error": f"{hint}不在当前预报数据覆盖范围内。可用地区：{'、'.join(sorted(available))}"
                    },
                    ensure_ascii=False,
                )

            forecast_data = [d for d in data_list if d["hour"] <= 12][:12]
            if len(forecast_data) < 12:
                return json.dumps(
                    {"error": f"预报数据不足12个时次（当前{len(forecast_data)}条），无法生成未来12小时预报"},
                    ensure_ascii=False,
                )
        finally:
            for p in cleanup_paths:
                _safe_remove(p)

        table_rows = self._build_table(forecast_data, base_time)

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "正在生成天气概况...", "done": False},
                }
            )

        summary = await self._generate_summary(
            narrative_name, forecast_data, base_time, __request__, __user__, __model__
        )

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "正在生成文档...", "done": False},
                }
            )

        from docxtpl import DocxTemplate

        now = datetime.now()
        report_dt = f"{now.year}年{now.month}月{now.day}日{now.hour}时"

        doc = DocxTemplate(self.valves.template_path)
        context = {
            "district": display_name,
            "report_datetime": report_dt,
            "summary": summary,
            "table": table_rows,
        }
        doc.render(context)

        self._merge_date_cells(doc.docx, table_rows)

        date_str = datetime.now().strftime("%Y%m%d%H")
        filename = f"{display_name}未来12小时天气预报_{date_str}.docx"

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        try:
            from fastapi import UploadFile
            from open_webui.models.users import Users
            from open_webui.models.chats import Chats
            from open_webui.routers.files import upload_file_handler

            with open(tmp_path, "rb") as f:
                content = f.read()

            upload = UploadFile(
                file=io.BytesIO(content),
                filename=filename,
                headers={
                    "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
            )
            user_obj = Users.get_user_by_id(__user__["id"])
            file_item = upload_file_handler(
                __request__,
                file=upload,
                metadata={
                    "chat_id": __chat_id__,
                    "message_id": __message_id__,
                },
                process=False,
                user=user_obj,
            )
            url = (
                str(__request__.base_url).rstrip("/")
                + f"/api/v1/files/{file_item.id}/content"
            )

            if __chat_id__ and __message_id__:
                try:
                    Chats.insert_chat_files(
                        chat_id=__chat_id__,
                        message_id=__message_id__,
                        file_ids=[file_item.id],
                        user_id=user_obj.id,
                    )
                except Exception:
                    pass

            download_md = f"[📄 下载 {filename}]({url})"
            assistant_reply = (
                f"{display_name}未来12小时天气预报文档已生成，点击下载：{download_md}"
            )

            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "文档生成完成", "done": True},
                    }
                )
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": f"\n\n{download_md}\n"},
                    }
                )

            return json.dumps(
                {
                    "status": "success",
                    "district": district,
                    "filename": filename,
                    "download_url": url,
                    "data_sources": [WF12H_OFFICIAL_NAME],
                    "reply_to_user": assistant_reply,
                    "message": assistant_reply,
                },
                ensure_ascii=False,
            )
        finally:
            os.unlink(tmp_path)

    # ========================================================================
    # 数据获取：本地目录 / FTP（按月分子目录）
    # ========================================================================
    def _location_hint(self) -> str:
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode == "ftp":
            now = datetime.now()
            cur = f"{self.valves.ftp_base_dir}/{now.strftime('%Y%m')}"
            return f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{cur}（及上月同名目录）"
        return self.valves.xml_dir

    def _find_latest_xml(self) -> tuple[str | None, list[str]]:
        """
        返回 (本地可读的 XML 文件路径, 需要清理的临时路径列表)。
        - local：直接扫 xml_dir（不分月）
        - ftp：FTP 上按月分子目录存放，本月 + 上月两个目录都列一遍再取全局最新
          （避免跨月边界时，最新文件其实还在"上月"目录里的问题）
        """
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode != "ftp":
            pattern = os.path.join(self.valves.xml_dir, "MSP2_BJ-MO_WF_ME_LNO_BJ_*_00000-01201.xml")
            files = glob.glob(pattern)
            if not files:
                return None, []
            latest = self._pick_latest_name(files)
            return latest, []

        now = datetime.now()
        this_month_dir = f"{self.valves.ftp_base_dir}/{now.strftime('%Y%m')}"
        last_month_dt = (now.replace(day=1) - timedelta(days=1))
        last_month_dir = f"{self.valves.ftp_base_dir}/{last_month_dt.strftime('%Y%m')}"

        v = self.valves
        try:
            ftp = FTP(timeout=v.ftp_timeout)
            ftp.connect(v.ftp_host, v.ftp_port, timeout=v.ftp_timeout)
            ftp.login(v.ftp_user, v.ftp_password)
            try:
                candidates: list[tuple[str, str, str]] = []  # (stamp, dir, basename)
                for d in (this_month_dir, last_month_dir):
                    try:
                        ftp.cwd(d)
                    except error_perm:
                        continue
                    try:
                        names = ftp.nlst()
                    except error_perm as e:
                        if str(e).startswith("550"):
                            names = []
                        else:
                            raise
                    for name in names:
                        base = os.path.basename(name)
                        m = XML_NAME_RE.search(base)
                        if m:
                            candidates.append((m.group(1), d, base))
                if not candidates:
                    return None, []
                now_str = now.strftime("%Y%m%d%H%M")
                past = [c for c in candidates if c[0] <= now_str]
                stamp, d, base = (max(past, key=lambda x: x[0]) if past
                                   else max(candidates, key=lambda x: x[0]))
                ftp.cwd(d)
                tmp_dir = tempfile.mkdtemp(prefix="bj12h_")
                tmp_path = os.path.join(tmp_dir, base)
                with open(tmp_path, "wb") as fp:
                    ftp.retrbinary(f"RETR {base}", fp.write)
                return tmp_path, [tmp_path, tmp_dir]
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()
        except Exception as e:
            print(f"[generate_twelve_hour_forecast] FTP 拉取失败: {e}")
            return None, []

    def _pick_latest_name(self, names: list[str]) -> str | None:
        candidates = []
        now = datetime.now()
        for name in names:
            base = os.path.basename(name)
            m = XML_NAME_RE.search(base)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y%m%d%H%M")
            except ValueError:
                continue
            candidates.append((ts, name))
        if not candidates:
            return None
        past = [c for c in candidates if c[0] <= now]
        return (max(past, key=lambda x: x[0]) if past else max(candidates, key=lambda x: x[0]))[1]

    def _parse_base_time(self, xml_path: str) -> datetime:
        m = re.search(r"_(\d{12})_", os.path.basename(xml_path))
        return datetime.strptime(m.group(1), "%Y%m%d%H%M")

    def _parse_xml(self, xml_path: str, district: str) -> tuple[list | None, set]:
        tree = ET.parse(xml_path)
        available = {s.get("stationname") for s in tree.findall(".//station")}
        if district not in available:
            return None, available
        for station in tree.findall(".//station"):
            if station.get("stationname") == district:
                data_list = []
                for d in station.findall("data"):
                    data_list.append(
                        {
                            "hour": int(d.find("hour").text),
                            "wp": d.find("wp").text or "",
                            "t": d.find("t").text or "",
                            "wdir": d.find("wdir").text or "",
                            "wspeed": d.find("wspeed").text or "",
                            "humi": (d.find("humi").text or "") if d.find("humi") is not None else "",
                        }
                    )
                return sorted(data_list, key=lambda x: x["hour"]), available
        return None, available

    # ========================================================================
    # 表格构造：逐小时，日期/时刻直接由 起报时间+hour偏移 算出
    # ========================================================================
    def _fmt_wdir(self, wdir: str) -> str:
        if not wdir:
            return ""
        return wdir if "风" in wdir else f"{wdir}风"

    def _fmt_wdir_wspeed(self, wdir: str, wspeed: str) -> str:
        wdir_part = self._fmt_wdir((wdir or "").strip())
        wspeed_part = (wspeed or "").strip()
        if wdir_part and wspeed_part:
            return f"{wdir_part}{wspeed_part}"
        return wdir_part or wspeed_part

    def _actual_time(self, base_time: datetime, hour: int) -> datetime:
        return base_time + timedelta(hours=hour)

    def _build_table(self, forecast_data: list[dict], base_time: datetime) -> list[dict]:
        """
        模板字段（与 weather_templates/12_hours/template.docx 对应）：
          date / period / weather / wind / humi / t
        逐小时数据没有白天/夜间的概念，date="X日"、period="HH时" 直接由
        起报时间 + hour 偏移量算出的真实时刻决定。
        """
        rows: list[dict] = []
        for item in forecast_data:
            at = self._actual_time(base_time, item["hour"])
            rows.append(
                {
                    "date": f"{at.day}日",
                    "period": f"{at.hour:02d}时",
                    "weather": item["wp"],
                    "wind": self._fmt_wdir_wspeed(item["wdir"], item["wspeed"]),
                    "humi": item["humi"],
                    "t": item["t"],
                }
            )
        return rows

    def _merge_date_cells(self, doc, table_rows: list[dict]) -> None:
        """渲染完成后把数据表第 1 列「连续相同日期」的单元格做 vMerge 合并（同其它工具的实现）。"""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        if not doc.tables or not table_rows:
            return
        tbl = doc.tables[0]
        trs = tbl._tbl.findall(qn("w:tr"))
        header_count = len(trs) - len(table_rows)
        if header_count < 0:
            return

        def first_tc(tr):
            return tr.findall(qn("w:tc"))[0]

        def clear_vmerge(tc) -> None:
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is None:
                return
            for old in tcPr.findall(qn("w:vMerge")):
                tcPr.remove(old)

        def set_vmerge(tc, val: str) -> None:
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is None:
                tcPr = OxmlElement("w:tcPr")
                tc.insert(0, tcPr)
            for old in tcPr.findall(qn("w:vMerge")):
                tcPr.remove(old)
            vMerge = OxmlElement("w:vMerge")
            if val == "restart":
                vMerge.set(qn("w:val"), "restart")
            tcPr.append(vMerge)

        for k in range(len(table_rows)):
            clear_vmerge(first_tc(trs[header_count + k]))

        i = 0
        n = len(table_rows)
        while i < n:
            j = i
            while j + 1 < n and table_rows[j + 1]["date"] == table_rows[i]["date"]:
                j += 1
            if j > i:
                set_vmerge(first_tc(trs[header_count + i]), "restart")
                for k in range(i + 1, j + 1):
                    set_vmerge(first_tc(trs[header_count + k]), "continue")
            i = j + 1

    # ========================================================================
    # 统计与概述：按日期分组（本窗口最多跨 2 个日期），概述只讲天气+风，不提气温/湿度
    # ========================================================================
    _PRECIP_KINDS = (
        ("暴雨", "暴雨"), ("大雨", "大雨"), ("中雨", "中雨"),
        ("雷阵雨", "雷阵雨"), ("雷雨", "雷阵雨"), ("阵雨", "阵雨"), ("小雨", "小雨"),
        ("雨夹雪", "雨夹雪"), ("大雪", "大雪"), ("中雪", "中雪"), ("小雪", "小雪"),
        ("阵雪", "阵雪"), ("雪", "雪"), ("雨", "雨"),
    )

    def _main_sky_word(self, wp: str) -> str:
        text = (wp or "").strip()
        if not text:
            return "多云"
        head = re.split(r"[，,；;。\s]", text, maxsplit=1)[0]
        if "转" in head:
            main = re.split(r"转为|转", head)[-1].strip()
        else:
            main = re.split(r"间|到", head)[0].strip()
        if "多云" in main:
            return "多云"
        if "阴" in main:
            return "阴"
        if "晴" in main:
            return "晴"
        for kw, kind in self._PRECIP_KINDS:
            if kw in main:
                return kind
        if "多云" in text:
            return "多云"
        if "阴" in text:
            return "阴"
        if "晴" in text:
            return "晴"
        for kw, kind in self._PRECIP_KINDS:
            if kw in text:
                return kind
        return "多云"

    def _describe_wind(self, items: list[tuple[str, str]]) -> str:
        """items = [(wdir, wspeed), ...]，按首尾风向 + 风力区间拼一句，如"南转北风3-4级"。"""
        dirs = [self._fmt_wdir((w or "").strip()).rstrip("风") for w, _ in items if (w or "").strip()]
        dir_str = ""
        if dirs:
            first_d, last_d = dirs[0], dirs[-1]
            dir_str = first_d if first_d == last_d else f"{first_d}转{last_d}"
        nums = []
        for _, s in items:
            m = re.search(r"\d+", s or "")
            if m:
                nums.append(int(m.group()))
        if not nums:
            speed_str = ""
        elif min(nums) == max(nums):
            speed_str = f"{min(nums)}级"
        else:
            speed_str = f"{min(nums)}-{max(nums)}级"
        if dir_str and speed_str:
            return f"{dir_str}风{speed_str}"
        return f"{dir_str}风" if dir_str else speed_str

    def _compute_stats(self, forecast_data: list[dict], base_time: datetime) -> dict:
        from collections import Counter, OrderedDict

        weather_counter: Counter = Counter()
        wdir_set: set[str] = set()
        wspeed_max_num = 0
        by_date: "OrderedDict[str, list[dict]]" = OrderedDict()

        for item in forecast_data:
            wp = (item.get("wp") or "").strip()
            if wp:
                weather_counter[wp] += 1
            wdir = self._fmt_wdir((item.get("wdir") or "").strip())
            if wdir:
                wdir_set.add(wdir)
            m = re.search(r"\d+", item.get("wspeed") or "")
            if m:
                wspeed_max_num = max(wspeed_max_num, int(m.group()))

            at = self._actual_time(base_time, item["hour"])
            date_label = f"{at.day}日"
            by_date.setdefault(date_label, []).append(item)

        date_facts = []
        for date_label, items in by_date.items():
            sky_words = Counter(self._main_sky_word(it["wp"]) for it in items if (it.get("wp") or "").strip())
            if sky_words:
                priority = {"多云": 3, "晴": 2, "阴": 1}
                sky_mood = max(sky_words.items(), key=lambda kv: (kv[1], priority.get(kv[0], 0)))[0]
            else:
                sky_mood = "多云"
            wind_desc = self._describe_wind([(it["wdir"], it["wspeed"]) for it in items])
            date_facts.append({
                "date": date_label,
                "sky_mood": sky_mood,
                "wind_desc": wind_desc,
                "periods": [it["hour"] for it in items],
            })

        return {
            "weather_ranked": weather_counter.most_common(),
            "wdir_set": wdir_set,
            "wspeed_max_num": wspeed_max_num,
            "date_facts": date_facts,
        }

    async def _generate_summary(
        self,
        area_label: str,
        forecast_data: list[dict],
        base_time: datetime,
        request,
        user: dict,
        current_model: dict = None,
    ) -> str:
        stats = self._compute_stats(forecast_data, base_time)
        date_facts = stats["date_facts"]
        allowed_dates_str = "、".join(f["date"] for f in date_facts)

        fact_lines = []
        for f in date_facts:
            fact_lines.append(f"  - {f['date']}：以{f['sky_mood']}为主，{f['wind_desc']}")
        fact_str = "\n".join(fact_lines)

        prompt = (
            f"你是资深气象预报员，为{area_label}撰写「未来12小时天气预报」的「天气概况」段落。\n"
            f"只输出正文，不要标题前缀，单段或按日期分句均可，语言精炼，40~80 字。\n\n"
            f"【未来12小时天气过程事实（已按日期分段统计得出，必须原样采用，不得改动晴雨词/风向风力数字）】\n"
            f"{fact_str}\n\n"
            f"【允许出现在正文里的日期】{allowed_dates_str}\n\n"
            f"【写作要求】\n"
            f"1. 全文只在开头用一次「预计，」，之后按上面给出的日期顺序依次描述每个日期，"
            f"格式类似「预计，X日以XX为主，YY风ZZ级；Y日以XX为主，YY风ZZ级。」——**「预计」只出现一次**，"
            f"后面的日期之间用分号或句号分隔，不要每个日期都重复写「预计」；\n"
            f"2. 晴雨词、风向、风力数字必须严格等于上面事实表里给出的值，不得编造或替换成其它词；\n"
            f"3. 只写天气现象和风，**不要出现任何气温数字（℃）或相对湿度数字（%）**——这两项已经在表格里体现；\n"
            f"4. 全文使用书面预报语言，不要出现「不过」「但是」「呢」「啦」等口语化转折词或语气词。\n\n"
            f"【绝对禁止】\n"
            f"- 任何防范建议 / 出行提示 / 生活指数 / 体感类话术；\n"
            f"- 编造数据里没有的雨型、风力或风向；\n"
            f"- 编造任何天气系统 / 环流背景（冷空气、副热带高压、雨带、台风等）；\n"
            f"- 任何数据来源描述（数值预报/模式/EC/ECMWF/GFS/卫星/雷达 等）；\n"
            f"- 出现气温数字（℃）或湿度数字（%）；\n"
            f"- 超出「允许出现在正文里的日期」之外的日期。\n"
        )

        log = logging.getLogger(__name__)

        def _fallback(reason: str, exc: BaseException | None = None) -> str:
            fb = self._fallback_summary(area_label, stats)
            if exc is not None:
                log.warning("twelve_hour summary fallback (%s): %s: %s", reason, type(exc).__name__, exc)
            else:
                log.warning("twelve_hour summary fallback (%s)", reason)
            if self.valves.debug and exc is not None:
                return f"{fb}\n[模型调用失败：{type(exc).__name__}: {exc}]"
            if self.valves.debug:
                return f"{fb}\n[模型调用兜底：{reason}]"
            return fb

        try:
            from open_webui.utils.chat import generate_chat_completion
            from open_webui.models.users import Users
            from open_webui.utils.models import get_all_models

            user_obj = Users.get_user_by_id(user["id"])
            if user_obj is None:
                return _fallback(f"找不到用户 id={user.get('id') if user else None}")

            if not getattr(request.app.state, "MODELS", None):
                await get_all_models(request, user=user_obj)
            models = getattr(request.app.state, "MODELS", {}) or {}

            requested = (self.valves.summary_model or "").strip()
            model_id = ""
            if requested and requested in models:
                model_id = requested
            if not model_id and current_model and current_model.get("id") in models:
                model_id = current_model["id"]
            if not model_id:
                if not models:
                    return _fallback("当前没有任何可用模型")
                model_id = next(iter(models.keys()))

            log.info("twelve_hour: 使用模型 %r 生成概况（候选 %d 个）", model_id, len(models))

            user_prompt = f"/no_think\n{prompt}"
            form_data = {
                "model": model_id,
                "messages": [{"role": "user", "content": user_prompt}],
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
                "reasoning": {"enabled": False},
            }

            saved_direct = getattr(request.state, "direct", None)
            timeout_sec = max(10, int(self.valves.summary_timeout or 120))
            try:
                request.state.direct = False
                response = await asyncio.wait_for(
                    generate_chat_completion(
                        request, form_data=form_data, user=user_obj, bypass_filter=True
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                return _fallback(f"调用模型 {model_id} 超时（>{timeout_sec}s），已用本地模板兜底")
            finally:
                if saved_direct is None:
                    try:
                        delattr(request.state, "direct")
                    except AttributeError:
                        pass
                else:
                    request.state.direct = saved_direct

            content = None
            try:
                if hasattr(response, "body_iterator"):
                    async def _consume_stream() -> str | None:
                        c = None
                        async for chunk in response.body_iterator:
                            data = json.loads(chunk.decode("utf-8", "replace"))
                            c = data["choices"][0]["message"]["content"]
                        if response.background is not None:
                            await response.background()
                        return c
                    content = await asyncio.wait_for(_consume_stream(), timeout=timeout_sec)
                elif isinstance(response, dict):
                    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            except asyncio.TimeoutError:
                return _fallback(f"读取模型 {model_id} 响应超时（>{timeout_sec}s），已用本地模板兜底")

            if content:
                content = self._strip_thinking(content)
                cleaned = content.strip()
                if self._validate_summary(cleaned, stats):
                    return cleaned
                log.warning("twelve_hour summary failed fact-check, fallback used. raw=%r", cleaned)
                return self._fallback_summary(area_label, stats)
            return _fallback("模型返回内容为空")
        except Exception as e:
            log.exception("generate_twelve_hour_forecast summary failed: %s", e)
            return _fallback("模型调用异常", e)

    def _fallback_summary(self, area_label: str, stats: dict) -> str:
        """本地兜底：直接把每个日期的事实拼成一句，保证 100% 符合数据。
        「预计」只在开头出现一次，后面的日期用分号隔开，不逐条重复。area_label
        已由调用方拼好后缀（如"海淀地区"或"北京市"），这里不再额外拼"地区"。"""
        facts = stats["date_facts"]
        if not facts:
            return f"预计未来12小时{area_label}天气平稳。"
        segments = [f"{f['date']}以{f['sky_mood']}为主，{f['wind_desc']}" for f in facts]
        return "预计，" + "；".join(segments) + "。"

    _FORBIDDEN_SOURCE_TERMS = (
        "数值预报产品", "数值预报", "数值模式", "模式预报", "模式资料",
        "集合预报", "再分析", "卫星云图", "雷达回波", "雷达图",
        "ECMWF", "ecmwf", "EC细网格", "EC", "GFS", "gfs", "WRF", "wrf", "T639", "T1280",
    )
    _FORBIDDEN_SYNOPTIC_TERMS = (
        "冷空气", "副热带高压", "副高", "雨带", "暖湿气流", "低涡", "切变",
        "台风", "热带", "西风槽", "高空槽", "低压槽", "锋面", "冷锋", "暖锋",
        "高压脊", "季风", "急流", "环流", "气旋", "反气旋",
    )
    _FORBIDDEN_ADVICE_TERMS = (
        "防范", "防御", "注意", "建议", "提示", "提醒", "请", "需注意", "谨防",
        "出行", "户外", "适宜", "不宜", "做好", "防护", "防雷", "防汛", "防暑",
        "添衣", "保暖", "携带", "雨具", "影响", "防止", "警惕", "关注",
        "体感", "舒适度", "舒适", "闷热", "凉爽", "炎热", "寒冷", "湿热",
    )
    _FORBIDDEN_COLLOQUIAL_TERMS = ("不过", "但是", "可是", "然而", "呢", "啦", "哦", "呀", "嘛")

    def _validate_summary(self, text: str, stats: dict) -> bool:
        if not text:
            return False

        # 「预计」只允许出现一次（多个日期不应逐条重复「预计，X日…预计，Y日…」）
        if text.count("预计") > 1:
            return False

        for term in self._FORBIDDEN_SOURCE_TERMS:
            if term in text:
                return False
        for term in self._FORBIDDEN_SYNOPTIC_TERMS:
            if term in text:
                return False
        for term in self._FORBIDDEN_ADVICE_TERMS:
            if term in text:
                return False
        for term in self._FORBIDDEN_COLLOQUIAL_TERMS:
            if term in text:
                return False

        # 概述不允许出现气温 / 湿度数字（这两项只在表格里体现）
        if "℃" in text or "°C" in text or re.search(r"\d+\s*度", text):
            return False
        if re.search(r"\d+\s*%", text):
            return False

        ranked = stats.get("weather_ranked") or []
        appeared_weather = {name for name, _ in ranked}
        suspicious_weather = [
            "雷阵雨", "雷雨", "阵雨", "小雨", "中雨", "大雨", "暴雨",
            "雨夹雪", "雪", "冰雹", "雾", "霾", "沙尘",
        ]
        for w in suspicious_weather:
            if w in text and not any(w in name for name in appeared_weather):
                return False

        wdir_set = stats.get("wdir_set") or set()
        appeared_dir_chars: set[str] = set()
        for w in wdir_set:
            for ch in w:
                if ch in "东南西北":
                    appeared_dir_chars.add(ch)
        suspicious_dirs = ["偏北风", "偏东风", "北风"]
        for d in suspicious_dirs:
            if d in text:
                key_chars = [ch for ch in d if ch in "东南西北"]
                if any(ch not in appeared_dir_chars for ch in key_chars):
                    return False

        max_num = stats.get("wspeed_max_num") or 0
        for m in re.finditer(r"(\d+)\s*(?:～|~|-)?\s*(\d+)?\s*级", text):
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            if max(a, b) > max_num:
                return False

        allowed_dates = {f["date"] for f in stats.get("date_facts") or []}
        for m in re.finditer(r"(\d{1,2})日", text):
            if f"{m.group(1)}日" not in allowed_dates:
                return False

        return True

    _THINK_BLOCK_RE = re.compile(r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.IGNORECASE | re.DOTALL)
    _THINK_OPEN_TAIL_RE = re.compile(r"<\s*think\s*>.*\Z", re.IGNORECASE | re.DOTALL)

    def _strip_thinking(self, text: str) -> str:
        if not text:
            return text
        text = self._THINK_BLOCK_RE.sub("", text)
        text = self._THINK_OPEN_TAIL_RE.sub("", text)
        return text.strip()


def _safe_remove(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass
