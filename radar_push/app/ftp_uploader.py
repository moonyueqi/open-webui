"""把每次推送的结果（雷达图 PNG + 文案 TXT）上传到 FTP 目录。

设计要点：
- 与企业微信推送解耦：上传失败只记日志、绝不影响主流程（推送照常完成）。
- 每次上传都新建一条短连接（推送频率很低，无需维持长连接），用完即关，避免
  长连接被 FTP 服务器空闲断开后产生的各种诡异问题。
- 远程目录按 "/" 逐级 MKD，已存在则忽略，兼容服务器不允许递归建目录的情况。
"""

from __future__ import annotations

import ftplib
import io
import logging
from typing import Optional

from .config import FtpSettings

log = logging.getLogger(__name__)


class FtpUploader:
    def __init__(self, settings: FtpSettings):
        self.s = settings

    @property
    def enabled(self) -> bool:
        return bool(self.s.enabled and self.s.host)

    def _connect(self) -> ftplib.FTP:
        if self.s.tls:
            ftp: ftplib.FTP = ftplib.FTP_TLS()
        else:
            ftp = ftplib.FTP()
        ftp.encoding = self.s.encoding
        ftp.connect(self.s.host, self.s.port, timeout=self.s.timeout)
        ftp.login(self.s.user, self.s.password)
        if self.s.tls and isinstance(ftp, ftplib.FTP_TLS):
            ftp.prot_p()
        ftp.set_pasv(self.s.passive)
        return ftp

    @staticmethod
    def _ensure_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
        """逐级进入/创建远程目录，结束后当前工作目录即为目标目录。"""
        remote_dir = remote_dir.strip().strip("/")
        if not remote_dir:
            return
        for part in remote_dir.split("/"):
            if not part:
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                try:
                    ftp.mkd(part)
                except ftplib.error_perm as e:
                    # 可能并发已创建，或无权限；再尝试进入一次
                    log.debug("mkd %s 失败（可能已存在）: %s", part, e)
                ftp.cwd(part)

    def upload_bytes(self, data: bytes, remote_name: str) -> bool:
        """把内存中的字节流以 remote_name 存到配置的远程目录下。"""
        if not self.enabled:
            log.debug("FTP 上传未启用或未配置 host，跳过 %s", remote_name)
            return False
        if not data:
            log.warning("FTP 上传内容为空，跳过 %s", remote_name)
            return False
        try:
            ftp = self._connect()
        except Exception as e:
            log.error("FTP 连接失败 %s:%s - %s", self.s.host, self.s.port, e)
            return False
        try:
            self._ensure_dir(ftp, self.s.remote_dir)
            ftp.storbinary(f"STOR {remote_name}", io.BytesIO(data))
            log.info("FTP 上传成功: %s/%s (%d bytes)",
                     self.s.remote_dir.strip("/"), remote_name, len(data))
            return True
        except Exception as e:
            log.error("FTP 上传失败 %s: %s", remote_name, e)
            return False
        finally:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass

    def upload_text(self, text: str, remote_name: str) -> bool:
        return self.upload_bytes(text.encode("utf-8"), remote_name)

    def upload_alert(
        self,
        *,
        base_name: str,
        text: str,
        png_bytes: Optional[bytes] = None,
    ) -> bool:
        """上传一组推送结果：{base_name}.txt 与 {base_name}.png。

        返回是否全部成功（任一失败返回 False，但不会抛异常影响主流程）。
        """
        if not self.enabled:
            return False
        ok_txt = self.upload_text(text, f"{base_name}.txt")
        ok_png = True
        if png_bytes is not None:
            ok_png = self.upload_bytes(png_bytes, f"{base_name}.png")
        return ok_txt and ok_png
