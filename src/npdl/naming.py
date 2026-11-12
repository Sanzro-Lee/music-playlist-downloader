"""文件命名：歌名 + 歌手，非法字符清洗，重名自动编号。"""

from __future__ import annotations

from collections.abc import Iterable

from .utils import sanitize


def display_artists(artists: str) -> str:
    """网易云用 " / " 分隔多歌手，文件名里换成逗号更易读。"""
    return ", ".join(part.strip() for part in (artists or "").split(" / ") if part.strip())


def format_name(song: dict, template: str = "{name} - {artists}") -> str:
    name = song.get("name") or f"song_{song.get('id')}"
    try:
        raw = template.format(
            name=name,
            artists=display_artists(song.get("artists") or ""),
            album=song.get("album") or "",
            id=song.get("id"),
        )
    except (KeyError, IndexError):
        raw = f"{name} - {display_artists(song.get('artists') or '')}"
    return sanitize(raw)


def build_name_map(songs: Iterable[dict], template: str = "{name} - {artists}") -> dict[int, str]:
    """返回 {song_id: 文件名(不含扩展名)}，同名时追加 (2)、(3)……"""
    used: dict[str, int] = {}
    names: dict[int, str] = {}
    for song in songs:
        base = format_name(song, template)
        key = base.casefold()
        if key in used:
            used[key] += 1
            base = f"{base} ({used[key]})"
        else:
            used[key] = 1
        names[int(song["id"])] = base
    return names
