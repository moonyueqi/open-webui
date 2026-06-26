"""企业微信群机器人 Webhook 推送：文本 + 图片。"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 企业微信图片上限 2MB


class WecomNotifier:
    def __init__(self, webhook_url: str, timeout: int = 15):
        self.webhook_url = webhook_url
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def _post(self, payload: dict) -> bool:
        if not self.enabled:
            log.warning("WECOM_WEBHOOK_URL 未配置，跳过推送（payload msgtype=%s）",
                        payload.get("msgtype"))
            return False
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            data = resp.json()
        except Exception as e:
            log.error("企业微信推送请求失败: %s", e)
            return False
        if data.get("errcode") != 0:
            log.error("企业微信推送返回错误: %s", data)
            return False
        return True

    def send_text(self, content: str) -> bool:
        return self._post({"msgtype": "text", "text": {"content": content}})

    def send_markdown(self, content: str) -> bool:
        return self._post({"msgtype": "markdown", "markdown": {"content": content}})

    def send_image(self, png_bytes: bytes) -> bool:
        if len(png_bytes) > _MAX_IMAGE_BYTES:
            log.error("图片 %d 字节超过企业微信 2MB 限制，跳过图片推送", len(png_bytes))
            return False
        b64 = base64.b64encode(png_bytes).decode("ascii")
        md5 = hashlib.md5(png_bytes).hexdigest()
        return self._post({"msgtype": "image", "image": {"base64": b64, "md5": md5}})

    def send_alert(self, text: str, png_bytes: Optional[bytes] = None) -> bool:
        ok_text = self.send_text(text)
        ok_img = True
        if png_bytes is not None:
            ok_img = self.send_image(png_bytes)
        return ok_text and ok_img
