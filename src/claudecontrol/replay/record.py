"""Recording helpers built on top of pexpect's logfile hooks."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Dict, List, Optional, Tuple

from .decorators import InputDecorator, OutputDecorator, TapeDecorator
from .matchers import MatchingContext
from .model import Chunk, Exchange, IOInput, IOOutput, Tape, TapeMeta
from .namegen import TapeNameGenerator
from .redact import redact_bytes
from .modes import RecordMode


def _input_to_bytes(io: IOInput) -> bytes:
    if io.data_b64:
        return base64.b64decode(io.data_b64)
    if io.data_text is not None:
        return io.data_text.encode("utf-8")
    return b""


class _CompositeWriter:
    """Fan out writes to multiple logfile targets."""

    def __init__(self, *writers) -> None:
        self._writers = tuple(writer for writer in writers if writer)

    def write(self, data):  # pragma: no cover - trivial passthrough
        for writer in self._writers:
            writer.write(data)

    def flush(self):  # pragma: no cover - trivial passthrough
        for writer in self._writers:
            if hasattr(writer, "flush"):
                writer.flush()


class ChunkSink:
    """Capture raw output bytes with per-chunk delays."""

    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding
        self._chunks: list[Chunk] = []
        self._last = time.monotonic()

    def reset(self) -> None:
        self._chunks = []
        self._last = time.monotonic()

    def write(self, data):
        if data is None:
            return
        if isinstance(data, str):
            raw = data.encode(self.encoding, errors="replace")
        else:
            raw = bytes(data)
        raw = redact_bytes(raw)
        now = time.monotonic()
        delay_ms = int((now - self._last) * 1000)
        self._last = now
        is_utf8 = True
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            is_utf8 = False
        payload = base64.b64encode(raw).decode("ascii")
        self._chunks.append(Chunk(delay_ms=delay_ms, data_b64=payload, is_utf8=is_utf8))

    def flush(self):  # pragma: no cover - hook for pexpect
        return None

    def to_output(self) -> IOOutput:
        return IOOutput(chunks=list(self._chunks))


@dataclass
class Recorder:
    """Encapsulates the logic required to persist exchanges to disk."""

    session: "Session"
    tapes_path: Path
    mode: RecordMode
    namegen: TapeNameGenerator
    input_decorator: Optional[InputDecorator] = None
    output_decorator: Optional[OutputDecorator] = None
    tape_decorator: Optional[TapeDecorator] = None

    def __post_init__(self) -> None:
        self._sink = ChunkSink(self.session.encoding)
        self._tape: Optional[Tape] = None
        self._tape_path: Optional[Path] = None
        self._current_input: Optional[IOInput] = None
        self._current_prompt: Optional[str] = None
        self._start_ts: Optional[float] = None
        self._pending: List[Tuple[MatchingContext, Exchange]] = []
        self._store = self.session._tape_store
        self._builder = self.session._key_builder
        # Prime the store for lookups so record modes can act deterministically.
        self._store.load_all()
        self._index: Dict[Tuple, Tuple[int, int]] = self._store.build_index(self._builder)

    # ------------------------------------------------------------------ setup
    def start(self) -> None:
        existing = getattr(self.session.process, "logfile_read", None)
        self.session.process.logfile_read = _CompositeWriter(existing, self._sink)

    # ---------------------------------------------------------------- exchange
    def on_send(self, raw: bytes, kind: str, ctx: MatchingContext) -> None:
        decorated = raw
        if self.input_decorator:
            decorated = self.input_decorator(ctx, raw)
        preview = decorated.decode("utf-8", "ignore")[:64]
        setattr(self.session, "_last_input_preview", preview)
        text = decorated.decode("utf-8", "ignore")
        if decorated == text.encode("utf-8"):
            data_text = text
            data_b64 = None
        else:
            data_text = None
            data_b64 = base64.b64encode(decorated).decode("ascii")
        self._current_input = IOInput(kind=kind, data_text=data_text, data_b64=data_b64)
        self._current_prompt = ctx.prompt
        self._sink.reset()
        self._start_ts = time.monotonic()

    def on_exchange_end(self, ctx: MatchingContext, exit_info: Optional[dict] = None) -> None:
        if not self._current_input:
            return
        output = self._sink.to_output()
        if self.output_decorator:
            # Apply decorator to each chunk as UTF-8 text where possible
            new_chunks = []
            for chunk in output.chunks:
                data = base64.b64decode(chunk.data_b64)
                decorated = self.output_decorator(ctx, data)
                payload = base64.b64encode(decorated).decode("ascii")
                new_chunks.append(Chunk(delay_ms=chunk.delay_ms, data_b64=payload, is_utf8=chunk.is_utf8))
            output = IOOutput(chunks=new_chunks)
        dur_ms = int((time.monotonic() - (self._start_ts or time.monotonic())) * 1000)
        exchange = Exchange(
            pre={"prompt": self._current_prompt},
            input=self._current_input,
            output=output,
            exit=exit_info,
            dur_ms=dur_ms,
        )
        self._pending.append((MatchingContext(
            program=ctx.program,
            args=list(ctx.args),
            env=dict(ctx.env),
            cwd=ctx.cwd,
            prompt=ctx.prompt,
        ), exchange))
        self._current_input = None

    # ----------------------------------------------------------------- helpers
    def _ensure_tape(self, ctx: MatchingContext) -> Tape:
        if self._tape is None:
            path = self.namegen(self.session)
            command_parts = self._split_command(self.session.command)
            program = command_parts[0] if command_parts else self.session.command
            args = command_parts[1:] if len(command_parts) > 1 else []
            meta = TapeMeta(
                created_at=time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                program=program,
                args=args,
                env=self.session.env,
                cwd=self.session.cwd,
                pty={"rows": self.session.dimensions[0], "cols": self.session.dimensions[1]},
                latency=self.session.latency,
                error_rate=self.session.error_rate,
            )
            tape = Tape(
                meta=meta,
                session={
                    "platform": self.session.platform,
                    "version": self.session.tool_version,
                },
                exchanges=[],
            )
            if self.tape_decorator:
                tape_dict = self.tape_decorator(ctx, {
                    "meta": {},
                })
                if isinstance(tape_dict, dict):
                    tape.meta.tag = tape_dict.get("tag", tape.meta.tag)
            self._tape = tape
            self._tape_path = path
        return self._tape

    def _split_command(self, command: str) -> List[str]:
        try:
            return shlex.split(command)
        except ValueError:  # pragma: no cover - defensive for malformed commands
            return [command]

    # ---------------------------------------------------------------- finalize
    def finalize(self, store) -> None:
        if not self._pending:
            return
        replacements: Dict[int, List[Tuple[int, Exchange]]] = {}
        new_exchanges: List[Tuple[MatchingContext, Exchange]] = []

        for ctx, exchange in self._pending:
            stdin = _input_to_bytes(exchange.input)
            key = self._builder.context_key(ctx, stdin)
            match = self._index.get(key)
            if match is None:
                new_exchanges.append((ctx, exchange))
                continue
            if self.mode == RecordMode.NEW:
                continue
            tape_idx, exchange_idx = match
            replacements.setdefault(tape_idx, []).append((exchange_idx, exchange))

        for tape_idx, pairs in replacements.items():
            tape = store.tapes[tape_idx]
            for exchange_idx, exchange in pairs:
                tape.exchanges[exchange_idx] = exchange
            store.write_tape(store.paths[tape_idx], tape, mark_new=False)

        if new_exchanges:
            first_ctx = new_exchanges[0][0]
            tape = self._ensure_tape(first_ctx)
            for _, exchange in new_exchanges:
                tape.exchanges.append(exchange)
            if self._tape_path:
                store.write_tape(self._tape_path, tape)

        self._pending.clear()
