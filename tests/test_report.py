from npdl.report import build_rows, summarize, verify_files
from npdl.state import StateStore

SONGS = [
    {"id": 1, "name": "Alpha", "artists": "A", "album": "X", "duration_ms": 60000},
    {"id": 2, "name": "Beta", "artists": "B", "album": "Y", "duration_ms": 120000},
    {"id": 3, "name": "Gamma", "artists": "C", "album": "Z", "duration_ms": 90000},
]


def _store(tmp_path):
    store = StateStore(str(tmp_path / "state.json"))
    (tmp_path / "Alpha - A.flac").write_bytes(b"0" * 1048576)
    store.update(1, {
        "status": "done", "quality": "flac", "source": "byfuns",
        "file": str(tmp_path / "Alpha - A.flac"), "size": 1048576, "duration": 60.0,
    })
    store.update(2, {
        "status": "mp3", "quality": "mp3-320", "source": "netease-official",
        "file": str(tmp_path / "missing.mp3"), "size": 524288, "duration": 120.0,
    })
    store.update(3, {"status": "fail", "error": "no source"})
    return store


def test_build_rows_and_summary(tmp_path):
    rows = build_rows(SONGS, _store(tmp_path))
    assert [row["文件名"] for row in rows] == ["Alpha - A.flac", "Beta - B.mp3", ""]
    summary = summarize(rows)
    assert summary["total"] == 3
    assert summary["quality"] == {"flac": 1, "mp3-320": 1}
    assert summary["fails"] == [("Gamma", "C")]


def test_verify_files_reports_missing(tmp_path):
    rows = build_rows(SONGS, _store(tmp_path))
    problems = verify_files(rows)
    assert len(problems) == 1
    assert "不存在" in problems[0][1]


def test_write_csv_roundtrip(tmp_path):
    import csv

    from npdl.report import write_csv

    rows = build_rows(SONGS, _store(tmp_path))
    out = tmp_path / "manifest.csv"
    write_csv(rows, str(out))
    with open(out, encoding="utf-8-sig") as fh:
        reader = list(csv.DictReader(fh))
    assert len(reader) == 3
    assert reader[0]["歌曲名"] == "Alpha"
