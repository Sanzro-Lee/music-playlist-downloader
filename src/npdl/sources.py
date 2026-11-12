"""音源解析：优先无损，逐级回退。

策略
----
1. 网易云第三方无损解析（按歌曲 ID，命中率高）：
   - byfuns（hires）
   - kangqi（lossless）
   - byfuns（lossless）
2. 网易云官方匿名链接（通常 320k MP3，作为兜底）
3. 酷我搜索（按“歌名 歌手”检索，可把 MP3 升级为 FLAC）

所有函数只返回可下载的 URL，失败返回 None。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .utils import session

log = logging.getLogger(__name__)


def _with_retry(resolver: Callable[[], str | None], attempts: int = 2, delay: float = 1.0) -> str | None:
    """解析源偶发失败时重试一次，仍失败返回 None。"""
    for attempt in range(attempts):
        url = resolver()
        if url:
            return url
        if attempt < attempts - 1:
            time.sleep(delay)
    return None


@dataclass
class KuwoHit:
    rid: int
    name: str
    artist: str
    duration: int
    album: str = ""


def byfuns_netease(song_id: int | str, level: str = "hires") -> str | None:
    """byfuns 网易云解析，返回直链或 None。"""
    try:
        resp = session().get(
            f"https://api.byfuns.top/1/?id={song_id}&level={level}",
            timeout=15, verify=False,
        )
        url = (resp.text or "").strip()
        return url if url.startswith("http") else None
    except Exception as exc:  # noqa: BLE001
        log.debug("byfuns 失败 %s: %s", song_id, exc)
        return None


def kangqi_netease(song_id: int | str, level: str = "lossless") -> str | None:
    """kangqi 网易云解析。"""
    try:
        resp = session().post(
            "https://ncm.kangqiovo.com/Song_V1",
            data={"url": str(song_id), "level": level, "type": "json"},
            timeout=20, verify=False,
        )
        data = resp.json().get("data") or {}
        url = data.get("url") or ""
        return url if url.startswith("http") else None
    except Exception as exc:  # noqa: BLE001
        log.debug("kangqi 失败 %s: %s", song_id, exc)
        return None


def kuwo_search(keyword: str, limit: int = 10) -> list[KuwoHit]:
    """酷我搜索（移动端旧接口，返回 JSON）。"""
    params = {
        "vipver": "1", "client": "kt", "ft": "music", "cluster": "0",
        "strategy": "2012", "encoding": "utf8", "rformat": "json", "mobi": "1",
        "issubtitle": "1", "show_copyright_off": "1",
        "pn": "0", "rn": str(limit), "all": keyword,
    }
    try:
        resp = session().get(
            "http://www.kuwo.cn/search/searchMusicBykeyWord",
            params=params, timeout=15,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.debug("酷我搜索失败 %s: %s", keyword, exc)
        return []

    hits: list[KuwoHit] = []
    for item in data.get("abslist") or []:
        rid_raw = str(item.get("MUSICRID") or "")
        rid = rid_raw.replace("MUSIC_", "")
        if not rid.isdigit():
            continue
        try:
            duration = int(float(item.get("DURATION") or 0))
        except (TypeError, ValueError):
            duration = 0
        hits.append(KuwoHit(
            rid=int(rid),
            name=item.get("SONGNAME") or "",
            artist=item.get("ARTIST") or "",
            duration=duration,
            album=item.get("ALBUM") or "",
        ))
    return hits


def kuwo_lossless_url(rid: int | str) -> str | None:
    """酷我 FLAC 直链（第三方解析）。"""
    try:
        resp = session().get(
            f"https://musicapi.haitangw.net/music/kw.php?id={rid}&level=lossless&type=json",
            timeout=15, verify=False,
        )
        url = (resp.json().get("data") or {}).get("url") or ""
        return url if url.startswith("http") else None
    except Exception as exc:  # noqa: BLE001
        log.debug("酷我直链失败 %s: %s", rid, exc)
        return None


def netease_official(song_id: int | str) -> str | None:
    """网易云官方匿名链接，用于兜底（通常 320k MP3）。"""
    from .netease import official_mp3_url

    return official_mp3_url(song_id)


def lossless_candidates(song_id: int | str) -> Iterator[tuple[str, str]]:
    """按优先级惰性返回 (来源名, URL)，某个源失败才会请求下一个。"""
    chain: list[tuple[str, Callable[[], str | None]]] = [
        ("byfuns-hires", lambda: byfuns_netease(song_id, "hires")),
        ("kangqi-lossless", lambda: kangqi_netease(song_id, "lossless")),
        ("byfuns-lossless", lambda: byfuns_netease(song_id, "lossless")),
    ]
    for name, resolver in chain:
        url = _with_retry(resolver)
        if url:
            yield name, url
