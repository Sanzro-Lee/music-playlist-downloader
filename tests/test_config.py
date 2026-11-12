import pytest

from npdl.config import Config


def test_validate_requires_playlist():
    cfg = Config()
    with pytest.raises(ValueError, match="歌单 ID"):
        cfg.validate()


def test_validate_requires_name_placeholder():
    cfg = Config(playlist_id="123", naming="{artists}")
    with pytest.raises(ValueError, match="name"):
        cfg.validate()


def test_validate_rejects_bad_workers():
    cfg = Config(playlist_id="123", workers=0)
    with pytest.raises(ValueError, match="workers"):
        cfg.validate()


def test_apply_ignores_unknown_keys():
    cfg = Config()
    cfg.apply({"dest": "/music", "unknown": 1, "workers": 6})
    assert cfg.dest == "/music"
    assert cfg.workers == 6
    assert not hasattr(cfg, "unknown")


def test_load_missing_explicit_config():
    with pytest.raises(ValueError, match="配置文件不存在"):
        Config.load("no-such-file.toml")


def test_load_config_with_bom(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b'\xef\xbb\xbfplaylist_id = "123"\nworkers = 2\n')
    cfg = Config.load(str(path))
    assert cfg.playlist_id == "123"
    assert cfg.workers == 2
