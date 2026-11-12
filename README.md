# 网易云歌单无损下载器

把网易云音乐**公开歌单**里的歌批量下载到本地：优先 FLAC 无损，找不到无损时自动回退 320k MP3，按「歌名 - 歌手」命名，可直接写进 NAS 共享目录。

适合几百到上千首规模的歌单：多线程并发、断点续传、失败自动换源、逐首校验。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/yourname/netease-playlist-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/netease-playlist-downloader/actions/workflows/ci.yml)

> 仅用于个人备份学习，请支持正版音乐并遵守各平台服务条款。

## 特性

- **无损优先**：先按歌曲 ID 调用多个无损解析源，拿到 FLAC 再下载
- **多级回退**：无损源全部失败时回退网易云官方 320k MP3，保证歌单尽量完整
- **补漏/升级**：`retry` 命令用酷我搜索补回失败歌曲，并把 MP3 升级成 FLAC
- **断点续传**：`work/state.json` 记录每首结果，中断后重跑只处理未完成的
- **逐首校验**：FLAC 文件头、文件大小、ffprobe 时长三重校验，拒绝错歌/坏文件
- **按原名命名**：`歌名 - 歌手.flac`，非法字符自动清洗，重名自动加 `(2)`
- **目标目录直写**：本地目录或 SMB/NAS 的 UNC 路径（如 `//nas/Musics`），先写 `.part` 再原子改名
- **可审计**：生成 CSV 清单（状态/音质/来源/大小/时长）并校验目标文件

## 工作原理

```
歌单 ID ──► 网易云公开接口（歌单 + 歌曲元数据）
                 │
                 ▼
        按歌曲 ID 解析无损（多源，依次尝试）
                 │ 失败
                 ▼
        网易云官方 320k MP3
                 │ 仍失败
                 ▼
        标记 fail ──► npdl retry（酷我搜索 → FLAC）
                 │
                 ▼
        校验 → 命名 → 写入目标目录 → 记录 state
```

全程不需要登录，支持公开歌单（私有歌单需要分享 token，不在支持范围内）。

## 快速开始

### 环境要求

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/)（可选，提供 `ffprobe` 用于时长校验；没有也能跑，只是少一道校验）

### 安装

```bash
git clone https://github.com/yourname/netease-playlist-downloader.git
cd netease-playlist-downloader

python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
# 或者安装为命令：pip install -e .
```

### 使用

复制配置文件并填写歌单 ID、输出目录：

```bash
cp config.example.toml config.toml
```

```toml
playlist_id = "16610553"
dest = "//nas/Musics"   # 本地目录也可以，如 "D:/Music"
workers = 4
```

然后运行：

```bash
npdl run
```

也可以完全用命令行参数：

```bash
npdl run --playlist 16610553 --dest "D:/Music" --workers 4
```

先拿前 10 首试水：

```bash
npdl run --playlist 16610553 --dest "D:/Music" --limit 10
```

补漏（失败歌曲 + 把 MP3 升级为 FLAC）：

```bash
npdl retry
```

生成清单并校验：

```bash
npdl report
```

### 命令一览

| 命令 | 作用 |
| --- | --- |
| `npdl fetch --playlist ID` | 只抓取歌单和歌曲元数据，缓存到 `work/songs.json` |
| `npdl run` | 抓取（或复用缓存）并下载，自动跳过已完成 |
| `npdl retry` | 对失败/MP3 歌曲用酷我搜索补成 FLAC |
| `npdl report` | 生成 `work/manifest.csv` 并校验目标文件 |

通用参数：`--config`、`--work`、`--dest`、`--workers`、`--limit`、`-v`。

## 配置项

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `playlist_id` | 空 | 网易云公开歌单 ID |
| `dest` | `./output` | 输出目录，支持 UNC 共享路径 |
| `work_dir` | `./work` | 缓存与状态目录 |
| `workers` | `4` | 并发线程数 |
| `naming` | `{name} - {artists}` | 文件名模板，必须含 `{name}` |
| `limit` | 无 | 只处理前 N 首 |
| `ffprobe` | `ffprobe` | ffprobe 可执行文件路径 |
| `timeout` | `90` | 单次请求超时（秒） |
| `retries` | `2` | 上传重试次数 |

命令行参数优先级高于 `config.toml`。

## 输出

```
work/
├── playlist.json     # 歌单信息
├── songs.json        # 歌曲元数据缓存
├── state.json        # 每首的处理结果（断点续传依据）
└── manifest.csv      # 清单（report 生成）
```

文件名示例：

```
Deep Diving - The Snuts.flac
夜に駆ける - YOASOBI.flac
Back to 8 - Else (2).flac        # 同名自动编号
```

## 常见问题

**为什么有些歌是 MP3？**
这首歌在可用的音源里确实没有无损版本（常见于混音、独立上传、老歌）。`npdl retry` 会再尝试用酷我搜索升级。

**为什么有少量歌曲失败？**
通常是版权下架、需要 VIP、或只有加密格式。`retry` 后仍失败的会在清单里列出，建议用官方客户端或其他渠道补齐。

**会用到我的网易云账号吗？**
不会。项目只调用公开接口，不读取浏览器 Cookie，也不需要登录。

**支持私有歌单吗？**
不支持。私有歌单需要分享 token，请先把歌单设为公开，或自行导出 `songs.json`。

**下载速度慢？**
`--workers` 调到 4~6；再高可能触发第三方解析源限流。

## 开发

```bash
pip install -e ".[dev]"
ruff check src tests
python -m pytest
```

## 免责声明

本项目仅用于学习 Python 网络编程与个人音乐备份。请勿用于商业用途或大规模分发；下载内容请自行确认拥有合法访问权限，并遵守网易云音乐等平台的服务条款。因使用本项目产生的一切后果由使用者自行承担。

## 许可证

[MIT](LICENSE)
