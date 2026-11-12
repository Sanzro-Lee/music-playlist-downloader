# Netease Playlist Downloader

Download every track of a **public NetEase Cloud Music playlist**: lossless FLAC first, 320 kbps MP3 as a fallback, named `Song - Artist`, ready for a NAS share.

Built for playlists with hundreds to thousands of tracks: concurrent downloads, resumable state, automatic source fallback, per-file verification.

> For personal backup and learning only. Please support the artists and comply with platform terms.

## Features

- Lossless first: resolves FLAC per track from multiple providers before downloading
- Graceful fallback: official 320 kbps MP3 when no lossless source is available
- Gap filling: `retry` searches Kuwo and upgrades MP3s to FLAC
- Resumable: `work/state.json` records every result, reruns skip finished tracks
- Verified: FLAC magic bytes, file size, and ffprobe duration checks
- Clean naming: `Song - Artist.flac`, illegal characters sanitized, duplicates numbered
- Direct-to-target: local folder or SMB/UNC path, written via `.part` + atomic rename
- Auditable: CSV manifest with status, quality, source, size and duration

## Requirements

- Python 3.10+
- ffmpeg/ffprobe (optional, used for duration verification)

## Install

```bash
git clone https://github.com/yourname/netease-playlist-downloader.git
cd netease-playlist-downloader
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

```bash
cp config.example.toml config.toml   # set playlist_id and dest
npdl run

# or everything from the command line
npdl run --playlist 3778678 --dest "D:/Music" --workers 4

# fill gaps / upgrade MP3s to FLAC
npdl retry

# write manifest.csv and verify files
npdl report
```

| Command | Description |
| --- | --- |
| `npdl fetch --playlist ID` | Fetch and cache playlist metadata only |
| `npdl run` | Download everything (resumes automatically) |
| `npdl retry` | Retry failed tracks and upgrade MP3s via Kuwo |
| `npdl report` | Generate `work/manifest.csv` and verify files |

## How it works

The playlist and track metadata come from public NetEase endpoints. Each track ID is resolved through several lossless providers in order; if none returns a real FLAC, the official 320 kbps MP3 URL is used. Tracks that still fail are picked up by `npdl retry`, which searches Kuwo by `title artist` and re-verifies the duration before uploading.

No account or browser cookie is used. Private playlists are not supported.

## Notes

- Some tracks only exist as MP3 (remixes, indie uploads); they are marked in the manifest.
- A handful may stay unavailable due to region/copyright restrictions.
- Higher `--workers` values may trigger rate limits on the third-party resolvers.

## License

[MIT](LICENSE)
