"""
title: 重要天气报告生成工具
description: 根据用户上传的"北京市降水预报图"，自动生成某区重要天气报告 Word 文档
author: lyq
version: 1.0.0
"""

import os
import re
import io
import json
import base64
import ftplib
import tempfile
from datetime import datetime

from pydantic import BaseModel, Field


# 北京市（全市）版本：district 传入以下别名时，不再局限于单一区的行政边界，
# 而是针对整张图分析北京全市范围的降水过程；标题/文件名统一显示为「北京市」。
CITY_LEVEL_DISTRICT_ALIASES = {"北京市", "全市"}
CITY_LEVEL_DISPLAY_NAME = "北京市"


class Tools:
    class Valves(BaseModel):
        template_path: str = Field(
            default=os.environ.get(
                "WEATHER_TEMPLATE_IMPORTANT_WEATHER",
                "/app/weather_templates/important_weather/template.docx",
            ),
            description="重要天气报告 docx 模板的绝对路径",
        )
        summary_model: str = Field(
            default="",
            description="用于读取图片并生成天气概况文字的视觉模型 ID（留空则使用当前对话所用模型）",
        )
        image_width_cm: float = Field(
            default=14.0,
            description="降水预报图插入到 Word 时的宽度（厘米）",
        )
        ftp_host: str = Field(
            default=os.environ.get("WEATHER_FTP_HOST", "10.225.3.71"),
            description="降水预报图 FTP 服务器地址",
        )
        ftp_port: int = Field(
            default=int(os.environ.get("WEATHER_FTP_PORT", "21")),
            description="降水预报图 FTP 服务器端口",
        )
        ftp_user: str = Field(
            default=os.environ.get("WEATHER_FTP_USER", "FtpFiles"),
            description="FTP 用户名",
        )
        ftp_password: str = Field(
            default=os.environ.get("WEATHER_FTP_PASSWORD", "hwftpqxt_Er_43Gh"),
            description="FTP 密码",
        )
        ftp_base_dir: str = Field(
            default=os.environ.get("WEATHER_FTP_BASE_DIR", "FTPDATA/Product/gzw"),
            description="降水预报图所在的 FTP 基础目录（其下按 YYYYMM 月份分子目录存放图片）",
        )
        debug: bool = Field(
            default=False,
            description="开启后，调用模型失败时会把错误信息写入概况文本，方便排查",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_important_weather_report(
        self,
        district: str,
        __user__: dict = None,
        __event_emitter__: callable = None,
        __request__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
        __messages__: list = None,
        __files__: list = None,
    ) -> str:
        """
        自动从 FTP 获取最新的北京市降水预报图，生成某区重要天气报告 Word 文档，并在聊天中提供下载。

        【对调用方/LLM 的回复守则】
        工具调用成功后会返回一个 JSON，里面的 `reply_to_user` 字段已经组装好了给用户看的回复
        （包含真实下载链接 markdown）。你应当**原样**把 `reply_to_user` 输出给用户，不要改写成
        "点击此处下载文件"之类的通用文案，也不要添加/删除/编造任何文件名、链接等元信息。

        :param district: 行政区名称，如"密云"、"延庆"、"海淀"、"朝阳"等北京各区；
            如需针对全市降水过程做分析，传入"北京市"（不再局限于单一区的边界，
            而是分析整张图上北京全市的降水分布，标题/文件名统一显示为"北京市"）
        :return: JSON 字符串，包含 status / district / filename / download_url / reply_to_user 等字段
        """
        return await _generate_report(
            tool=self,
            kind="important_weather",
            district=district,
            user=__user__,
            event_emitter=__event_emitter__,
            request=__request__,
            chat_id=__chat_id__,
            message_id=__message_id__,
            current_model=__model__,
            messages=__messages__,
            files=__files__,
        )


# =====================================================================
# 下方为共享实现：两个工具（天气情况、重要天气报告）共用同一段逻辑。
# 由于 open-webui 的工具文件是独立加载、不能 import 同目录其他工具，
# 我们把实现以"模块级函数"形式平铺在工具文件里。两个工具文件保持完全
# 一致的实现，只通过 kind 区分模板路径、文件命名等。
# =====================================================================

KIND_CONFIG = {
    "weather_situation": {
        "label": "天气情况",
        "filename_prefix": "天气情况",
    },
    "important_weather": {
        "label": "重要天气报告",
        "filename_prefix": "重要天气报告",
    },
}


async def _generate_report(
    *,
    tool,
    kind: str,
    district: str,
    user: dict,
    event_emitter,
    request,
    chat_id: str,
    message_id: str,
    current_model: dict,
    messages: list,
    files: list,
) -> str:
    cfg = KIND_CONFIG[kind]
    label = cfg["label"]
    is_city_level = district.strip() in CITY_LEVEL_DISTRICT_ALIASES
    display_name = CITY_LEVEL_DISPLAY_NAME if is_city_level else f"{district}区"

    if event_emitter:
        await event_emitter(
            {
                "type": "status",
                "data": {"description": "正在从 FTP 获取最新降水预报图...", "done": False},
            }
        )

    try:
        image_bytes, mime, src_name = _fetch_latest_png_from_ftp(tool.valves)
    except Exception as e:
        if event_emitter:
            await event_emitter(
                {
                    "type": "status",
                    "data": {"description": "FTP 取图失败", "done": True},
                }
            )
        return json.dumps(
            {
                "error": (
                    f"从 FTP 获取最新降水预报图失败：{type(e).__name__}: {e}。"
                    f"请检查 FTP 配置（地址/端口/账号/路径）与网络连通性。"
                )
            },
            ensure_ascii=False,
        )

    if image_bytes is None:
        return json.dumps(
            {
                "error": (
                    "未在 FTP 指定目录下找到任何 PNG 降水预报图，请确认该路径下确有最新图片。"
                )
            },
            ensure_ascii=False,
        )

    if event_emitter:
        await event_emitter(
            {
                "type": "status",
                "data": {"description": f"已获取最新图片：{src_name}", "done": False},
            }
        )

    # 选定 + 校验视觉模型，避免后续在文本模型上反复重试
    try:
        vision_model_id = await _resolve_vision_model_id(
            request=request,
            user_dict=user,
            valves=tool.valves,
            current_model=current_model,
        )
    except _NoVisionModelError as e:
        if event_emitter:
            await event_emitter(
                {
                    "type": "status",
                    "data": {"description": "未配置可用的视觉模型", "done": True},
                }
            )
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    # 1) 让视觉模型一次性识别「预报时段 + 降水相态」（合并调用，省一次往返）。
    #    相态判别依据右下角图例 colorbar 数量与配色：
    #      · 单一彩色 colorbar（绿—蓝—粉—棕，最大 250 mm）= 纯降雨
    #      · 三组 colorbar（彩色 + 斜纹彩色 + 黑灰色，黑灰最大 30 mm）= 含降雪过程
    #    地图主色调（绿色为主 vs 黑灰为主）用于辅助判定主导相态。
    if event_emitter:
        await event_emitter(
            {
                "type": "status",
                "data": {"description": "正在识别预报时段与降水相态...", "done": False},
            }
        )

    period_info = await _read_period_and_phase_from_image(
        image_bytes=image_bytes,
        mime=mime,
        request=request,
        user=user,
        valves=tool.valves,
        model_id=vision_model_id,
    )
    phase = period_info.get("phase") or "rain"

    image_caption = _format_caption(period_info)

    # 2) 让视觉模型生成 XX 区降水描述 + 一句话标题
    if event_emitter:
        phase_label = {"rain": "降雨", "snow": "降雪", "mixed": "雨雪"}.get(phase, "降水")
        await event_emitter(
            {
                "type": "status",
                "data": {"description": f"正在分析{display_name}{phase_label}情况...", "done": False},
            }
        )

    summary, title = await _describe_precipitation(
        image_bytes=image_bytes,
        mime=mime,
        district=district,
        is_city_level=is_city_level,
        period_info=period_info,
        request=request,
        user=user,
        valves=tool.valves,
        model_id=vision_model_id,
    )

    # 3) 用 docxtpl 渲染模板
    if event_emitter:
        await event_emitter(
            {
                "type": "status",
                "data": {"description": "正在生成文档...", "done": False},
            }
        )

    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Cm

    now = datetime.now()
    report_dt = f"{now.year}年{now.month}月{now.day}日{now.hour}时"

    # 把图片落到临时文件给 InlineImage 用
    suffix = ".png" if "png" in (mime or "") else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as img_tmp:
        img_tmp.write(image_bytes)
        img_tmp_path = img_tmp.name

    try:
        doc = DocxTemplate(tool.valves.template_path)
        context = {
            "district": display_name,
            "report_datetime": report_dt,
            "title": title,
            "summary": summary,
            "image": InlineImage(doc, img_tmp_path, width=Cm(tool.valves.image_width_cm)),
            "image_caption": image_caption,
        }
        doc.render(context)

        date_str = datetime.now().strftime("%Y%m%d%H")
        filename = f"{display_name}{cfg['filename_prefix']}_{date_str}.docx"

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            doc.save(tmp.name)
            tmp_path = tmp.name

        # 「重要天气报告」在正文/图片之后再追加标准防范建议 + 固定结尾。
        # （天气情况报告不追加；逻辑共享但用 kind 控制是否调用。）
        if kind == "important_weather":
            _append_advice_to_docx(
                tmp_path,
                phase=phase,
                summary=summary,
                title=title,
            )
    finally:
        try:
            os.unlink(img_tmp_path)
        except OSError:
            pass

    try:
        # 4) 上传 docx 文件到 open-webui，得到下载链接
        from fastapi import UploadFile
        from open_webui.models.users import Users
        from open_webui.models.chats import Chats
        from open_webui.routers.files import upload_file_handler

        with open(tmp_path, "rb") as f:
            content_bytes = f.read()

        upload = UploadFile(
            file=io.BytesIO(content_bytes),
            filename=filename,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            },
        )
        user_obj = Users.get_user_by_id(user["id"])
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
        # 给 LLM 看的"完成回执"：必须包含真实下载链接，且要求模型原样输出，
        # 避免模型把链接改写成"点击此处下载文件"之类的通用文案或编造假链接。
        assistant_reply = (
            f"已为您生成{display_name}{label}文档，点击下载：{download_md}"
        )

        if event_emitter:
            await event_emitter(
                {
                    "type": "status",
                    "data": {"description": "文档生成完成", "done": True},
                }
            )
            await event_emitter(
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
                "reply_to_user": assistant_reply,
                "message": assistant_reply,
            },
            ensure_ascii=False,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------
# 图片获取（从 FTP 取最新 PNG）
# ---------------------------------------------------------------------
# 业务约定：
#   · FTP 上图片放在 {base_dir}/{YYYYMM}/ 下，按月份分子目录；
#   · 文件名形如
#       MSP2_BJ_202605271700_20260527153518-MO_QPF_PRCPV_LNO_BJ_2026052720_2026052820.png
#     其中**第二个 14 位时间戳**（此例 20260527153518 = YYYYMMDDHHMMSS）为图片发布时间；
#   · "最新"以该发布时间戳最大者为准；
#   · 同一发布时间可能同时存在 .svg / .png / .GRB2，我们只取 .png。
# 取图策略：从当前月份起，往前最多回看 _FTP_MONTH_LOOKBACK 个月，
#           逐月扫描，只要某月里找到 PNG 即在该月内选发布时间最大的，并结束。

_FTP_MONTH_LOOKBACK = 6

# 文件名里第二个 14 位时间戳（发布时间）。形如：_20260527153518-
_PUB_TIME_PATTERN = re.compile(r"_(\d{14})-")


def _extract_pub_time(filename: str) -> str | None:
    """从文件名中提取发布时间戳（14 位字符串 YYYYMMDDHHMMSS）。取不到返回 None。"""
    matches = _PUB_TIME_PATTERN.findall(filename or "")
    if matches:
        # 文件名中可能有多个时间戳，发布时间是紧跟在起报时间之后、带 '-' 分隔的那个；
        # 正则已锁定 "_<14位>-" 这种形态，取第一个即可。
        return matches[0]
    return None


def _recent_month_dirs(lookback: int) -> list[str]:
    """返回从本月起往前 lookback 个月的 YYYYMM 列表（按从新到旧排序）。"""
    now = datetime.now()
    year, month = now.year, now.month
    result: list[str] = []
    for _ in range(max(1, lookback)):
        result.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return result


def _ftp_connect(valves) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(valves.ftp_host, int(valves.ftp_port), timeout=30)
    ftp.login(valves.ftp_user, valves.ftp_password)
    try:
        ftp.set_pasv(True)
    except Exception:
        pass
    return ftp


def _ftp_list_pngs(ftp: ftplib.FTP, dir_path: str) -> list[str]:
    """列出目录下所有 .png 文件名（仅文件名，不含路径）。目录不存在/为空时返回 []。"""
    names: list[str] = []
    try:
        entries = ftp.nlst(dir_path)
    except ftplib.error_perm:
        return []
    except Exception:
        return []
    for entry in entries:
        # nlst 可能返回完整路径，也可能仅文件名；统一取末段
        base = entry.replace("\\", "/").rstrip("/").split("/")[-1]
        if base.lower().endswith(".png"):
            names.append(base)
    return names


def _fetch_latest_png_from_ftp(valves) -> tuple[bytes | None, str | None, str | None]:
    """从 FTP 的 {base_dir}/{YYYYMM}/ 下取发布时间最新的 PNG。
    返回 (image_bytes, mime, filename)。找不到时返回 (None, None, None)。
    异常向上抛出，由调用方转成友好错误。
    """
    base_dir = (valves.ftp_base_dir or "").strip().rstrip("/")
    ftp = _ftp_connect(valves)
    try:
        for ym in _recent_month_dirs(_FTP_MONTH_LOOKBACK):
            dir_path = f"{base_dir}/{ym}"
            pngs = _ftp_list_pngs(ftp, dir_path)
            if not pngs:
                continue

            # 按发布时间戳排序，取最大者；取不到时间戳的排在最后
            def sort_key(name: str) -> str:
                t = _extract_pub_time(name)
                return t if t else "0"

            latest = max(pngs, key=sort_key)
            remote_path = f"{dir_path}/{latest}"

            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {remote_path}", buf.write)
            data = buf.getvalue()
            if data:
                return data, "image/png", latest
        return None, None, None
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


def _image_to_data_url(image_bytes: bytes, mime: str | None) -> str:
    mime = mime or "image/png"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------
# 调用视觉模型
# ---------------------------------------------------------------------

class _NoVisionModelError(RuntimeError):
    """没有可用的视觉模型时抛出，由外层捕获并以友好错误返回给用户。"""


def _model_supports_vision(model: dict | None) -> bool:
    """复用前端规则：info.meta.capabilities.vision 不为 False 即视为支持。
    未显式标注时默认按支持处理（与 open-webui 前端 `?? true` 一致）。"""
    if not isinstance(model, dict):
        return True
    info = model.get("info") or {}
    meta = (info.get("meta") if isinstance(info, dict) else None) or {}
    caps = meta.get("capabilities") if isinstance(meta, dict) else None
    if not isinstance(caps, dict):
        return True
    vision = caps.get("vision")
    if vision is None:
        return True
    return bool(vision)


async def _resolve_vision_model_id(
    *,
    request,
    user_dict: dict,
    valves,
    current_model: dict | None,
) -> str:
    """挑出一个支持视觉的模型 ID。优先级：
        1) Valves.summary_model（若存在且支持视觉）
        2) 当前对话所用模型 __model__（若支持视觉）
        3) 系统中第一个被标注 vision=true 的模型

    若三步都没找到，抛 _NoVisionModelError。
    """
    from open_webui.models.users import Users
    from open_webui.utils.models import get_all_models

    user_obj = Users.get_user_by_id(user_dict["id"])
    if user_obj is None:
        raise RuntimeError(f"找不到用户 id={user_dict.get('id')}")

    if not getattr(request.app.state, "MODELS", None):
        await get_all_models(request, user=user_obj)
    models = getattr(request.app.state, "MODELS", {}) or {}
    if not models:
        raise _NoVisionModelError(
            "当前没有任何可用模型，请先在 open-webui 中配置模型后再调用本工具。"
        )

    configured_id = (valves.summary_model or "").strip()
    if configured_id:
        if configured_id not in models:
            raise _NoVisionModelError(
                f"Valves 中配置的 summary_model='{configured_id}' 在系统中不存在或不可用，"
                f"请改为有效的模型 ID。"
            )
        if not _model_supports_vision(models[configured_id]):
            raise _NoVisionModelError(
                f"Valves 中配置的 summary_model='{configured_id}' 不是视觉模型"
                f"（capabilities.vision=false）。请改为支持图像输入的多模态模型。"
            )
        return configured_id

    if current_model and current_model.get("id") in models:
        cm = models[current_model["id"]]
        if _model_supports_vision(cm):
            return current_model["id"]

    explicit_vision = [
        mid for mid, m in models.items()
        if isinstance(m, dict)
        and (((m.get("info") or {}).get("meta") or {}).get("capabilities") or {}).get(
            "vision"
        ) is True
    ]
    if explicit_vision:
        return explicit_vision[0]

    raise _NoVisionModelError(
        "当前对话所用模型未启用视觉能力，且 Valves 的 summary_model 未配置。"
        "请：(1) 在工具的 Valves 里把 summary_model 设为视觉模型的 ID；"
        "或 (2) 在聊天里切换到支持图像输入的多模态模型后再调用本工具。"
    )


async def _vlm_chat(
    *,
    request,
    user_dict: dict,
    model_id: str,
    user_text: str,
    image_bytes: bytes,
    mime: str | None,
) -> str:
    """通用：发一条带图的 user 消息给指定的视觉模型，返回文本回复。"""
    from open_webui.utils.chat import generate_chat_completion
    from open_webui.models.users import Users

    user_obj = Users.get_user_by_id(user_dict["id"])
    if user_obj is None:
        raise RuntimeError(f"找不到用户 id={user_dict.get('id')}")

    data_url = _image_to_data_url(image_bytes, mime)
    # 关闭推理类模型（如 qwen3 系列）的 thinking / reasoning，避免每次识图都先「想很久」：
    # 1) /no_think 是 qwen3 在 chat template 里识别的开关，对上游推理框架（vLLM/SGLang/Ollama）都生效；
    # 2) chat_template_kwargs.enable_thinking=false 是 qwen3 在 OpenAI 兼容接口上的事实标准；
    # 3) reasoning_effort=none / reasoning={"enabled": false} 是 OpenAI o 系列 / 部分 router 的写法，
    #    多写一份无害，不识别就被忽略。
    form_data = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"/no_think\n{user_text}"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "reasoning_effort": "none",
        "reasoning": {"enabled": False},
    }

    saved_direct = getattr(request.state, "direct", None)
    try:
        request.state.direct = False
        response = await generate_chat_completion(
            request, form_data=form_data, user=user_obj, bypass_filter=True
        )
    finally:
        if saved_direct is None:
            try:
                delattr(request.state, "direct")
            except AttributeError:
                pass
        else:
            request.state.direct = saved_direct

    content = ""
    if hasattr(response, "body_iterator"):
        async for chunk in response.body_iterator:
            data = json.loads(chunk.decode("utf-8", "replace"))
            content = data["choices"][0]["message"]["content"] or ""
        if response.background is not None:
            await response.background()
    elif isinstance(response, dict):
        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            or ""
        )
    # 兜底：万一上游没识别 /no_think，模型仍返回了 <think>...</think> 块，
    # 这里整体剥掉再交给后续 JSON / 文本解析，避免思维链污染结果。
    return _strip_thinking(content).strip()


# qwen3 / deepseek-r1 等"思考型"模型在 thinking 开启时会把推理过程放在
# 「<think> 推理… </think>」块里。我们只需要最终回答，把这些块剥掉；
# 若只出现了未闭合的 <think>（思维没给出正式答案），则从 <think> 起整段丢弃。
_THINK_BLOCK_RE = re.compile(
    r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.IGNORECASE | re.DOTALL
)
_THINK_OPEN_TAIL_RE = re.compile(r"<\s*think\s*>.*\Z", re.IGNORECASE | re.DOTALL)


def _strip_thinking(text: str) -> str:
    if not text:
        return text or ""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _THINK_OPEN_TAIL_RE.sub("", text)
    return text


# ---------------------------------------------------------------------
# 业务：识别时段
# ---------------------------------------------------------------------

PERIOD_PROMPT = (
    "这是一张《北京市降水预报图》。请只看图片左上角的标题区域，"
    "提取『预报时段』，时段通常写作类似『2026年03月04日08时-05日20时』或"
    "『2026年03月04日08时至05日20时』的格式。\n"
    "请只返回严格的 JSON 对象，不要包含 markdown 代码块、不要解释。JSON 字段：\n"
    "  - year: 年份（4 位整数）\n"
    "  - start_month: 起始月（整数 1-12）\n"
    "  - start_day: 起始日（整数 1-31）\n"
    "  - start_hour: 起始时（整数 0-23）\n"
    "  - end_month: 结束月（整数；若图中未单独给出结束月，则与 start_month 相同）\n"
    "  - end_day: 结束日（整数 1-31）\n"
    "  - end_hour: 结束时（整数 0-23）\n"
    "示例输出：{\"year\":2026,\"start_month\":3,\"start_day\":4,\"start_hour\":8,"
    "\"end_month\":3,\"end_day\":5,\"end_hour\":20}"
)


async def _read_period_from_image(
    *,
    image_bytes: bytes,
    mime: str | None,
    request,
    user: dict,
    valves,
    model_id: str,
) -> dict:
    """返回 dict：year/start_month/start_day/start_hour/end_month/end_day/end_hour。
    失败时返回 {}（图标题里会显示占位 X）。
    """
    try:
        raw = await _vlm_chat(
            request=request,
            user_dict=user,
            model_id=model_id,
            user_text=PERIOD_PROMPT,
            image_bytes=image_bytes,
            mime=mime,
        )
    except Exception as e:
        if valves.debug:
            return {"_error": f"period model call failed: {e}"}
        return {}

    return _parse_period_json(raw)


def _parse_period_json(text: str) -> dict:
    """尽量从模型回复中抽出 JSON。"""
    if not text:
        return {}
    # 去掉可能的 ```json ``` 包裹
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 直接尝试解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 退一步：找第一个 { ... } 块
    m = re.search(r"\{[^{}]*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------
# 业务：识别相态（纯降雨 / 雨夹雪 / 降雪）
# ---------------------------------------------------------------------
# 北京市气象台《降水预报图》的图例与配色约定：
#   · 纯降雨图：右下角只有 1 组彩色 colorbar（浅绿—绿—青—蓝—粉—棕，
#     最大量级 250 mm），地图填色以绿色调为主，图中红色数字 = 降雨量(mm)。
#   · 含降雪过程的图：右下角并排 3 组 colorbar：
#       1) 左：纯彩色（雨量，最大 250 mm）
#       2) 中：带斜纹的彩色（雨夹雪量，最大 250 mm）
#       3) 右：黑灰色调（雪量，最大 30 mm）
#     地图主色调若以**黑灰色**为主 → 主导相态为「降雪」，红色数字为雪量(mm)；
#     若图上同时存在彩色与黑灰色填色 → 「雨夹雪/雨雪混合」，红色数字按局部色块所属
#     colorbar 解读，但量级表述用降雪/雨夹雪标准。
# 我们把相态归为三类：rain / snow / mixed。

PHASE_PROMPT = (
    "这是一张《北京市降水预报图》。请仔细观察图片**右下角的图例（colorbar）**和"
    "**地图整体的填色色调**，判断本图的降水相态。\n\n"
    "判别规则（务必严格遵循）：\n"
    "1) 若右下角只有 **1 组彩色 colorbar**（颜色从浅绿、绿、青、蓝、粉到棕，"
    "最大数值 250 mm），并且地图填色以**绿色调**为主 → 这是『纯降雨』图，"
    "phase = \"rain\"，此时地图上的红色数字代表降雨量（毫米）。\n"
    "2) 若右下角并排出现 **3 组 colorbar**："
    "左侧为纯彩色（雨量）、中间为带斜纹的彩色（雨夹雪量）、"
    "右侧为**黑灰色调**（雪量，最大数值通常为 30 mm）；并且地图填色**整体以黑灰色为主**"
    "（看不到明显绿色块）→ 这是『纯降雪』图，phase = \"snow\"，"
    "此时地图上的红色数字代表降雪量（毫米）。\n"
    "3) 若右下角有 3 组 colorbar，但地图上**同时**出现明显的绿色填色块"
    "（部分区域用纯彩色，部分区域用黑灰色或斜纹色） → 这是『雨夹雪/雨雪混合』图，"
    "phase = \"mixed\"。\n\n"
    "请只返回严格的 JSON 对象，不要包含 markdown 代码块、不要解释。字段：\n"
    "  - phase: 字符串，必须是 \"rain\" / \"snow\" / \"mixed\" 之一\n"
    "  - colorbar_count: 整数，右下角 colorbar 的组数（通常为 1 或 3）\n"
    "  - map_dominant_color: 字符串，地图主色调，必须是 "
    "\"green\"（绿色调，对应降雨）/ \"gray\"（黑灰色调，对应降雪）/ "
    "\"mixed\"（绿色与黑灰色都明显存在）之一\n"
    "示例输出 1（纯降雨图）：{\"phase\":\"rain\",\"colorbar_count\":1,\"map_dominant_color\":\"green\"}\n"
    "示例输出 2（纯降雪图）：{\"phase\":\"snow\",\"colorbar_count\":3,\"map_dominant_color\":\"gray\"}\n"
    "示例输出 3（雨雪混合图）：{\"phase\":\"mixed\",\"colorbar_count\":3,\"map_dominant_color\":\"mixed\"}"
)


async def _read_phase_from_image(
    *,
    image_bytes: bytes,
    mime: str | None,
    request,
    user: dict,
    valves,
    model_id: str,
) -> str:
    """识别图片相态，返回 "rain" / "snow" / "mixed" 之一。
    任何识别失败/异常情况都默认回退为 "rain"（纯降雨），以保证向后兼容。
    """
    try:
        raw = await _vlm_chat(
            request=request,
            user_dict=user,
            model_id=model_id,
            user_text=PHASE_PROMPT,
            image_bytes=image_bytes,
            mime=mime,
        )
    except Exception:
        return "rain"

    obj = _parse_period_json(raw)
    phase = (obj.get("phase") or "").strip().lower()
    if phase in ("rain", "snow", "mixed"):
        return phase

    # 兜底：若 phase 字段无效，根据 colorbar_count + map_dominant_color 反推
    cb = obj.get("colorbar_count")
    color = (obj.get("map_dominant_color") or "").strip().lower()
    if isinstance(cb, int) and cb >= 2:
        if color == "gray":
            return "snow"
        if color == "mixed":
            return "mixed"
        # 多 colorbar 但主色仍是绿，按业务通常仍偏雨：保守起见走 mixed
        return "mixed"
    return "rain"


# ---------------------------------------------------------------------
# 业务：一次性识别「时段 + 相态」（合并调用，减少一次视觉模型往返）
# ---------------------------------------------------------------------
# 时段提取与相态判别都是对同一张图的简单结构化任务，互不干扰，
# 合并到同一个 prompt 里一次返回，可把视觉模型调用从 3 次降到 2 次。

PERIOD_PHASE_PROMPT = (
    "这是一张《北京市降水预报图》。请同时完成两件事，并把结果合并到**一个** JSON 对象中返回。\n\n"
    "【任务一：读取左上角标题区域的『预报时段』】\n"
    "时段通常写作类似『2026年03月04日08时-05日20时』或『2026年03月04日08时至05日20时』。\n"
    "需要的字段：\n"
    "  - year: 年份（4 位整数）\n"
    "  - start_month: 起始月（整数 1-12）\n"
    "  - start_day: 起始日（整数 1-31）\n"
    "  - start_hour: 起始时（整数 0-23）\n"
    "  - end_month: 结束月（整数；若图中未单独给出结束月，则与 start_month 相同）\n"
    "  - end_day: 结束日（整数 1-31）\n"
    "  - end_hour: 结束时（整数 0-23）\n\n"
    "【任务二：观察右下角图例（colorbar）与地图整体填色色调，判断降水相态】\n"
    "判别规则（务必严格遵循）：\n"
    "1) 若右下角只有 **1 组彩色 colorbar**（颜色从浅绿、绿、青、蓝、粉到棕，最大数值 250 mm），"
    "且地图填色以**绿色调**为主 → 『纯降雨』，phase=\"rain\"。\n"
    "2) 若右下角并排出现 **3 组 colorbar**（左：纯彩色雨量；中：斜纹彩色雨夹雪量；"
    "右：**黑灰色调**雪量，最大约 30 mm），且地图填色**整体以黑灰色为主** → 『纯降雪』，phase=\"snow\"。\n"
    "3) 若右下角有 3 组 colorbar，但地图上**同时**出现明显绿色填色块与黑灰/斜纹色块 → "
    "『雨夹雪/雨雪混合』，phase=\"mixed\"。\n"
    "需要的字段：\n"
    "  - phase: 字符串，必须是 \"rain\" / \"snow\" / \"mixed\" 之一\n"
    "  - colorbar_count: 整数，右下角 colorbar 的组数（通常为 1 或 3）\n"
    "  - map_dominant_color: 字符串，地图主色调，必须是 "
    "\"green\"（绿色调）/ \"gray\"（黑灰色调）/ \"mixed\"（绿色与黑灰色都明显存在）之一\n\n"
    "请只返回严格的 JSON 对象，不要包含 markdown 代码块、不要解释。\n"
    "示例输出：{\"year\":2026,\"start_month\":3,\"start_day\":4,\"start_hour\":8,"
    "\"end_month\":3,\"end_day\":5,\"end_hour\":20,"
    "\"phase\":\"rain\",\"colorbar_count\":1,\"map_dominant_color\":\"green\"}"
)


def _phase_from_obj(obj: dict) -> str:
    """从合并 JSON 中解析相态，沿用原 _read_phase_from_image 的兜底逻辑。"""
    phase = (obj.get("phase") or "").strip().lower()
    if phase in ("rain", "snow", "mixed"):
        return phase
    cb = obj.get("colorbar_count")
    color = (obj.get("map_dominant_color") or "").strip().lower()
    if isinstance(cb, int) and cb >= 2:
        if color == "gray":
            return "snow"
        if color == "mixed":
            return "mixed"
        return "mixed"
    return "rain"


async def _read_period_and_phase_from_image(
    *,
    image_bytes: bytes,
    mime: str | None,
    request,
    user: dict,
    valves,
    model_id: str,
) -> dict:
    """一次调用同时拿回时段字段与相态。返回的 dict 含
    year/start_month/.../end_hour 以及 phase。
    任何失败都做安全兜底：时段缺失留空（标题显示 X），相态默认 "rain"。
    """
    try:
        raw = await _vlm_chat(
            request=request,
            user_dict=user,
            model_id=model_id,
            user_text=PERIOD_PHASE_PROMPT,
            image_bytes=image_bytes,
            mime=mime,
        )
    except Exception as e:
        if valves.debug:
            return {"_error": f"period+phase model call failed: {e}", "phase": "rain"}
        return {"phase": "rain"}

    obj = _parse_period_json(raw)
    if not isinstance(obj, dict):
        return {"phase": "rain"}
    obj["phase"] = _phase_from_obj(obj)
    return obj


def _format_caption(period: dict) -> str:
    """根据时段字典生成图标题（固定为"北京地区累计降雨预报图"，
    与单位提供的 Word 模板一致；相态差异在正文中描述）。
    若某字段缺失，则相应位置写 X。
    """

    def fmt(v):
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str) and v.strip().isdigit():
            return str(int(v.strip()))
        return "X"

    sm = fmt(period.get("start_month"))
    sd = fmt(period.get("start_day"))
    sh = fmt(period.get("start_hour"))
    em = fmt(period.get("end_month"))
    ed = fmt(period.get("end_day"))
    eh = fmt(period.get("end_hour"))

    # 结束月若与开始月相同，按惯例不重复写月份
    if em == sm:
        return f"（{sm}月{sd}日{sh}时至{ed}日{eh}时）北京地区累计降雨预报图"
    return f"（{sm}月{sd}日{sh}时至{em}月{ed}日{eh}时）北京地区累计降雨预报图"


# ---------------------------------------------------------------------
# 业务：生成 XX 区降水概况 + 一句话标题
# ---------------------------------------------------------------------

def _period_brief(period: dict, district: str) -> str:
    """把识别到的时段拼成自然语言短语，作为提示词的上下文。"""
    if not period:
        return f"图中标注的预报时段"

    def g(k):
        v = period.get(k)
        return str(v) if isinstance(v, int) else None

    sm, sd, sh = g("start_month"), g("start_day"), g("start_hour")
    em, ed, eh = g("end_month"), g("end_day"), g("end_hour")
    if all([sm, sd, sh, ed, eh]):
        if em and em != sm:
            return f"{sm}月{sd}日{sh}时至{em}月{ed}日{eh}时"
        return f"{sm}月{sd}日{sh}时至{ed}日{eh}时"
    return "图中标注的预报时段"


def _period_hours(period: dict) -> int | None:
    """计算时段长度（小时）。失败时返回 None。
    起止月份若不一致，需要识别出年份才能精确计算；这里做尽力而为：
      - 若年份和起止月日时齐全，直接用 datetime 算差；
      - 若仅起止日时齐全（最常见情形），按 24 小时为周期推断：
          end_hour_total = end_day * 24 + end_hour
          start_hour_total = start_day * 24 + start_hour
          若 end < start，按跨月（+30 天）兜底（极少触发）。
    """
    try:
        sm = period.get("start_month")
        sd = period.get("start_day")
        sh = period.get("start_hour")
        em = period.get("end_month")
        ed = period.get("end_day")
        eh = period.get("end_hour")
        if not all(isinstance(v, int) for v in (sd, sh, ed, eh)):
            return None
        if isinstance(sm, int) and isinstance(em, int) and sm != em:
            # 跨月：粗略按 30 天补
            end_total = (ed + 30) * 24 + eh
            start_total = sd * 24 + sh
        else:
            end_total = ed * 24 + eh
            start_total = sd * 24 + sh
            if end_total < start_total:
                end_total += 30 * 24
        delta = end_total - start_total
        return delta if delta > 0 else None
    except Exception:
        return None


# 量级档位结构（与 GB/T 28592-2012 对齐）。
# 每条 (lo, hi, name)：表示 [lo, hi) 区间内的值归为 name；hi 为 None 表示「≥ lo」。
_LEVELS_12H = [
    (0.1, 5.0, "小雨"),
    (5.0, 15.0, "中雨"),
    (15.0, 30.0, "大雨"),
    (30.0, 70.0, "暴雨"),
    (70.0, 140.0, "大暴雨"),
    (140.0, None, "特大暴雨"),
]
_LEVELS_24H = [
    (0.1, 10.0, "小雨"),
    (10.0, 25.0, "中雨"),
    (25.0, 50.0, "大雨"),
    (50.0, 100.0, "暴雨"),
    (100.0, 250.0, "大暴雨"),
    (250.0, None, "特大暴雨"),
]

# 降雪量等级（GB/T 28592-2012）。注意降雪图上的红色数字 = 降雪量(融化后毫米数)，
# 而不是积雪深度(cm)。积雪深度需要在文案中另行描述。
_SNOW_LEVELS_12H = [
    (0.1, 1.0, "小雪"),
    (1.0, 3.0, "中雪"),
    (3.0, 6.0, "大雪"),
    (6.0, 10.0, "暴雪"),
    (10.0, 15.0, "大暴雪"),
    (15.0, None, "特大暴雪"),
]
_SNOW_LEVELS_24H = [
    (0.1, 2.5, "小雪"),
    (2.5, 5.0, "中雪"),
    (5.0, 10.0, "大雪"),
    (10.0, 20.0, "暴雪"),
    (20.0, 30.0, "大暴雪"),
    (30.0, None, "特大暴雪"),
]


def _rain_level_table(period_hours: int | None) -> tuple[str, str, list[tuple[float, float | None, str]]]:
    """根据时段长度返回（分类标签字符串, 速查表文本, 结构化档位列表）。
    选用规则（GB/T 28592-2012）：
      - 时段 ≤ 12 小时：12 小时标准
      - 13 ~ 24 小时：24 小时标准
      - >24 小时：24 小时标准
      - 未知时段：12 小时标准（保守起见用更严格的下档，避免高估量级）
    """
    table_12h = (
        "【12 小时降水量等级（适用于本图预报时段）】\n"
        "  - 小雨：    0.1 ~ 4.9 mm\n"
        "  - 中雨：    5.0 ~ 14.9 mm\n"
        "  - 大雨：    15.0 ~ 29.9 mm\n"
        "  - 暴雨：    30.0 ~ 69.9 mm\n"
        "  - 大暴雨：  70.0 ~ 139.9 mm\n"
        "  - 特大暴雨：≥ 140.0 mm"
    )
    table_24h = (
        "【24 小时降水量等级（适用于本图预报时段）】\n"
        "  - 小雨：    0.1 ~ 9.9 mm\n"
        "  - 中雨：    10.0 ~ 24.9 mm\n"
        "  - 大雨：    25.0 ~ 49.9 mm\n"
        "  - 暴雨：    50.0 ~ 99.9 mm\n"
        "  - 大暴雨：  100.0 ~ 249.9 mm\n"
        "  - 特大暴雨：≥ 250.0 mm"
    )

    if period_hours is None:
        return (
            "未知时段长度（请按图片左上角时段自行判定 12h 或 24h 标准）",
            "【降水量等级标准（依据 GB/T 28592-2012）】\n"
            "  本工具未能识别时段长度，请根据图片左上角标题判断本预报是 12 小时还是 24 小时累计量后按表对照：\n\n"
            + table_12h
            + "\n\n"
            + table_24h,
            _LEVELS_12H,
        )
    if period_hours <= 12:
        return (f"{period_hours} 小时（采用 12 小时标准）", table_12h, _LEVELS_12H)
    if period_hours <= 24:
        return (f"{period_hours} 小时（采用 24 小时标准）", table_24h, _LEVELS_24H)
    return (
        f"{period_hours} 小时（超过 24 小时，仍按 24 小时标准对照，并明确累计时段）",
        table_24h,
        _LEVELS_24H,
    )


def _snow_level_table(period_hours: int | None) -> tuple[str, str, list[tuple[float, float | None, str]]]:
    """降雪量等级速查表，结构与 _rain_level_table 一致。"""
    table_12h = (
        "【12 小时降雪量等级（适用于本图预报时段）】\n"
        "  - 小雪：    0.1 ~ 0.9 mm\n"
        "  - 中雪：    1.0 ~ 2.9 mm\n"
        "  - 大雪：    3.0 ~ 5.9 mm\n"
        "  - 暴雪：    6.0 ~ 9.9 mm\n"
        "  - 大暴雪：  10.0 ~ 14.9 mm\n"
        "  - 特大暴雪：≥ 15.0 mm"
    )
    table_24h = (
        "【24 小时降雪量等级（适用于本图预报时段）】\n"
        "  - 小雪：    0.1 ~ 2.4 mm\n"
        "  - 中雪：    2.5 ~ 4.9 mm\n"
        "  - 大雪：    5.0 ~ 9.9 mm\n"
        "  - 暴雪：    10.0 ~ 19.9 mm\n"
        "  - 大暴雪：  20.0 ~ 29.9 mm\n"
        "  - 特大暴雪：≥ 30.0 mm"
    )

    if period_hours is None:
        return (
            "未知时段长度（请按图片左上角时段自行判定 12h 或 24h 标准）",
            "【降雪量等级标准（依据 GB/T 28592-2012）】\n"
            "  本工具未能识别时段长度，请根据图片左上角标题判断本预报是 12 小时还是 24 小时累计量后按表对照：\n\n"
            + table_12h
            + "\n\n"
            + table_24h,
            _SNOW_LEVELS_12H,
        )
    if period_hours <= 12:
        return (f"{period_hours} 小时（采用 12 小时降雪标准）", table_12h, _SNOW_LEVELS_12H)
    if period_hours <= 24:
        return (f"{period_hours} 小时（采用 24 小时降雪标准）", table_24h, _SNOW_LEVELS_24H)
    return (
        f"{period_hours} 小时（超过 24 小时，仍按 24 小时降雪标准对照，并明确累计时段）",
        table_24h,
        _SNOW_LEVELS_24H,
    )


def _phase_level_table(
    phase: str, period_hours: int | None
) -> tuple[str, str, list[tuple[float, float | None, str]]]:
    """根据相态选择对应的等级速查表。
      · rain  → 降雨等级
      · snow  → 降雪等级
      · mixed → 主导相态以雪为主，量级按降雪标准（业务上雨夹雪量级与雪相同）
    """
    if phase == "snow" or phase == "mixed":
        return _snow_level_table(period_hours)
    return _rain_level_table(period_hours)


def _classify_level(value: float, levels: list[tuple[float, float | None, str]]) -> str | None:
    """把单个降水量值映射到档位名。低于 0.1 mm 归 None。"""
    if value is None or value < 0.1:
        return None
    for lo, hi, name in levels:
        if hi is None:
            if value >= lo:
                return name
        else:
            if lo <= value < hi:
                return name
    return None


def _classify_range(
    lo: float, hi: float, levels: list[tuple[float, float | None, str]]
) -> tuple[str, list[str]]:
    """把区间 [lo, hi] 映射到「主导量级 + 跨档量级列表」。
    返回 (label, levels_in_range)：
      - label: 用于正文/标题的量级表述，例如「小到中雨」「中雨」「中到大雨」。
      - levels_in_range: 区间覆盖到的所有档名（按强度从弱到强），用于自洽校验。
    判定逻辑：
      - 取区间内的低端与高端各自归档；若两端在同一档 → 单档（如「中雨」）；
        若跨档 → 用「弱档到强档」连接（如「小到中雨」「中到大雨」）。
    """
    if hi < lo:
        lo, hi = hi, lo
    low_name = _classify_level(lo, levels)
    high_name = _classify_level(hi, levels)
    order = [name for _, _, name in levels]

    if low_name is None and high_name is None:
        return "无明显降水", []
    if low_name is None:
        low_name = high_name
    if high_name is None:
        high_name = low_name

    if low_name == high_name:
        return low_name, [low_name]

    # 收集区间覆盖到的所有档（含中间档）
    li, hi_i = order.index(low_name), order.index(high_name)
    covered = order[li : hi_i + 1]

    # 业务习惯：相邻档写成 "X到Y雨"（小到中雨、中到大雨、大到暴雨…）
    label = f"{low_name[:-1]}到{high_name}"
    return label, covered


async def _describe_precipitation(
    *,
    image_bytes: bytes,
    mime: str | None,
    district: str,
    period_info: dict,
    request,
    user: dict,
    valves,
    model_id: str,
    is_city_level: bool = False,
) -> tuple[str, str]:
    """让模型读图，输出 (summary, title)。失败时给一个安全的兜底。
    根据 period_info 中的 phase 字段（rain/snow/mixed），自动切换到相应的
    "降雨 / 降雪 / 雨夹雪" 写作分支与量级标准。

    is_city_level=True 时（district 为"北京市"/"全市"），改用
    _build_city_precipitation_prompt：不再局限于单一区的行政边界，而是
    针对整张图分析北京全市范围的降水分布，且允许在正文中点出具体区名/方位。

    流程：调一次 → 若解析到的红色数字 < 3 或缺关键字段，再调一次重试；
    取并集后用 max_value 做客观锚点驱动 _enforce_levels。
    """
    label = CITY_LEVEL_DISPLAY_NAME if is_city_level else f"{district}区"
    period_str = _period_brief(period_info, district)
    p_hours = _period_hours(period_info)
    phase = (period_info.get("phase") or "rain").strip().lower()
    if phase not in ("rain", "snow", "mixed"):
        phase = "rain"
    which_std, level_table, levels = _phase_level_table(phase, p_hours)

    if is_city_level:
        prompt = _build_city_precipitation_prompt(
            period_str=period_str,
            which_std=which_std,
            level_table=level_table,
            phase=phase,
        )
    else:
        prompt = _build_precipitation_prompt(
            district=district,
            period_str=period_str,
            which_std=which_std,
            level_table=level_table,
            phase=phase,
        )

    async def _ask_once() -> dict:
        try:
            raw = await _vlm_chat(
                request=request,
                user_dict=user,
                model_id=model_id,
                user_text=prompt,
                image_bytes=image_bytes,
                mime=mime,
            )
        except Exception as e:
            return {"_error": f"{type(e).__name__}: {e}"}
        return _parse_precip_json(raw)

    first = await _ask_once()
    # 触发 retry 的条件：解析失败、红色数字不足 3 个、或缺关键字段
    needs_retry = (
        first.get("_error")
        or not first.get("title")
        or not first.get("summary")
        or len(first.get("district_red_numbers") or []) < 3
        or first.get("max_value") is None
    )
    if needs_retry:
        second = await _ask_once()
        merged = _merge_precip_responses(first, second)
    else:
        merged = first

    title = merged.get("title") or ""
    summary = merged.get("summary") or ""

    if not title and not summary:
        if valves.debug and merged.get("_error"):
            return (
                f"[模型调用失败：{merged['_error']}] 预计{label}有降水。",
                f"{label}降水预报",
            )
        return _fallback_summary(label, phase), _fallback_title(label, phase)

    summary = _filter_summary(summary, district, is_city_level=is_city_level)
    summary, title = _enforce_levels(
        summary,
        title,
        label,
        levels,
        phase,
        max_value=merged.get("max_value"),
        main_range_lo=merged.get("main_range_lo"),
        main_range_hi=merged.get("main_range_hi"),
    )
    if not title:
        title = _fallback_title(label, phase)
    if not summary:
        summary = _fallback_summary(label, phase)
    return summary, title


def _parse_precip_json(text: str) -> dict:
    """解析模型回复，提取所有结构化字段。失败返回带 _error 的 dict。"""
    out: dict = {}
    if not text:
        out["_error"] = "empty response"
        return out
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    obj = None
    try:
        obj = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = None
    if not isinstance(obj, dict):
        # 回退：第一行当 title，剩余当 summary
        parts = [s for s in text.splitlines() if s.strip()]
        if parts:
            out["title"] = _clean_oneliner(parts[0])
            out["summary"] = _clean_paragraph(
                "".join(parts[1:]) if len(parts) > 1 else parts[0]
            )
        else:
            out["_error"] = "no parseable content"
        return out

    out["title"] = _clean_oneliner(obj.get("title", ""))
    out["summary"] = _clean_paragraph(obj.get("summary", ""))
    nums = obj.get("district_red_numbers")
    if isinstance(nums, list):
        clean_nums: list[float] = []
        for v in nums:
            try:
                clean_nums.append(float(v))
            except (TypeError, ValueError):
                continue
        out["district_red_numbers"] = clean_nums
    for k in ("max_value", "main_range_lo", "main_range_hi"):
        v = obj.get(k)
        if v is None:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _merge_precip_responses(a: dict, b: dict) -> dict:
    """合并两次模型回复：title/summary 优先取信息更完整的那次，
    红色数字取并集（去重后从大到小排序），max_value 取两次最大值。"""
    pick = b if (b.get("title") and b.get("summary")) else a
    merged: dict = dict(pick)

    nums = set()
    for d in (a, b):
        for v in d.get("district_red_numbers") or []:
            try:
                nums.add(round(float(v), 2))
            except (TypeError, ValueError):
                continue
    if nums:
        merged["district_red_numbers"] = sorted(nums, reverse=True)

    max_vals = [
        d.get("max_value") for d in (a, b) if isinstance(d.get("max_value"), (int, float))
    ]
    if nums or max_vals:
        candidates = list(max_vals)
        if nums:
            candidates.append(max(nums))
        merged["max_value"] = max(candidates)

    # main_range：取两次的并集（lo 取最小、hi 取最大）
    lo_vals = [
        d.get("main_range_lo") for d in (a, b)
        if isinstance(d.get("main_range_lo"), (int, float))
    ]
    hi_vals = [
        d.get("main_range_hi") for d in (a, b)
        if isinstance(d.get("main_range_hi"), (int, float))
    ]
    if lo_vals:
        merged["main_range_lo"] = min(lo_vals)
    if hi_vals:
        merged["main_range_hi"] = max(hi_vals)
    return merged


def _build_precipitation_prompt(
    *,
    district: str,
    period_str: str,
    which_std: str,
    level_table: str,
    phase: str,
) -> str:
    """根据相态拼装 LLM 提示词。三种分支 rain / snow / mixed。
    关键改造：要求模型把目标区内所有红色数字穷举出来（含小数），并把
    『主流范围 main_range_hi』与『极值 max_value』分开返回。Python 侧用
    max_value 做客观锚点，自动补/删「局地{更高档}」表述。
    """
    if phase == "snow":
        kind_word = "降雪"
        amount_word = "降雪量"
        cum_word = "累计降雪量"
        intensity_word = "雪势"
        end_char = "雪"
        levels_hint = "小雪/中雪/大雪/暴雪/大暴雪/特大暴雪"
        legend_intro = (
            "图例右下角为三组并排 colorbar；地图主色调为黑灰色，"
            "判定为『纯降雪』，红色数字代表降雪量（毫米，融化水当量）。"
        )
        title_examples = (
            f"【有局地强降水】「{district}区南部将出现大雪」「{district}区局地暴雪」"
            f"「{district}区东南部有大雪」\n"
            f"          【全区一致】「{district}区将出现中雪」「{district}区有小雪」"
            f"「{district}区基本无明显降雪」"
        )
        extra_elements = (
            f"━━━ 降雪可选要素（酌情写 1 项，必须以降雪量为锚） ━━━\n"
            f"- 积雪：1毫米雪量约对应 0.5~1厘米积雪；可写「平原积雪不足 1 厘米」「山区 1~2 厘米」。\n"
            f"- 交通：可写「道面湿滑，局地积雪结冰，影响交通出行」。\n\n"
        )
    elif phase == "mixed":
        kind_word = "雨雪"
        amount_word = "降水量"
        cum_word = "累计降水量"
        intensity_word = "雨雪势"
        end_char = "雪"
        levels_hint = "（按降雪标准）小雪/中雪/大雪/暴雪/大暴雪/特大暴雪"
        legend_intro = (
            "图例右下角为三组并排 colorbar；地图同时出现彩色与黑灰色填色，"
            "判定为『雨雪混合』，红色数字代表降水量（毫米）。"
        )
        title_examples = (
            f"「{district}区有雨夹雪或小雪」「{district}区将出现雨转雪，量级中雪」"
            f"「{district}区南部有大雪」"
        )
        extra_elements = (
            f"━━━ 雨雪混合可选要素（酌情写 1~2 项） ━━━\n"
            f"- 相态（最重要）：例如「山区以雪为主，平原由雨或雨夹雪转雪」。\n"
            f"- 积雪：1毫米雪量约对应 0.5~1厘米积雪。\n"
            f"- 交通：可写「道面湿滑，局地积雪结冰」。\n\n"
        )
    else:
        phase = "rain"
        kind_word = "降雨"
        amount_word = "降水量"
        cum_word = "累计降水量"
        intensity_word = "雨势"
        end_char = "雨"
        levels_hint = "小雨/中雨/大雨/暴雨/大暴雨/特大暴雨"
        legend_intro = (
            "图例右下角为单一彩色 colorbar（最大 250 毫米），"
            "判定为『纯降雨』，红色数字代表降雨量（毫米）。"
        )
        title_examples = (
            f"【有局地强降水】「{district}区南部将出现大雨」「{district}区局地暴雨」"
            f"「{district}区东南部有大雨」\n"
            f"          【全区一致】「{district}区将出现中雨」「{district}区有小雨」"
            f"「{district}区基本无明显降水」"
        )
        extra_elements = ""

    prompt = (
        f"你是北京市气象台首席预报员，正在分析《北京市降水预报图》。\n"
        f"{legend_intro}\n"
        f"预报时段：{period_str}（{which_std}）。\n\n"
        f"━━━ 量级标准 ━━━\n"
        f"{level_table}\n\n"
        f"━━━ 工作流程（按顺序完成，禁止跳步） ━━━\n"
        f"第 1 步：扫描{district}区行政边界内所有红色加粗数字（含小数），"
        f"逐个记录。不要遗漏任何一个——即使数字处于色块边界、字号偏小、"
        f"或被周围色块衬托得不明显，只要它的中心点落在{district}区内就必须计入。\n"
        f"第 2 步：从第 1 步的数字中识别——\n"
        f"   · main_range_lo / main_range_hi：绝大多数数字的下界 / 上界（毫米）\n"
        f"   · max_value：所有数字中的最大值（毫米）\n"
        f"   · 注意：max_value 通常 ≥ main_range_hi，必须分开计算\n"
        f"第 3 步：查上表，把 main_range_lo / main_range_hi / max_value 各自归档"
        f"（档位：{levels_hint}），得到 L_lo / L_hi / L_max。\n"
        f"第 4 步：主导量级——\n"
        f"   · L_lo == L_hi → 写单档；L_lo ≠ L_hi → 必须写「{{L_lo 去末字}}到{{L_hi}}」跨档。\n"
        f"第 5 步：局地量级——\n"
        f"   · 若 L_max 严格高于 L_hi → 必须在 title 与 summary 都写「局地{{L_max}}」；\n"
        f"   · 若 L_max == L_hi → 不写「局地{{L_max}}」，可写「最大可达 max_value 毫米」。\n\n"
        f"━━━ JSON 输出（严格遵守，不要 markdown 代码块） ━━━\n"
        f"{{\n"
        f'  "district_red_numbers": [所有红色数字数组，含小数，从大到小排序],\n'
        f'  "max_value": 最大值（float，毫米；必须取自 district_red_numbers）,\n'
        f'  "main_range_lo": 主流下界（float，毫米）,\n'
        f'  "main_range_hi": 主流上界（float，毫米）,\n'
        f'  "title": "12~22 字一句话总结，无标点结尾，无引号",\n'
        f'  "summary": "90~150 字正文，2~3 句"\n'
        f"}}\n\n"
        f"━━━ title 写法（预报员口吻，直接以最严重情况定调） ━━━\n"
        f"- **title 必须直接以 L_max（最严重那档）定调**，绝对禁止使用「以…为主」「主要…」"
        f"「整体…」等需要『加局地修饰』的折中句式。\n"
        f"- 若 L_max 高于 L_hi（区内有局地强降水）：title 直接写「{district}区{{方位}}将出现"
        f"{{L_max}}」或「{district}区局地{{L_max}}」，**不要**写「{district}区以小到中雨为主，"
        f"南部局地大雨」这种二段式。\n"
        f"- 若 L_max == L_hi（全区一致）：title 写「{district}区将出现{{L_hi}}」或"
        f"「{district}区有{{L_hi}}」。\n"
        f"- title 句型参考：\n"
        f"{title_examples}\n\n"
        f"━━━ summary 写法（按预报员习惯） ━━━\n"
        f"- 第 1 句写北京全市：复述「预计{period_str}」+ 简述全市{kind_word}情况 + "
        f"区域差异（用「西部」「北部」「东南部」「平原」「山区」「城区」等方位 / 地形词）"
        f"+ 全市{amount_word}范围（lo~max_value 毫米）。\n"
        f"- 第 2 句写{district}区：用 1~2 句话**直接以最严重情况定调**——\n"
        f"   · 若 L_max 高于 L_hi（区内有局地强降水）：句式如"
        f"「{district}区将出现 L_hi 跨档表述，局地 L_max，最大可达 max_value 毫米」，"
        f"必须指明强降水大致方位（如「南部」「东部」「山前」）；\n"
        f"   · 若 L_max == L_hi（全区一致）：句式如"
        f"「{district}区{cum_word}多在 lo 至 hi 毫米，量级 L_hi」。\n\n"
        f"{extra_elements}"
        f"━━━ 红线禁忌 ━━━\n"
        f"1. 不描述{district}区方位（不写「位于北京××部」「地处××」等）。\n"
        f"2. 不出现{district}以外的具体区名；全市层面只用方位 / 地形词。\n"
        f"3. 不出现「格点 / 网格 / 数值预报 / 模式 / EC / ECMWF / GFS / 雷达 / 再分析」等技术字眼。\n"
        f"4. 不编造能见度、气温、风、湿度、气压等图上没有的要素。\n"
        f"5. 不用 markdown / emoji / 括号注释 / 换行。\n"
        f"6. 数字用阿拉伯数字 + 毫米，范围用「至」或「—」连接（如「6至12毫米」）。\n"
        f"7. title 与 summary 的量级表述必须一致；「局地{end_char}」前缀加更高档"
        f"（如「局地大{end_char}」）只能在 L_max 真正跨档时使用。\n"
        f"8. **严禁使用学究腔/AI 腔词**：禁止出现「主导量级」「主流量级」「主要降水量」"
        f"「主要在 X 至 Y 毫米」「值得注意的是」「请注意防范」「带来的不利影响」"
        f"「呈现 X 趋势」「整体降水分布」等冗余表达。预报员只说事实：「X 区有小到中雨，"
        f"局地大雨，最大 27 毫米」即可。\n"
        f"9. **严禁出现 max_value 以外的极值数字**：summary 中提到的所有毫米数必须 ≤ max_value；"
        f"严禁凭空写出 9.9 / 14.9 / 24.9 / 29.9 / 49.9 / 99.9 / 249.9 等量级阈值数字"
        f"（这些是 GB/T 28592 档位上限，不是图上读数）。"
    )
    return prompt


def _build_city_precipitation_prompt(
    *,
    period_str: str,
    which_std: str,
    level_table: str,
    phase: str,
) -> str:
    """北京市（全市）版本的提示词：不再局限于单一区的行政边界，而是通读整张
    《北京市降水预报图》，分析全市范围的降水/降雪分布过程，允许在正文中点出
    具体区名/方位来说明分布差异。JSON 输出字段与 _build_precipitation_prompt
    保持一致，便于复用 _parse_precip_json / _enforce_levels 等下游逻辑。
    """
    label = CITY_LEVEL_DISPLAY_NAME  # "北京市"

    if phase == "snow":
        kind_word = "降雪"
        amount_word = "降雪量"
        cum_word = "累计降雪量"
        end_char = "雪"
        levels_hint = "小雪/中雪/大雪/暴雪/大暴雪/特大暴雪"
        legend_intro = (
            "图例右下角为三组并排 colorbar；地图主色调为黑灰色，"
            "判定为『纯降雪』，红色数字代表降雪量（毫米，融化水当量）。"
        )
        title_examples = (
            f"【有局地强降水】「{label}南部将出现大雪」「{label}局地暴雪」\n"
            f"          【全市一致】「{label}将出现中雪」「{label}有小雪」"
            f"「{label}基本无明显降雪」"
        )
        extra_elements = (
            f"━━━ 降雪可选要素（酌情写 1 项，必须以降雪量为锚） ━━━\n"
            f"- 积雪：1毫米雪量约对应 0.5~1厘米积雪；可写「平原积雪不足 1 厘米」「山区 1~2 厘米」。\n"
            f"- 交通：可写「道面湿滑，局地积雪结冰，影响交通出行」。\n\n"
        )
    elif phase == "mixed":
        kind_word = "雨雪"
        amount_word = "降水量"
        cum_word = "累计降水量"
        end_char = "雪"
        levels_hint = "（按降雪标准）小雪/中雪/大雪/暴雪/大暴雪/特大暴雪"
        legend_intro = (
            "图例右下角为三组并排 colorbar；地图同时出现彩色与黑灰色填色，"
            "判定为『雨雪混合』，红色数字代表降水量（毫米）。"
        )
        title_examples = (
            f"「{label}有雨夹雪或小雪」「{label}将出现雨转雪，量级中雪」"
            f"「{label}南部有大雪」"
        )
        extra_elements = (
            f"━━━ 雨雪混合可选要素（酌情写 1~2 项） ━━━\n"
            f"- 相态（最重要）：例如「山区以雪为主，平原由雨或雨夹雪转雪」。\n"
            f"- 积雪：1毫米雪量约对应 0.5~1厘米积雪。\n"
            f"- 交通：可写「道面湿滑，局地积雪结冰」。\n\n"
        )
    else:
        phase = "rain"
        kind_word = "降雨"
        amount_word = "降水量"
        cum_word = "累计降水量"
        end_char = "雨"
        levels_hint = "小雨/中雨/大雨/暴雨/大暴雨/特大暴雨"
        legend_intro = (
            "图例右下角为单一彩色 colorbar（最大 250 毫米），"
            "判定为『纯降雨』，红色数字代表降雨量（毫米）。"
        )
        title_examples = (
            f"【有局地强降水】「{label}南部将出现大雨」「{label}局地暴雨」\n"
            f"          【全市一致】「{label}将出现中雨」「{label}有小雨」"
            f"「{label}基本无明显降水」"
        )
        extra_elements = ""

    prompt = (
        f"你是北京市气象台首席预报员，正在分析《北京市降水预报图》，"
        f"这次需要针对**北京全市范围**（而非单一区）做整体{kind_word}过程分析。\n"
        f"{legend_intro}\n"
        f"预报时段：{period_str}（{which_std}）。\n\n"
        f"━━━ 量级标准 ━━━\n"
        f"{level_table}\n\n"
        f"━━━ 工作流程（按顺序完成，禁止跳步） ━━━\n"
        f"第 1 步：通读整张地图，扫描北京全市范围内所有红色加粗数字（含小数），"
        f"逐个记录，覆盖城区、平原、山区等各处，不要只盯着某一小块区域。\n"
        f"第 2 步：从第 1 步的数字中识别——\n"
        f"   · main_range_lo / main_range_hi：绝大多数数字的下界 / 上界（毫米）\n"
        f"   · max_value：全市所有数字中的最大值（毫米）\n"
        f"   · 注意：max_value 通常 ≥ main_range_hi，必须分开计算\n"
        f"第 3 步：查上表，把 main_range_lo / main_range_hi / max_value 各自归档"
        f"（档位：{levels_hint}），得到 L_lo / L_hi / L_max。\n"
        f"第 4 步：主导量级——\n"
        f"   · L_lo == L_hi → 写单档；L_lo ≠ L_hi → 必须写「{{L_lo 去末字}}到{{L_hi}}」跨档。\n"
        f"第 5 步：局地量级 + 方位——\n"
        f"   · 若 L_max 严格高于 L_hi → 必须在 title 与 summary 都写出「局地{{L_max}}」，"
        f"并指明大致方位或区域（如『南部』『西部山区』『通州』等，此时**允许**点出具体区名）；\n"
        f"   · 若 L_max == L_hi → 不写「局地{{L_max}}」，可写「最大可达 max_value 毫米」。\n\n"
        f"━━━ JSON 输出（严格遵守，不要 markdown 代码块） ━━━\n"
        f"{{\n"
        f'  "district_red_numbers": [全市所有红色数字数组，含小数，从大到小排序],\n'
        f'  "max_value": 最大值（float，毫米；必须取自 district_red_numbers）,\n'
        f'  "main_range_lo": 主流下界（float，毫米）,\n'
        f'  "main_range_hi": 主流上界（float，毫米）,\n'
        f'  "title": "12~22 字一句话总结，无标点结尾，无引号",\n'
        f'  "summary": "90~150 字正文，2~4 句"\n'
        f"}}\n\n"
        f"━━━ title 写法（预报员口吻，直接以最严重情况定调） ━━━\n"
        f"- **title 必须直接以 L_max（最严重那档）定调**，绝对禁止使用「以…为主」「主要…」"
        f"「整体…」等需要『加局地修饰』的折中句式。\n"
        f"- 若 L_max 高于 L_hi（有局地强降水）：title 直接写「{label}{{方位/区名}}将出现"
        f"{{L_max}}」或「{label}局地{{L_max}}」。\n"
        f"- 若 L_max == L_hi（全市一致）：title 写「{label}将出现{{L_hi}}」或「{label}有{{L_hi}}」。\n"
        f"- title 句型参考：\n"
        f"{title_examples}\n\n"
        f"━━━ summary 写法（按预报员习惯，围绕全市展开） ━━━\n"
        f"- 第 1 句：复述「预计{period_str}」+ 概述全市{kind_word}过程 + "
        f"{amount_word}范围（lo~max_value 毫米）。\n"
        f"- 第 2 句起：点出{kind_word}偏强/偏弱的方位或具体区域（可直接点名区，"
        f"如『通州』『房山』『延庆』等，也可用『南部』『西部山区』等方位/地形词），"
        f"**直接以最严重情况定调**——\n"
        f"   · 若有局地强降水：句式如「{label}{cum_word}多在 lo 至 hi 毫米，"
        f"其中{{方位/区名}}偏强，局地可达 L_max，最大 max_value 毫米」；\n"
        f"   · 若全市较为一致：句式如「{label}{cum_word}多在 lo 至 hi 毫米，量级{{L_hi}}」。\n\n"
        f"{extra_elements}"
        f"━━━ 红线禁忌 ━━━\n"
        f"1. 这是全市分析，**允许**点出具体区名或方位来说明降水分布差异（与单区版本不同）。\n"
        f"2. 不出现「格点 / 网格 / 数值预报 / 模式 / EC / ECMWF / GFS / 雷达 / 再分析」等技术字眼。\n"
        f"3. 不编造能见度、气温、风、湿度、气压等图上没有的要素。\n"
        f"4. 不用 markdown / emoji / 括号注释 / 换行。\n"
        f"5. 数字用阿拉伯数字 + 毫米，范围用「至」或「—」连接（如「6至12毫米」）。\n"
        f"6. title 与 summary 的量级表述必须一致；「局地{end_char}」前缀加更高档"
        f"（如「局地大{end_char}」）只能在 L_max 真正跨档时使用。\n"
        f"7. **严禁使用学究腔/AI 腔词**：禁止出现「主导量级」「主流量级」「主要降水量」"
        f"「主要在 X 至 Y 毫米」「值得注意的是」「请注意防范」「带来的不利影响」"
        f"「呈现 X 趋势」「整体降水分布」等冗余表达。\n"
        f"8. **严禁出现 max_value 以外的极值数字**：summary 中提到的所有毫米数必须 ≤ max_value；"
        f"严禁凭空写出 9.9 / 14.9 / 24.9 / 29.9 / 49.9 / 99.9 / 249.9 等量级阈值数字"
        f"（这些是 GB/T 28592 档位上限，不是图上读数）。"
    )
    return prompt


def _clean_oneliner(s: str) -> str:
    s = (s or "").strip().strip("\"'，。；！？!?")
    s = re.sub(r"\s+", "", s)
    return s


def _clean_paragraph(s: str) -> str:
    s = (s or "").strip()
    # 去掉模型可能加的引号
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("“") and s.endswith("”")):
        s = s[1:-1]
    s = re.sub(r"[\r\n]+", "", s)
    return s.strip()


# 北京 16 个区名，用于在概况正文中过滤"目标区之外的具体区名"。
_BJ_DISTRICTS = (
    "东城", "西城", "朝阳", "海淀", "丰台", "石景山",
    "门头沟", "房山", "通州", "顺义", "昌平", "大兴",
    "怀柔", "平谷", "密云", "延庆",
)


# 「图上读不到的气象要素」关键词。本工具的输入只是一张降水量预报图，
# 红色数字只代表降水量(mm)，图上没有任何能见度、气温、风、湿度、气压的信息。
# 一旦模型在某个子句里写到这些要素，该子句就直接整段删除（兜底防御）。
# 注意：不要把"低""高""差"这种过于宽泛的词放进来，避免误伤"量级偏低""偏强"等正常表述。
_OFFLIMIT_PATTERNS = (
    re.compile(r"能见度"),
    re.compile(r"最高气温"),
    re.compile(r"最低气温"),
    re.compile(r"气温\s*(?:波动|较低|较高|偏低|偏高|下降|降低|升高|回升|骤降|骤升)"),
    re.compile(r"气温[^，。；]{0,4}\d"),  # "气温 X℃"、"气温在 X~Y℃"等
    re.compile(r"-?\d+\s*(?:℃|°C|度)"),  # 直接出现摄氏度数值
    re.compile(r"(?:偏[东南西北]|东北|东南|西北|西南)\s*风"),
    re.compile(r"风力\s*(?:可达|约|为|达)?\s*\d"),
    re.compile(r"\d+\s*(?:～|~|-|—|至)\s*\d+\s*级"),  # "3~4级"
    re.compile(r"阵风"),
    re.compile(r"相对湿度"),
    re.compile(r"湿度\s*(?:较大|较小|偏大|偏小|约|为)?\s*\d"),
    re.compile(r"气压\s*(?:较|偏|约|为)?\s*\d"),
)


def _has_offlimit_element(sentence: str) -> bool:
    """判定子句是否包含"图上读不到的要素"（能见度/气温/风/湿度/气压等）。
    用于子句级兜底过滤——若一条子句命中这些词，则直接删除整条子句。
    """
    if not sentence:
        return False
    for pat in _OFFLIMIT_PATTERNS:
        if pat.search(sentence):
            return True
    return False


def _filter_summary(text: str, district: str, is_city_level: bool = False) -> str:
    """对模型生成的 summary 做最后一道兜底清洗：
      1) 把"{district}区位于北京××部，"「{district}区地处××，」「北京××部的{district}区」
         等方位定语**就地删除**（保留同一子句中的数值/天气描述）。
      2) 删除整段提及目标区之外其它北京区名的子句（专业预报员只聚焦目标区）。
         is_city_level=True 时跳过这一步——全市分析本来就需要点出具体区名说明分布差异。
      3) 末尾若残留孤立的「，」「；」之类标点，自动收尾。

    切分粒度：按"，。；！？"分子句。
    """
    if not text:
        return text

    target = district.strip()

    # --- 1) 方位定语就地删除 ---
    # 1a) 「{target}区位于/地处/…+方位词…，区内…」
    #     这种结构里，前半句「{target}区位于…」是方位定语（需删），
    #     后半句以「区内」开头，删掉前半句后会丢失主语，所以把「区内」补成「{target}区内」。
    text = re.sub(
        rf"{re.escape(target)}\s*区\s*"
        r"(?:位于|地处|坐落于|处于|属于|位居)"
        r"[^，。；]{0,20}?"
        r"(?:东|南|西|北|中|东南|东北|西南|西北|城区|郊区|山区|平原|市区)"
        r"[^，。；]{0,5}"
        r"[，；]\s*区内",
        f"{target}区内",
        text,
    )
    # 1b) 没有紧接「区内」的版本：「{target}区位于…部，xxx 」→ 删除「位于…部，」，保留「{target}区」主语
    text = re.sub(
        rf"({re.escape(target)}\s*区)"
        r"\s*(?:位于|地处|坐落于|处于|属于|位居)"
        r"[^，。；]{0,20}?"
        r"(?:东|南|西|北|中|东南|东北|西南|西北|城区|郊区|山区|平原|市区)"
        r"[^，。；]{0,5}"
        r"[，；]\s*",
        r"\1",
        text,
    )
    # 1c) 倒装：「(北京)?××部的{target}区」→ 替换为「{target}区」（仅删方位定语）
    text = re.sub(
        rf"(?:北京|京)?[东南西北中]+(?:部|郊|区域)\s*的\s*{re.escape(target)}\s*区",
        f"{target}区",
        text,
    )

    # --- 1d) "格点 / 网格 / 模式 / 数值预报" 等 AI 腔 → 自然表述 ---
    text = _strip_ai_jargon(text, target)

    # --- 1e) 学究腔 / AI 公文腔 → 预报员自然口吻 ---
    text = _strip_bureaucratic_phrases(text)

    # --- 2) 子句级过滤：剔除提到其它区名的子句，
    #        以及涉及图上读不到的气象要素（能见度/气温/风/湿度/气压）的子句 ---
    sentences = re.split(r"(?<=[，。；！？])", text)
    kept: list[str] = []
    for s in sentences:
        if not s.strip():
            continue
        other_district_in_s = False
        if not is_city_level:
            for d in _BJ_DISTRICTS:
                if d == target:
                    continue
                if re.search(rf"{re.escape(d)}(?:区|地区|一带|等地|及|、|，|。|；)", s):
                    other_district_in_s = True
                    break
        if other_district_in_s:
            continue
        if _has_offlimit_element(s):
            continue
        kept.append(s)

    result = "".join(kept).strip()

    # --- 3) 收尾：清理孤立标点 / 空白 ---
    # 连续标点合并
    result = re.sub(r"[，；]{2,}", "，", result)
    # 句首若是标点则去掉
    result = re.sub(r"^[，。；！？\s]+", "", result)
    # 句末若是逗号/分号，换成句号
    result = re.sub(r"[，；]+\s*$", "", result)
    # 若末尾不是终止符，补句号
    if result and result[-1] not in "。！？.!?":
        result += "。"
    return result


def _enforce_levels(
    summary: str,
    title: str,
    label: str,
    levels: list[tuple[float, float | None, str]],
    phase: str = "rain",
    *,
    max_value: float | None = None,
    main_range_lo: float | None = None,
    main_range_hi: float | None = None,
) -> tuple[str, str]:
    """根据 GB/T 28592-2012 + 模型返回的客观锚点，校正 summary 与 title 中的量级表述。

    新版本接受三个客观锚点参数（来自模型 JSON 的 main_range_lo / main_range_hi / max_value）：
      - 优先使用这三个数值做跨档判定，比从 summary 正则抽出的范围更可靠；
      - 若 max_value 严格高于 main_range_hi 所在档，会**主动给 title 和 summary 补上**
        「局地{更高档}」，避免模型漏写；
      - 若模型只是写了「局地{更高档}」但 max_value 没到，会自动删除该表述。

    无任何锚点时，回退到旧逻辑（从 summary 正则抽范围）。
    """
    if not summary and not title:
        return summary, title

    end_char = "雪" if phase in ("snow", "mixed") else "雨"
    order = [name for _, _, name in levels]

    lo: float | None = main_range_lo
    hi: float | None = main_range_hi
    mx: float | None = max_value

    # 锚点缺失时，从 summary 抽 X 至 Y 毫米作为兜底
    if lo is None or hi is None:
        range_pat = re.compile(
            rf"{re.escape(label)}(?:[^，。；]{{0,12}}?)"
            r"(\d+(?:\.\d+)?)\s*(?:至|到|-|—|~|～)\s*(\d+(?:\.\d+)?)\s*毫米"
        )
        m = range_pat.search(summary or "")
        if m:
            lo = lo if lo is not None else float(m.group(1))
            hi = hi if hi is not None else float(m.group(2))

    if lo is None and hi is None:
        return summary, title

    # 用主流范围判定主导量级
    if lo is None:
        lo = hi
    if hi is None:
        hi = lo
    if mx is None or mx < hi:
        mx = hi

    correct_label, covered = _classify_range(lo, hi, levels)
    if not covered:
        return summary, title
    top_in_range = covered[-1]
    higher_levels = order[order.index(top_in_range) + 1 :]

    # max_value 真正落到的档
    max_level = _classify_level(mx, levels)
    needs_local = (
        max_level is not None
        and max_level in higher_levels
    )

    new_summary = summary or ""
    new_title = title or ""

    # 1) 修正 summary 中的主导量级短语
    quantifier_pat = re.compile(
        r"(?P<lead>，|；|。|\s)"
        r"(?P<phrase>(?:普遍|主要|大部|大都|多|整体|总体)?\s*"
        r"(?:为|是|以)?\s*"
        r"(?P<level>(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
        + end_char
        + r")"
        r"(?:为主)?)"
    )

    def fix_phrase(match):
        old = match.group("phrase")
        if match.group("level") == correct_label:
            return match.group(0)
        if old.startswith("以") and old.endswith("为主"):
            new = f"以{correct_label}为主"
        elif "为主" in old:
            new = f"以{correct_label}为主"
        elif old.startswith(("普遍为", "主要为", "大部为", "整体为", "总体为")):
            new = old[:3] + correct_label
        elif old.startswith(("普遍", "主要", "大部", "整体", "总体")):
            new = old[:2] + correct_label
        else:
            new = correct_label
        return match.group("lead") + new

    new_summary = quantifier_pat.sub(fix_phrase, new_summary, count=2)
    new_summary = re.sub(
        r"主导量级(?:为|是)\s*(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
        + end_char,
        f"主导量级为{correct_label}",
        new_summary,
    )
    new_summary = re.sub(
        r"将出现\s*(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
        + end_char,
        f"将出现{correct_label}",
        new_summary,
    )

    # 2) 对齐 title：第一处量级若不正确则替换。
    #    例外：如果 title 已经是预报员"定调式"（含「局地 X 雨」、「{方位}将出现 X 雨」、
    #    「{方位}有 X 雨」），那 title 里写的量级是基于 max_value 的，不应被
    #    correct_label（基于 main_range）覆盖，否则会把 "局地大雨" 改成 "局地小雨"。
    if new_title:
        title_level_pat = re.compile(
            r"(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
            + end_char
        )
        is_assertive_title = bool(
            re.search(r"局地(?:有|可达|达|为|出现)?\s*(?:小|中|大|暴|大暴|特大暴)", new_title)
        ) or any(d in new_title for d in _DIRECTION_WORDS)
        if not is_assertive_title:
            t_levels = title_level_pat.findall(new_title)
            if t_levels and t_levels[0] != correct_label:
                new_title = title_level_pat.sub(correct_label, new_title, count=1)

    # 3) 局地量级处理
    if needs_local and max_level:
        # 3a) 删掉所有「局地{比 max_level 更高的档}」（说过头了）
        for h in higher_levels:
            if h == max_level:
                continue
            new_title = re.sub(
                rf"[，,；;]?\s*局地(?:可达|达)?\s*{re.escape(h)}",
                "",
                new_title,
            )
            new_summary = re.sub(
                rf"[，;；]?\s*局地(?:可达|达)?\s*{re.escape(h)}",
                "",
                new_summary,
            )
        # 3b) 若 title 与 summary 都没体现「局地达到 max_level」，主动补上。
        #     "是否已体现"用语义检测，允许模型写「局地大雨」「局地有大雨」「局地可达大雨」
        #     「最大可达大雨」等多种表达，命中任意一种都视为已写过。
        local_pat = re.compile(rf"(?:局地|最大|可达|达到|达).{{0,4}}?{re.escape(max_level)}")
        local_phrase = f"局地{max_level}"
        if not local_pat.search(new_title):
            sep = "" if new_title.endswith(("，", "、")) else "，"
            new_title = (new_title.rstrip("。！？.,!?") + sep + local_phrase).strip("，、 ")
        mx_int = int(round(mx)) if abs(mx - round(mx)) < 0.05 else mx
        summary_mentions_max_level = bool(local_pat.search(new_summary)) or bool(
            re.search(rf"{re.escape(max_level)}.{{0,4}}?量级", new_summary)
        )
        summary_mentions_max_value = bool(
            re.search(rf"(?<!\d){re.escape(str(mx_int))}\s*毫米", new_summary)
        )
        if not (summary_mentions_max_level or summary_mentions_max_value):
            insert = f"，局地最大可达{mx_int}毫米"
            if new_summary:
                stripped = new_summary.rstrip()
                tail = ""
                if stripped and stripped[-1] in "。！？.!?":
                    tail = stripped[-1]
                    stripped = stripped[:-1]
                new_summary = stripped + insert + (tail or "。")

        # 3d) title 重写：把折中句式「X 区以小到中雨为主，南部局地大雨」
        #     直接改写为预报员定调句「X 区南部将出现大雨」/「X 区局地大雨」。
        new_title = _rewrite_title_assertive(
            new_title, label=label, max_level=max_level, end_char=end_char
        )
        # 3e) summary 折中句式正常化：把"小雨到局地大雨天气过程"这类拼接也
        #     正常化为定调式（与 title 保持一致风格）。
        new_summary = _normalize_compromise_in_summary(
            new_summary, max_level=max_level, end_char=end_char
        )
    else:
        # 3c) max_value 没真正跨档：删掉所有违规「局地{更高档}」
        for h in higher_levels:
            new_title = re.sub(
                rf"[，,；;]?\s*局地(?:可达|达)?\s*{re.escape(h)}",
                "",
                new_title,
            )
            new_summary = re.sub(
                rf"[，;；]?\s*局地(?:可达|达)?\s*{re.escape(h)}",
                "",
                new_summary,
            )

    # 收尾：清重复、清残留标点
    new_summary = _dedup_local_extreme(new_summary)
    new_summary = re.sub(r"[，；]{2,}", "，", new_summary).strip()
    new_summary = re.sub(r"^[，。；！？\s]+", "", new_summary)
    new_summary = re.sub(r"[，；]+\s*$", "。", new_summary)
    if new_summary and new_summary[-1] not in "。！？.!?":
        new_summary += "。"

    new_title = _dedup_title_local(new_title or "")
    new_title = new_title.strip().strip("，。；、 ")

    return new_summary, new_title


def _dedup_local_extreme(text: str) -> str:
    """summary 中如果出现多次描述"区内最大值"的等价表述，只保留第一次出现。
    业务场景：模型常常在同一段里用不同句式重复表达同一极值，例如
      「...降水量可达27毫米，达到大雨，最大降水量为27毫米。」
    去重前缀覆盖以下"等价句式"（均后跟相同数值 + 毫米）：
      - 局地最大可达 / 局地最大降水量可达 / 局地最大降水量为
      - 最大降水量为 / 最大降水量可达 / 最大降水量达到
      - 降水量可达 / 累计降水量可达 / 雨量可达 / 雪量可达
      - 区内最大 / 极值为 / 极值可达
    匹配相同毫米数时，保留第一次出现的，删除其余。
    """
    if not text:
        return text
    pat = re.compile(
        r"[，,；;]?\s*"
        r"(?:"
        r"局地最大(?:降水量|降雪量|降水|降雪|雪量|雨量)?(?:可达|达|为)?"
        r"|最大(?:降水量|降雪量|降水|降雪|雪量|雨量)(?:为|可达|达到|达)"
        r"|(?:累计)?(?:降水量|降雪量|降水|降雪|雪量|雨量)\s*(?:可达|达到|达|为)"
        r"|区内最大(?:为|可达|达)?"
        r"|极(?:大)?值(?:为|可达|达)?"
        r")"
        r"\s*(\d+(?:\.\d+)?)\s*毫米"
    )
    matches = list(pat.finditer(text))
    if len(matches) < 2:
        return text
    seen_values: set[str] = set()
    spans_to_drop: list[tuple[int, int]] = []
    for m in matches:
        val = m.group(1)
        if val in seen_values:
            spans_to_drop.append(m.span())
        else:
            seen_values.add(val)
    if not spans_to_drop:
        return text
    # 从后往前删，保持索引稳定
    for start, end in reversed(spans_to_drop):
        text = text[:start] + text[end:]
    return text


def _dedup_title_local(text: str) -> str:
    """title 内部去重：同一量级名的「局地X雨/雪」短语只保留第一次出现，避免
      「顺义区降水以小到中雨为主，局地有大雨，局地大雨」之类的重复。
    """
    if not text:
        return text
    # 抓所有形如 「局地(有|可达|达|为)?X雨/雪」 的片段
    pat = re.compile(
        r"(?:，|,|、)?\s*局地(?:有|可达|达|为|出现)?\s*"
        r"((?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?[雨雪])"
    )
    matches = list(pat.finditer(text))
    if len(matches) < 2:
        return text
    seen: set[str] = set()
    spans_to_drop: list[tuple[int, int]] = []
    for m in matches:
        level = m.group(1)
        if level in seen:
            spans_to_drop.append(m.span())
        else:
            seen.add(level)
    if not spans_to_drop:
        return text
    for start, end in reversed(spans_to_drop):
        text = text[:start] + text[end:]
    return text


# 标题里只可能出现的方位词集合（用于改写时保留方位信息）
_DIRECTION_WORDS = (
    "东南部", "西南部", "东北部", "西北部",
    "东部", "南部", "西部", "北部", "中部",
    "山前", "山区", "平原", "城区", "南郊", "北郊",
)


def _rewrite_title_assertive(
    text: str, *, label: str, max_level: str, end_char: str
) -> str:
    """把折中口吻的 title 重写为预报员定调式（以最严重情况开门见山）。

    典型转换：
      · 「顺义区降水以小到中雨为主，南部局地大雨」      → 「顺义区南部将出现大雨」
      · 「顺义区有小雨，局地大雨」                  → 「顺义区局地大雨」
      · 「顺义区将出现小到中雨，局地大雨」          → 「顺义区局地大雨」
      · 「顺义区将出现小雨到局地大雨天气过程」      → 「顺义区局地大雨」
      · 「顺义区将出现小到局地大雨」                → 「顺义区局地大雨」
      · 「顺义区将出现大雨」                       → 不动（已经定调）

    规则：
      1. 找出 title 中的方位词（南部 / 东部 / 山区 …）
      2. 检测是否包含折中句式特征
      3. 若是 → 重写为「label（已含区/市后缀）+ 方位（可选）+ 将出现 / 局地 + max_level」
    """
    if not text:
        return text
    target = label.strip()

    # 1) 抽取方位词（保留第一个出现的）
    direction = ""
    for d in _DIRECTION_WORDS:
        if d in text:
            direction = d
            break

    has_compromise = _is_compromise_phrase(text, end_char)
    if not has_compromise:
        return text

    # 2) 重写：以方位为主语 / 用「局地」开口
    if direction:
        new_title = f"{target}{direction}将出现{max_level}"
    else:
        new_title = f"{target}局地{max_level}"
    return new_title


def _is_compromise_phrase(text: str, end_char: str) -> bool:
    """判断一段文本（title 或 summary 片段）是否含有"折中口吻"特征。

    覆盖的折中句式：
      · 「以 X{雨/雪} 为主」「主要为 X{雨/雪}」
      · 「将出现 X{雨/雪}，... 局地 ...」二段式（弱档主调 + 局地修饰）
      · 「X{雨/雪} 到局地 Y{雨/雪}」「小到局地大雨」这种"到局地"拼接
      · 「小雨到局地大雨天气过程」这种带"天气过程"的拼接
    """
    if not text:
        return False
    level_re = r"(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
    ec = re.escape(end_char)
    patterns = (
        # 「以 X 雨为主」
        rf"以\s*{level_re}{ec}\s*为主",
        # 「主要为 X 雨」「整体为 X 雨」
        rf"(?:主要|整体|大部|总体)\s*(?:为|呈现)?\s*{level_re}{ec}",
        # 「将出现 X 雨, 局地」二段式
        rf"(?:将出现|出现|有)\s*(?:小|中)(?:到(?:小|中|大|暴))?{ec}\s*[,，、]?\s*(?:[东南西北中]+部)?\s*局地",
        # 「X 雨到局地 Y 雨」「小到局地大雨」这种拼接
        rf"{level_re}{ec}?\s*到\s*局地\s*{level_re}{ec}",
        # 「X 到局地 Y 雨」（X 可以没有末字）
        rf"{level_re}\s*到\s*局地\s*{level_re}{ec}",
    )
    for pat in patterns:
        if re.search(pat, text):
            return True
    return False


def _normalize_compromise_in_summary(text: str, *, max_level: str, end_char: str) -> str:
    """把 summary 里的拼接折中句式正常化为预报员定调表达。

    典型转换：
      · 「将出现小雨到局地大雨天气过程」→「将出现大雨，部分地区有小雨」
      · 「顺义区将出现小到局地大雨」    →「顺义区局地大雨」
      · 「小雨到局地大雨」              →「局地大雨」
    业务原则：保留最严重那档作为定调，去掉"过程""天气过程"等冗余收尾词。
    """
    if not text:
        return text
    ec = re.escape(end_char)
    level_re = r"(?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?"
    # 1) 「X{雨/雪}到局地Y{雨/雪}(天气过程)?」 → 「局地Y{雨/雪}」
    text = re.sub(
        rf"{level_re}{ec}?\s*到\s*局地\s*{level_re}{ec}\s*(?:天气过程|过程)?",
        f"局地{max_level}",
        text,
    )
    # 2) 「X(去末字)到局地Y{雨/雪}」 → 「局地Y{雨/雪}」
    text = re.sub(
        rf"{level_re}\s*到\s*局地\s*{level_re}{ec}\s*(?:天气过程|过程)?",
        f"局地{max_level}",
        text,
    )
    # 3) 「将出现局地X{雨/雪}天气过程」 → 「将出现局地X{雨/雪}」
    text = re.sub(rf"(局地\s*{level_re}{ec})\s*(?:天气过程|过程)", r"\1", text)
    return text


def _enforce_rain_levels(
    summary: str,
    title: str,
    district: str,
    levels: list[tuple[float, float | None, str]],
) -> tuple[str, str]:
    """旧名薄包装，保留向后兼容。"""
    return _enforce_levels(summary, title, district, levels, phase="rain")

def _strip_ai_jargon(text: str, target: str) -> str:
    """把模型可能生成的"格点/网格/数值预报数值"等技术腔表述，替换为预报员自然口吻。

    示例：
      - "{target}区内格点降水数值多在 6 至 12 毫米之间"
        → "{target}区降水量多在 6 至 12 毫米"
      - "区内格点降水数值多在 6~12 毫米"
        → "{target}区降水量多在 6~12 毫米"
      - "网格降水数值多在 …"  → "{target}区降水量多在 …"
      - "模式预报降水量为 …"   → "降水量为 …"
    保证只替换形容降水的字眼，不会动到「网格」等出现在地理或其他语境下的可能含义。
    """
    if not text:
        return text

    # 1) 带有目标区名的 AI 腔片段，整段替换为「{target}区降水量」
    #    支持："{target}区内格点降水数值"、"{target}区格点降水"、"{target}区网格降水量"等
    text = re.sub(
        rf"{re.escape(target)}\s*区(?:内)?\s*"
        r"(?:格点|网格|模式|数值预报|预报模式|预报)\s*"
        r"降(?:水|雨)\s*(?:数值|量值|预报值|值|量)?",
        f"{target}区降水量",
        text,
    )

    # 2) 不带目标区名的 AI 腔片段，直接降级为「降水量」（让上下文自然衔接，避免重复区名）
    text = re.sub(
        r"(?:区内\s*)?(?:格点|网格)\s*降(?:水|雨)\s*(?:数值|量值|预报值|值|量)?",
        "降水量",
        text,
    )
    text = re.sub(
        r"(?:模式|数值预报|预报模式|预报)\s*降(?:水|雨)\s*(?:数值|量值|预报值|值|量)?",
        "降水量",
        text,
    )

    # 3) 单独出现的"降水数值 / 降水预报值 / 降雨数值"等
    text = re.sub(r"降水\s*(?:数值|量值|预报值|值)", "降水量", text)
    text = re.sub(r"降雨\s*(?:数值|量值|预报值|值)", "降雨量", text)

    # 4) 修正常见语病：「{target}区降水量(...)在{target}区为...」 → 「{target}区降水量为...」
    text = re.sub(
        rf"({re.escape(target)}\s*区降水量)[^，。；]{{0,8}}?在\s*{re.escape(target)}\s*区(?:内)?\s*为",
        r"\1为",
        text,
    )

    # 5) 去重：避免出现「{target}区{target}区降水量」或紧邻两个「{target}区降水量」
    text = re.sub(
        rf"({re.escape(target)}\s*区)(?:\s*\1)+",
        r"\1",
        text,
    )
    text = re.sub(
        rf"({re.escape(target)}\s*区降水量)\s*\1",
        r"\1",
        text,
    )

    return text


# 学究腔 / AI 公文腔 → 自然预报员表达的替换规则。
# 业务原则：预报员只陈述事实（区 + 量级 + 数值），不用「主导量级」「值得注意的是」
# 「请注意防范」「整体呈现」等冗长措辞。这里只做"无损"替换：
#   · 能直接换成同义的简洁表达（如「主流量级为」→「为」）就换；
#   · 完全无用的修辞片段（如「值得注意的是，」「整体降水分布呈现」）直接删掉。
_BUREAUCRATIC_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 主导量级 / 主流量级 / 主要量级 → 直接说"量级"
    (re.compile(r"主导量级(?:为|是|呈)?\s*"), "量级"),
    (re.compile(r"主流量级(?:为|是|呈)?\s*"), "量级"),
    (re.compile(r"主要量级(?:为|是|呈)?\s*"), "量级"),
    # 「主要降水量在 X 至 Y」「主要在 X 至 Y」→「降水量 X 至 Y」
    (re.compile(r"主要(?:累积|累计)?(?:降水量|降雪量|降雨量)?在\s*"), "降水量"),
    (re.compile(r"(?<![\u4e00-\u9fa5])主要在\s*(?=\d)"), ""),
    # 「值得注意的是，」「需要指出的是，」「特别地，」整段删
    (re.compile(r"值得注意的是[，,]?\s*"), ""),
    (re.compile(r"(?:需要|须|应)(?:特别)?(?:注意|指出|关注)的是[，,]?\s*"), ""),
    (re.compile(r"特别地?[，,]?\s*"), ""),
    # 「整体降水分布呈现 X 趋势」「整体呈现 X」整段连同尾部"趋势"一并删
    (re.compile(r"整体(?:降水|降雪|雨势|雪势)?(?:分布)?(?:呈现|呈|为)[^，。；]{0,15}?趋势"), ""),
    (re.compile(r"整体(?:降水|降雪|雨势|雪势)?(?:分布)?(?:呈现|呈|为)\s*"), ""),
    # 「请注意防范 / 请关注 / 请做好防范 / 注意防范短时强降水...」整句通常出现在末尾，删掉
    (re.compile(r"[，,。；;]\s*请(?:注意|关注|做好)[^。]{0,40}(?:防范|准备|影响)[^。]{0,40}(?=[。！？]|$)"), ""),
    (re.compile(r"[，,。；;]\s*(?:可能)?带来[^。]{0,30}(?:不利)?影响[^。]{0,20}(?=[。！？]|$)"), ""),
    # 「达到大雨级别」「达到大雨量级」→「达到大雨」（保留语义，去掉冗余「级别 / 量级」）
    (re.compile(r"达到((?:小|中|大|暴|大暴|特大暴)(?:到(?:小|中|大|暴|大暴|特大暴))?[雨雪])(?:级别|量级|等级)"), r"达到\1"),
)


def _strip_bureaucratic_phrases(text: str) -> str:
    """删除模型常见的学究腔/AI 公文腔，让正文回到预报员的简洁陈述风格。"""
    if not text:
        return text
    for pat, repl in _BUREAUCRATIC_REPLACEMENTS:
        text = pat.sub(repl, text)
    # 清理替换后产生的标点残留
    # 1) 连续逗号 → 单逗号
    text = re.sub(r"[，,]\s*[，,]+", "，", text)
    # 2) 终止符后紧跟逗号 / 分号 → 仅保留终止符
    text = re.sub(r"([。！？])\s*[，,；;]+", r"\1", text)
    # 3) 逗号 + 终止符 → 仅保留终止符（"...，。" → "...。"）
    text = re.sub(r"[，,；;]+\s*([。！？])", r"\1", text)
    return text


def _fallback_title(label: str, phase: str = "rain") -> str:
    if phase == "snow":
        return f"{label}降雪预报"
    if phase == "mixed":
        return f"{label}雨雪预报"
    return f"{label}降水预报"


def _fallback_summary(label: str, phase: str = "rain") -> str:
    if phase == "snow":
        return f"根据最新降水预报图，{label}将出现降雪过程，请关注后续天气变化及交通出行影响。"
    if phase == "mixed":
        return (
            f"根据最新降水预报图，{label}将出现雨雪天气过程，相态较为复杂，"
            f"请关注相态变化及对交通出行的影响。"
        )
    return f"根据最新降水预报图，{label}将出现降水过程，请关注后续天气变化。"


# ---------------------------------------------------------------------
# 防范建议（仅用于「重要天气报告」）
# ---------------------------------------------------------------------
# 单位提供的标准防范建议模板，按相态 + 量级强弱分 4 套：
#   · 降雨—小雨或中雨（rain / weak）
#   · 降雨—大雨或暴雨（rain / strong）
#   · 降雪—小雪或中雪（snow / weak）
#   · 降雪—大雪或暴雪（snow / strong）
# mixed（雨夹雪）按业务约定走降雪那一套。
# 每套是一组「条目」字符串列表，渲染时自动加 1./2./3. 编号。

_ADVICE_FIXED_TAIL = "（区气象台将密切监视天气变化，及时更新决策服务材料）"

_ADVICE_RAIN_WEAK = [
    "降雨将导致路面湿滑、能见度下降，存在交通拥堵和安全事故风险。请注意减速慢行，保持安全车距。",
    "部分低洼路段可能出现积水，对交通、排水等城市运行造成影响。请勿将车辆停放在低洼处。",
]

_ADVICE_RAIN_STRONG = [
    "强降雨造成路面湿滑、能见度下降、低洼路段积水，对交通、排水、电力、通信等城市运行存在不利影响。请减少不必要的出行。",
    "短时雨强较大，城市易积水区域（下凹式立交桥、地铁站、涵洞等）易出现内涝，请提前绕行；山区易塌方、落石路段存在交通安全风险，请注意观察通行。",
    "山区和浅山区可能发生山洪、滑坡、崩塌、泥石流等次生灾害，请提前做好危险区域人员转移避险准备。强降雨可能引发中小河流洪水，请注意远离河道。",
    "请勿前往山区、河道、地质灾害隐患区域。雷雨和大风时，请勿在高大建筑物、广告牌、临时搭建物或大树下方停留。请勿涉水行车。",
]

_ADVICE_SNOW_WEAK = [
    "降雪造成道面湿滑、能见度下降，可能出现积雪及道路结冰，对城市交通、铁路运输、航班起降等存在不利影响。请注意出行安全，提前规划路线。",
    "降雪对电力、热力、燃气等能源供应及设施农业、园林树木等存在不利影响，请提前做好防范。",
    "雪后风力较明显，请注意加固临时搭建物、广告牌，加强户外高空作业安全防护。",
    "体感阴冷，请注意防寒保暖，谨防感冒。燃煤取暖用户请注意防范一氧化碳中毒，保持室内通风。",
]

_ADVICE_SNOW_STRONG = [
    "降雪将造成明显积雪及道路结冰，能见度极低，对城市交通影响较大。请减少不必要出行，行车时请开启雾灯、示廓灯，减速慢行。",
    "暴雪期间可能出现“白蒙”现象（能见度极低），请注意行车安全，及时开启雾灯、示廓灯，保持安全车距。",
    "请提前做好铲冰除雪准备，注意防范城际列车、航班延误及旅客滞留风险。",
    "强降雪易造成树枝折断，请注意及时除雪，做好古树、行道树木防护，及时清理倒树断枝。",
    "请注意对简易房、临时搭建物、农业大棚、围栏等进行加固，及时清理积雪，防范垮塌。",
    "降雪过后气温明显下降，请注意做好能源调度和供应保障。请注意防寒保暖，谨防感冒和心脑血管疾病。燃煤取暖用户请注意防范一氧化碳中毒。",
]


def _resolve_advice_items(phase: str, summary: str, title: str) -> list[str]:
    """根据相态与已识别量级，选出对应的一套标准防范建议条目。

    判档规则（与正文已判定的主导量级保持一致）：
      · 相态：mixed 归入降雪类；其余按 rain / snow。
      · 强弱：summary + title 文本中只要出现「大雨/暴雨/大暴雨/特大暴雨」
        或「大雪/暴雪/大暴雪/特大暴雪」字样 → 强档；否则 → 弱档。
        解析不到任何量级时，保守用弱档。
    """
    text = f"{title or ''} {summary or ''}"
    is_snow = phase in ("snow", "mixed")

    if is_snow:
        # 注意「大雪」「暴雪」要避免被「小到中雪」误判；这里直接找强档关键词
        strong = bool(re.search(r"(?:大雪|暴雪|大暴雪|特大暴雪)", text))
        return list(_ADVICE_SNOW_STRONG if strong else _ADVICE_SNOW_WEAK)

    strong = bool(re.search(r"(?:大雨|暴雨|大暴雨|特大暴雨)", text))
    return list(_ADVICE_RAIN_STRONG if strong else _ADVICE_RAIN_WEAK)


def _append_advice_to_docx(
    docx_path: str, *, phase: str, summary: str, title: str
) -> None:
    """在已生成的 docx 末尾追加「防范建议」段落、编号条目，以及固定结尾。
    复用文档正文段落的字体/字号，保证与正文风格一致。失败时静默跳过（不影响主流程）。
    """
    try:
        from docx import Document

        items = _resolve_advice_items(phase, summary, title)
        if not items:
            return

        doc = Document(docx_path)

        # 探测「正文」字体/字号：取全文**字数最多**的那个段落的首个 run。
        # 概况正文（{{ summary }} 渲染出来的那段）通常是全文最长的段落，
        # 这样能避开红色大标题、图注、表尾「制作/签发」等短行，避免追加内容偏大。
        base_font_name = None
        base_font_size = None
        best_len = 0
        for p in doc.paragraphs:
            text = (p.text or "").strip()
            if len(text) <= best_len:
                continue
            run = next((r for r in p.runs if (r.text or "").strip()), None)
            if run is None:
                continue
            best_len = len(text)
            base_font_size = run.font.size
            base_font_name = run.font.name
            # 段落级 / 样式级字体兜底：run 上没显式设置时，回落到段落样式字体
            if base_font_size is None and p.style is not None:
                try:
                    base_font_size = p.style.font.size
                except Exception:
                    pass
            if not base_font_name and p.style is not None:
                try:
                    base_font_name = p.style.font.name
                except Exception:
                    pass

        def _add_paragraph(text: str, *, bold: bool = False):
            para = doc.add_paragraph()
            run = para.add_run(text)
            run.bold = bold
            if base_font_size is not None:
                run.font.size = base_font_size
            if base_font_name:
                run.font.name = base_font_name
                # 中文字体需同时设置 eastAsia，否则中文可能回退到默认字体
                try:
                    from docx.oxml.ns import qn

                    run._element.rPr.rFonts.set(qn("w:eastAsia"), base_font_name)
                except Exception:
                    pass
            return para

        # 标题段
        _add_paragraph("防范建议", bold=True)
        # 编号条目
        for idx, item in enumerate(items, start=1):
            _add_paragraph(f"{idx}.{item}")
        # 与图样一致：另起一行写固定结尾
        _add_paragraph(_ADVICE_FIXED_TAIL)

        doc.save(docx_path)
    except Exception:
        # 防范建议追加属于增强项，任何异常都不应阻断报告生成
        pass
