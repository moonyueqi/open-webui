"""
title: 汛期天气周报生成器
description: 根据「北京市气象台 240h 精细化预报产品」自动生成某区汛期天气周报 Word 文档
author: weather-tools
version: 1.0.0
license: MIT

【数据源官方称呼（用户可见文案、错误信息、模型回执统一使用）】
  - 240 XML：北京市气象台 240h 精细化预报产品
"""

WF240_OFFICIAL_NAME = "北京市气象台 240h 精细化预报产品"

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


class Tools:
    class Valves(BaseModel):
        source_mode: str = Field(
            default=os.environ.get("BJ240_SOURCE_MODE", "ftp"),
            description="BJ-240 XML 数据源：local=读本地目录(xml_dir)；ftp=登录 FTP 拉取",
        )
        xml_dir: str = Field(
            default=os.environ.get("BJ240_LOCAL_DIR", "/app/data/BJ-240"),
            description="source_mode=local 时使用：BJ-240 XML 文件所在目录的绝对路径",
        )
        ftp_host: str = Field(
            default=os.environ.get("BJ240_FTP_HOST", "10.225.3.71"),
            description="source_mode=ftp 时使用：FTP 服务器地址",
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
        ftp_dir: str = Field(
            default=os.environ.get("BJ240_FTP_DIR", "/cpzz/tqgb-12"),
            description="FTP 上 BJ-240 XML 所在目录",
        )
        ftp_timeout: int = Field(
            default=int(os.environ.get("BJ240_FTP_TIMEOUT", "30")),
            description="FTP 连接 / 操作超时（秒）",
        )
        template_path: str = Field(
            default=os.environ.get(
                "WEATHER_TEMPLATE_FLOOD_WEEKLY",
                "/app/weather_templates/flood_weekly/template.docx",
            ),
            description="汛期天气周报 docx 模板的绝对路径",
        )
        summary_model: str = Field(
            default="",
            description="用于生成天气概况文字的模型 ID（留空则自动使用当前对话模型 / 第一个可用模型）",
        )
        summary_timeout: int = Field(
            default=int(os.environ.get("FLOOD_WEEKLY_SUMMARY_TIMEOUT", "120")),
            description="调用模型生成天气概况的最大等待秒数，超时即用本地模板兜底，不阻塞文档生成",
        )
        debug: bool = Field(
            default=False,
            description="开启后，调用模型失败时会把错误信息写入概况文本，方便排查",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_flood_weekly_report(
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
        生成某区汛期天气周报 Word 文档，并在聊天中提供下载。

        数据来源固定为「北京市气象台 240h 精细化预报产品」，在向用户介绍数据来源时**必须**使用
        该全称，严禁简写为「240/BJ-240/模式数据/数值模式」等。

        【对调用方/LLM 的回复守则】
        工具调用成功后会返回一个 JSON，里面的 `reply_to_user` 字段已经组装好了给用户看的回复
        （包含真实下载链接 markdown）。你应当**原样**把 `reply_to_user` 输出给用户，不要在
        其中添加/删除/编造任何文件名、链接、起报时间、预报时效等元信息。

        :param district: 行政区名称，如"密云"、"延庆"、"海淀"、"朝阳"等北京各区
        :return: JSON 字符串，包含 status / district / filename / download_url / reply_to_user 等字段
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "正在读取预报数据...", "done": False}}
            )

        # 1. 找最新 XML
        xml_path = self._find_latest_xml()
        if not xml_path:
            mode = (self.valves.source_mode or "local").strip().lower()
            if mode == "ftp":
                location = f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{self.valves.ftp_dir}"
            else:
                location = self.valves.xml_dir
            return json.dumps(
                {"error": f"在 {location} 未找到{WF240_OFFICIAL_NAME} XML 文件"},
                ensure_ascii=False,
            )

        # 2. 解析 XML + 校验地区
        base_time = self._parse_base_time(xml_path)
        data_list, available = self._parse_xml(xml_path, district)
        # FTP 模式下 xml_path 是临时目录下的文件，解析完即可清理
        if (self.valves.source_mode or "local").strip().lower() == "ftp":
            try:
                os.unlink(xml_path)
            except OSError:
                pass
            try:
                os.rmdir(os.path.dirname(xml_path))
            except OSError:
                pass
        if data_list is None:
            return json.dumps(
                {
                    "error": f"'{district}'不在当前预报数据覆盖范围内。可用地区：{'、'.join(sorted(available))}"
                },
                ensure_ascii=False,
            )

        # 3. 取前14条数据（7天 x 白天/夜间，hour 12~168）
        forecast_data = [d for d in data_list if d["hour"] <= 168][:14]
        if len(forecast_data) < 14:
            return json.dumps(
                {"error": f"预报数据不足14个时次（当前{len(forecast_data)}条），无法生成汛期周报"},
                ensure_ascii=False,
            )

        # 4. 构建表格数据
        table_rows = self._build_table(forecast_data, base_time)

        # 5. 调 LLM 生成概括文字
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "正在生成天气概况...", "done": False}}
            )

        summary = await self._generate_summary(
            district, forecast_data, base_time, __request__, __user__, __model__
        )

        # 6. docxtpl 渲染
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "正在生成文档...", "done": False}}
            )

        from docxtpl import DocxTemplate

        now = datetime.now()
        report_dt = f"{now.year}年{now.month}月{now.day}日{now.hour}时"

        doc = DocxTemplate(self.valves.template_path)
        context = {
            "district": district,
            "report_datetime": report_dt,
            "summary": summary,
            "table": table_rows,
        }
        doc.render(context)

        self._merge_date_cells(doc.docx, table_rows)

        date_str = datetime.now().strftime("%Y%m%d%H")
        filename = f"{district}区汛期天气周报_{date_str}.docx"

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        try:
            # 7. 上传文件
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
            # 直接指向后端的绝对 URL（避开前端 dev server 把 /api/v1/files/... 当成页面路由）。
            # 生产环境前后端同源，base_url 与前端相同；开发环境 base_url 是后端真实地址。
            url = (
                str(__request__.base_url).rstrip("/")
                + f"/api/v1/files/{file_item.id}/content"
            )

            # 把文件关联到当前聊天消息（让消息携带可下载附件）
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
            # 给 LLM 看的"完成回执"：必须包含真实下载链接，且明确要求按原文输出，
            # 避免 LLM 自己编造文件名/链接/起报时间等元数据
            assistant_reply = (
                f"{district}区汛期天气周报文档已生成，点击下载：{download_md}"
            )

            # 8. event_emitter 把下载链接追加到消息（不影响工具 return）
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

            # 工具返回值会进 LLM 上下文，模型通常会"复述"里面的文字。这里：
            # 1) 不再放任何元指令（"数据来源固定…严禁简写…"），避免被当成正文播报；
            # 2) 但**必须**把真实下载链接和文件名放在 message 里，否则模型拿不到链接，
            #    就会像之前看到的那样自由发挥编造一份假链接 / 假起报时间。
            # 3) reply_to_user 这个字段是显式信号，告诉模型"原样输出这一句即可"。
            return json.dumps(
                {
                    "status": "success",
                    "district": district,
                    "filename": filename,
                    "download_url": url,
                    "data_sources": [WF240_OFFICIAL_NAME],
                    "reply_to_user": assistant_reply,
                    "message": assistant_reply,
                },
                ensure_ascii=False,
            )
        finally:
            os.unlink(tmp_path)

    XML_NAME_RE = re.compile(r"MSP2_BJ-MO_WF_ME_LNO_BJ_\d{12}_00000-24012\.xml$")

    def _pick_latest_name(self, names: list[str]) -> str | None:
        candidates = []
        now = datetime.now()
        for name in names:
            base = os.path.basename(name)
            if not self.XML_NAME_RE.search(base):
                continue
            m = re.search(r"_(\d{12})_", base)
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

    def _find_latest_xml(self) -> str | None:
        """
        返回一个**本地可读**的 XML 文件路径。
        - source_mode=local：直接返回宿主目录下的最新文件路径
        - source_mode=ftp：登录 FTP 取最新一份 XML，下载到临时文件，返回临时路径
        """
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._fetch_latest_xml_from_ftp()
        pattern = os.path.join(
            self.valves.xml_dir, "MSP2_BJ-MO_WF_ME_LNO_BJ_*_00000-24012.xml"
        )
        files = glob.glob(pattern)
        if not files:
            return None
        return self._pick_latest_name(files)

    def _fetch_latest_xml_from_ftp(self) -> str | None:
        v = self.valves
        try:
            ftp = FTP(timeout=v.ftp_timeout)
            ftp.connect(v.ftp_host, v.ftp_port, timeout=v.ftp_timeout)
            ftp.login(v.ftp_user, v.ftp_password)
            try:
                ftp.cwd(v.ftp_dir)
                try:
                    names = ftp.nlst()
                except error_perm as e:
                    if str(e).startswith("550"):
                        names = []
                    else:
                        raise
                target = self._pick_latest_name(names)
                if not target:
                    return None
                # 临时文件名里保留原始 basename（含 12 位时间戳），
                # 这样下游 _parse_base_time / _pick_latest_name 等依赖文件名的逻辑都能复用
                original_basename = os.path.basename(target)
                tmp_dir = tempfile.mkdtemp(prefix="bj240_")
                tmp_path = os.path.join(tmp_dir, original_basename)
                with open(tmp_path, "wb") as fp:
                    ftp.retrbinary(f"RETR {original_basename}", fp.write)
                return tmp_path
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()
        except Exception as e:
            print(f"[generate_flood_weekly_report] FTP 拉取失败: {e}")
            return None

    def _parse_base_time(self, xml_path: str) -> datetime:
        m = re.search(r"_(\d{12})_", os.path.basename(xml_path))
        return datetime.strptime(m.group(1), "%Y%m%d%H%M")

    def _parse_xml(
        self, xml_path: str, district: str
    ) -> tuple[list | None, set]:
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
                        }
                    )
                return sorted(data_list, key=lambda x: x["hour"]), available
        return None, available

    def _get_period_label(self, base_hour: int, hour: int) -> str:
        """
        根据起报时刻和 hour 偏移，返回时段标签。
        """
        if hour == 12:
            if base_hour in (6, 9):
                return "白天"
            elif base_hour in (11, 14):
                return "下午"
            elif base_hour in (17, 20):
                return "夜间"
            elif base_hour == 23:
                return "后半夜"
            else:
                return "白天"

        if base_hour in (6, 9, 11, 14):
            return "白天" if hour % 24 == 12 else "夜间"
        else:
            return "夜间" if hour % 24 == 12 else "白天"

    def _is_max_temp(self, base_hour: int, hour: int) -> bool:
        label = self._get_period_label(base_hour, hour)
        return label in ("白天", "下午")

    def _get_date_label(self, base_time: datetime, base_hour: int, hour: int) -> str:
        actual_time = base_time + timedelta(hours=hour)
        label = self._get_period_label(base_hour, hour)
        if label in ("夜间", "后半夜"):
            ref_time = actual_time - timedelta(hours=12)
        else:
            ref_time = actual_time
        return f"{ref_time.day}日"

    def _fmt_wdir(self, wdir: str) -> str:
        """风向格式化：若原值未含"风"字，则末尾追加。
        例：'东南' → '东南风'，'南转北风' → '南转北风'（不变）。"""
        if not wdir:
            return ""
        return wdir if "风" in wdir else f"{wdir}风"

    def _build_table(
        self, forecast_data: list[dict], base_time: datetime
    ) -> list[dict]:
        """
        按预报数据原始顺序，每个时次产出 1 行（扁平结构），用于模板按行循环：
          [
            {"date": "11日", "period": "白天", "weather": "晴", "wind": "南风3级", "temp": "31"},
            {"date": "11日", "period": "夜间", "weather": "多云", "wind": "南风1级", "temp": "15"},
            ...
          ]
        日期列的 vMerge 合并由 _merge_date_cells 在 docxtpl 渲染完之后做。
        """
        base_hour = base_time.hour
        rows: list[dict] = []
        for item in forecast_data:
            hour = item["hour"]
            period = self._get_period_label(base_hour, hour)
            date_key = self._get_date_label(base_time, base_hour, hour)
            wind_str = f"{self._fmt_wdir(item['wdir'])}{item['wspeed']}"
            rows.append(
                {
                    "date": date_key,
                    "period": period,
                    "weather": item["wp"],
                    "wind": wind_str,
                    "temp": item["t"],
                }
            )
        return rows

    def _merge_date_cells(self, doc, table_rows: list[dict]) -> None:
        """
        docxtpl 渲染完成后，把数据表第 1 列里"连续相同日期"的单元格做 vMerge 合并。
        约定：数据表是文档里第 1 个 table，渲染后表头占 N 行，其后是与 table_rows 一一对应的数据行。
        直接操作底层 w:tc 元素，避免 python-docx 的 cells 缓存把不同 tc 折叠返回。
        """
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

    def _compute_stats(
        self, forecast_data: list[dict], base_time: datetime
    ) -> dict:
        """统计：天气次数（高到低排序）、白天/夜间温度区间、温差、风向风力序列、按日聚合的天气事实表。"""
        from collections import Counter, OrderedDict

        base_hour = base_time.hour
        weather_counter: Counter = Counter()
        day_temps = []
        night_temps = []
        wind_seq: list[dict] = []
        wdir_set: set[str] = set()
        wspeed_max_num = 0
        wspeed_max_str = ""
        # 按日聚合：{"10日": OrderedDict([("后半夜","晴间多云")]), "11日": OrderedDict([("白天","晴间多云"),("夜间","多云")]), ...}
        day_weather_map: "OrderedDict[str, OrderedDict[str, str]]" = OrderedDict()

        for item in forecast_data:
            wp = (item.get("wp") or "").strip()
            if wp:
                weather_counter[wp] += 1
            t = item.get("t", "")
            if t.lstrip("-").isdigit():
                if self._is_max_temp(base_hour, item["hour"]):
                    day_temps.append(int(t))
                else:
                    night_temps.append(int(t))

            wdir = self._fmt_wdir((item.get("wdir") or "").strip())
            wspeed = (item.get("wspeed") or "").strip()
            date_label = self._get_date_label(base_time, base_hour, item["hour"])
            period = self._get_period_label(base_hour, item["hour"])
            wind_seq.append(
                {
                    "date": date_label,
                    "period": period,
                    "wdir": wdir,
                    "wspeed": wspeed,
                }
            )
            if wdir:
                wdir_set.add(wdir)
            m = re.search(r"\d+", wspeed)
            if m:
                num = int(m.group(0))
                if num > wspeed_max_num:
                    wspeed_max_num = num
                    wspeed_max_str = wspeed

            if date_label not in day_weather_map:
                day_weather_map[date_label] = OrderedDict()
            if wp:
                day_weather_map[date_label][period] = wp

        weather_ranked = weather_counter.most_common()
        weather_stat_str = "、".join(
            [f"{name}{cnt}次" for name, cnt in weather_ranked]
        ) if weather_ranked else "无"

        t_day_min = min(day_temps) if day_temps else None
        t_day_max = max(day_temps) if day_temps else None
        t_night_min = min(night_temps) if night_temps else None
        t_night_max = max(night_temps) if night_temps else None

        narrative = self._summarize_process(
            forecast_data, base_time, day_weather_map, day_temps
        )

        return {
            "weather_counter": weather_counter,
            "weather_ranked": weather_ranked,
            "weather_stat_str": weather_stat_str,
            "day_temps": day_temps,
            "night_temps": night_temps,
            "t_day_min": t_day_min,
            "t_day_max": t_day_max,
            "t_night_min": t_night_min,
            "t_night_max": t_night_max,
            "wind_seq": wind_seq,
            "wdir_set": wdir_set,
            "wspeed_max_num": wspeed_max_num,
            "wspeed_max_str": wspeed_max_str,
            "day_weather_map": day_weather_map,
            "narrative": narrative,
        }

    # 天气类型归类：把 wp 文本归到"晴好 / 阴 / 降水"三类，并识别降水形态。
    # 注意 wp 可能是「晴转多云」「多云有阵雨」「晴间多云，午后有雷阵雨」等组合，
    # 这里按"是否含降水关键字"为第一优先级判定。
    _PRECIP_KINDS = (
        # (关键字, 归一化形态名)；顺序很重要：先匹配更具体/更强的
        ("暴雨", "暴雨"),
        ("大雨", "大雨"),
        ("中雨", "中雨"),
        ("雷阵雨", "雷阵雨"),
        ("雷雨", "雷阵雨"),
        ("阵雨", "阵雨"),
        ("小雨", "小雨"),
        ("雨夹雪", "雨夹雪"),
        ("大雪", "大雪"),
        ("中雪", "中雪"),
        ("小雪", "小雪"),
        ("阵雪", "阵雪"),
        ("雪", "雪"),
        ("雨", "雨"),
    )

    def _classify_weather(self, wp: str) -> tuple[str, str | None]:
        """返回 (大类, 降水形态)。
        大类 ∈ {"晴好","阴","降水"}；降水形态在大类为"降水"时给出，否则 None。
        只用于"该时段是否算有降水"及降水形态统计：只要文本含降水关键字即判降水。"""
        text = (wp or "").strip()
        if not text:
            return "晴好", None
        for kw, kind in self._PRECIP_KINDS:
            if kw in text:
                return "降水", kind
        if "阴" in text:
            return "阴", None
        # 晴 / 多云 / 晴间多云 / 少云 等都算晴好
        return "晴好", None

    def _main_sky_word(self, wp: str) -> str:
        """从单元格「天气状况」文本里提取一个用于"以XX为主"统计的主天气短词。
        规则（贴近预报员读表习惯）：
          1. 「X转Y…」「X间Y…」「X到Y…」取分隔符后的主导态 Y；
          2. 形如「晴转多云，傍晚有分散性雷阵雨」这种"主态 + 次要降水修饰"，
             主短词取主态（多云），不取被「傍晚有/局地有/午后有」修饰的次要降水；
          3. 若整格主体本身就是降水（如「雷阵雨」「小雨」），主短词取该降水形态；
          4. 否则在「多云 / 晴 / 阴」里按出现情况取（多云优先于晴）。
        返回值是具体短词，如「多云」「晴」「阴」「雷阵雨」「小雨」。"""
        text = (wp or "").strip()
        if not text:
            return "多云"

        head = re.split(r"[，,；;。\s]", text, maxsplit=1)[0]
        # 「X转Y」「X转为Y」表示天气转折，主导态取转折后的 Y；
        # 「X间Y」「X到Y」表示"以 X 为主、间或 Y"，主导态取前段 X。
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

    def _summarize_process(
        self,
        forecast_data: list[dict],
        base_time: datetime,
        day_weather_map: "dict",
        day_temps: list[int],
    ) -> dict:
        """把逐时段预报归纳成"天气过程事实"，供概述生成使用。
        产出供模型/兜底直接落笔的中间量：
          - sky_mood: 主导晴雨基调短语，**严格按时段计数得出**，
                      取值 "晴" / "多云" / "晴间多云" / "阴" 之一
          - dominant_mood: 给模型看的一句话基调（含降水提示）
          - has_precip / precip_ratio / main_precip_kinds / precip_days / precip_density
          - temp_trend / temp_trend_word
        """
        base_hour = base_time.hour
        total = 0
        precip_cnt = 0
        from collections import Counter, OrderedDict

        precip_kind_counter: Counter = Counter()
        precip_day_set: "OrderedDict[str, None]" = OrderedDict()
        # 主天气短词计数：sky_mood 直接取出现最多的主短词
        sky_word_counter: Counter = Counter()

        for item in forecast_data:
            wp = (item.get("wp") or "").strip()
            if not wp:
                continue
            total += 1

            # 主短词计数（用于"以XX为主"）
            sky_word_counter[self._main_sky_word(wp)] += 1

            # 是否含降水（用于降水日期 / 雨型统计），与主短词独立
            cat, kind = self._classify_weather(wp)
            if cat == "降水":
                precip_cnt += 1
                if kind:
                    precip_kind_counter[kind] += 1
                d = self._get_date_label(base_time, base_hour, item["hour"])
                precip_day_set[d] = None

        precip_ratio = (precip_cnt / total) if total else 0.0

        # 降水频度
        if precip_cnt == 0:
            precip_density = "none"
        elif precip_ratio >= 0.4:
            precip_density = "frequent"
        else:
            precip_density = "occasional"

        # 主导降水形态（最多两种）
        main_precip_kinds = [k for k, _ in precip_kind_counter.most_common(2)]

        # 主导晴雨基调：严格取主天气短词里出现次数最多者；
        # 平局时按"多云 > 晴 > 阴 > 其它(降水)"的常见播报优先级打破。
        if sky_word_counter:
            priority = {"多云": 3, "晴": 2, "阴": 1}
            sky_mood = max(
                sky_word_counter.items(),
                key=lambda kv: (kv[1], priority.get(kv[0], 0)),
            )[0]
        else:
            sky_mood = "多云"

        # 给模型看的一句话基调（含降水提示），开头晴雨词与 sky_mood 一致
        if precip_ratio >= 0.5:
            dominant_mood = f"以{sky_mood}为主，阴雨天气较多"
        elif precip_cnt > 0:
            dominant_mood = f"以{sky_mood}为主，其间伴有零星降水"
        else:
            dominant_mood = f"以{sky_mood}为主，无明显降水"

        # 气温趋势：取白天最高温序列，比较前 1/3 与后 1/3 的均值
        temp_trend = "steady"
        temp_trend_word = "变化不大"
        if len(day_temps) >= 3:
            k = max(1, len(day_temps) // 3)
            head = sum(day_temps[:k]) / k
            tail = sum(day_temps[-k:]) / k
            diff = tail - head
            if diff >= 2:
                temp_trend, temp_trend_word = "rising", "有所上升"
            elif diff <= -2:
                temp_trend, temp_trend_word = "falling", "有所下降"

        return {
            "sky_mood": sky_mood,
            "sky_word_counts": dict(sky_word_counter),
            "dominant_mood": dominant_mood,
            "has_precip": precip_cnt > 0,
            "precip_ratio": round(precip_ratio, 2),
            "main_precip_kinds": main_precip_kinds,
            "precip_days": list(precip_day_set.keys()),
            "precip_density": precip_density,
            "temp_trend": temp_trend,
            "temp_trend_word": temp_trend_word,
        }

    async def _generate_summary(
        self,
        district: str,
        forecast_data: list[dict],
        base_time: datetime,
        request,
        user: dict,
        current_model: dict = None,
    ) -> str:
        base_hour = base_time.hour
        stats = self._compute_stats(forecast_data, base_time)

        t_day_range = (
            f"{stats['t_day_min']}～{stats['t_day_max']}"
            if stats["day_temps"] else "无数据"
        )
        t_night_range = (
            f"{stats['t_night_min']}～{stats['t_night_max']}"
            if stats["night_temps"] else "无数据"
        )

        ranked = stats["weather_ranked"]
        top_weather = ranked[0][0] if ranked else "晴间多云"
        other_weathers = [name for name, _ in ranked[1:]]
        other_weather_str = "、".join(other_weathers) if other_weathers else "无"

        date_labels: list[str] = []
        for item in forecast_data:
            d = self._get_date_label(base_time, base_hour, item["hour"])
            if d not in date_labels:
                date_labels.append(d)
        allowed_dates_str = "、".join(date_labels) if date_labels else "（无）"

        temp_sentence = (
            f"白天最高气温{t_day_range}℃，夜间最低气温{t_night_range}℃。"
        )

        # 按日事实表：仅作为模型的事实依据（哪天有什么天气），不要求逐日照搬
        day_weather_map = stats.get("day_weather_map") or {}
        day_fact_lines = []
        for d, period_map in day_weather_map.items():
            seg_parts = [f"{p}{w}" for p, w in period_map.items()]
            day_fact_lines.append(
                f"  - {d}：{'、'.join(seg_parts) if seg_parts else '无数据'}"
            )
        day_fact_str = "\n".join(day_fact_lines) if day_fact_lines else "（无）"

        nv = stats.get("narrative") or {}
        precip_days = nv.get("precip_days") or []
        precip_days_str = "、".join(precip_days) if precip_days else "无"
        main_kinds = nv.get("main_precip_kinds") or []
        main_kinds_str = "、".join(main_kinds) if main_kinds else "无"
        sky_mood = nv.get("sky_mood") or "多云"
        density_map = {
            "frequent": "降水时段较多",
            "occasional": "仅零星/分散降水",
            "none": "全程无降水",
        }
        density_str = density_map.get(nv.get("precip_density"), "—")

        # 预报员风格 prompt：要的是"天气过程综述"，不是逐日机械罗列。
        # 文字部分聚焦晴雨大势、降水过程与气温趋势（趋势用定性词，不报具体数值），
        # 唯一的具体气温数值放在最后一句固定温度句里。
        prompt = (
            f"你是资深气象预报员，为{district}地区撰写汛期天气周报开头的「天气概况」段落。\n"
            f"要写成一段连贯、自然、有预报员口吻的总体天气趋势综述，"
            f"而不是「29日…、30日…」这样逐日罗列流水账。只输出正文，单段不换行，70~120 字。\n\n"
            f"【本周天气过程事实（请据此归纳，不要逐条复述）】\n"
            f"- 主导晴雨基调（已严格按时段统计得出，必须采用，不得改成其它晴雨词）：{sky_mood}\n"
            f"- 一句话基调参考：{nv.get('dominant_mood', '以多云天气为主')}\n"
            f"- 降水概况：{density_str}\n"
            f"- 主要降水形态（按出现多少排序）：{main_kinds_str}\n"
            f"- 有降水的日期：{precip_days_str}\n"
            f"- 气温趋势：{nv.get('temp_trend_word', '变化不大')}\n\n"
            f"【可参考的逐日天气（仅供你判断事实，禁止逐日照抄成流水账）】\n"
            f"{day_fact_str}\n\n"
            f"【允许出现在正文里的日期】{allowed_dates_str}\n\n"
            f"【写作要求】\n"
            f"1. 开头必须写成「预计未来一周{district}地区以{sky_mood}为主」，"
            f"其中晴雨词只能用上面的「主导晴雨基调」即「{sky_mood}」，"
            f"严禁自行改成「晴」「多云」「晴间多云」等其它词，也不要在其后加「天气」二字；"
            f"随后再概括降水过程（用上面的「主要降水形态」，可点出集中在哪几天，但不要把每天都列一遍）；\n"
            f"2. 若降水零星，可用「其间有分散性阵雨」「局部时段有阵雨」等书面表达，"
            f"但只能使用上面「主要降水形态」里出现过的雨型词，不得升级雨量（不许把阵雨写成中雨/大雨/暴雨）；"
            f"全文使用书面预报语言，不要出现「不过」「但是」「呢」「啦」等口语化转折词或语气词；\n"
            f"3. 气温趋势只用定性说法（如「最高气温有所下降」「较前期变化不大」），"
            f"**正文中不得出现任何具体气温数字、℃、最高/最低气温的数值**；\n"
            f"4. 段落最后一句必须一字不差地写：「{temp_sentence}」"
            f"（这是唯一允许出现具体气温数值的地方）；\n"
            f"5. 单日写「X日」，连续多日写「X-Y日」（均用阿拉伯数字），"
            f"严禁「11-日」「i6日」「l3日」等错误写法。\n\n"
            f"【绝对禁止】\n"
            f"- 任何防范建议 / 出行提示 / 生活指数 / 体感类话术（如「注意防范」「请携带雨具」「适宜户外活动」"
            f"「需关注短时强降水影响」「体感舒适度下降」「闷热」「凉爽」等）—— 概述只客观描述天气，绝不给建议、不写体感；\n"
            f"- 编造任何天气系统/环流背景（副热带高压、雨带、冷空气、低涡、切变、台风、西风槽等一律不许出现），"
            f"因为数据中并无这些信息；\n"
            f"- 逐日罗列式流水账（「29日多云、30日阴、31日阵雨…」这种写法）；\n"
            f"- 在最后一句之前出现任何气温数字 / ℃；\n"
            f"- 出现「有降水的日期」之外日期的降水，或事实里没有的雨型；\n"
            f"- 任何统计数字（「X天」「X次」「占比」等）；\n"
            f"- 任何数据来源描述（数值预报/模式/EC/ECMWF/GFS/卫星/雷达/集合预报/再分析 等）；\n"
            f"- 超出「允许出现在正文里的日期」之外的日期。\n"
        )

        log = logging.getLogger(__name__)

        # 任何分支异常 / 超时都走这套兜底，保证文档生成不被阻塞
        def _fallback(reason: str, exc: BaseException | None = None) -> str:
            fb = self._normalize_temp_sentence(
                self._fallback_summary(district, stats), stats
            )
            if exc is not None:
                log.warning(
                    "flood_weekly summary fallback (%s): %s: %s",
                    reason, type(exc).__name__, exc,
                )
            else:
                log.warning("flood_weekly summary fallback (%s)", reason)
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

            # 选模型：优先级 valves.summary_model > 当前对话模型 > models 第一个
            requested = (self.valves.summary_model or "").strip()
            model_id = ""
            if requested:
                if requested in models:
                    model_id = requested
                else:
                    log.warning(
                        "flood_weekly: summary_model=%r 不在 app.state.MODELS 中"
                        "（已知 %d 个），忽略该配置",
                        requested, len(models),
                    )
            if not model_id and current_model and current_model.get("id"):
                cid = current_model["id"]
                if cid in models:
                    model_id = cid
                else:
                    log.info(
                        "flood_weekly: 当前对话模型 %r 不在后端代理可见列表中"
                        "（共 %d 个），将自动改用其它可用模型",
                        cid, len(models),
                    )
            if not model_id:
                if not models:
                    return _fallback("当前没有任何可用模型")
                model_id = next(iter(models.keys()))

            log.info("flood_weekly: 使用模型 %r 生成概况（候选 %d 个）", model_id, len(models))

            # 关闭推理类模型的 thinking / reasoning：
            # 1) /no_think 是 qwen3 系列在 chat template 里识别的开关，对上游推理框架（vLLM/SGLang/Ollama）都生效；
            # 2) chat_template_kwargs.enable_thinking=false 是 qwen3 在 OpenAI 兼容接口上的事实标准，
            #    vLLM/SGLang 都会直接读取；
            # 3) reasoning_effort=none / reasoning={"enabled": false} 是 OpenAI o 系列 / 部分 router 的写法，
            #    多写一份没害处，不识别就被忽略。
            user_prompt = f"/no_think\n{prompt}"
            form_data = {
                "model": model_id,
                "messages": [{"role": "user", "content": user_prompt}],
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
                "reasoning": {"enabled": False},
            }

            # 外层对话若使用 direct 模式（浏览器中转）调模型，会让 generate_chat_completion
            # 内部只认 request.state.model 这一个模型，并且通过 socket.io 等浏览器回包
            # （默认 60s 超时）。这里临时把 direct 关掉，强制走后端代理路径，使用
            # request.app.state.MODELS 里的模型直接由后端发起调用。
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
                return _fallback(
                    f"调用模型 {model_id} 超时（>{timeout_sec}s），已用本地模板兜底"
                )
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
                    content = (
                        response.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
            except asyncio.TimeoutError:
                return _fallback(
                    f"读取模型 {model_id} 响应超时（>{timeout_sec}s），已用本地模板兜底"
                )

            if content:
                # 兜底：万一上游没识别 /no_think，模型仍返回了 <think>...</think> 块，
                # 把这部分整体剥掉再走后续校验/规整
                content = self._strip_thinking(content)
                cleaned = self._sanitize_summary(content.strip())
                if self._validate_summary(cleaned, stats, date_labels):
                    return self._normalize_temp_sentence(cleaned, stats)
                log.warning(
                    "flood_weekly summary failed fact-check, fallback used. raw=%r",
                    cleaned,
                )
                return self._normalize_temp_sentence(
                    self._fallback_summary(district, stats), stats
                )
            return _fallback("模型返回内容为空")
        except Exception as e:
            log.exception("generate_flood_weekly_report summary failed: %s", e)
            return _fallback("模型调用异常", e)

    def _fallback_summary(self, district: str, stats: dict) -> str:
        """本地兜底：不依赖模型，基于过程事实拼出一段预报员风格的大势综述。
        气温数值只在结尾温度句出现，前文不带任何具体气温。"""
        t_day = (
            f"{stats['t_day_min']}～{stats['t_day_max']}"
            if stats["day_temps"] else "N/A"
        )
        t_night = (
            f"{stats['t_night_min']}～{stats['t_night_max']}"
            if stats["night_temps"] else "N/A"
        )
        body = self._compose_narrative_sentence(district, stats, span_word="未来一周")
        return (
            f"{body}"
            f"白天最高气温{t_day}℃，夜间最低气温{t_night}℃。"
        )

    def _compose_narrative_sentence(
        self, district: str, stats: dict, span_word: str
    ) -> str:
        """根据过程事实拼一句/两句"晴雨大势 + 降水过程 + 气温趋势"的综述，
        不含任何具体气温数值。span_word 形如"未来一周""未来三天"。"""
        nv = stats.get("narrative") or {}
        density = nv.get("precip_density", "none")
        kinds = nv.get("main_precip_kinds") or []
        kind_word = kinds[0] if kinds else "阵雨"
        days = nv.get("precip_days") or []
        sky_mood = nv.get("sky_mood") or "多云"

        mood_is_precip = sky_mood not in ("晴", "多云", "阴", "晴间多云")
        day_hint = self._fmt_day_list(days)

        if density == "none":
            mood = f"预计{span_word}{district}地区以{sky_mood}为主，大部分时间无明显降水。"
            precip = ""
        elif mood_is_precip:
            # 主导就是降水
            if day_hint:
                mood = f"预计{span_word}{district}地区以{sky_mood}为主，"
                precip = f"降水主要集中在{day_hint}。"
            else:
                mood = f"预计{span_word}{district}地区以{sky_mood}为主。"
                precip = ""
        else:
            # 主导是晴/多云/阴，降水为次要过程
            mood = f"预计{span_word}{district}地区大部分时间以{sky_mood}为主，"
            precip = f"其间{day_hint}有分散性{kind_word}。" if day_hint else f"其间多分散性{kind_word}。"

        trend = nv.get("temp_trend", "steady")
        if trend == "rising":
            trend_sentence = "预计期间最高气温有所上升。"
        elif trend == "falling":
            trend_sentence = "预计期间最高气温有所下降。"
        else:
            trend_sentence = ""

        return f"{mood}{precip}{trend_sentence}"

    def _fmt_day_list(self, days: list[str]) -> str:
        """把降水日期列表压缩成自然语言。
        - 1~3 天：直接「29日、2日」
        - >3 天：「部分时段」（避免变成流水账）"""
        if not days:
            return ""
        if len(days) <= 3:
            return "、".join(days)
        return "部分时段"

    # 数据来源相关的"幻觉"词：本工具的数据都来自北京市气象台官方发布的 BJ-240 XML，
    # 模型不应在正文中提及任何"数值预报产品/模式/EC/卫星/雷达"等来源描述。
    _FORBIDDEN_SOURCE_TERMS = (
        "数值预报产品", "数值预报", "数值模式", "模式预报", "模式资料",
        "集合预报", "再分析", "卫星云图", "雷达回波", "雷达图",
        "ECMWF", "ecmwf", "EC细网格", "EC", "GFS", "gfs",
        "WRF", "wrf", "T639", "T1280",
    )

    # 数据里没有、模型却可能凭空编造的"天气系统/环流背景"词。预报员综述里
    # 提到这些一定是模型自己脑补的，必须拦截。
    _FORBIDDEN_SYNOPTIC_TERMS = (
        "副热带高压", "副高", "雨带", "冷空气", "暖湿气流", "低涡", "切变",
        "台风", "热带", "西风槽", "高空槽", "低压槽", "锋面", "冷锋", "暖锋",
        "高压脊", "季风", "急流", "环流", "气旋", "反气旋",
    )

    # 概述只描述天气事实，不得出现任何防范建议 / 出行提示 / 生活指数 / 体感类话术。
    _FORBIDDEN_ADVICE_TERMS = (
        "防范", "防御", "注意", "建议", "提示", "提醒", "请", "需注意", "谨防",
        "出行", "户外", "适宜", "不宜", "做好", "防护", "防雷", "防汛", "防暑",
        "添衣", "保暖", "携带", "雨具", "影响", "防止", "警惕", "关注",
        "体感", "舒适度", "舒适", "闷热", "凉爽", "炎热", "寒冷", "湿热",
    )

    # 口语化转折词 / 语气词：概述要用书面预报语言，命中即判失败走兜底。
    _FORBIDDEN_COLLOQUIAL_TERMS = (
        "不过", "但是", "可是", "然而", "呢", "啦", "哦", "呀", "嘛",
    )

    def _validate_summary(self, text: str, stats: dict, allowed_dates: list[str]) -> bool:
        """事实校验（适配预报员综述风格）：
        - 不得提及数据来源（数值模式/卫星雷达等）；
        - 不得凭空编造天气系统/环流背景；
        - 不得升级雨量到数据里没有的更强雨型；
        - 不得超过实际最大风力；
        - 结尾温度句之前不得出现具体气温数字。
        命中任何一条即判失败，外层会改用 fallback。"""
        if not text:
            return False

        # 0) 禁止提及数据来源相关字眼
        for term in self._FORBIDDEN_SOURCE_TERMS:
            if term in text:
                return False

        # 0b) 禁止凭空编造天气系统 / 环流背景
        for term in self._FORBIDDEN_SYNOPTIC_TERMS:
            if term in text:
                return False

        # 0b2) 禁止防范建议 / 出行提示 / 生活指数类话术（概述只描述天气）
        for term in self._FORBIDDEN_ADVICE_TERMS:
            if term in text:
                return False

        # 0b3) 禁止口语化转折词 / 语气词（要求书面预报语言）
        for term in self._FORBIDDEN_COLLOQUIAL_TERMS:
            if term in text:
                return False

        # 0c) 开头主导晴雨基调必须与按时段统计得出的 sky_mood 一致：
        #     正文里第一个「以X(天气)为主」中的 X 必须等于 sky_mood，
        #     防止模型把统计上"以晴为主"的周改写成"以多云为主"之类。
        nv = stats.get("narrative") or {}
        sky_mood = nv.get("sky_mood")
        if sky_mood:
            m = re.search(r"以([\u4e00-\u9fa5]{1,6}?)(?:天气)?为主", text)
            if m and m.group(1) != sky_mood:
                return False

        ranked = stats.get("weather_ranked") or []
        appeared_weather = {name for name, _ in ranked}

        # 1) 禁止出现数据中没有的降水/雨型（防止把阵雨升级成中雨/大雨/暴雨等）
        suspicious_weather = [
            "雷阵雨", "雷雨", "阵雨", "小雨", "中雨", "大雨", "暴雨",
            "雨夹雪", "雪", "冰雹", "雾", "霾", "沙尘",
        ]
        for w in suspicious_weather:
            if w in text and not any(w in name for name in appeared_weather):
                return False

        # 2) 风向：禁止出现数据中未出现的风向
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

        # 3) 风力：禁止超过实际最大风力
        max_num = stats.get("wspeed_max_num") or 0
        for m in re.finditer(r"(\d+)\s*(?:～|~|-)?\s*(\d+)?\s*级", text):
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            if max(a, b) > max_num:
                return False

        # 4) 结尾温度句之前不得出现具体气温数字（℃ / “…度”）。
        #    预报员要求：正文只写晴雨过程与定性气温趋势，气温数值只允许出现在
        #    结尾「白天最高气温…℃，夜间最低气温…℃。」这一句里。
        head = text
        m = self._TEMP_HEAD_RE.search(text)
        if m:
            head = text[: m.start()]
        if "℃" in head or "°C" in head or re.search(r"\d+\s*度", head):
            return False

        return True

    # qwen3 / deepseek-r1 等"思考型"模型在 thinking 启用时，会在最终内容前/中
    # 输出形如「<think> 这里是思维链 </think>」的块。本工具只想要最终回答，
    # 这里把所有 <think>…</think> 整体剥掉；如果整段都是思考没有正式答案，则取空。
    _THINK_BLOCK_RE = re.compile(
        r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.IGNORECASE | re.DOTALL
    )
    # 兜底：万一模型只输出了 <think> 开头但忘了闭合，直接把 <think>... 之后到结尾全部丢掉
    _THINK_OPEN_TAIL_RE = re.compile(
        r"<\s*think\s*>.*\Z", re.IGNORECASE | re.DOTALL
    )

    def _strip_thinking(self, text: str) -> str:
        if not text:
            return text
        text = self._THINK_BLOCK_RE.sub("", text)
        text = self._THINK_OPEN_TAIL_RE.sub("", text)
        return text.strip()

    # 形近字 → 数字 的映射，用于纠正模型把数字写成 i / I / l / L / o / O 的情况
    _SANITIZE_CHAR_MAP = str.maketrans(
        {"i": "1", "I": "1", "l": "1", "L": "1", "o": "0", "O": "0"}
    )

    # 数字与「日」之间多余的连字符 / 破折号（半角-、全角—、连字符–、全角－等）：
    # 形如「11-日」「13—日」「16–日」「i6—日」，
    # 但保留「11-12日」「16—17日」这种合法日期段（中间还有数字时不匹配）
    _SANITIZE_DASH_RE = re.compile(
        r"([0-9iIlLoO]{1,2})[\-\u2010-\u2015\uFF0D]+(?=日)"
    )

    # 匹配「日」字之前 1~2 位、由数字或形近字母（i/I/l/L/o/O）混合组成的片段
    # 经过 _SANITIZE_DASH_RE 处理后，再把片段里的形近字母还原为数字
    _SANITIZE_DATE_RE = re.compile(
        r"(?<![A-Za-z0-9])([0-9iIlLoO]{1,2})(?=日)"
    )

    def _sanitize_summary(self, text: str) -> str:
        """修正模型常见的日期书写错误：
        1) 把「11-日 / 13—日 / 16–日 / i6—日」这类「数字-日」之间多余的连字符去掉
           （日期段「11-12日」中的连字符不会被去掉，因为它中间还有数字）；
        2) 把「i1日 / l3日 / I2日」这类形近字误写还原成阿拉伯数字。
        """
        if not text:
            return text

        text = self._SANITIZE_DASH_RE.sub(lambda m: m.group(1), text)

        def fix_digits(m: "re.Match[str]") -> str:
            s = m.group(1)
            if not any(ch in "iIlLoO" for ch in s):
                return s
            return s.translate(self._SANITIZE_CHAR_MAP)

        text = self._SANITIZE_DATE_RE.sub(fix_digits, text)
        return text

    # 找到正文中温度句的起点，从该处截断，后面统一替换为规范温度句。
    # 兼容模型可能误加的「预计未来一周」前缀，截断时一并去掉。
    _TEMP_HEAD_RE = re.compile(r"(?:预计未来一周)?白天最高气温")

    def _normalize_temp_sentence(self, text: str, stats: dict) -> str:
        """把段落末尾的温度句强制规范为固定格式：
            「白天最高气温X～Y℃，夜间最低气温M～N℃。」
        不带任何「预计未来一周」之类前缀；如果数据缺失则保持原文不动。
        无论模型写得多花哨（"整体气温变化不大""略有升温"等），都会被这句替换掉。
        """
        if not text:
            return text
        if not stats.get("day_temps") or not stats.get("night_temps"):
            return text

        target = (
            f"白天最高气温{stats['t_day_min']}～{stats['t_day_max']}℃，"
            f"夜间最低气温{stats['t_night_min']}～{stats['t_night_max']}℃。"
        )

        m = self._TEMP_HEAD_RE.search(text)
        if m:
            head = text[: m.start()]
        else:
            head = text

        head = head.rstrip().rstrip("，,。；;").rstrip()
        if head and not head.endswith(("。", "！", "？")):
            head += "。"
        return head + target
