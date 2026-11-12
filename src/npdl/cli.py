"""命令行入口：npdl run / fetch / retry / report。"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__, report, runner
from .config import Config
from .state import StateStore
from .utils import silence_insecure_warnings

log = logging.getLogger("npdl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="npdl",
        description="网易云歌单无损下载器：多源回退、断点续传、按歌名命名。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")

    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, with_playlist: bool = True) -> None:
        p.add_argument("--config", help="TOML 配置文件路径（默认 ./config.toml）")
        p.add_argument("--work", help="工作目录，存放歌曲列表与断点状态")
        if with_playlist:
            p.add_argument("--playlist", help="网易云歌单 ID（公开歌单）")

    p_run = sub.add_parser("run", help="抓取歌单并下载")
    common(p_run)
    p_run.add_argument("--dest", help="输出目录（本地或 UNC 共享路径）")
    p_run.add_argument("--workers", type=int, help="并发线程数（默认 4）")
    p_run.add_argument("--limit", type=int, help="只处理前 N 首（调试用）")
    p_run.add_argument("--refresh", action="store_true", help="忽略缓存，重新拉取歌单")

    p_fetch = sub.add_parser("fetch", help="只抓取歌单与歌曲元数据")
    common(p_fetch)
    p_fetch.add_argument("--refresh", action="store_true", help="强制重新拉取")

    p_retry = sub.add_parser("retry", help="用酷我搜索补漏/把 MP3 升级为 FLAC")
    common(p_retry, with_playlist=False)
    p_retry.add_argument("--dest", help="输出目录")
    p_retry.add_argument("--no-upgrade-mp3", action="store_true", help="只补失败歌曲，不动 MP3")

    p_report = sub.add_parser("report", help="生成 CSV 清单并校验文件")
    common(p_report, with_playlist=False)
    p_report.add_argument("--dest", help="输出目录")
    p_report.add_argument("--out", help="CSV 输出路径（默认 <work>/manifest.csv）")

    return parser


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    silence_insecure_warnings()

    cfg = Config.load(getattr(args, "config", None))
    if getattr(args, "playlist", None):
        cfg.playlist_id = args.playlist
    if getattr(args, "dest", None):
        cfg.dest = args.dest
    if getattr(args, "work", None):
        cfg.work_dir = args.work
    if getattr(args, "workers", None):
        cfg.workers = args.workers
    if getattr(args, "limit", None) is not None:
        cfg.limit = args.limit

    try:
        if args.command == "fetch":
            cfg.validate()
            songs = runner.load_or_fetch_songs(cfg, refresh=args.refresh)
            log.info("已缓存 %d 首歌曲到 %s", len(songs), os.path.join(cfg.work_dir, "songs.json"))
            return 0

        if args.command == "run":
            cfg.validate()
            runner.run(cfg, refresh=args.refresh)
            return 0

        if args.command == "retry":
            _require_songs(cfg)
            runner.retry_failed(cfg, upgrade_mp3=not args.no_upgrade_mp3)
            return 0

        if args.command == "report":
            _require_songs(cfg)
            return _report(cfg, args.out)
    except ValueError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.warning("已中断")
        return 130
    return 1


def _require_songs(cfg: Config) -> None:
    if not os.path.exists(os.path.join(cfg.work_dir, "songs.json")):
        if not cfg.playlist_id:
            raise ValueError("找不到 songs.json，请先运行 npdl fetch --playlist <ID>")
        runner.load_or_fetch_songs(cfg)


def _report(cfg: Config, out: str | None) -> int:
    songs = runner.load_or_fetch_songs(cfg)
    songs = [song for song in songs if song.get("name")]
    store = StateStore(os.path.join(cfg.work_dir, "state.json"))
    rows = report.build_rows(songs, store, cfg.naming)
    csv_path = out or os.path.join(cfg.work_dir, "manifest.csv")
    report.write_csv(rows, csv_path)
    summary = report.summarize(rows)
    problems = report.verify_files(rows)

    print()
    print(f"清单：{csv_path}")
    print(f"总计 {summary['total']} 首："
          f"无损 {summary['quality'].get('flac', 0)} / "
          f"MP3 {summary['quality'].get('mp3-320', 0)} / "
          f"失败 {summary['status'].get('fail', 0)}，"
          f"合计 {summary['size_gb']} GB")
    print(f"文件校验：{'全部正常' if not problems else f'{len(problems)} 个问题'}")
    for name, issue, _ in problems[:20]:
        print(f"  ! {name}: {issue}")
    if summary["fails"]:
        print("未获取：")
        for name, artist in summary["fails"]:
            print(f"  - {name} / {artist}")
    if summary["mp3"]:
        print(f"仅 MP3（{len(summary['mp3'])} 首）：")
        for name, artist in summary["mp3"][:20]:
            print(f"  - {name} / {artist}")
        if len(summary["mp3"]) > 20:
            print(f"  ... 其余 {len(summary['mp3']) - 20} 首见 CSV")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
