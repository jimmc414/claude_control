import base64

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
