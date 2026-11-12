from npdl.naming import build_name_map, display_artists, format_name


def test_display_artists():
    assert display_artists("A / B / C") == "A, B, C"
    assert display_artists("Solo") == "Solo"
    assert display_artists("") == ""


def test_format_name_sanitizes_illegal_chars():
    name = format_name({"name": 'a/b:c*?"<>|', "artists": "x"})
    assert not any(ch in name for ch in '\\/:*?"<>|')


def test_format_name_uses_template():
    song = {"name": "夜に駆ける", "artists": "YOASOBI / 幾田りら", "album": "THE BOOK"}
    assert format_name(song) == "夜に駆ける - YOASOBI, 幾田りら"
    assert format_name(song, "[{album}] {name}") == "[THE BOOK] 夜に駆ける"


def test_format_name_falls_back_when_template_invalid():
    song = {"name": "Song", "artists": "Artist"}
    assert format_name(song, "{unknown}") == "Song - Artist"


def test_missing_name_uses_id():
    assert format_name({"id": 42, "name": "", "artists": "x"}) == "song_42 - x"


def test_build_name_map_dedupes_case_insensitively():
    songs = [
        {"id": 1, "name": "Hello", "artists": "A"},
        {"id": 2, "name": "hello", "artists": "a"},
        {"id": 3, "name": "World", "artists": "B"},
    ]
    names = build_name_map(songs)
    assert names[1] == "Hello - A"
    assert names[2] == "hello - a (2)"
    assert names[3] == "World - B"
