"""数据源抽象：本地文件 + FTP，业务层共用同一接口。"""

from __future__ import annotations

import io
import os
import logging
from ftplib import FTP, error_perm
from typing import Protocol


log = logging.getLogger(__name__)


class DataSource(Protocol):
    """数据源协议。所有路径都是相对于 base_dir 的相对路径，使用正斜杠分隔。"""

    kind: str

    def exists(self, relative_path: str) -> bool: ...

    def open_binary(self, relative_path: str) -> io.BytesIO: ...

    def describe(self, relative_path: str) -> str: ...


class LocalDataSource:
    kind = "local"

    def __init__(self, base_dir: str):
        # 规范化（支持相对路径），但不强制存在 - 启动时不报错，第一次请求时再报
        self.base_dir = os.path.abspath(base_dir)
        log.info("LocalDataSource base_dir=%s", self.base_dir)

    def _full(self, relative_path: str) -> str:
        return os.path.normpath(os.path.join(self.base_dir, relative_path))

    def exists(self, relative_path: str) -> bool:
        return os.path.isfile(self._full(relative_path))

    def open_binary(self, relative_path: str) -> io.BytesIO:
        path = self._full(relative_path)
        with open(path, "rb") as f:
            return io.BytesIO(f.read())

    def describe(self, relative_path: str) -> str:
        return "file:///" + self._full(relative_path).replace("\\", "/")


class FtpDataSource:
    kind = "ftp"

    def __init__(self, host: str, port: int, user: str, password: str, base_dir: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        # 统一去掉首尾斜杠，存储路径时再拼
        self.base_dir = "/" + base_dir.strip("/")
        log.info("FtpDataSource %s:%s base_dir=%s", host, port, self.base_dir)

    def _connect(self) -> FTP:
        ftp = FTP()
        ftp.connect(self.host, self.port, timeout=30)
        ftp.login(self.user, self.password)
        ftp.set_pasv(True)
        return ftp

    def _remote_path(self, relative_path: str) -> str:
        rel = relative_path.replace("\\", "/").lstrip("/")
        return f"{self.base_dir}/{rel}"

    def exists(self, relative_path: str) -> bool:
        path = self._remote_path(relative_path)
        try:
            with self._connect() as ftp:
                ftp.voidcmd("TYPE I")
                ftp.size(path)
            return True
        except (error_perm, OSError) as e:
            log.debug("FTP exists(%s) -> False (%s)", path, e)
            return False
        except Exception as e:
            log.warning("FTP exists(%s) unexpected error: %s", path, e)
            return False

    def open_binary(self, relative_path: str) -> io.BytesIO:
        path = self._remote_path(relative_path)
        buf = io.BytesIO()
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                with self._connect() as ftp:
                    ftp.retrbinary(f"RETR {path}", buf.write)
                buf.seek(0)
                return buf
            except Exception as e:
                last_err = e
                log.warning("FTP RETR %s failed (attempt %d): %s", path, attempt, e)
                buf = io.BytesIO()
        raise RuntimeError(f"FTP RETR failed for {path}: {last_err}")

    def describe(self, relative_path: str) -> str:
        return f"ftp://{self.host}:{self.port}{self._remote_path(relative_path)}"
