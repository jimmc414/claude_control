from claudecontrol.replay.normalize import collapse_ws, scrub, strip_ansi


def test_strip_ansi_removes_codes():
    text = "\x1b[31merror\x1b[0m"
    assert strip_ansi(text) == "error"


def test_collapse_ws_compacts_spaces():
    text = "foo\n\tbar"
    assert collapse_ws(text) == "foo bar"


def test_scrub_replaces_timestamps():
    text = "started 2024-01-01 00:00:00"
    assert "<TS>" in scrub(text)
