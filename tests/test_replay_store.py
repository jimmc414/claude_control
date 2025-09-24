import base64

import pyjson5

from claudecontrol.replay.model import Chunk, Exchange, IOInput, IOOutput, Tape, TapeMeta
from claudecontrol.replay.store import TapeStore


def test_store_write_and_load(tmp_path):
    store = TapeStore(tmp_path)
    tape = Tape(
        meta=TapeMeta(
            created_at="2024-01-01T00:00:00Z",
            program="demo",
            args=[],
            env={},
            cwd=str(tmp_path),
            pty={"rows": 24, "cols": 80},
        ),
        session={"version": "test"},
        exchanges=[
            Exchange(
                pre={"prompt": ">"},
                input=IOInput(kind="line", data_text="hello"),
                output=IOOutput(
                    chunks=[
                        Chunk(
                            delay_ms=0,
                            data_b64=base64.b64encode(b"world\n").decode("ascii"),
                            is_utf8=True,
                        )
                    ]
                ),
                exit=None,
            )
        ],
    )

    path = tmp_path / "demo" / "tape.json5"
    store.write_tape(path, tape)

    loaded = TapeStore(tmp_path)
    loaded.load_all()
    assert len(loaded.tapes) == 1
    assert loaded.tapes[0].meta.program == "demo"
    assert loaded.tapes[0].exchanges[0].input.data_text == "hello"


def test_store_validate_reports_errors(tmp_path):
    # Write an intentionally malformed tape file
    bad_path = tmp_path / "bad" / "tape.json5"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("{meta: {program: 'demo'}}", encoding="utf-8")

    store = TapeStore(tmp_path)
    errors = store.validate()
    assert errors
    assert errors[0][0] == bad_path


def test_store_redact_inplace_updates_file(tmp_path):
    store = TapeStore(tmp_path)
    tape = Tape(
        meta=TapeMeta(
            created_at="2024-01-01T00:00:00Z",
            program="demo",
            args=[],
            env={},
            cwd=str(tmp_path),
            pty={"rows": 24, "cols": 80},
        ),
        session={"version": "test"},
        exchanges=[
            Exchange(
                pre={"prompt": ">"},
                input=IOInput(kind="line", data_text="password=secret"),
                output=IOOutput(
                    chunks=[
                        Chunk(
                            delay_ms=0,
                            data_b64=base64.b64encode(b"token: supersecret\n").decode("ascii"),
                            is_utf8=True,
                        )
                    ]
                ),
                exit=None,
            )
        ],
    )

    path = tmp_path / "demo" / "secret.json5"
    store.write_tape(path, tape)

    reloaded = TapeStore(tmp_path)
    reloaded.load_all()
    results = reloaded.redact_all(inplace=True)
    assert any(p == path and changed for p, changed in results)

    updated = pyjson5.load(path.open("r", encoding="utf-8"))
    input_text = updated["exchanges"][0]["input"]["dataText"]
    chunk_data = updated["exchanges"][0]["output"]["chunks"][0]["dataB64"]
    assert "***" in input_text
    assert base64.b64decode(chunk_data).decode("utf-8").endswith("***\n")
