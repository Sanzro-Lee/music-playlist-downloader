"""上传（或移动到目标目录）：本地目录、NAS 共享（UNC）均可。

先写 ``.part`` 再原子改名，失败不会留下半截文件；复制后校验大小。
"""

from __future__ import annotations

import logging
import os
import shutil
import time

log = logging.getLogger(__name__)


def upload_file(local_path: str, dest_dir: str, filename: str, retries: int = 3) -> str:
    """把 local_path 复制为 dest_dir/filename，返回最终路径。"""
    os.makedirs(dest_dir, exist_ok=True)
    final_path = os.path.join(dest_dir, filename)
    size = os.path.getsize(local_path)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        tmp = f"{final_path}.part"
        try:
            shutil.copyfile(local_path, tmp)
            if os.path.getsize(tmp) != size:
                raise OSError(f"上传后大小不一致: {os.path.getsize(tmp)} != {size}")
            os.replace(tmp, final_path)
            return final_path
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("上传失败（第 %d/%d 次）%s: %s", attempt, retries, filename, exc)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"上传失败: {filename}: {last_error}")
