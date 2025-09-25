"""Replay transport that mimics the minimal pexpect interface we rely on."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import Optional

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
        if isinstance(pattern, (list, tuple)):
            return self._expect_list(pattern, timeout)
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        deadline = time.time() + (timeout or 30)
        while time.time() < deadline:
            try:
                text = self._buffer.decode("utf-8")
            except UnicodeDecodeError:
                text = self._buffer.decode("utf-8", "ignore")
            match = regex.search(text)
            if match:
                self.match = match
                self.before = text[: match.start()].encode("utf-8", "ignore")
                self.after = text[match.end() :].encode("utf-8", "ignore")
                return 0
            time.sleep(0.01)
        raise TimeoutError("Replay expect timeout")

    def expect_exact(self, pattern, timeout: Optional[int] = None) -> int:
        if isinstance(pattern, str):
            pattern = [pattern]
        elif not isinstance(pattern, (list, tuple)):
            pattern = [pattern]
        deadline = time.time() + (timeout or 30)
        while time.time() < deadline:
            text = self._buffer.decode("utf-8", "ignore")
            for idx, candidate in enumerate(pattern):
                if candidate in text:
                    self.match = None
                    self.before = text.split(candidate)[0].encode("utf-8", "ignore")
                    tail = text.split(candidate, 1)[1]
                    self.after = tail.encode("utf-8", "ignore")
                    return idx
            time.sleep(0.01)
        raise TimeoutError("Replay expect_exact timeout")

    def _expect_list(self, patterns, timeout: Optional[int]) -> int:
        compiled = [re.compile(p) if isinstance(p, str) else p for p in patterns]
        deadline = time.time() + (timeout or 30)
        while time.time() < deadline:
            text = self._buffer.decode("utf-8", "ignore")
            for idx, regex in enumerate(compiled):
                match = regex.search(text)
                if match:
                    self.match = match
                    self.before = text[: match.start()].encode("utf-8", "ignore")
                    self.after = text[match.end() :].encode("utf-8", "ignore")
                    return idx
            time.sleep(0.01)
        raise TimeoutError("Replay expect timeout")

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
