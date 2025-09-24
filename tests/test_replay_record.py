import base64
from pathlib import Path
from types import SimpleNamespace

from claudecontrol.replay.matchers import MatchingContext, default_command_matcher, default_stdin_matcher
from claudecontrol.replay.modes import RecordMode
from claudecontrol.replay.model import Chunk, Exchange, IOInput, IOOutput, Tape, TapeMeta
from claudecontrol.replay.namegen import TapeNameGenerator
from claudecontrol.replay.record import Recorder
from claudecontrol.replay.store import KeyBuilder, TapeStore


class DummySession:
    def __init__(self, command: str, root: Path):
        self.encoding = "utf-8"
        self.command = command
        self.env = {}
        self.cwd = str(root)
        self.dimensions = (24, 80)
        self.latency = 0
        self.error_rate = 0
        self.platform = "test-platform"
        self.tool_version = "claude_control-test"
        self.process = SimpleNamespace(logfile_read=None)
        self._tape_store = TapeStore(root)
        self._key_builder = KeyBuilder(None, None, default_stdin_matcher, default_command_matcher)
        self._tape_name_generator = TapeNameGenerator(root)
        self._last_input_preview = ""


def _make_exchange(prompt: str, text: str, output: str) -> Exchange:
    return Exchange(
        pre={"prompt": prompt},
        input=IOInput(kind="line", data_text=text),
        output=IOOutput(
            chunks=[
                Chunk(delay_ms=0, data_b64=base64.b64encode(output.encode("utf-8")).decode("ascii"))
            ]
        ),
        exit=None,
        dur_ms=1,
    )


def _matching_ctx(root: Path, prompt: str = ">") -> MatchingContext:
    return MatchingContext(program="demo", args=["--flag"], env={}, cwd=str(root), prompt=prompt)


def test_recorder_new_mode_skips_existing_exchange(tmp_path):
    session = DummySession("demo --flag", tmp_path)
    store = session._tape_store
    existing = Tape(
        meta=TapeMeta(
            created_at="2024-01-01T00:00:00Z",
            program="demo",
            args=["--flag"],
            env={},
            cwd=str(tmp_path),
            pty={"rows": 24, "cols": 80},
        ),
        session={"version": "test"},
        exchanges=[_make_exchange(">", "status", "ok")],
    )
    path = tmp_path / "demo" / "existing.json5"
    store.write_tape(path, existing)
    store.new.clear()

    recorder = Recorder(
        session=session,
        tapes_path=tmp_path,
        mode=RecordMode.NEW,
        namegen=session._tape_name_generator,
    )

    ctx = _matching_ctx(tmp_path)
    recorder.on_send(b"status\n", "line", ctx)
    recorder._sink.write(b"ok\n")
    recorder.on_exchange_end(ctx)
    recorder.finalize(store)

    # No new tapes should be created and existing tape remains unchanged
    assert not store.new
    reloaded = TapeStore(tmp_path)
    reloaded.load_all()
    assert len(reloaded.tapes) == 1
    assert reloaded.tapes[0].exchanges[0].output.chunks[0].data_b64 == existing.exchanges[0].output.chunks[0].data_b64


def test_recorder_overwrite_mode_updates_existing(tmp_path):
    session = DummySession("demo --flag", tmp_path)
    store = session._tape_store
    original = Tape(
        meta=TapeMeta(
            created_at="2024-01-01T00:00:00Z",
            program="demo",
            args=["--flag"],
            env={},
            cwd=str(tmp_path),
            pty={"rows": 24, "cols": 80},
        ),
        session={"version": "test"},
        exchanges=[_make_exchange(">", "status", "old")],
    )
    path = tmp_path / "demo" / "existing.json5"
    store.write_tape(path, original)

    recorder = Recorder(
        session=session,
        tapes_path=tmp_path,
        mode=RecordMode.OVERWRITE,
        namegen=session._tape_name_generator,
    )

    ctx = _matching_ctx(tmp_path)
    recorder.on_send(b"status\n", "line", ctx)
    recorder._sink.write(b"new\n")
    recorder.on_exchange_end(ctx)
    recorder.finalize(store)

    reloaded = TapeStore(tmp_path)
    reloaded.load_all()
    assert len(reloaded.tapes) == 1
    updated_chunk = reloaded.tapes[0].exchanges[0].output.chunks[0].data_b64
    assert base64.b64decode(updated_chunk).decode("utf-8").strip() == "new"


def test_recorder_new_mode_persists_new_exchange(tmp_path):
    session = DummySession("demo --flag", tmp_path)
    store = session._tape_store

    recorder = Recorder(
        session=session,
        tapes_path=tmp_path,
        mode=RecordMode.NEW,
        namegen=session._tape_name_generator,
    )

    ctx = _matching_ctx(tmp_path)
    recorder.on_send(b"deploy\n", "line", ctx)
    recorder._sink.write(b"done\n")
    recorder.on_exchange_end(ctx)
    recorder.finalize(store)

    assert store.new
    reloaded = TapeStore(tmp_path)
    reloaded.load_all()
    assert len(reloaded.tapes) == 1
    recorded_input = reloaded.tapes[0].exchanges[0].input.data_text
    assert recorded_input == "deploy\n"
