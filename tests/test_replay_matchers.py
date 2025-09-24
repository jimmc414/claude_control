from claudecontrol.replay.matchers import MatchingContext, default_stdin_matcher


def test_default_stdin_matcher_ignores_line_endings():
    ctx = MatchingContext(program="prog", args=[], env={}, cwd="/tmp", prompt=">")
    assert default_stdin_matcher(b"select 1\r\n", b"select 1\n", ctx)
