"""通用工具：HTTP 会话、重试、原子写 JSON、ffprobe 探测。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

import requests

T = TypeVar("T")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)

_thread_local = threading.local()


def session() -> requests.Session:
    """每个线程复用同一个会话（连接池），避免跨线程共享。"""
    sess = getattr(_thread_local, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({"User-Agent": USER_AGENT})
        sess.verify = False
        _thread_local.session = sess
    return sess


def silence_insecure_warnings() -> None:
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass


def retry(func: Callable[[], T], attempts: int = 3, delay: float = 1.0,
          backoff: float = 2.0, exceptions: tuple = (Exception,)) -> T:
    """简单指数退避重试。最后一次异常会原样抛出。"""
    last: Exception | None = None
    wait = delay
    for i in range(attempts):
        try:
            return func()
        except exceptions as exc:  # noqa: PERF203
            last = exc
            if i == attempts - 1:
                break
            threading.Event().wait(wait)
            wait *= backoff
    assert last is not None
    raise last


def atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024 or unit == "GB":
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}GB"


@dataclass
class ProbeResult:
    duration: float
    format_name: str


def ffprobe(path: str, executable: str = "ffprobe") -> ProbeResult | None:
    """读取音频时长；未安装 ffprobe 时返回 None。"""
    if not shutil.which(executable) and not os.path.exists(executable):
        return None
    try:
        proc = subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration,format_name",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60,
        )
        info = json.loads(proc.stdout)["format"]
        return ProbeResult(float(info.get("duration") or 0), info.get("format_name") or "")
    except Exception:
        return None


_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(text: str, max_len: int = 140) -> str:
    """替换 Windows/macOS 不允许的文件名字符。"""
    cleaned = _ILLEGAL.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .")
    return cleaned or "untitled"


def iter_chunks(items: Iterable[T], size: int):
    chunk: list[T] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
