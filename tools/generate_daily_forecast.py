"""
title: 当日预报生成工具
description: 按发布时段（08/11/17）从「北京市气象台天气公报」+「北京市气象台未来240h预报产品」自动生成某区当日预报 Word 文档
author: lyq
version: 1.0.0
"""
BULLETIN_OFFICIAL_NAME = "北京市气象台天气公报"
WF240_OFFICIAL_NAME = "北京市气象台未来240h预报产品"

import os
import re
import io
import json
import glob
import shutil
import tempfile
import subprocess
from datetime import datetime, timedelta
from typing import Any, Optional
from xml.etree import ElementTree as ET
from ftplib import FTP, error_perm

from pydantic import BaseModel, Field


SLOT_SPEC: dict[str, dict] = {
    "morning": {
        "hhmm": "0600",
        "template": "morning.docx",
        "publish_hour": 8,
        "title_p1": "今天白天：",
        "title_p2": "今天夜间：",
        "p1_temp_hour": 12, "temp_label_p1": "最高气温",
        "p2_temp_hour": 24, "temp_label_p2": "最低气温",
    },
    "noon": {
        "hhmm": "1100",
        "template": "noon.docx",
        "publish_hour": 11,
        "title_p1": "今天下午：",
        "title_p2": "今天夜间：",
        "p1_temp_hour": 12, "temp_label_p1": "最高气温",
        "p2_temp_hour": 24, "temp_label_p2": "最低气温",
    },
    "afternoon": {
        "hhmm": "1700",
        "template": "afternoon.docx",
        "publish_hour": 17,
        "title_p1": "今天夜间：",
        "title_p2": "明天白天：",
        "p1_temp_hour": 12, "temp_label_p1": "最低气温",
        "p2_temp_hour": 24, "temp_label_p2": "最高气温",
    },
}

SLOT_LABEL_CN = {"morning": "上午", "noon": "中午", "afternoon": "下午"}

# 当天内按时间从晚到早的优先级
SLOT_ORDER_DESC = ["afternoon", "noon", "morning"]

DOC_NAME_RE = re.compile(r"MSP2_BJ-MO_MDWB_ME_LNO_BJ_(\d{12})_00000-24012\.doc$")
XML_NAME_RE = re.compile(r"MSP2_BJ-MO_WF_ME_LNO_BJ_(\d{12})_00000-24012\.xml$")

# 公报「二、未来一周天气预报」章节标题（容忍空白与编号写法差异）
WEEK_SECTION_HEADING_RE = re.compile(r"未来一周.*天气预报")

# 公报里一条「日预报」段的开头形式，例如：
#   29日白天：…
#   2日傍晚-夜间：…
#   30日夜间：…
# 这里只用来「认出这是一条日预报段」，并不依赖具体时段写法。
DAY_SEGMENT_HEAD_RE = re.compile(r"^\s*(?P<day>\d{1,2})日(?P<period>[^:：]+)[:：]")


class Tools:
    class Valves(BaseModel):
        # -------- BJ-240 (240h 预报 XML) --------
        xml_source_mode: str = Field(
            default=os.environ.get("BJ240_SOURCE_MODE", "ftp"),
            description="BJ-240 XML 数据源：local=读本地目录(xml_dir)；ftp=登录 FTP 拉取",
        )
        xml_dir: str = Field(
            default=os.environ.get("BJ240_LOCAL_DIR", "/app/data/BJ-240"),
            description="xml_source_mode=local 时使用：BJ-240 XML 所在目录绝对路径",
        )
        xml_ftp_dir: str = Field(
            default=os.environ.get("BJ240_FTP_DIR", "/cpzz/tqgb-12"),
            description="xml_source_mode=ftp 时使用：BJ-240 XML 在 FTP 上的目录",
        )

        # -------- 公报 .doc --------
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

        # -------- FTP 公用账号（与 BJ240 工具复用同一台机器） --------
        ftp_host: str = Field(
            default=os.environ.get("BJ240_FTP_HOST", "10.225.3.71"),
            description="FTP 服务器地址（公报与 240 共用）",
        )
        ftp_port: int = Field(
            default=int(os.environ.get("BJ240_FTP_PORT", "21")),
            description="FTP 端口",
        )
        ftp_user: str = Field(
            default=os.environ.get("BJ240_FTP_USER", "FtpFiles"),
            description="FTP 用户名",
        )
        ftp_password: str = Field(
            default=os.environ.get("BJ240_FTP_PASSWORD", ""),
            description="FTP 密码",
        )
        ftp_timeout: int = Field(
            default=int(os.environ.get("BJ240_FTP_TIMEOUT", "30")),
            description="FTP 超时（秒）",
        )

        # -------- 模板 --------
        template_dir: str = Field(
            default=os.environ.get(
                "WEATHER_TEMPLATE_DAILY_DIR",
                "/app/weather_templates/daily",
            ),
            description="当日预报模板目录，需包含 morning.docx / noon.docx / afternoon.docx",
        )

        # -------- 行为 --------
        max_backtrack_days: int = Field(
            default=int(os.environ.get("DAILY_MAX_BACKTRACK_DAYS", "2")),
            description="找不到当天可用版本时，最多向前回退几天",
        )
        soffice_bin: str = Field(
            default=os.environ.get("SOFFICE_BIN", "soffice"),
            description="LibreOffice 可执行文件名/绝对路径（用于把 .doc 转 .docx）",
        )
        soffice_timeout: int = Field(
            default=int(os.environ.get("SOFFICE_TIMEOUT", "60")),
            description="soffice 转换超时（秒）",
        )
        debug: bool = Field(
            default=False,
            description="开启后会在错误信息里附加调试细节",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ========================================================================
    # 入口
    # ========================================================================
    async def generate_daily_forecast(
        self,
        district: str,
        force_slot: str = "",
        __user__: dict = None,
        __event_emitter__: Any = None,
        __request__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
    ) -> str:
        """
        生成某区当日预报 Word 文档（上午08/中午11/下午17 三个版本之一），并在聊天中提供下载。

        数据来源固定为「北京市气象台天气公报」和「北京市气象台未来240h预报产品」，
        在向用户介绍数据来源时**必须**使用这两个全称，严禁简写为「公报/240/BJ-240/模式数据」等。

        每天只存在 3 个版本，对应文件名时间戳 0600 / 1100 / 1700；工具会自动选取**最新且
        两份数据均已就绪**的那一份；若当前时段尚未到位，会回退到上一个已就绪时段
        （最多回退 max_backtrack_days 天）。

        【对调用方/LLM 的回复守则】
        工具调用成功后会返回一个 JSON，里面的 `reply_to_user` 字段已经组装好了给用户看的回复
        （包含真实下载链接 markdown）。你应当**原样**把 `reply_to_user` 输出给用户，不要在
        其中添加/删除/编造任何文件名、链接、起报时间、预报时效等元信息。

        :param district: 行政区名称，如"密云"、"延庆"、"昌平"等北京各区
        :param force_slot: 可选，强制 slot=morning/noon/afternoon。传值时只在该 slot 对应的所有
                           日期里回退查找（不会切到别的 slot）；不传则按当前时间自动选最新。
        :return: JSON 字符串，包含 status / district / filename / slot / version_time /
                 reply_to_user 等字段
        """
        emit = __event_emitter__

        await _status(
            emit,
            f"正在扫描{BULLETIN_OFFICIAL_NAME}与{WF240_OFFICIAL_NAME}...",
            False,
        )

        # ---------- 1. 列出两边所有候选时间戳 ----------
        try:
            bulletin_stamps = self._list_bulletin_stamps()
        except Exception as e:
            return _err(
                f"列举{BULLETIN_OFFICIAL_NAME}目录失败：{e}",
                debug=self.valves.debug,
            )

        try:
            xml_stamps = self._list_xml_stamps()
        except Exception as e:
            return _err(
                f"列举{WF240_OFFICIAL_NAME}目录失败：{e}",
                debug=self.valves.debug,
            )

        if not bulletin_stamps:
            return _err(
                f"未找到任何{BULLETIN_OFFICIAL_NAME} .doc 文件"
                f"（{self._bulletin_location_hint()}）"
            )
        if not xml_stamps:
            return _err(
                f"未找到任何{WF240_OFFICIAL_NAME} XML 文件"
                f"（{self._xml_location_hint()}）"
            )

        # ---------- 2. 决定本次生成哪个版本 ----------
        force_slot = (force_slot or "").strip().lower()
        if force_slot and force_slot not in SLOT_SPEC:
            return _err(
                f"非法 force_slot='{force_slot}'，仅支持 morning / noon / afternoon"
            )

        now = datetime.now()
        chosen = self._resolve_chosen_version(
            now, bulletin_stamps, xml_stamps, force_slot or None
        )
        if not chosen:
            scope = (
                f"slot={force_slot}" if force_slot else "morning/noon/afternoon"
            )
            return _err(
                f"最近 {self.valves.max_backtrack_days + 1} 天内没有任何"
                f"「{BULLETIN_OFFICIAL_NAME} + {WF240_OFFICIAL_NAME} 同一时刻均已就绪」"
                f"的版本（{scope}）。"
                f"\n  {BULLETIN_OFFICIAL_NAME}已到时间戳：{sorted(bulletin_stamps)[-6:] or '无'}"
                f"\n  {WF240_OFFICIAL_NAME}已到时间戳：{sorted(xml_stamps)[-6:] or '无'}"
            )
        slot_name, chosen_dt = chosen
        spec = SLOT_SPEC[slot_name]
        stamp_str = chosen_dt.strftime("%Y%m%d%H%M")

        await _status(
            emit,
            f"已选定版本：{SLOT_LABEL_CN[slot_name]}（{chosen_dt:%Y-%m-%d %H:%M}）",
            False,
        )

        # ---------- 3. 拉取该时刻的公报 .doc + 240 XML ----------
        await _status(
            emit,
            f"正在下载{BULLETIN_OFFICIAL_NAME}与{WF240_OFFICIAL_NAME}...",
            False,
        )
        try:
            doc_local, xml_local, cleanup_paths = self._fetch_pair(stamp_str)
        except Exception as e:
            return _err(f"下载数据文件失败：{e}", debug=self.valves.debug)

        try:
            # ---------- 4. 转 .doc → .docx 并解析公报 ----------
            await _status(emit, f"正在解析{BULLETIN_OFFICIAL_NAME}内容...", False)
            try:
                bulletin_docx = self._doc_to_docx(doc_local)
                cleanup_paths.append(os.path.dirname(bulletin_docx))
                paragraphs = self._read_paragraphs(bulletin_docx)
            except Exception as e:
                return _err(
                    f"{BULLETIN_OFFICIAL_NAME} .doc 转换/解析失败：{e}",
                    debug=self.valves.debug,
                )

            # 公报「二、未来一周天气预报」章节的段落顺序是固定的：
            # 不管段标题被人工写成「白天/下午/傍晚-夜间/夜间」哪种，
            # 该 slot 要的内容就在章节的第 1、第 2 段。
            try:
                seg1, seg2 = _extract_first_two_segments(paragraphs)
            except _BulletinParseError as e:
                return _err(
                    f"解析{BULLETIN_OFFICIAL_NAME}「未来一周天气预报」段失败：{e}"
                    f"\n段落预览：{[p for p in paragraphs if '日' in p][:8]}"
                )

            # ---------- 5. 解析 240 XML 取气温 ----------
            await _status(emit, f"正在解析{WF240_OFFICIAL_NAME}数据...", False)
            try:
                xml_data, available = self._parse_xml(xml_local, district)
            except Exception as e:
                return _err(
                    f"解析{WF240_OFFICIAL_NAME} XML 失败：{e}",
                    debug=self.valves.debug,
                )

            if xml_data is None:
                return _err(
                    f"'{district}' 不在{WF240_OFFICIAL_NAME}覆盖范围内。"
                    f"可用地区：{'、'.join(sorted(available))}"
                )

            t1 = xml_data.get(spec["p1_temp_hour"])
            t2 = xml_data.get(spec["p2_temp_hour"])
            if t1 is None or t1.get("t") in (None, ""):
                return _err(
                    f"{WF240_OFFICIAL_NAME}中找不到 hour={spec['p1_temp_hour']} 的预报数据"
                )
            if t2 is None or t2.get("t") in (None, ""):
                return _err(
                    f"{WF240_OFFICIAL_NAME}中找不到 hour={spec['p2_temp_hour']} 的预报数据"
                )

            # ---------- 6. 渲染模板 ----------
            await _status(emit, "正在生成 Word 文档...", False)

            template_path = os.path.join(
                self.valves.template_dir, spec["template"]
            )
            if not os.path.isfile(template_path):
                return _err(f"模板文件不存在：{template_path}")

            from docx import Document  # 延迟导入，避免模块加载期就要求 python-docx

            doc = Document(template_path)

            self._render(
                doc,
                district=district,
                chosen_dt=chosen_dt,
                spec=spec,
                seg1=seg1,
                seg2=seg2,
                t1_str=t1["t"],
                t2_str=t2["t"],
            )

            # ---------- 7. 保存到临时文件 + 上传 + 推下载链接 ----------
            filename = (
                f"{district}区当日预报_{SLOT_LABEL_CN[slot_name]}_"
                f"{chosen_dt:%Y%m%d}.docx"
            )
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                doc.save(tmp.name)
                tmp_path = tmp.name
            cleanup_paths.append(tmp_path)

            version_hint = (
                f"基于 {chosen_dt:%Y年%-m月%-d日 %H:%M} 的"
                f"{BULLETIN_OFFICIAL_NAME}与{WF240_OFFICIAL_NAME}，"
                f"生成「{SLOT_LABEL_CN[slot_name]}预报」"
            ) if os.name != "nt" else (
                # Windows 上 %-m / %-d 不支持，退化用 month / day
                f"基于 {chosen_dt.year}年{chosen_dt.month}月{chosen_dt.day}日 "
                f"{chosen_dt:%H:%M} 的{BULLETIN_OFFICIAL_NAME}与{WF240_OFFICIAL_NAME}，"
                f"生成「{SLOT_LABEL_CN[slot_name]}预报」"
            )
            download_md = await self._upload_and_emit(
                tmp_path=tmp_path,
                filename=filename,
                request=__request__,
                user_dict=__user__,
                chat_id=__chat_id__,
                message_id=__message_id__,
                emit=emit,
                version_hint=version_hint,
            )

            # 给 LLM 看的"完成回执"：必须包含真实下载链接，且明确要求按原文输出，
            # 避免 LLM 自己编造文件名/链接/起报时间等元数据
            assistant_reply = (
                f"{district}区{SLOT_LABEL_CN[slot_name]}当日预报文档已生成，"
                f"点击下载：{download_md}"
            )

            # 工具返回值会进 LLM 上下文，模型通常会"复述"里面的文字。这里：
            # 1) 不再放任何元指令（"数据来源固定…严禁简写…"），避免被当成正文播报；
            # 2) 但**必须**把真实下载链接和文件名放在 message 里，否则模型拿不到链接，
            #    就会自由发挥编造一份假链接 / 假起报时间。
            # 3) reply_to_user 这个字段是显式信号，告诉模型"原样输出这一句即可"。
            return json.dumps(
                {
                    "status": "success",
                    "district": district,
                    "filename": filename,
                    "slot": slot_name,
                    "version_time": chosen_dt.strftime("%Y-%m-%d %H:%M"),
                    "data_sources": [BULLETIN_OFFICIAL_NAME, WF240_OFFICIAL_NAME],
                    "reply_to_user": assistant_reply,
                    "message": assistant_reply,
                },
                ensure_ascii=False,
            )
        finally:
            for p in cleanup_paths:
                _safe_remove(p)

    # ========================================================================
    # 版本选择
    # ========================================================================
    def _resolve_chosen_version(
        self,
        now: datetime,
        bulletin_stamps: set[str],
        xml_stamps: set[str],
        force_slot: str | None,
    ) -> tuple[str, datetime] | None:
        """
        从最新候选时间倒序遍历：今天三个 slot → 昨天三个 slot → ……
        返回第一个「同时存在于 bulletin_stamps 和 xml_stamps」的 (slot, dt)。

        - 当 day == today 时，只考虑 stamp_dt <= now 的 slot（避免选到未来时刻的数据）
        - 当 day  < today 时，三个 slot 都可考虑
        - force_slot 不为 None 时，只在该 slot 上回退
        """
        max_back = max(0, int(self.valves.max_backtrack_days))
        slot_pool = [force_slot] if force_slot else SLOT_ORDER_DESC

        for back in range(max_back + 1):
            day = (now - timedelta(days=back)).date()
            for slot in slot_pool:
                spec = SLOT_SPEC[slot]
                hh = int(spec["hhmm"][:2])
                mm = int(spec["hhmm"][2:])
                stamp_dt = datetime(day.year, day.month, day.day, hh, mm)
                if back == 0 and stamp_dt > now:
                    continue
                stamp_str = stamp_dt.strftime("%Y%m%d%H%M")
                if stamp_str in bulletin_stamps and stamp_str in xml_stamps:
                    return slot, stamp_dt
        return None

    # ========================================================================
    # 公报：列时间戳 / 取确切文件
    # ========================================================================
    def _list_bulletin_stamps(self) -> set[str]:
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_list_stamps(
                self.valves.bulletin_ftp_dir, DOC_NAME_RE
            )
        return self._local_list_stamps(
            self.valves.bulletin_local_dir, DOC_NAME_RE
        )

    def _fetch_bulletin(self, stamp_str: str) -> tuple[str, list[str]]:
        """返回 (本地可读路径, 需要清理的临时路径列表)。"""
        fname = f"MSP2_BJ-MO_MDWB_ME_LNO_BJ_{stamp_str}_00000-24012.doc"
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            local = self._ftp_download(
                self.valves.bulletin_ftp_dir, fname, suffix=".doc", prefix="bulletin_"
            )
            return local, [local]
        full = os.path.join(self.valves.bulletin_local_dir, fname)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"本地找不到公报文件：{full}")
        return full, []

    def _bulletin_location_hint(self) -> str:
        mode = (self.valves.bulletin_source_mode or "local").strip().lower()
        if mode == "ftp":
            return f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{self.valves.bulletin_ftp_dir}"
        return self.valves.bulletin_local_dir

    # ========================================================================
    # BJ-240：列时间戳 / 取确切文件
    # ========================================================================
    def _list_xml_stamps(self) -> set[str]:
        mode = (self.valves.xml_source_mode or "local").strip().lower()
        if mode == "ftp":
            return self._ftp_list_stamps(self.valves.xml_ftp_dir, XML_NAME_RE)
        return self._local_list_stamps(self.valves.xml_dir, XML_NAME_RE)

    def _fetch_xml(self, stamp_str: str) -> tuple[str, list[str]]:
        fname = f"MSP2_BJ-MO_WF_ME_LNO_BJ_{stamp_str}_00000-24012.xml"
        mode = (self.valves.xml_source_mode or "local").strip().lower()
        if mode == "ftp":
            local = self._ftp_download(
                self.valves.xml_ftp_dir, fname, suffix=".xml", prefix="bj240_"
            )
            return local, [local]
        full = os.path.join(self.valves.xml_dir, fname)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"本地找不到 240 XML 文件：{full}")
        return full, []

    def _xml_location_hint(self) -> str:
        mode = (self.valves.xml_source_mode or "local").strip().lower()
        if mode == "ftp":
            return f"ftp://{self.valves.ftp_host}:{self.valves.ftp_port}{self.valves.xml_ftp_dir}"
        return self.valves.xml_dir

    def _fetch_pair(self, stamp_str: str) -> tuple[str, str, list[str]]:
        cleanup: list[str] = []
        doc_local, c1 = self._fetch_bulletin(stamp_str)
        cleanup.extend(c1)
        try:
            xml_local, c2 = self._fetch_xml(stamp_str)
            cleanup.extend(c2)
        except Exception:
            for p in cleanup:
                _safe_remove(p)
            raise
        return doc_local, xml_local, cleanup

    # ========================================================================
    # 本地 / FTP 共用：扫目录列时间戳、下载单个文件
    # ========================================================================
    @staticmethod
    def _local_list_stamps(dirpath: str, name_re: re.Pattern) -> set[str]:
        if not os.path.isdir(dirpath):
            return set()
        out: set[str] = set()
        for name in os.listdir(dirpath):
            m = name_re.search(name)
            if m:
                out.add(m.group(1))
        return out

    def _ftp_list_stamps(self, ftp_dir: str, name_re: re.Pattern) -> set[str]:
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

    def _ftp_download(
        self, ftp_dir: str, filename: str, *, suffix: str, prefix: str
    ) -> str:
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

    # ========================================================================
    # .doc → .docx，读段落
    # ========================================================================
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
        # soffice 生成的文件名 = 原 basename + .docx
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
        # 表格里偶尔也会塞段落，这里也读出来兜底
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        out.append(p.text or "")
        return out

    # ========================================================================
    # 240 XML：取 hour=N 的字段
    # ========================================================================
    @staticmethod
    def _parse_xml(
        xml_path: str, district: str
    ) -> tuple[dict[int, dict] | None, set[str]]:
        tree = ET.parse(xml_path)
        available = {s.get("stationname") for s in tree.findall(".//station")}
        if district not in available:
            return None, available
        for station in tree.findall(".//station"):
            if station.get("stationname") != district:
                continue
            by_hour: dict[int, dict] = {}
            for d in station.findall("data"):
                try:
                    h = int((d.findtext("hour") or "").strip())
                except ValueError:
                    continue
                by_hour[h] = {
                    "hour": h,
                    "wp": (d.findtext("wp") or "").strip(),
                    "t": (d.findtext("t") or "").strip(),
                    "wdir": (d.findtext("wdir") or "").strip(),
                    "wspeed": (d.findtext("wspeed") or "").strip(),
                }
            return by_hour, available
        return None, available

    # ========================================================================
    # 模板渲染：就地改段落（保留首个 run 的格式）
    # ========================================================================
    def _render(
        self,
        doc,
        *,
        district: str,
        chosen_dt: datetime,
        spec: dict,
        seg1: dict,
        seg2: dict,
        t1_str: str,
        t2_str: str,
    ) -> None:
        # 模板段落约定（已在样本中确认）：
        # P0 标题；P2 = "xx区气象台 ... x年x月x日HH时发布"
        # P4 = 标题1；P5 = 天气1；P6 = 风1；P7 = 最高/最低气温:T℃。
        # P10 = 标题2；P11 = 天气2；P12 = 风2；P13 = 最高/最低气温:T℃。
        paragraphs = doc.paragraphs
        if len(paragraphs) < 14:
            raise RuntimeError(
                f"模板段落数异常（共 {len(paragraphs)} 段，至少需要 14 段），"
                "请确认模板未被改动"
            )

        publish_hour = spec["publish_hour"]
        # 顶部时间行：以请求当天的日期 + slot 的 publish_hour 显示
        # 当回退到昨天版本时，chosen_dt 已经是昨天的，照实显示
        header = (
            f"{district}区气象台                                 "
            f"{chosen_dt.year}年{chosen_dt.month}月{chosen_dt.day}日"
            f"{publish_hour:02d}时发布"
        )
        _set_paragraph_text(paragraphs[2], header)

        _set_paragraph_text(paragraphs[4], spec["title_p1"])
        _set_paragraph_text(paragraphs[5], f"{seg1['weather']}；")
        _set_paragraph_text(paragraphs[6], f"{seg1['wind']}；")
        _set_paragraph_text(
            paragraphs[7], f"{spec['temp_label_p1']}：{t1_str}℃。"
        )

        _set_paragraph_text(paragraphs[10], spec["title_p2"])
        _set_paragraph_text(paragraphs[11], f"{seg2['weather']}；")
        _set_paragraph_text(paragraphs[12], f"{seg2['wind']}；")
        _set_paragraph_text(
            paragraphs[13], f"{spec['temp_label_p2']}：{t2_str}℃。"
        )

    # ========================================================================
    # 上传 + 下发下载链接
    # ========================================================================
    async def _upload_and_emit(
        self,
        *,
        tmp_path: str,
        filename: str,
        request,
        user_dict: dict,
        chat_id: str | None,
        message_id: str | None,
        emit: Any,
        version_hint: str,
    ) -> str:
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
        user_obj = Users.get_user_by_id(user_dict["id"])
        file_item = upload_file_handler(
            request,
            file=upload,
            metadata={"chat_id": chat_id, "message_id": message_id},
            process=False,
            user=user_obj,
        )
        url = (
            str(request.base_url).rstrip("/")
            + f"/api/v1/files/{file_item.id}/content"
        )
        if chat_id and message_id:
            try:
                Chats.insert_chat_files(
                    chat_id=chat_id,
                    message_id=message_id,
                    file_ids=[file_item.id],
                    user_id=user_obj.id,
                )
            except Exception:
                pass

        download_md = f"[📄 下载 {filename}]({url})"

        if emit:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "文档生成完成", "done": True},
                }
            )
            await emit(
                {
                    "type": "message",
                    "data": {"content": f"\n\n_{version_hint}_\n\n{download_md}\n"},
                }
            )
        return download_md


# ============================================================================
# 模块级工具函数
# ============================================================================

def _err(msg: str, *, debug: bool = False) -> str:
    payload = {"error": msg}
    return json.dumps(payload, ensure_ascii=False)


async def _status(emit, description: str, done: bool):
    if emit is None:
        return
    try:
        await emit(
            {"type": "status", "data": {"description": description, "done": done}}
        )
    except Exception:
        pass


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


class _BulletinParseError(Exception):
    """公报「未来一周天气预报」段解析失败。"""


def _extract_first_two_segments(
    paragraphs: list[str],
) -> tuple[dict, dict]:
    """定位「二、未来一周天气预报」章节，返回章节后的前 2 段 {weather, wind}。

    设计原则：公报里这两段的标题（X日白天/下午/夜间/傍晚-夜间…）经常因人工撰写
    出现非标准写法，但**段落在章节里的位置是固定的**：
      - 0600 版：第1段 = 今天白天，第2段 = 今天夜间
      - 1100 版：第1段 = 今天下午，第2段 = 今天夜间
      - 1700 版：第1段 = 今天夜间，第2段 = 明天白天
    所以本函数不再尝试匹配段标题里写的是什么时段，只严格按顺序取前两段。

    每段形如：
        29日白天：晴间多云；北转南风2—3级；平原地区最高气温32℃，山区最高气温31～32℃；最小相对湿度30%。
      → weather = "晴间多云"
      → wind    = "北转南风2—3级"
    """
    heading_idx = -1
    for i, raw in enumerate(paragraphs):
        line = (raw or "").strip()
        if WEEK_SECTION_HEADING_RE.search(line):
            heading_idx = i
            break
    if heading_idx < 0:
        raise _BulletinParseError("未找到「未来一周天气预报」章节标题")

    segments: list[dict] = []
    for raw in paragraphs[heading_idx + 1:]:
        line = (raw or "").strip()
        if not line:
            continue
        # 一旦遇到下一个章节标题（如「三、未来八到十四天天气预报」「四、上下班天气」），停止
        if re.search(r"未来.*天气预报", line) or re.search(r"^[一二三四五六七八九十]、", line):
            break
        m = DAY_SEGMENT_HEAD_RE.match(line)
        if not m:
            continue
        # 去掉「X日XXX：」前缀，剩下的 rest 是分号串
        rest = line[m.end():].rstrip("。").strip()
        # 全角分号 ； / 半角分号 ; 都切，兼容混用
        parts = [s.strip() for s in re.split(r"[；;]", rest) if s.strip()]
        if not parts:
            continue
        segments.append({
            "weather": parts[0],
            "wind": parts[1] if len(parts) > 1 else "",
        })
        if len(segments) >= 2:
            break

    if len(segments) < 2:
        raise _BulletinParseError(
            f"「未来一周天气预报」章节后只识别到 {len(segments)} 段日预报，"
            "至少需要 2 段"
        )
    return segments[0], segments[1]


def _set_paragraph_text(paragraph, text: str) -> None:
    """把 paragraph 的文本整段替换为 text，保留首个 run 的字体/字号/颜色等格式。

    python-docx 的 paragraph.text = "..." 会丢失原有 run 的格式（字号会被重置为默认），
    所以我们手动：把首个 run 的 text 改成 text，把其余 run 清空（保留底层 XML 占位避免破坏样式）。
    """
    runs = paragraph.runs
    if not runs:
        # 没有任何 run（极少见，例如空段），直接 add_run
        paragraph.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""
