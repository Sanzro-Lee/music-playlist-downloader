"""断点续传状态：JSON 文件 + 线程安全 + 原子写。"""

from __future__ import annotations

import threading
from typing import Any

from .utils import atomic_write_json, read_json


class StateStore:
    """记录每首歌的处理结果，进程中断后可继续。"""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = read_json(path, {}) or {}

    def get(self, song_id: int | str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get(str(song_id), {}))

    def update(self, song_id: int | str, record: dict[str, Any]) -> None:
        with self._lock:
            self._data[str(song_id)] = record
            atomic_write_json(self.path, self._data)

    def items(self):
        with self._lock:
            return list(self._data.items())

    def values(self):
        with self._lock:
            return list(self._data.values())

    def finished_ids(self, states: tuple[str, ...] = ("done", "mp3")) -> set[int]:
        with self._lock:
            return {
                int(sid) for sid, rec in self._data.items()
                if rec.get("status") in states
            }

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._lock:
            for rec in self._data.values():
                status = rec.get("status") or "unknown"
                counts[status] = counts.get(status, 0) + 1
        return counts
