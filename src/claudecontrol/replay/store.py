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
        ignore_args: Optional[Iterable[int | str]] = None,
        ignore_stdin: bool = False,
    ) -> None:
        self.allow_env = list(allow_env) if allow_env else None
        self.ignore_env = list(ignore_env) if ignore_env else None
        self.stdin_matcher = stdin_matcher
        self.command_matcher = command_matcher
        self.ignore_stdin = ignore_stdin
        ignore_args = list(ignore_args) if ignore_args else []
        self._ignore_arg_indices = {int(item) for item in ignore_args if isinstance(item, int)}
        self._ignore_arg_values = {str(item) for item in ignore_args if isinstance(item, str)}

    # ------------------------------------------------------------------ helpers
    def filter_env_values(self, env: Dict[str, str]) -> Dict[str, str]:
        return filter_env(env, self.allow_env, self.ignore_env)

    def _filtered_args(self, args: Iterable[str]) -> List[str]:
        filtered: List[str] = []
        for index, value in enumerate(args):
            if index in self._ignore_arg_indices:
                continue
            if value in self._ignore_arg_values:
                continue
            filtered.append(value)
        return filtered

    def _prompt_signature(self, prompt: Optional[str]) -> str:
        return strip_ansi(prompt or "")

    def command_for_tape(self, tape: Tape) -> List[str]:
        return [tape.meta.program, *self._filtered_args(tape.meta.args)]

    def command_for_context(self, ctx: MatchingContext) -> List[str]:
        return [ctx.program, *self._filtered_args(ctx.args)]

    def stdin_for_exchange(self, exchange: Exchange) -> bytes:
        if self.ignore_stdin:
            return b""
        return _input_to_bytes(exchange.input)

    def stdin_for_payload(self, payload: bytes) -> bytes:
        if self.ignore_stdin:
            return b""
        return payload

    def _stdin_key(self, data: bytes) -> bytes:
        if self.ignore_stdin:
            return b""
        return data.rstrip(b"\r\n")

    # ------------------------------------------------------------------ key building
    def build_key(self, tape: Tape, exchange: Exchange) -> Tuple:
        env_items = tuple(sorted(self.filter_env_values(tape.meta.env).items()))
        command = tuple(self.command_for_tape(tape))
        prompt = self._prompt_signature((exchange.pre or {}).get("prompt"))
        stdin = self._stdin_key(self.stdin_for_exchange(exchange))
        return (
            command,
            env_items,
            tape.meta.cwd,
            prompt,
            stdin,
        )

    def context_key(self, ctx: MatchingContext, stdin: bytes) -> Tuple:
        env_items = tuple(sorted(self.filter_env_values(ctx.env).items()))
        command = tuple(self.command_for_context(ctx))
        prompt = self._prompt_signature(ctx.prompt)
        stdin_key = self._stdin_key(self.stdin_for_payload(stdin))
        return (
            command,
            env_items,
            ctx.cwd,
            prompt,
            stdin_key,
        )

    def bucket_key(self, tape: Tape, exchange: Exchange) -> Tuple:
        prompt = self._prompt_signature((exchange.pre or {}).get("prompt"))
        return (
            tape.meta.program,
            tape.meta.cwd,
            prompt,
        )

    def bucket_context_key(self, ctx: MatchingContext) -> Tuple:
        prompt = self._prompt_signature(ctx.prompt)
        return (
            ctx.program,
            ctx.cwd,
            prompt,
        )


class TapeStore:
    """Loads, indexes, and writes tapes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.tapes: List[Tape] = []
        self.paths: List[Path] = []
        self.used: set[Path] = set()
        self.new: set[Path] = set()
        self._index: Dict[Tuple, List[Tuple[int, int]]] = {}
        self._buckets: Dict[Tuple, List[Tuple[int, int]]] = {}

    # ------------------------------------------------------------------ loading
    def load_all(self) -> None:
        self.tapes.clear()
        self.paths.clear()
        self._index.clear()
        self._buckets.clear()
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*.json5")):
            tape = self._read_tape(path)
            self.tapes.append(tape)
            self.paths.append(path)

    # ------------------------------------------------------------------ indexing
    def build_index(self, builder: KeyBuilder) -> Dict[Tuple, List[Tuple[int, int]]]:
        index: Dict[Tuple, List[Tuple[int, int]]] = {}
        buckets: Dict[Tuple, List[Tuple[int, int]]] = {}
        for tape_idx, tape in enumerate(self.tapes):
            for ex_idx, exchange in enumerate(tape.exchanges):
                key = builder.build_key(tape, exchange)
                index.setdefault(key, []).append((tape_idx, ex_idx))
                bucket = builder.bucket_key(tape, exchange)
                buckets.setdefault(bucket, []).append((tape_idx, ex_idx))
        self._index = index
        self._buckets = buckets
        return index

    def find_matches(
        self, builder: KeyBuilder, ctx: MatchingContext, stdin: bytes
    ) -> List[Tuple[int, int]]:
        if not self.tapes:
            self.load_all()
        if not self._index:
            self.build_index(builder)

        key = builder.context_key(ctx, stdin)
        matches = self._index.get(key)
        if matches:
            return matches

        bucket_key = builder.bucket_context_key(ctx)
        candidates = self._buckets.get(bucket_key, [])
        if not candidates:
            return []

        actual_env = builder.filter_env_values(ctx.env)
        actual_command = builder.command_for_context(ctx)
        actual_stdin = builder.stdin_for_payload(stdin)

        resolved: List[Tuple[int, int]] = []
        for tape_idx, ex_idx in candidates:
            tape = self.tapes[tape_idx]
            exchange = tape.exchanges[ex_idx]
            if builder.filter_env_values(tape.meta.env) != actual_env:
                continue
            if not builder.command_matcher(builder.command_for_tape(tape), actual_command, ctx):
                continue
            if not builder.stdin_matcher(
                builder.stdin_for_exchange(exchange), actual_stdin, ctx
            ):
                continue
            resolved.append((tape_idx, ex_idx))
        return resolved

    # ---------------------------------------------------------------- writing
    def write_tape(self, path: Path, tape: Tape, *, mark_new: bool = True) -> None:
        data = self._encode_tape(tape)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with portalocker.Lock(tmp, "w", timeout=5) as handle:
            json_text = pyjson5.dumps(data, indent=2) + "\n"
            handle.write(json_text)
        os.replace(tmp, path)

        # Invalidate cached indexes so callers rebuild with latest content.
        self._index.clear()
        self._buckets.clear()

        if path in self.paths:
            idx = self.paths.index(path)
            # Ensure the in-memory tape list stays aligned with ``paths``
            if idx < len(self.tapes):
                self.tapes[idx] = tape
            else:  # pragma: no cover - defensive, should not happen in practice
                self.tapes.append(tape)
        else:
            self.paths.append(path)
            self.tapes.append(tape)

        if mark_new:
            self.new.add(path)

    def mark_used(self, path: Path) -> None:
        self.used.add(path)

    # ---------------------------------------------------------------- management
    def iter_tapes(self) -> Iterable[tuple[Path, Tape]]:
        if not self.paths:
            self.load_all()
        return list(zip(self.paths, self.tapes))

    def read_tape(self, path: Path) -> Tape:
        return self._read_tape(path)

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
