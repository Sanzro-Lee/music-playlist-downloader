"""配置：默认值 + 可选 TOML 配置文件 + 命令行覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        _toml = None


@dataclass
class Config:
    """运行配置。字段名与 config.toml 中的键一一对应。"""

    playlist_id: str = ""
    dest: str = "./output"
    work_dir: str = "./work"
    workers: int = 4
    naming: str = "{name} - {artists}"
    limit: int | None = None
    ffprobe: str = "ffprobe"
    timeout: int = 90
    retries: int = 2

    @classmethod
    def load(cls, path: str | None = None) -> Config:
        cfg = cls()
        if path:
            if not os.path.exists(path):
                raise ValueError(f"配置文件不存在: {path}")
            cfg.apply(_read_toml(path))
            return cfg
        for candidate in ("config.toml", os.path.join("config", "config.toml")):
            if os.path.exists(candidate):
                cfg.apply(_read_toml(candidate))
                break
        return cfg

    def apply(self, values: dict[str, Any]) -> None:
        known = {f.name for f in fields(self)}
        for key, value in values.items():
            if key in known and value is not None:
                setattr(self, key, value)

    def validate(self) -> None:
        if not self.playlist_id:
            raise ValueError("缺少歌单 ID：请使用 --playlist 或 config.toml 中的 playlist_id")
        if self.workers < 1:
            raise ValueError("workers 必须 >= 1")
        if "{name}" not in self.naming:
            raise ValueError("naming 模板必须包含 {name}")


def _read_toml(path: str) -> dict[str, Any]:
    if _toml is None:
        raise RuntimeError("当前 Python 无法解析 TOML，请升级到 3.11+ 或安装 tomli")
    # utf-8-sig：兼容 Windows 记事本 / VS Code 可能写入的 BOM
    with open(path, encoding="utf-8-sig") as fh:
        return _toml.loads(fh.read())
