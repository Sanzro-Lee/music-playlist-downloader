"""网易云音乐公开接口：歌单、歌曲元数据、官方播放链接。

只使用公开的 web 接口，不需要登录；仅支持公开歌单。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from .utils import iter_chunks, retry, session

log = logging.getLogger(__name__)

BASE = "https://music.163.com"
REFERER = {"Referer": "https://music.163.com/"}


def fetch_playlist(playlist_id: str | int) -> dict[str, Any]:
    """返回 {name, track_count, ids}。"""
    url = f"{BASE}/api/v6/playlist/detail?id={playlist_id}&n=1000&s=0"

    def do() -> dict[str, Any]:
        resp = session().get(url, headers=REFERER, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200 or "playlist" not in data:
            raise RuntimeError(f"歌单接口返回异常: {str(data)[:200]}")
        return data["playlist"]

    playlist = retry(do, attempts=3)
    ids = [int(item["id"]) for item in playlist.get("trackIds") or []]
    return {
        "name": playlist.get("name") or "",
        "track_count": int(playlist.get("trackCount") or len(ids)),
        "ids": ids,
        "tracks": playlist.get("tracks") or [],
    }


def fetch_songs(ids: Iterable[int], chunk_size: int = 200) -> list[dict[str, Any]]:
    """批量拉取歌曲元数据，返回按 ids 顺序排列的歌曲列表。"""
    ids = list(ids)
    found: dict[int, dict[str, Any]] = {}

    for chunk in iter_chunks(ids, chunk_size):
        payload = quote(json.dumps(chunk))

        def do(payload: str = payload) -> list[dict[str, Any]]:
            resp = session().get(f"{BASE}/api/song/detail?ids={payload}", headers=REFERER, timeout=30)
            resp.raise_for_status()
            return resp.json().get("songs") or []

        songs = retry(do, attempts=3)
        for song in songs:
            found[int(song["id"])] = _normalize(song)

    result = []
    missing = 0
    for sid in ids:
        if sid in found:
            result.append(found[sid])
        else:
            missing += 1
            result.append({"id": sid, "name": None, "missing": True})
    if missing:
        log.warning("有 %d 首歌无法获取元数据（可能已下架）", missing)
    return result


def official_mp3_url(song_id: int | str) -> str | None:
    """匿名可用的最高音质链接（通常为 320k MP3）。"""
    for level in ("exhigh", "higher", "standard"):
        try:
            resp = session().get(
                f"{BASE}/api/song/enhance/player/url/v1"
                f"?ids=[{song_id}]&level={level}&encodeType=mp3",
                headers=REFERER, timeout=15,
            )
            data = resp.json().get("data") or []
            if data and data[0].get("url"):
                return data[0]["url"]
        except Exception:  # noqa: BLE001
            continue
    return None


def _normalize(song: dict[str, Any]) -> dict[str, Any]:
    artists = song.get("ar") or song.get("artists") or []
    album = (song.get("al") or song.get("album") or {}).get("name") or ""
    return {
        "id": int(song.get("id")),
        "name": song.get("name") or "",
        "artists": " / ".join(a.get("name", "") for a in artists if a.get("name")),
        "album": album,
        "duration_ms": int(song.get("dt") or song.get("duration") or 0),
        "fee": song.get("fee"),
        "missing": False,
    }
