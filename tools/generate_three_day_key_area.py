"""
title: 未来三天气象服务专报生成工具（首都关键区）
description: 根据「北京市气象台天气公报」+「北京市气象台未来240h预报产品」自动生成首都关键区
             气象服务保障中心所辖东城区 / 西城区 / 天安门地区的「未来三天气象服务专报」Word 文档
author: lyq
version: 1.0.0
"""

WF240_OFFICIAL_NAME = "北京市气象台未来240h预报产品"
BULLETIN_OFFICIAL_NAME = "北京市气象台天气公报"

import os
import re
import io
import json
import glob
import shutil
import asyncio
import logging
import tempfile
import subprocess
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET
from ftplib import FTP, error_perm

from pydantic import BaseModel, Field


BULLETIN_DOC_NAME_RE = re.compile(r"MSP2_BJ-MO_MDWB_ME_LNO_BJ_(\d{12})_00000-24012\.doc$")
_WEEK_SECTION_HEADING_RE = re.compile(r"未来一周.*天气预报")
_NUMBERED_HEADING_RE = re.compile(r"^[一二三四五六七八九十]、")
_FORECAST_SECTION_HEADING_RE = re.compile(r"未来.*天气预报")
_DAY_SEGMENT_HEAD_RE = re.compile(r"^\s*(?P<day>\d{1,2})日(?P<period>[^:：]+)[:：]")


class _BulletinParseError(Exception):
    """公报「未来一周/未来八到十四天天气预报」章节解析失败。"""


def _safe_remove(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


# 服务对象别名归一化表：每个目标区域允许的用户输入写法集合。
# 用户输入将先做去空格 / 去「区」「地区」等冗余字处理，然后查这张表。
AREA_ALIASES: dict[str, set[str]] = {
    "东城": {"东城", "东城区"},
    "西城": {"西城", "西城区"},
    "天安门": {"天安门", "天安门地区", "天安门广场", "天安门区域"},
}

# 240 XML 里 station 实际可能用到的命名候选——按优先级匹配，第一个能在数据里命中的即采用。
# 这样无论 XML 里写的是「东城」「东城区」「天安门」「天安门地区」哪一种都能兼容。
AREA_STATION_CANDIDATES: dict[str, list[str]] = {
    "东城": ["东城", "东城区"],
    "西城": ["西城", "西城区"],
    "天安门": ["天安门", "天安门地区", "天安门广场"],
}

# 渲染到 docx 标题里的「正式名称」
AREA_DISPLAY_TITLE: dict[str, str] = {
    "东城": "东城区",
    "西城": "西城区",
    "天安门": "天安门地区",
}


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
                "WEATHER_TEMPLATE_THREE_DAY_KEY_AREA",
                "/app/weather_templates/three_day_key_area/template.docx",
            ),
            description="未来三天气象服务专报（首都关键区域）docx 模板的绝对路径",
        )
        use_bulletin_for_weather: bool = Field(
            default=True,
            description=(
                "是否用「北京市气象台天气公报」覆盖表格里的天气/风向、风力（气温始终取自 240 XML）。"
                "关闭后退回纯 240 数据（旧行为），用于公报数据异常时应急回退，无需改代码/重新部署。"
            ),
        )
        bulletin_source_mode: str = Field(
            default=os.environ.get("BULLETIN_SOURCE_MODE", "ftp"),
            description="公报 .doc 数据源：local=读 bulletin_local_dir；ftp=登录 FTP 拉取",
        )
        bulletin_local_dir: str = Field(
            default=os.environ.get("BULLETIN_LOCAL_DIR", "/app/data/bulletin"),
            description="bulletin_source_mode=local 时使用：公报 .doc 所在目录绝对路径",
        )
        bulletin_ftp_dir: str = Field(
            default=os.environ.get("BULLETIN_FTP_DIR", "/cpzz/tqgb"),
            description="bulletin_source_mode=ftp 时使用：公报 .doc 在 FTP 上的目录",
        )
        soffice_bin: str = Field(
            default=os.environ.get("SOFFICE_BIN", "soffice"),
            description="LibreOffice 可执行文件名/绝对路径（用于把公报 .doc 转 .docx）",
        )
        soffice_timeout: int = Field(
            default=int(os.environ.get("SOFFICE_TIMEOUT", "60")),
            description="soffice 转换超时（秒）",
        )
        summary_model: str = Field(
            default="",
            description="用于生成天气概况文字的模型 ID（留空则自动使用当前对话模型 / 第一个可用模型）",
        )
        summary_timeout: int = Field(
            default=int(os.environ.get("THREE_DAY_KEY_AREA_SUMMARY_TIMEOUT", "120")),
            description="调用模型生成天气概况的最大等待秒数，超时即用本地模板兜底，不阻塞文档生成",
        )
        debug: bool = Field(
            default=False,
            description="开启后，调用模型失败时会把错误信息写入概况文本，方便排查",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_three_day_key_area_forecast(
        self,
        area: str,
        __user__: dict = None,
        __event_emitter__: Any = None,
        __request__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
    ) -> str:
        """
        为「首都关键区域气象服务保障中心」生成东城区 / 西城区 / 天安门地区的
        未来三天气象服务专报 Word 文档，并在聊天中提供下载。

        数据来源固定为「北京市气象台天气公报」（提供天气/风向、风力）与
        「北京市气象台未来240h预报产品」（提供气温），在向用户介绍数据来源时**必须**使用
        这两个全称，严禁简写为「公报/240/BJ-240/模式数据/数值模式」等。

        【对调用方/LLM 的回复守则】
        工具调用成功后会返回一个 JSON，里面的 `reply_to_user` 字段已经组装好了给用户看的回复
        （包含真实下载链接 markdown）。你应当**原样**把 `reply_to_user` 输出给用户，不要在
        其中添加/删除/编造任何文件名、链接、起报时间、预报时效等元信息。

        :param area: 服务区域，可选「东城」「西城」「天安门」三者之一；
                     允许的写法包含「东城区」「西城区」「天安门地区」「天安门广场」等。
        :return: JSON 字符串，包含 status / area / filename / download_url / reply_to_user 等字段
        """
        use_bulletin = self.valves.use_bulletin_for_weather
        cleanup_paths: list[str] = []

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": (
                            f"正在读取{BULLETIN_OFFICIAL_NAME}与{WF240_OFFICIAL_NAME}..."
                            if use_bulletin
                            else "正在读取预报数据..."
                        ),
                        "done": False,
                    },
                }
            )

        area_key = self._normalize_area(area)
        if area_key is None:
            return json.dumps(
                {
                    "error": (
                        f"暂不支持的服务区域：{area!r}。本工具仅服务于"
                        "「东城区 / 西城区 / 天安门地区」三者，请明确指定其一。"
                    )
                },
                ensure_ascii=False,
            )

        try:
            if use_bulletin:
                xml_stamps = self._list_xml_stamps()
                bulletin_stamps = self._list_bulletin_stamps()
                if not xml_stamps:
                    return json.dumps(
                        {"error": f"未找到任何{WF240_OFFICIAL_NAME} XML 文件（{self._xml_location_hint()}）"},
                        ensure_ascii=False,
                    )
                if not bulletin_stamps:
                    return json.dumps(
                        {"error": f"未找到任何{BULLETIN_OFFICIAL_NAME} .doc 文件（{self._bulletin_location_hint()}）"},
                        ensure_ascii=False,
                    )
                stamp = self._resolve_common_stamp(xml_stamps, bulletin_stamps, datetime.now())
                if not stamp:
                    return json.dumps(
                        {
                            "error": (
                                f"没有找到{WF240_OFFICIAL_NAME}与{BULLETIN_OFFICIAL_NAME}同一时刻都齐备的版本。"
                                f"\n  {WF240_OFFICIAL_NAME}已到时间戳：{sorted(xml_stamps)[-6:]}"
                                f"\n  {BULLETIN_OFFICIAL_NAME}已到时间戳：{sorted(bulletin_stamps)[-6:]}"
                            )
                        },
                        ensure_ascii=False,
                    )
                try:
                    xml_path = self._fetch_xml_by_stamp(stamp)
                except Exception as e:
                    return json.dumps({"error": f"下载{WF240_OFFICIAL_NAME}失败：{e}"}, ensure_ascii=False)
                if (self.valves.source_mode or "local").strip().lower() == "ftp":
                    cleanup_paths.append(xml_path)
            else:
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
                if (self.valves.source_mode or "local").strip().lower() == "ftp":
                    cleanup_paths.append(xml_path)

            base_time = self._parse_base_time(xml_path)
            # 在 240 数据里查找该区域对应的 station：候选名按顺序尝试
            data_list, available, matched_station = self._parse_xml(xml_path, area_key)
            if data_list is None:
                return json.dumps(
                    {
                        "error": (
                            f"{WF240_OFFICIAL_NAME}里没有「{AREA_DISPLAY_TITLE[area_key]}」对应的"
                            f"站点数据（已尝试名称：{'、'.join(AREA_STATION_CANDIDATES[area_key])}）。"
                            f"实际可用站点：{'、'.join(sorted(available))}"
                        )
                    },
                    ensure_ascii=False,
                )

            # 三天 = hour<=72，6 个时次（白天/夜间各 1 个）
            forecast_data = [d for d in data_list if d["hour"] <= 72][:6]
            if len(forecast_data) < 6:
                return json.dumps(
                    {"error": "预报数据不足 6 个时次，无法生成未来三天专报"},
                    ensure_ascii=False,
                )

            # 用公报覆盖天气/风向风力（气温继续用240数据不变）
            if use_bulletin:
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {"description": f"正在解析{BULLETIN_OFFICIAL_NAME}内容...", "done": False},
                        }
                    )
                try:
                    bulletin_local = self._fetch_bulletin_by_stamp(stamp)
                    cleanup_paths.append(bulletin_local)
                    bulletin_docx = self._doc_to_docx(bulletin_local)
                    cleanup_paths.append(os.path.dirname(bulletin_docx))
                    paragraphs = self._read_paragraphs(bulletin_docx)
                    bulletin_segments = self._extract_day_segments(paragraphs, need_count=6)
                except Exception as e:
                    return json.dumps(
                        {"error": f"解析{BULLETIN_OFFICIAL_NAME}失败：{e}"},
                        ensure_ascii=False,
                    )
                for item, seg in zip(forecast_data, bulletin_segments):
                    item["wp"] = seg["weather"]
                    wdir, wspeed = self._split_wind(seg["wind"])
                    item["wdir"] = wdir
                    item["wspeed"] = wspeed
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
            area_key, forecast_data, base_time, __request__, __user__, __model__
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
        report_dt = f"{now.year}年{now.month:02d}月{now.day:02d}日{now.hour:02d}时"

        doc = DocxTemplate(self.valves.template_path)
        context = {
            "district_title": AREA_DISPLAY_TITLE[area_key],
            "report_datetime": report_dt,
            "summary": summary,
            "table": table_rows,
        }
        doc.render(context)

        self._merge_date_cells(doc.docx, table_rows)

        date_str = datetime.now().strftime("%Y%m%d%H")
        filename = f"未来三天气象服务专报-{AREA_DISPLAY_TITLE[area_key]}_{date_str}.docx"

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
                f"{AREA_DISPLAY_TITLE[area_key]}未来三天气象服务专报已生成，"
                f"点击下载：{download_md}"
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
                    "area": AREA_DISPLAY_TITLE[area_key],
                    "matched_station": matched_station,
                    "filename": filename,
                    "download_url": url,
                    "data_sources": (
                        [BULLETIN_OFFICIAL_NAME, WF240_OFFICIAL_NAME]
                        if use_bulletin
                        else [WF240_OFFICIAL_NAME]
                    ),
                    "reply_to_user": assistant_reply,
                    "message": assistant_reply,
                },
                ensure_ascii=False,
            )
        finally:
            os.unlink(tmp_path)

    # ---------- 区域归一化 ----------

    def _normalize_area(self, area: str) -> str | None:
        """把用户输入归一为 AREA_ALIASES 的 key（东城/西城/天安门）。匹配不到返回 None。"""
        if not area:
            return None
        text = area.strip()
        # 兼容用户写的「天安门广场地区」「东城区政府」等冗余表达：
        # 把别名表里每个写法当成子串去匹配，命中即返回 key。
        for key, aliases in AREA_ALIASES.items():
            for a in aliases:
                if a in text or text in a:
                    return key
        return None

    # ---------- XML 取数 ----------

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
            print(f"[generate_three_day_key_area] FTP 拉取失败: {e}")
            return None

    def _xml_location_hint(self) -> str:
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode == "ftp":
            return f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{self.valves.ftp_dir}"
        return self.valves.xml_dir

    def _bulletin_location_hint(self) -> str:
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            return f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{self.valves.bulletin_ftp_dir}"
        return self.valves.bulletin_local_dir

    # ========================================================================
    # 公报接入：列时间戳 / 按精确时间戳取文件 / 转 docx / 解析逐日逐段天气风力
    # ========================================================================
    def _list_xml_stamps(self) -> set[str]:
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_list_stamps(self.valves.ftp_dir, self.XML_NAME_RE)
        if not os.path.isdir(self.valves.xml_dir):
            return set()
        out: set[str] = set()
        for name in os.listdir(self.valves.xml_dir):
            if self.XML_NAME_RE.search(name):
                m = re.search(r"_(\d{12})_", name)
                if m:
                    out.add(m.group(1))
        return out

    def _fetch_xml_by_stamp(self, stamp: str) -> str:
        fname = f"MSP2_BJ-MO_WF_ME_LNO_BJ_{stamp}_00000-24012.xml"
        mode = (self.valves.source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_download(self.valves.ftp_dir, fname, suffix=".xml", prefix="bj240_")
        full = os.path.join(self.valves.xml_dir, fname)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"本地找不到 240 XML 文件：{full}")
        return full

    def _list_bulletin_stamps(self) -> set[str]:
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_list_stamps(self.valves.bulletin_ftp_dir, BULLETIN_DOC_NAME_RE)
        if not os.path.isdir(self.valves.bulletin_local_dir):
            return set()
        out: set[str] = set()
        for name in os.listdir(self.valves.bulletin_local_dir):
            m = BULLETIN_DOC_NAME_RE.search(name)
            if m:
                out.add(m.group(1))
        return out

    def _fetch_bulletin_by_stamp(self, stamp: str) -> str:
        fname = f"MSP2_BJ-MO_MDWB_ME_LNO_BJ_{stamp}_00000-24012.doc"
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_download(self.valves.bulletin_ftp_dir, fname, suffix=".doc", prefix="bulletin_")
        full = os.path.join(self.valves.bulletin_local_dir, fname)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"本地找不到公报文件：{full}")
        return full

    def _ftp_list_stamps(self, ftp_dir: str, name_re: "re.Pattern") -> set[str]:
        v = self.valves
        out: set[str] = set()
        ftp = FTP(timeout=v.ftp_timeout)
        ftp.connect(v.ftp_host, v.ftp_port, timeout=v.ftp_timeout)
        ftp.login(v.ftp_user, v.ftp_password)
        try:
            ftp.cwd(ftp_dir)
            try:
                names = ftp.nlst()
            except error_perm as e:
                if str(e).startswith("550"):
                    names = []
                else:
                    raise
            for name in names:
                m = name_re.search(os.path.basename(name))
                if m:
                    out.add(m.group(1))
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()
        return out

    def _ftp_download(self, ftp_dir: str, filename: str, *, suffix: str, prefix: str) -> str:
        v = self.valves
        ftp = FTP(timeout=v.ftp_timeout)
        ftp.connect(v.ftp_host, v.ftp_port, timeout=v.ftp_timeout)
        ftp.login(v.ftp_user, v.ftp_password)
        try:
            ftp.cwd(ftp_dir)
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
            os.close(fd)
            try:
                with open(tmp_path, "wb") as fp:
                    ftp.retrbinary(f"RETR {filename}", fp.write)
            except Exception:
                _safe_remove(tmp_path)
                raise
            return tmp_path
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()

    def _resolve_common_stamp(
        self, xml_stamps: set[str], bulletin_stamps: set[str], now: datetime
    ) -> str | None:
        common = xml_stamps & bulletin_stamps
        if not common:
            return None
        now_str = now.strftime("%Y%m%d%H%M")
        past = [s for s in common if s <= now_str]
        return max(past) if past else max(common)

    def _doc_to_docx(self, doc_path: str) -> str:
        out_dir = tempfile.mkdtemp(prefix="bulletin_docx_")
        # 每次调用都用独立的 LibreOffice 用户配置目录（-env:UserInstallation），避免
        # 多次/连续调用共享同一份 profile 抢同一把锁：上一次调用退出后 soffice.bin
        # 有时不会立刻释放锁，导致紧接着的下一次调用卡死在"等锁"上——这个等待不受
        # 下面 subprocess.run 的 timeout 约束（卡的是等锁，不是真的在转换文档），
        # 会直接把整个后端事件循环拖住（工具是同步阻塞调用，不在线程池里跑）。
        profile_dir = tempfile.mkdtemp(prefix="lo_profile_")
        try:
            subprocess.run(
                [
                    self.valves.soffice_bin,
                    "--headless",
                    "--norestore",
                    f"-env:UserInstallation=file://{profile_dir}",
                    "--convert-to", "docx",
                    "--outdir", out_dir,
                    doc_path,
                ],
                check=True,
                timeout=self.valves.soffice_timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(out_dir, ignore_errors=True)
            raise RuntimeError(
                f"soffice 转换失败：{e.stderr.decode('utf-8', 'replace') if e.stderr else e}"
            )
        except FileNotFoundError:
            shutil.rmtree(out_dir, ignore_errors=True)
            raise RuntimeError(
                f"找不到 soffice 可执行文件（{self.valves.soffice_bin}）。"
                "请在 Valves 中配置 soffice_bin，或在系统中安装 LibreOffice。"
            )
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        produced = glob.glob(os.path.join(out_dir, "*.docx"))
        if not produced:
            shutil.rmtree(out_dir, ignore_errors=True)
            raise RuntimeError("soffice 没有产出 .docx 文件")
        return produced[0]

    @staticmethod
    def _read_paragraphs(docx_path: str) -> list[str]:
        from docx import Document

        d = Document(docx_path)
        out: list[str] = []
        for p in d.paragraphs:
            out.append(p.text or "")
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        out.append(p.text or "")
        return out

    def _extract_day_segments(self, paragraphs: list[str], need_count: int) -> list[dict]:
        """从「二、未来一周天气预报」开始连续抽取逐日逐时段 {weather, wind}，
        跳过「三、未来八到十四天天气预报」等仍属预报正文的章节标题继续读，
        只在遇到「四、上下班天气」等非预报章节标题或段数够用时停止。"""
        heading_idx = -1
        for i, raw in enumerate(paragraphs):
            line = (raw or "").strip()
            if _WEEK_SECTION_HEADING_RE.search(line):
                heading_idx = i
                break
        if heading_idx < 0:
            raise _BulletinParseError("未找到「未来一周天气预报」章节标题")

        segments: list[dict] = []
        for raw in paragraphs[heading_idx + 1:]:
            line = (raw or "").strip()
            if not line:
                continue
            if _NUMBERED_HEADING_RE.match(line):
                if _FORECAST_SECTION_HEADING_RE.search(line):
                    continue
                break
            m = _DAY_SEGMENT_HEAD_RE.match(line)
            if not m:
                continue
            rest = line[m.end():].rstrip("。").strip()
            parts = [s.strip() for s in re.split(r"[；;]", rest) if s.strip()]
            if not parts:
                continue
            segments.append({"weather": parts[0], "wind": parts[1] if len(parts) > 1 else ""})
            if len(segments) >= need_count:
                break

        if len(segments) < need_count:
            raise _BulletinParseError(
                f"「未来一周/未来八到十四天天气预报」章节合计只识别到 {len(segments)} 段日预报，"
                f"不足所需的 {need_count} 段"
            )
        return segments

    _WIND_SPLIT_RE = re.compile(r"^(?P<wdir>.*?风)(?P<wspeed>.*)$")

    def _split_wind(self, text: str) -> tuple[str, str]:
        """把公报风力句子拆成 (风向, 风力)，按第一个"风"字切分。"""
        text = (text or "").strip()
        if not text:
            return "", ""
        m = self._WIND_SPLIT_RE.match(text)
        if not m:
            return "", text
        return m.group("wdir"), m.group("wspeed")

    def _parse_base_time(self, xml_path: str) -> datetime:
        m = re.search(r"_(\d{12})_", os.path.basename(xml_path))
        return datetime.strptime(m.group(1), "%Y%m%d%H%M")

    def _parse_xml(
        self, xml_path: str, area_key: str
    ) -> tuple[list | None, set, str | None]:
        """返回 (data_list, available_stationnames, matched_stationname)。
        如果该区域在数据里没找到，第一个返回值为 None。"""
        tree = ET.parse(xml_path)
        available = {s.get("stationname") for s in tree.findall(".//station") if s.get("stationname")}
        candidates = AREA_STATION_CANDIDATES.get(area_key, [area_key])
        matched_name: str | None = None
        for cand in candidates:
            if cand in available:
                matched_name = cand
                break
        if matched_name is None:
            return None, available, None
        for station in tree.findall(".//station"):
            if station.get("stationname") == matched_name:
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
                return sorted(data_list, key=lambda x: x["hour"]), available, matched_name
        return None, available, None

    # ---------- 表格构造 ----------

    def _get_period_label(self, base_hour: int, hour: int) -> str:
        """白天/夜间判定。"""
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
        if not wdir:
            return ""
        return wdir if "风" in wdir else f"{wdir}风"

    def _fmt_wdir_wspeed(self, wdir: str, wspeed: str) -> str:
        """合并风向 + 风力为单列文本，与示例模板一致，例如「北转南风2、3级」。"""
        wdir_part = self._fmt_wdir((wdir or "").strip())
        wspeed_part = (wspeed or "").strip()
        if wdir_part and wspeed_part:
            return f"{wdir_part}{wspeed_part}"
        return wdir_part or wspeed_part

    def _build_table(
        self, forecast_data: list[dict], base_time: datetime
    ) -> list[dict]:
        """模板字段（与 weather_templates/three_day_key_area/template.docx 对应）：
          date / period / weather / wdir_wspeed / t / vis
        能见度（vis）240 数据里没有，先整列留空。"""
        base_hour = base_time.hour
        rows: list[dict] = []
        for item in forecast_data:
            hour = item["hour"]
            period = self._get_period_label(base_hour, hour)
            date_key = self._get_date_label(base_time, base_hour, hour)
            rows.append(
                {
                    "date": date_key,
                    "period": period,
                    "weather": item["wp"],
                    "wdir_wspeed": self._fmt_wdir_wspeed(item["wdir"], item["wspeed"]),
                    "t": item["t"],
                    "vis": "",
                }
            )
        return rows

    def _merge_date_cells(self, doc, table_rows: list[dict]) -> None:
        """渲染完成后把数据表第 1 列「连续相同日期」的单元格做 vMerge 合并。
        约定：数据表是文档里第 1 个 table；表头占 N 行（这里 N=1），其后是与 table_rows 一一对应的数据行。"""
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

    # ---------- 统计与概述 ----------

    def _compute_stats(self, forecast_data: list[dict], base_time: datetime) -> dict:
        from collections import Counter, OrderedDict

        base_hour = base_time.hour
        weather_counter: Counter = Counter()
        day_temps = []
        night_temps = []
        wind_seq: list[dict] = []
        wdir_set: set[str] = set()
        wspeed_max_num = 0
        wspeed_max_str = ""
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
        weather_stat_str = (
            "、".join([f"{name}{cnt}次" for name, cnt in weather_ranked])
            if weather_ranked
            else "无"
        )

        narrative = self._summarize_process(
            forecast_data, base_time, day_weather_map, day_temps
        )

        return {
            "weather_ranked": weather_ranked,
            "weather_stat_str": weather_stat_str,
            "day_temps": day_temps,
            "night_temps": night_temps,
            "t_day_min": min(day_temps) if day_temps else None,
            "t_day_max": max(day_temps) if day_temps else None,
            "t_night_min": min(night_temps) if night_temps else None,
            "t_night_max": max(night_temps) if night_temps else None,
            "wind_seq": wind_seq,
            "wdir_set": wdir_set,
            "wspeed_max_num": wspeed_max_num,
            "wspeed_max_str": wspeed_max_str,
            "day_weather_map": day_weather_map,
            "narrative": narrative,
        }

    _PRECIP_KINDS = (
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
        text = (wp or "").strip()
        if not text:
            return "晴好", None
        for kw, kind in self._PRECIP_KINDS:
            if kw in text:
                return "降水", kind
        if "阴" in text:
            return "阴", None
        return "晴好", None

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

    def _summarize_process(
        self,
        forecast_data: list[dict],
        base_time: datetime,
        day_weather_map: "dict",
        day_temps: list[int],
    ) -> dict:
        from collections import Counter, OrderedDict

        base_hour = base_time.hour
        total = 0
        precip_cnt = 0
        precip_kind_counter: Counter = Counter()
        precip_day_set: "OrderedDict[str, None]" = OrderedDict()
        sky_word_counter: Counter = Counter()

        for item in forecast_data:
            wp = (item.get("wp") or "").strip()
            if not wp:
                continue
            total += 1
            sky_word_counter[self._main_sky_word(wp)] += 1
            cat, kind = self._classify_weather(wp)
            if cat == "降水":
                precip_cnt += 1
                if kind:
                    precip_kind_counter[kind] += 1
                d = self._get_date_label(base_time, base_hour, item["hour"])
                precip_day_set[d] = None

        precip_ratio = (precip_cnt / total) if total else 0.0
        if precip_cnt == 0:
            precip_density = "none"
        elif precip_ratio >= 0.4:
            precip_density = "frequent"
        else:
            precip_density = "occasional"

        main_precip_kinds = [k for k, _ in precip_kind_counter.most_common(2)]

        if sky_word_counter:
            priority = {"多云": 3, "晴": 2, "阴": 1}
            sky_mood = max(
                sky_word_counter.items(),
                key=lambda kv: (kv[1], priority.get(kv[0], 0)),
            )[0]
        else:
            sky_mood = "多云"

        if precip_ratio >= 0.5:
            dominant_mood = f"以{sky_mood}为主，阴雨天气较多"
        elif precip_cnt > 0:
            dominant_mood = f"以{sky_mood}为主，其间伴有零星降水"
        else:
            dominant_mood = f"以{sky_mood}为主，无明显降水"

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

        # 三天概述还要带上「白天/夜间气温区间」给本地兜底用——
        # 本工具的概述参考示例（东城）里就明确含气温描述。
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
        area_key: str,
        forecast_data: list[dict],
        base_time: datetime,
        request,
        user: dict,
        current_model: dict = None,
    ) -> str:
        base_hour = base_time.hour
        stats = self._compute_stats(forecast_data, base_time)

        ranked = stats["weather_ranked"]

        date_labels: list[str] = []
        for item in forecast_data:
            d = self._get_date_label(base_time, base_hour, item["hour"])
            if d not in date_labels:
                date_labels.append(d)
        allowed_dates_str = "、".join(date_labels) if date_labels else "（无）"

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

        t_day_min = stats.get("t_day_min")
        t_day_max = stats.get("t_day_max")
        t_night_min = stats.get("t_night_min")
        t_night_max = stats.get("t_night_max")

        def _temp_range_str(lo, hi) -> str:
            if lo is None or hi is None:
                return "—"
            if lo == hi:
                return f"{lo}℃"
            return f"{lo}～{hi}℃"

        day_temp_str = _temp_range_str(t_day_min, t_day_max)
        night_temp_str = _temp_range_str(t_night_min, t_night_max)

        area_title = AREA_DISPLAY_TITLE[area_key]

        # 这一版的概述参考示例文（东城/西城/天安门各一份）的风格：
        # 1) 简要叙述未来三天的晴雨大势；
        # 2) 若有显著大风过程，仅做事实陈述（出现的风向/风力数字必须来自统计实况）；
        # 3) 末尾给出白天最高 / 夜间最低气温区间。
        # 注意：示例文里出现的"冷空气活动""受冷空气影响"等表述属于预报员人工背景判断，
        # 本工具没有冷空气/天气系统数据依据，**严禁**让 LLM 编造此类表述。
        prompt = (
            f"你是资深气象预报员，为首都关键区域气象服务保障中心撰写「未来三天{area_title}天气服务专报」"
            f"中的「天气综述」段落。\n"
            f"段落直接拼接在「一、天气综述」标题下，请直接给出正文，不要重复任何标题前缀。\n"
            f"要写成一段连贯、自然、有预报员口吻的总体天气趋势综述，"
            f"而不是「16日…、17日…」这样逐日罗列流水账。只输出正文，单段不换行，60~110 字。\n\n"
            f"【未来三天天气过程事实（请据此归纳，不要逐条复述）】\n"
            f"- 主导晴雨基调（已严格按时段统计得出，必须采用，不得改成其它晴雨词）：{sky_mood}\n"
            f"- 一句话基调参考：{nv.get('dominant_mood', '以多云天气为主')}\n"
            f"- 降水概况：{density_str}\n"
            f"- 主要降水形态（按出现多少排序）：{main_kinds_str}\n"
            f"- 有降水的日期：{precip_days_str}\n"
            f"- 白天最高气温区间：{day_temp_str}；夜间最低气温区间：{night_temp_str}\n"
            f"- 最大风力实况：{stats.get('wspeed_max_str') or '无显著大风'}\n\n"
            f"【可参考的逐日天气（仅供你判断事实，禁止逐日照抄成流水账）】\n"
            f"{day_fact_str}\n\n"
            f"【允许出现在正文里的日期】{allowed_dates_str}\n\n"
            f"【写作要求】\n"
            f"1. 开头建议为「未来三天{area_title}以{sky_mood}为主」或类似句式，"
            f"晴雨词只能用「{sky_mood}」，不要在其后加「天气」二字；\n"
            f"2. 若有显著大风过程（如 4 级以上偏北风），仅可做事实陈述，如"
            f"「期间最大风力可达X级」「X日有X级偏北风」，"
            f"风力数字不得超过实际最大风力{stats.get('wspeed_max_num') or 0}级；\n"
            f"3. 末尾必须给出白天最高气温区间 {day_temp_str} 和夜间最低气温区间 {night_temp_str}，"
            f"使用「该期间白天最高气温X～Y℃，夜间最低气温M～N℃。」这种格式（M、N、X、Y 必须严格等于上述数值，不得编造）；\n"
            f"4. 全文使用书面预报语言，单日写「X日」，连续多日写「X-Y日」（均用阿拉伯数字）。\n\n"
            f"【绝对禁止】\n"
            f"- 任何防范建议 / 出行提示 / 生活指数 / 体感类话术（「注意防范」「请携带雨具」等）；\n"
            f"- 编造数据里没有的雨型、风力或风向；\n"
            f"- 编造非「东城/西城/天安门」相关的具体地名；\n"
            f"- 编造任何天气系统 / 环流背景，包括但不限于「冷空气」「弱冷空气」「冷空气活动」「冷空气影响」"
            f"「副热带高压」「雨带」「台风」「急流」「西风槽」等——本工具没有这类数据依据，"
            f"不得做任何成因/背景判断，只能客观描述晴雨、风、温度本身；\n"
            f"- 「受X影响」「受其影响」这类成因措辞一律禁用，只能直接陈述天气事实；\n"
            f"- 任何数据来源描述（数值预报/模式/EC/ECMWF/GFS/卫星/雷达 等）；\n"
            f"- 超出「允许出现在正文里的日期」之外的日期。\n"
        )

        log = logging.getLogger(__name__)

        def _fallback(reason: str, exc: BaseException | None = None) -> str:
            fb = self._fallback_summary(area_key, stats)
            if exc is not None:
                log.warning(
                    "three_day_key_area summary fallback (%s): %s: %s",
                    reason, type(exc).__name__, exc,
                )
            else:
                log.warning("three_day_key_area summary fallback (%s)", reason)
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
            if requested:
                if requested in models:
                    model_id = requested
                else:
                    log.warning(
                        "three_day_key_area: summary_model=%r 不在 app.state.MODELS 中"
                        "（已知 %d 个），忽略该配置",
                        requested, len(models),
                    )
            if not model_id and current_model and current_model.get("id"):
                cid = current_model["id"]
                if cid in models:
                    model_id = cid
                else:
                    log.info(
                        "three_day_key_area: 当前对话模型 %r 不在后端代理可见列表中"
                        "（共 %d 个），将自动改用其它可用模型",
                        cid, len(models),
                    )
            if not model_id:
                if not models:
                    return _fallback("当前没有任何可用模型")
                model_id = next(iter(models.keys()))

            log.info("three_day_key_area: 使用模型 %r 生成概况（候选 %d 个）", model_id, len(models))

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
                content = self._strip_thinking(content)
                cleaned = self._sanitize_summary(content.strip())
                if self._validate_summary(cleaned, stats, date_labels):
                    return cleaned
                log.warning(
                    "three_day_key_area summary failed fact-check, fallback used. raw=%r",
                    cleaned,
                )
                return self._fallback_summary(area_key, stats)
            return _fallback("模型返回内容为空")
        except Exception as e:
            log.exception("generate_three_day_key_area summary failed: %s", e)
            return _fallback("模型调用异常", e)

    def _fallback_summary(self, area_key: str, stats: dict) -> str:
        """本地兜底：参考示例文本风格——
          「未来三天<area>以XX为主[，受弱冷空气影响…]。该期间白天最高气温X～Y℃，夜间最低气温M～N℃。」
        晴雨词严格使用按时段统计得出的 sky_mood。"""
        nv = stats.get("narrative") or {}
        density = nv.get("precip_density", "none")
        kinds = nv.get("main_precip_kinds") or []
        kind_word = kinds[0] if kinds else "阵雨"
        days = nv.get("precip_days") or []
        sky_mood = nv.get("sky_mood") or "多云"

        area_title = AREA_DISPLAY_TITLE[area_key]

        # 主体描述
        if density == "none":
            head = f"未来三天{area_title}以{sky_mood}为主"
        elif density == "frequent":
            day_hint = "、".join(days) if 0 < len(days) <= 3 else "部分时段"
            head = f"未来三天{area_title}以{sky_mood}为主，{day_hint}有{kind_word}"
        else:
            day_hint = "、".join(days) if 0 < len(days) <= 3 else "部分时段"
            head = f"未来三天{area_title}以{sky_mood}为主，{day_hint}有分散性{kind_word}"

        # 大风事实陈述（不写"冷空气过程"等成因，只描述风力本身）
        max_n = stats.get("wspeed_max_num") or 0
        if max_n >= 4:
            head += f"，期间最大风力可达{stats.get('wspeed_max_str') or f'{max_n}级'}"

        # 气温区间结尾（参照示例：「该期间白天最高气温4～6℃，夜间最低气温-4～-2℃。」）
        t_day_min = stats.get("t_day_min")
        t_day_max = stats.get("t_day_max")
        t_night_min = stats.get("t_night_min")
        t_night_max = stats.get("t_night_max")
        tail_parts = []
        if t_day_min is not None and t_day_max is not None:
            if t_day_min == t_day_max:
                tail_parts.append(f"白天最高气温{t_day_max}℃")
            else:
                tail_parts.append(f"白天最高气温{t_day_min}～{t_day_max}℃")
        if t_night_min is not None and t_night_max is not None:
            if t_night_min == t_night_max:
                tail_parts.append(f"夜间最低气温{t_night_min}℃")
            else:
                tail_parts.append(f"夜间最低气温{t_night_min}～{t_night_max}℃")
        if tail_parts:
            return head + "。该期间" + "，".join(tail_parts) + "。"
        return head + "。"

    # ---------- 概述校验（允许出现气温） ----------

    _FORBIDDEN_SOURCE_TERMS = (
        "数值预报产品", "数值预报", "数值模式", "模式预报", "模式资料",
        "集合预报", "再分析", "卫星云图", "雷达回波", "雷达图",
        "ECMWF", "ecmwf", "EC细网格", "EC", "GFS", "gfs",
        "WRF", "wrf", "T639", "T1280",
    )

    # 任何天气系统 / 环流 / 成因背景词都禁用——本工具的数据源里没有这些信息，
    # LLM 写出来一律算编造。「冷空气」「弱冷空气」「冷空气活动」「冷空气影响」也属于此类。
    _FORBIDDEN_SYNOPTIC_TERMS = (
        "冷空气",
        "副热带高压", "副高", "雨带", "暖湿气流", "低涡", "切变",
        "台风", "热带", "西风槽", "高空槽", "低压槽", "锋面", "冷锋", "暖锋",
        "高压脊", "季风", "急流", "环流", "气旋", "反气旋",
    )

    # 成因措辞禁用：示例文里「受X影响」是预报员人工判断后的成因表述，
    # 本工具没有这种数据依据，LLM 写出来都是幻觉，按子串命中即判失败。
    _FORBIDDEN_CAUSATION_PATTERNS = (
        "受其影响", "受影响", "受冷空气", "受弱冷", "受其",
    )

    _FORBIDDEN_ADVICE_TERMS = (
        "防范", "防御", "注意", "建议", "提示", "提醒", "请", "需注意", "谨防",
        "出行", "户外", "适宜", "不宜", "做好", "防护", "防雷", "防汛", "防暑",
        "添衣", "保暖", "携带", "雨具", "防止", "警惕",
        "体感", "舒适度", "舒适", "闷热", "凉爽", "炎热", "寒冷", "湿热",
    )

    _FORBIDDEN_COLLOQUIAL_TERMS = (
        "不过", "但是", "可是", "然而", "呢", "啦", "哦", "呀", "嘛",
    )

    def _validate_summary(self, text: str, stats: dict, allowed_dates: list[str]) -> bool:
        if not text:
            return False

        for term in self._FORBIDDEN_SOURCE_TERMS:
            if term in text:
                return False

        for term in self._FORBIDDEN_SYNOPTIC_TERMS:
            if term in text:
                return False

        for term in self._FORBIDDEN_CAUSATION_PATTERNS:
            if term in text:
                return False
        # 「受...影响」这种成因句式也禁用：用正则匹配「受 + 任意 1~6 字 + 影响」
        if re.search(r"受[\u4e00-\u9fa5]{1,6}影响", text):
            return False

        for term in self._FORBIDDEN_ADVICE_TERMS:
            if term in text:
                return False

        for term in self._FORBIDDEN_COLLOQUIAL_TERMS:
            if term in text:
                return False

        # 本工具的概述允许出现气温——所以这里**不**再禁止℃/温度数字

        # 主导晴雨基调一致性校验
        nv = stats.get("narrative") or {}
        sky_mood = nv.get("sky_mood")
        if sky_mood:
            m = re.search(r"以([\u4e00-\u9fa5]{1,6}?)(?:天气)?为主", text)
            if m and m.group(1) != sky_mood:
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

        # 气温值校验：只允许出现统计得出的实际区间数字
        t_day_min = stats.get("t_day_min")
        t_day_max = stats.get("t_day_max")
        t_night_min = stats.get("t_night_min")
        t_night_max = stats.get("t_night_max")
        allowed_temps: set[int] = set()
        for v in (t_day_min, t_day_max, t_night_min, t_night_max):
            if v is not None:
                allowed_temps.add(int(v))
        # 抓「℃」前的整数（含负号），逐个核对必须 ∈ allowed_temps
        for m in re.finditer(r"(-?\d+)\s*℃", text):
            if int(m.group(1)) not in allowed_temps:
                return False

        return True

    # ---------- thinking / 形近字纠正 ----------

    _THINK_BLOCK_RE = re.compile(
        r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.IGNORECASE | re.DOTALL
    )
    _THINK_OPEN_TAIL_RE = re.compile(
        r"<\s*think\s*>.*\Z", re.IGNORECASE | re.DOTALL
    )

    def _strip_thinking(self, text: str) -> str:
        if not text:
            return text
        text = self._THINK_BLOCK_RE.sub("", text)
        text = self._THINK_OPEN_TAIL_RE.sub("", text)
        return text.strip()

    _SANITIZE_CHAR_MAP = str.maketrans(
        {"i": "1", "I": "1", "l": "1", "L": "1", "o": "0", "O": "0"}
    )

    _SANITIZE_DASH_RE = re.compile(
        r"([0-9iIlLoO]{1,2})[\-\u2010-\u2015\uFF0D]+(?=日)"
    )

    _SANITIZE_DATE_RE = re.compile(
        r"(?<![A-Za-z0-9])([0-9iIlLoO]{1,2})(?=日)"
    )

    def _sanitize_summary(self, text: str) -> str:
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
