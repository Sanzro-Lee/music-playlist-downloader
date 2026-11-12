"""单曲下载：多源回退 → 校验（文件头/大小/时长）→ 上传。"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from dataclasses import dataclass, field

from . import sources
from .config import Config
from .upload import upload_file
from .utils import ffprobe, human_size, retry, session

log = logging.getLogger(__name__)

FLAC_MAGIC = b"fLaC"
MIN_FLAC_BYTES = 1024 * 1024
MIN_MP3_BYTES = 512 * 1024
DURATION_TOLERANCE = 3.0


@dataclass
class Record:
    status: str
    quality: str = ""
    source: str = ""
    file: str = ""
    size: int = 0
    duration: float = 0.0
    error: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "status": self.status,
            "quality": self.quality,
            "source": self.source,
            "file": self.file,
            "size": self.size,
            "duration": round(self.duration, 1),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.error:
            data["error"] = self.error
        data.update(self.extra)
        return data


def download_url(url: str, path: str, expect_flac: bool, timeout: int = 90) -> tuple[bool, int, bytes]:
    """流式下载；expect_flac=True 时校验 fLaC 文件头。"""
    part = f"{path}.part"
    with session().get(url, stream=True, timeout=timeout, verify=False) as resp:
        resp.raise_for_status()
        expected = int(resp.headers.get("Content-Length") or 0)
        iterator = resp.iter_content(262144)
        first = next(iterator, b"")
        if expect_flac and first[:4] != FLAC_MAGIC:
            raise ValueError(f"不是 FLAC 文件（magic={first[:4]!r}）")
        written = 0
        with open(part, "wb") as fh:
            fh.write(first)
            written += len(first)
            for chunk in iterator:
                fh.write(chunk)
                written += len(chunk)
    if expected and written != expected:
        os.remove(part)
        raise OSError(f"下载不完整: {written}/{expected} 字节")
    os.replace(part, path)
    return True, written, first[:4]


def _remove(*paths: str) -> None:
    for path in paths:
        with contextlib.suppress(OSError):
            if os.path.exists(path):
                os.remove(path)


def process_song(cfg: Config, song: dict, name: str) -> dict:
    """处理一首歌，返回可写入 state 的字典。"""
    song_id = int(song["id"])
    expected = (song.get("duration_ms") or 0) / 1000.0
    tmp_base = os.path.join(cfg.work_dir, "tmp", str(song_id))
    os.makedirs(os.path.dirname(tmp_base), exist_ok=True)
    errors: list[str] = []

    # ---------- 1. 无损 ----------
    for source, url in sources.lossless_candidates(song_id):
        path = f"{tmp_base}.flac"
        try:
            _, size, _ = retry(
                lambda url=url, path=path: download_url(url, path, expect_flac=True, timeout=cfg.timeout),
                attempts=2, delay=1.0,
            )
            if size < MIN_FLAC_BYTES:
                raise ValueError(f"文件过小 {human_size(size)}")
            probe = ffprobe(path, cfg.ffprobe)
            if probe and expected and abs(probe.duration - expected) > DURATION_TOLERANCE:
                raise ValueError(f"时长不符 {probe.duration:.1f}s != {expected:.1f}s")
            final = upload_file(path, cfg.dest, f"{name}.flac")
            record = Record("done", "flac", source, final, size,
                            probe.duration if probe else 0.0)
            log.info("✓ %s [%s %s]", name, source, human_size(size))
            _remove(path)
            return record.to_dict()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")
            log.debug("✗ %s %s: %s", name, source, exc)
            _remove(path, f"{path}.part")

    # ---------- 2. 官方 320k 兜底 ----------
    url = sources.netease_official(song_id)
    if url:
        path = f"{tmp_base}.mp3"
        try:
            _, size, _ = retry(
                lambda url=url, path=path: download_url(url, path, expect_flac=False, timeout=cfg.timeout),
                attempts=2, delay=1.0,
            )
            if size < MIN_MP3_BYTES:
                raise ValueError(f"文件过小 {human_size(size)}")
            probe = ffprobe(path, cfg.ffprobe)
            if probe and expected and abs(probe.duration - expected) > DURATION_TOLERANCE:
                raise ValueError(f"时长不符 {probe.duration:.1f}s != {expected:.1f}s")
            final = upload_file(path, cfg.dest, f"{name}.mp3")
            record = Record("mp3", "mp3-320", "netease-official", final, size,
                            probe.duration if probe else 0.0,
                            error="; ".join(errors[-2:]) if errors else "")
            log.warning("△ %s 仅找到 320k MP3", name)
            _remove(path)
            return record.to_dict()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"netease-official: {exc}")
            _remove(path, f"{path}.part")

    log.error("✗ %s 全部音源失败", name)
    return Record("fail", error="; ".join(errors)).to_dict()
