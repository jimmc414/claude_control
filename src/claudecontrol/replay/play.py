"""Replay transport that mimics the minimal pexpect interface we rely on."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import Optional

import pexpect

from .errors import should_inject_error
from .exceptions import TapeMissError
from .latency import resolve_latency
from .matchers import MatchingContext
from .model import Exchange
from .store import KeyBuilder, TapeStore


@dataclass
class ReplayHandle:
    tape_index: int
    exchange_index: int


class ReplayTransport:
    """A lightweight stand-in for ``pexpect.spawn`` during playback."""

    def __init__(
        self,
        store: TapeStore,
        builder: KeyBuilder,
        ctx: MatchingContext,
        latency_cfg,
        error_cfg,
    ) -> None:
        self.store = store
        self.builder = builder
        self.ctx = ctx
        self.latency_cfg = latency_cfg
        self.error_cfg = error_cfg
        self.before: bytes = b""
        self.after: bytes = b""
        self.match: Optional[re.Match[str]] = None
        self.exitstatus: Optional[int] = 0
        self.signalstatus: Optional[int] = None
        self.pid: Optional[int] = None
        self._buffer = bytearray()
        self._closed = False
        self._current: Optional[ReplayHandle] = None

    # ---------------------------------------------------------------- send api
    def send(self, data: bytes) -> int:
        return self._handle_send(data)

    def sendline(self, text: str) -> int:
        return self._handle_send((text + "\n").encode("utf-8"))

    def _handle_send(self, payload: bytes) -> int:
        matches = self.store.find_matches(self.builder, self.ctx, payload)
        if not matches:
            raise TapeMissError(f"No tape found for input {payload!r}")
        tape_idx, exchange_idx = matches[0]
        self._current = ReplayHandle(tape_idx, exchange_idx)
        tape = self.store.tapes[tape_idx]
        exchange = tape.exchanges[exchange_idx]
        self.store.mark_used(self.store.paths[tape_idx])
        self.before = payload
        self._buffer.clear()
        self._stream_exchange(tape.meta.latency or self.latency_cfg, exchange)
        if should_inject_error(self.error_cfg or tape.meta.error_rate, self.ctx):
            raise TapeMissError("Synthetic error injected by configuration")
        if exchange.exit:
            self.exitstatus = exchange.exit.get("code", 0)
            self.signalstatus = exchange.exit.get("signal")
            self._closed = True
        return len(payload)

    # ---------------------------------------------------------------- expect api
    def expect(self, pattern, timeout: Optional[int] = None) -> int:
        patterns = pattern if isinstance(pattern, (list, tuple)) else [pattern]
        return self._expect_list(patterns, timeout)

    def expect_exact(self, pattern, timeout: Optional[int] = None) -> int:
        if not isinstance(pattern, (list, tuple)):
            patterns = [pattern]
        else:
            patterns = list(pattern)

        deadline = time.time() + (timeout or 30)
        timeout_index = self._timeout_index(patterns)

        while time.time() < deadline:
            text = self._buffer.decode("utf-8", "ignore")
            buf_bytes = bytes(self._buffer)
            for idx, candidate in enumerate(patterns):
                if self._is_eof(candidate):
                    if self._buffer_closed():
                        self._set_before_after(buf_bytes, b"")
                        self.match = None
                        return idx
                    continue
                if self._is_timeout(candidate):
                    continue

                if isinstance(candidate, bytes):
                    if candidate in buf_bytes:
                        head, tail = buf_bytes.split(candidate, 1)
                        self.match = None
                        self._set_before_after(head, tail)
                        return idx
                else:
                    literal = str(candidate)
                    if literal in text:
                        head, tail = text.split(literal, 1)
                        self.match = None
                        self.before = head.encode("utf-8", "ignore")
                        self.after = tail.encode("utf-8", "ignore")
                        return idx
            time.sleep(0.01)

        if timeout_index is not None:
            self.match = None
            self._set_before_after(bytes(self._buffer), b"")
            return timeout_index
        raise TimeoutError("Replay expect_exact timeout")

    def _expect_list(self, patterns, timeout: Optional[int]) -> int:
        compiled = [self._prepare_pattern(p) for p in patterns]
        deadline = time.time() + (timeout or 30)
        timeout_index = self._timeout_index(patterns)

        while time.time() < deadline:
            try:
                text = self._buffer.decode("utf-8")
            except UnicodeDecodeError:
                text = self._buffer.decode("utf-8", "ignore")
            buf_bytes = bytes(self._buffer)
            for idx, entry in enumerate(compiled):
                kind, payload = entry
                if kind == "timeout":
                    continue
                if kind == "eof":
                    if self._buffer_closed():
                        self.match = None
                        self._set_before_after(buf_bytes, b"")
                        return idx
                    continue
                if kind == "regex":
                    match = payload.search(text)
                    if match:
                        self.match = match
                        self.before = text[: match.start()].encode("utf-8", "ignore")
                        self.after = text[match.end() :].encode("utf-8", "ignore")
                        return idx
                elif kind == "bytes" and payload in buf_bytes:
                    head, tail = buf_bytes.split(payload, 1)
                    self.match = None
                    self._set_before_after(head, tail)
                    return idx
                elif kind == "literal":
                    if payload in text:
                        head, tail = text.split(payload, 1)
                        self.match = None
                        self.before = head.encode("utf-8", "ignore")
                        self.after = tail.encode("utf-8", "ignore")
                        return idx
            time.sleep(0.01)

        if timeout_index is not None:
            self.match = None
            self._set_before_after(bytes(self._buffer), b"")
            return timeout_index
        raise TimeoutError("Replay expect timeout")

    def _prepare_pattern(self, pattern):
        if self._is_timeout(pattern):
            return ("timeout", pattern)
        if self._is_eof(pattern):
            return ("eof", pattern)
        if isinstance(pattern, bytes):
            return ("bytes", pattern)
        if isinstance(pattern, str):
            return ("regex", re.compile(pattern))
        if hasattr(pattern, "search"):
            return ("regex", pattern)
        return ("literal", str(pattern))

    def _timeout_index(self, patterns) -> Optional[int]:
        for idx, pattern in enumerate(patterns):
            if self._is_timeout(pattern):
                return idx
        return None

    def _is_timeout(self, pattern) -> bool:
        return pattern is pexpect.TIMEOUT

    def _is_eof(self, pattern) -> bool:
        return pattern is pexpect.EOF

    def _buffer_closed(self) -> bool:
        return self._closed

    def _set_before_after(self, before: bytes, after: bytes) -> None:
        self.before = before
        self.after = after

    # ---------------------------------------------------------------- misc api
    def read_nonblocking(self, size: int = 1024, timeout: float = 0) -> str:
        data = self._buffer[:size]
        del self._buffer[:size]
        return data.decode("utf-8", "ignore")

    def isalive(self) -> bool:
        return not self._closed

    def close(self) -> None:
        self._closed = True

    def interact(self):  # pragma: no cover - debugging convenience
        print(self._buffer.decode("utf-8", "ignore"))

    # ---------------------------------------------------------------- helpers
    def _stream_exchange(self, latency_cfg, exchange: Exchange) -> None:
        for chunk in exchange.output.chunks:
            delay = resolve_latency(latency_cfg, self.ctx) if latency_cfg else chunk.delay_ms
            if delay:
                time.sleep(delay / 1000.0)
            self._buffer.extend(base64.b64decode(chunk.data_b64))
