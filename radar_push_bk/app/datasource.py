"""数据源抽象：SFTP（生产）+ 本地目录（开发测试）。相对路径统一用正斜杠分隔。"""

from __future__ import annotations

import io
import logging
import os
import stat
from typing import List, Optional, Protocol

log = logging.getLogger(__name__)


class DataSource(Protocol):
    kind: str

    def list_dir(self, relative_dir: str) -> List[str]: ...

    def exists(self, relative_path: str) -> bool: ...

    def open_binary(self, relative_path: str) -> bytes: ...

    def describe(self, relative_path: str) -> str: ...


class LocalDataSource:
    kind = "local"

    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        log.info("LocalDataSource base_dir=%s", self.base_dir)

    def _full(self, relative_path: str) -> str:
        return os.path.normpath(os.path.join(self.base_dir, relative_path))

    def list_dir(self, relative_dir: str) -> List[str]:
        full = self._full(relative_dir)
        if not os.path.isdir(full):
            return []
        return [
            name for name in os.listdir(full)
            if os.path.isfile(os.path.join(full, name))
        ]

    def exists(self, relative_path: str) -> bool:
        return os.path.isfile(self._full(relative_path))

    def open_binary(self, relative_path: str) -> bytes:
        with open(self._full(relative_path), "rb") as f:
            return f.read()

    def describe(self, relative_path: str) -> str:
        return "file:///" + self._full(relative_path).replace("\\", "/")


class SftpDataSource:
    """基于 paramiko 的 SFTP 数据源，连接失效时自动重连一次。"""

    kind = "sftp"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        base_dir: str,
        timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.base_dir = "/" + base_dir.strip("/")
        self.timeout = timeout
        self._client = None
        self._sftp = None
        log.info("SftpDataSource %s:%s base_dir=%s", host, port, self.base_dir)

    def _remote_path(self, relative_path: str) -> str:
        rel = relative_path.replace("\\", "/").lstrip("/")
        return f"{self.base_dir}/{rel}" if rel else self.base_dir

    def _ensure(self):
        if self._sftp is not None:
            try:
                self._sftp.stat(".")
                return
            except Exception:
                self._close_quietly()
        self._connect()

    def _connect(self):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            timeout=self.timeout,
            banner_timeout=self.timeout,
            auth_timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        self._client = client
        self._sftp = client.open_sftp()
        self._sftp.get_channel().settimeout(self.timeout)

    def _close_quietly(self):
        for obj in (self._sftp, self._client):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._sftp = None
        self._client = None

    def close(self):
        self._close_quietly()

    def _run(self, fn, *args):
        last_err: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                self._ensure()
                return fn(*args)
            except (FileNotFoundError, PermissionError):
                raise
            except Exception as e:
                last_err = e
                log.warning("SFTP op failed (attempt %d): %s", attempt, e)
                self._close_quietly()
        raise RuntimeError(f"SFTP operation failed: {last_err}")

    def list_dir(self, relative_dir: str) -> List[str]:
        path = self._remote_path(relative_dir)

        def _do():
            entries = self._sftp.listdir_attr(path)
            return [
                e.filename for e in entries
                if not stat.S_ISDIR(e.st_mode)
            ]

        try:
            return self._run(_do)
        except (RuntimeError, FileNotFoundError, PermissionError) as e:
            log.debug("list_dir(%s) -> [] (%s)", path, e)
            return []

    def exists(self, relative_path: str) -> bool:
        path = self._remote_path(relative_path)

        def _do():
            try:
                self._sftp.stat(path)
                return True
            except FileNotFoundError:
                return False

        try:
            return self._run(_do)
        except (RuntimeError, FileNotFoundError, PermissionError):
            return False

    def open_binary(self, relative_path: str) -> bytes:
        path = self._remote_path(relative_path)

        def _do():
            buf = io.BytesIO()
            with self._sftp.open(path, "rb") as rf:
                rf.prefetch()
                buf.write(rf.read())
            return buf.getvalue()

        return self._run(_do)

    def describe(self, relative_path: str) -> str:
        return f"sftp://{self.host}:{self.port}{self._remote_path(relative_path)}"


def build_datasource(settings) -> DataSource:
    if settings.data_source_kind == "sftp":
        s = settings.sftp
        if s is None:
            raise RuntimeError("DATA_SOURCE=sftp 但 SFTP 配置缺失")
        return SftpDataSource(
            host=s.host,
            port=s.port,
            user=s.user,
            password=s.password,
            base_dir=s.nc_base_dir,
        )
    return LocalDataSource(base_dir=settings.local_base_dir)
