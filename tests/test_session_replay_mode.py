from claudecontrol import Session
from claudecontrol.replay.modes import FallbackMode, RecordMode
from claudecontrol.replay.play import ReplayTransport


def test_session_uses_replay_transport_when_disabled(tmp_path):
    session = Session(
        "echo hi",
        record=RecordMode.DISABLED,
        fallback=FallbackMode.NOT_FOUND,
        replay=True,
        tapes_path=str(tmp_path),
        persist=False,
    )
    try:
        assert isinstance(session.process, ReplayTransport)
    finally:
        session.close()
