"""Storage helpers for replay tapes."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import fastjsonschema
import portalocker
import pyjson5

from .exceptions import SchemaError
from .matchers import MatchingContext, default_command_matcher, default_stdin_matcher, filter_env
from .model import Chunk, Exchange, IOInput, IOOutput, Tape, TapeMeta
from .normalize import strip_ansi
from .redact import redact_bytes


_TAPE_SCHEMA = {
    "type": "object",
    "required": ["meta", "session", "exchanges"],
    "properties": {
        "meta": {
            "type": "object",
            "required": ["program", "args", "env", "cwd"],
            "properties": {
                "createdAt": {"type": "string"},
                "program": {"type": "string"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "cwd": {"type": "string"},
                "pty": {
                    "type": ["object", "null"],
                    "properties": {
                        "rows": {"type": "integer"},
                        "cols": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                "tag": {"type": ["string", "null"]},
                "latency": {},
                "errorRate": {},
                "seed": {"type": ["integer", "null"]},
            },
            "additionalProperties": True,
        },
        "session": {"type": "object"},
        "exchanges": {
            "type": "array",
            "items": {"type": "object"},
        },
    },
    "additionalProperties": False,
}

_STRICT_TAPE_SCHEMA = {
    "type": "object",
    "required": ["meta", "session", "exchanges"],
    "properties": {
        "meta": _TAPE_SCHEMA["properties"]["meta"],
        "session": {"type": "object"},
        "exchanges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["pre", "input", "output"],
                "properties": {
                    "pre": {"type": "object"},
                    "input": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {"type": "string"},
                            "dataText": {"type": ["string", "null"]},
                            "dataBytesB64": {"type": ["string", "null"]},
                        },
                        "additionalProperties": False,
                    },
                    "output": {
                        "type": "object",
                        "required": ["chunks"],
                        "properties": {
                            "chunks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["delay_ms", "dataB64"],
                                    "properties": {
                                        "delay_ms": {"type": "integer"},
                                        "dataB64": {"type": "string"},
                                        "isUtf8": {"type": ["boolean", "null"]},
                                    },
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "additionalProperties": False,
                    },
                    "exit": {"type": ["object", "null"]},
                    "dur_ms": {"type": ["integer", "null"]},
                    "annotations": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

_VALIDATE = fastjsonschema.compile(_TAPE_SCHEMA)
_STRICT_VALIDATE = fastjsonschema.compile(_STRICT_TAPE_SCHEMA)


def _input_to_bytes(io: IOInput) -> bytes:
    if io.data_b64:
        return base64.b64decode(io.data_b64)
    return (io.data_text or "").encode("utf-8")


class KeyBuilder:
    """Builds normalized keys for index lookup."""

    def __init__(
        self,
        allow_env: Optional[Iterable[str]] = None,
        ignore_env: Optional[Iterable[str]] = None,
        stdin_matcher=default_stdin_matcher,
        command_matcher=default_command_matcher,
    ) -> None:
        self.allow_env = list(allow_env) if allow_env else None
        self.ignore_env = list(ignore_env) if ignore_env else None
        self.stdin_matcher = stdin_matcher
        self.command_matcher = command_matcher

    def build_key(self, tape: Tape, exchange: Exchange) -> Tuple:
        env = filter_env(tape.meta.env, self.allow_env, self.ignore_env)
        env_items = tuple(sorted(env.items()))
        command = [tape.meta.program, *tape.meta.args]
        prompt = strip_ansi((exchange.pre or {}).get("prompt", "") or "")
        stdin = _input_to_bytes(exchange.input).rstrip(b"\r\n")
        return (
            tape.meta.program,
            tuple(command),
            env_items,
            tape.meta.cwd,
            prompt,
            stdin,
        )

    def context_key(self, ctx: MatchingContext, stdin: bytes) -> Tuple:
        env = filter_env(ctx.env, self.allow_env, self.ignore_env)
        env_items = tuple(sorted(env.items()))
        command = [ctx.program, *ctx.args]
        prompt = strip_ansi(ctx.prompt or "")
        return (
            ctx.program,
            tuple(command),
            env_items,
            ctx.cwd,
            prompt,
            stdin.rstrip(b"\r\n"),
        )


class TapeStore:
    """Loads, indexes, and writes tapes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.tapes: List[Tape] = []
        self.paths: List[Path] = []
        self.used: set[Path] = set()
        self.new: set[Path] = set()

    # ------------------------------------------------------------------ loading
    def load_all(self) -> None:
        self.tapes.clear()
        self.paths.clear()
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*.json5")):
            tape = self._read_tape(path)
            self.tapes.append(tape)
            self.paths.append(path)

    # ------------------------------------------------------------------ indexing
    def build_index(self, builder: KeyBuilder) -> Dict[Tuple, Tuple[int, int]]:
        index: Dict[Tuple, Tuple[int, int]] = {}
        for tape_idx, tape in enumerate(self.tapes):
            for ex_idx, exchange in enumerate(tape.exchanges):
                key = builder.build_key(tape, exchange)
                index[key] = (tape_idx, ex_idx)
        return index

    # ---------------------------------------------------------------- writing
    def write_tape(self, path: Path, tape: Tape, *, mark_new: bool = True) -> None:
        data = self._encode_tape(tape)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with portalocker.Lock(tmp, "w", timeout=5) as handle:
            json_text = pyjson5.dumps(data, indent=2) + "\n"
            handle.write(json_text)
        os.replace(tmp, path)
        if path not in self.paths:
            self.paths.append(path)
        if mark_new:
            self.new.add(path)

    def mark_used(self, path: Path) -> None:
        self.used.add(path)

    # ---------------------------------------------------------------- management
    def iter_tapes(self) -> Iterable[tuple[Path, Tape]]:
        if not self.paths:
            self.load_all()
        return list(zip(self.paths, self.tapes))

    def validate(self, *, strict: bool = False) -> List[tuple[Path, str]]:
        validator = _STRICT_VALIDATE if strict else _VALIDATE
        errors: List[tuple[Path, str]] = []
        if not self.root.exists():
            return errors
        for path in sorted(self.root.rglob("*.json5")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = pyjson5.load(handle)
                validator(payload)
            except Exception as exc:  # pragma: no cover - schema raises detailed error
                errors.append((path, str(exc)))
        return errors

    def redact_all(self, *, inplace: bool = False) -> List[tuple[Path, bool]]:
        results: List[tuple[Path, bool]] = []
        for path, tape in self.iter_tapes():
            changed = False
            for exchange in tape.exchanges:
                if self._redact_input(exchange.input):
                    changed = True
                if self._redact_output(exchange.output):
                    changed = True
            results.append((path, changed))
            if changed and inplace:
                self.write_tape(path, tape, mark_new=False)
        return results

    def _redact_input(self, io: IOInput) -> bool:
        changed = False
        if io.data_text:
            raw = io.data_text.encode("utf-8")
            redacted = redact_bytes(raw)
            text = redacted.decode("utf-8")
            if text != io.data_text:
                io.data_text = text
                changed = True
        if io.data_b64:
            decoded = base64.b64decode(io.data_b64)
            redacted = redact_bytes(decoded)
            if redacted != decoded:
                io.data_b64 = base64.b64encode(redacted).decode("ascii")
                changed = True
        return changed

    def _redact_output(self, output: IOOutput) -> bool:
        changed = False
        for chunk in output.chunks:
            decoded = base64.b64decode(chunk.data_b64)
            redacted = redact_bytes(decoded)
            if redacted != decoded:
                chunk.data_b64 = base64.b64encode(redacted).decode("ascii")
                changed = True
        return changed

    # ---------------------------------------------------------------- helpers
    def _read_tape(self, path: Path) -> Tape:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = pyjson5.load(handle)
        except Exception as exc:  # pragma: no cover - defensive
            raise SchemaError(f"Failed to load tape {path}: {exc}") from exc
        return self._decode_tape(payload)

    def _decode_tape(self, data: Dict) -> Tape:
        meta_dict = data.get("meta", {})
        meta = TapeMeta(
            created_at=meta_dict.get("createdAt") or meta_dict.get("created_at", ""),
            program=meta_dict.get("program", ""),
            args=list(meta_dict.get("args", [])),
            env=dict(meta_dict.get("env", {})),
            cwd=meta_dict.get("cwd", ""),
            pty=meta_dict.get("pty"),
            tag=meta_dict.get("tag"),
            latency=meta_dict.get("latency", 0),
            error_rate=meta_dict.get("errorRate", 0),
            seed=meta_dict.get("seed"),
        )
        session = data.get("session", {})
        exchanges: List[Exchange] = []
        for ex in data.get("exchanges", []):
            input_dict = ex.get("input", {})
            output_dict = ex.get("output", {})
            chunks = [
                Chunk(
                    delay_ms=int(chunk.get("delay_ms", 0)),
                    data_b64=str(chunk.get("dataB64") or chunk.get("data_b64")),
                    is_utf8=bool(chunk.get("isUtf8", True)),
                )
                for chunk in output_dict.get("chunks", [])
            ]
            exchange = Exchange(
                pre=dict(ex.get("pre", {})),
                input=IOInput(
                    kind=input_dict.get("type") or input_dict.get("kind", "line"),
                    data_text=input_dict.get("dataText") or input_dict.get("data_text"),
                    data_b64=input_dict.get("dataBytesB64") or input_dict.get("data_b64"),
                ),
                output=IOOutput(chunks=chunks),
                exit=ex.get("exit"),
                dur_ms=ex.get("dur_ms"),
                annotations=dict(ex.get("annotations", {})),
            )
            exchanges.append(exchange)
        return Tape(meta=meta, session=session, exchanges=exchanges)

    def _encode_tape(self, tape: Tape) -> Dict:
        data = {
            "meta": {
                "createdAt": tape.meta.created_at,
                "program": tape.meta.program,
                "args": tape.meta.args,
                "env": tape.meta.env,
                "cwd": tape.meta.cwd,
                "pty": tape.meta.pty,
                "tag": tape.meta.tag,
                "latency": tape.meta.latency,
                "errorRate": tape.meta.error_rate,
                "seed": tape.meta.seed,
            },
            "session": tape.session,
            "exchanges": [],
        }
        for exchange in tape.exchanges:
            chunks = [
                {
                    "delay_ms": chunk.delay_ms,
                    "dataB64": chunk.data_b64,
                    "isUtf8": chunk.is_utf8,
                }
                for chunk in exchange.output.chunks
            ]
            data["exchanges"].append(
                {
                    "pre": exchange.pre,
                    "input": {
                        "type": exchange.input.kind,
                        "dataText": exchange.input.data_text,
                        "dataBytesB64": exchange.input.data_b64,
                    },
                    "output": {"chunks": chunks},
                    "exit": exchange.exit,
                    "dur_ms": exchange.dur_ms,
                    "annotations": exchange.annotations,
                }
            )
        return data


def make_matching_context(tape: Tape, exchange: Exchange) -> MatchingContext:
    prompt = (exchange.pre or {}).get("prompt")
    return MatchingContext(
        program=tape.meta.program,
        args=list(tape.meta.args),
        env=dict(tape.meta.env),
        cwd=tape.meta.cwd,
        prompt=prompt,
    )
