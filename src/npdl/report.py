"""清单与校验：生成 CSV、统计音质、检查目标目录中的文件。"""

from __future__ import annotations

import csv
import os
from collections import Counter
from typing import Any

from .naming import build_name_map
from .state import StateStore


def build_rows(
    songs: list[dict], store: StateStore, naming: str = "{name} - {artists}"
) -> list[dict[str, Any]]:
    names = build_name_map(songs, naming)
    rows: list[dict[str, Any]] = []
    for index, song in enumerate(songs, 1):
        record = store.get(song["id"])
        status = record.get("status") or "未处理"
        ext = ".flac" if record.get("quality") == "flac" else (".mp3" if status == "mp3" else "")
        filename = f"{names.get(int(song['id']), '')}{ext}" if status in ("done", "mp3") else ""
        rows.append({
            "序号": index,
            "歌曲ID": song["id"],
            "歌曲名": song.get("name") or "",
            "歌手": song.get("artists") or "",
            "专辑": song.get("album") or "",
            "时长(秒)": round((song.get("duration_ms") or 0) / 1000, 1),
            "状态": status,
            "音质": record.get("quality") or "",
            "来源": record.get("source") or "",
            "文件名": filename,
            "大小(MB)": round((record.get("size") or 0) / 1048576, 2),
            "实际时长(秒)": record.get("duration") or "",
            "目标文件": record.get("file") or "",
            "备注": record.get("error") or record.get("note") or "",
            "_bytes": int(record.get("size") or 0),
        })
    return rows


def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fieldnames = [key for key in rows[0].keys() if not key.startswith("_")]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def verify_files(rows: list[dict[str, Any]]) -> list[tuple[str, str, bool | None]]:
    """返回 [(文件名, 问题, 是否存在)]。"""
    problems: list[tuple[str, str, bool | None]] = []
    for row in rows:
        if row["状态"] not in ("done", "mp3"):
            continue
        target = row["目标文件"]
        filename = row["文件名"]
        if not target:
            problems.append((filename, "未记录目标路径", None))
            continue
        if not os.path.exists(target):
            problems.append((filename, "目标文件不存在", False))
            continue
        actual = os.path.getsize(target)
        expected = int(row.get("_bytes") or 0)
        if expected and actual != expected:
            problems.append((filename, f"大小不符 {actual} != {expected}", True))
    return problems


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status = Counter(row["状态"] for row in rows)
    quality = Counter(row["音质"] for row in rows if row["音质"])
    total_gb = sum(row["大小(MB)"] for row in rows) / 1024
    return {
        "total": len(rows),
        "status": dict(status),
        "quality": dict(quality),
        "size_gb": round(total_gb, 2),
        "fails": [(row["歌曲名"], row["歌手"]) for row in rows if row["状态"] == "fail"],
        "mp3": [(row["歌曲名"], row["歌手"]) for row in rows if row["状态"] == "mp3"],
    }
