from npdl.state import StateStore


def test_update_get_and_reload(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(str(path))
    store.update(1, {"status": "done", "quality": "flac"})

    assert store.get(1)["status"] == "done"
    assert store.finished_ids() == {1}

    reloaded = StateStore(str(path))
    assert reloaded.get("1")["quality"] == "flac"


def test_summary_counts_statuses(tmp_path):
    store = StateStore(str(tmp_path / "state.json"))
    store.update(1, {"status": "done"})
    store.update(2, {"status": "mp3"})
    store.update(3, {"status": "fail"})

    assert store.summary() == {"done": 1, "mp3": 1, "fail": 1}
    assert store.finished_ids() == {1, 2}
    assert store.finished_ids(("fail",)) == {3}


def test_get_missing_returns_empty(tmp_path):
    store = StateStore(str(tmp_path / "missing.json"))
    assert store.get(999) == {}
