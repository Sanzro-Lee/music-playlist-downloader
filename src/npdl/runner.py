"""流程编排：抓取歌单 → 并发下载 → 酷我补漏 → 汇总。"""

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

from . import sources
from .config import Config
from .download import process_song
from .naming import build_name_map
from .netease import fetch_playlist, fetch_songs
from .state import StateStore
from .upload import upload_file
from .utils import ffprobe, human_size, read_json

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 歌单准备
# --------------------------------------------------------------------------- #
def load_or_fetch_songs(cfg: Config, refresh: bool = False) -> list[dict]:
    """读取 work_dir/songs.json；不存在或 refresh 时从网易云抓取。"""
    songs_path = os.path.join(cfg.work_dir, "songs.json")
    if os.path.exists(songs_path) and not refresh:
        songs = read_json(songs_path)
        log.info("复用已缓存的歌曲列表：%s（%d 首）", songs_path, len(songs))
        return songs

    log.info("拉取歌单 %s ...", cfg.playlist_id)
    playlist = fetch_playlist(cfg.playlist_id)
    log.info("歌单《%s》：%d 首（可获取 %d 个 trackId）",
             playlist["name"], playlist["track_count"], len(playlist["ids"]))
    songs = fetch_songs(playlist["ids"])
    os.makedirs(cfg.work_dir, exist_ok=True)
    from .utils import atomic_write_json

    atomic_write_json(songs_path, songs)
    atomic_write_json(os.path.join(cfg.work_dir, "playlist.json"), {
        "id": str(cfg.playlist_id),
        "name": playlist["name"],
        "track_count": playlist["track_count"],
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return songs


# --------------------------------------------------------------------------- #
# 主下载流程
# --------------------------------------------------------------------------- #
def run(cfg: Config, refresh: bool = False) -> dict[str, int]:
    cfg.validate()
    os.makedirs(cfg.work_dir, exist_ok=True)
    os.makedirs(os.path.join(cfg.work_dir, "tmp"), exist_ok=True)
    os.makedirs(cfg.dest, exist_ok=True)

    songs = load_or_fetch_songs(cfg, refresh=refresh)
    songs = [s for s in songs if s.get("name")]
    names = build_name_map(songs, cfg.naming)
    store = StateStore(os.path.join(cfg.work_dir, "state.json"))

    finished = store.finished_ids()
    todo = [s for s in songs if int(s["id"]) not in finished]
    if cfg.limit:
        todo = todo[: cfg.limit]

    log.info("共 %d 首，已完成 %d，本次处理 %d 首（%d 线程）",
             len(songs), len(finished), len(todo), cfg.workers)
    if not todo:
        return store.summary()

    started = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {pool.submit(process_song, cfg, song, names[int(song["id"])]): song for song in todo}
        try:
            for future in as_completed(futures):
                song = futures[future]
                try:
                    record = future.result()
                except Exception as exc:  # noqa: BLE001
                    record = {"status": "fail", "error": f"线程异常: {exc}"}
                record["name"] = names[int(song["id"])]
                store.update(song["id"], record)
                done += 1

                elapsed = time.time() - started
                rate = done / elapsed * 60 if elapsed else 0
                remaining = len(todo) - done
                eta = remaining / rate if rate else 0
                if done % 10 == 0 or record["status"] != "done":
                    log.info("[%d/%d] %-4s %-8s %s | %.1f 首/分，预计剩余 %.0f 分钟",
                             done, len(todo), record["status"], record.get("quality", ""),
                             names[int(song["id"])][:36], rate, eta)
        except KeyboardInterrupt:
            log.warning("收到中断，正在等待进行中的任务结束 ...")
            for future in futures:
                future.cancel()

    summary = store.summary()
    log.info("完成：%s（耗时 %.1f 分钟）", summary, (time.time() - started) / 60)
    if summary.get("mp3") or summary.get("fail"):
        log.info("提示：运行 npdl retry 可尝试把 MP3 / 失败项补成 FLAC")
    return summary


# --------------------------------------------------------------------------- #
# 酷我补漏 / 升级
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"\s*[\(\[（【].*?[\)\]）】]\s*", " ", text)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _similar(a: str, b: str) -> float:
    a, b = _normalize(a), _normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 4 and (a in b or b in a):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def retry_failed(cfg: Config, upgrade_mp3: bool = True) -> dict[str, int]:
    """对失败歌曲（可选：MP3 歌曲）用酷我搜索补成 FLAC。"""
    if not os.path.exists(os.path.join(cfg.work_dir, "songs.json")) and not cfg.playlist_id:
        raise ValueError("找不到 songs.json，请先运行 npdl fetch --playlist <ID>")
    songs = load_or_fetch_songs(cfg)
    names = build_name_map(songs, cfg.naming)
    store = StateStore(os.path.join(cfg.work_dir, "state.json"))

    targets = []
    for song in songs:
        record = store.get(song["id"])
        status = record.get("status")
        if status == "fail" or (upgrade_mp3 and status == "mp3"):
            targets.append(song)
    if not targets:
        log.info("没有需要补漏的歌曲")
        return store.summary()

    log.info("补漏目标：%d 首（失败 %d，MP3 %d）", len(targets),
             sum(1 for s in targets if store.get(s["id"]).get("status") == "fail"),
             sum(1 for s in targets if store.get(s["id"]).get("status") == "mp3"))

    fixed = 0
    for index, song in enumerate(targets, 1):
        name = names[int(song["id"])]
        record = store.get(song["id"])
        expected = (song.get("duration_ms") or 0) / 1000.0
        keyword = f"{song['name']} {str(song.get('artists', '')).replace(' / ', ' ')}"
        log.info("[%d/%d] 搜索 %s", index, len(targets), name[:40])
        try:
            if _retry_song(cfg, store, song, name, record, expected, keyword):
                fixed += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("补漏异常 %s: %s", name, exc)

    summary = store.summary()
    log.info("补漏完成：新增/升级 %d 首，当前 %s", fixed, summary)
    return summary


def _retry_song(cfg: Config, store: StateStore, song: dict, name: str, record: dict,
                expected: float, keyword: str) -> bool:
    from .download import download_url

    hits = sources.kuwo_search(keyword, limit=10)
    scored: list[tuple[float, sources.KuwoHit]] = []
    for hit in hits:
        name_score = _similar(song["name"], hit.name)
        artist_score = _similar(song.get("artists", ""), hit.artist)
        if name_score < 0.75 or artist_score < 0.45:
            continue
        if expected and hit.duration and abs(hit.duration - expected) > 8:
            continue
        scored.append((name_score * 2 + artist_score, hit))
    scored.sort(key=lambda item: -item[0])

    for _, hit in scored[:3]:
        url = sources.kuwo_lossless_url(hit.rid)
        if not url:
            continue
        tmp = os.path.join(cfg.work_dir, "tmp", f"{song['id']}.flac")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        try:
            _, size, magic = download_url(url, tmp, expect_flac=True, timeout=cfg.timeout)
        except Exception as exc:  # noqa: BLE001
            log.debug("酷我下载失败 %s: %s", name, exc)
            for path in (tmp, f"{tmp}.part"):
                if os.path.exists(path):
                    os.remove(path)
            continue

        probe = ffprobe(tmp, cfg.ffprobe)
        if probe and expected and abs(probe.duration - expected) > 8:
            log.info("跳过（时长不符）%s", name)
            os.remove(tmp)
            continue
        final = upload_file(tmp, cfg.dest, f"{name}.flac")
        os.remove(tmp)
        old = record.get("file")
        if record.get("status") == "mp3" and old and old.lower().endswith(".mp3") and os.path.exists(old):
            try:
                os.remove(old)
            except OSError:
                pass
        store_record = {
            "status": "done", "quality": "flac", "source": "kuwo-search",
            "file": final, "size": size, "duration": round(probe.duration, 1) if probe else 0,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "name": name,
        }
        store.update(song["id"], store_record)
        log.info("✓ 升级为 FLAC：%s（%s）", name, human_size(size))
        return True
    return False
