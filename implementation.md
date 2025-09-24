# implementation.md — Record & Replay for `claude_control`

> Add Talkback‑style tapes, matchers, modes, decorators, latency/error injection, and exit summaries to interactive CLI automation, built on `pexpect`. Reference parity points: options, tape behavior, startup load, latency, and exit summary come from Talkback’s README. `pexpect` capture uses `logfile_read`. `claude_control` layout and config path come from its README. ([GitHub][1])

---

## 0) Preconditions

* Python ≥3.9.
* `pexpect` already used by `claude_control`. We will intercept at the spawn/IO boundary using `logfile_read`. ([Pexpect][2])
* Repo structure exposes `src/claudecontrol/core.py`, `patterns.py`, `testing.py`, `cli.py`. Config lives at `~/.claude-control/config.json`. ([GitHub][3])

---

## 1) Dependencies

Append to `requirements.txt`:

```
pyjson5>=1.6.9        # JSON5 read/write (faster than pure-Python json5)
fastjsonschema>=2.20  # optional: schema validation
portalocker>=2.8      # cross-platform file locks
```

Rationale: JSON5 for human‑editable tapes, schema checks for CI, atomicity and cross‑process safety. JSON5 parser choices: `pyjson5` or `json-five`; `pyjson5` offers Cython speedups. ([PyJSON5][4])

---

## 2) New package layout

Create `src/claudecontrol/replay/`:

```
replay/
  __init__.py
  modes.py            # RecordMode, FallbackMode
  model.py            # dataclasses: Tape, Exchange, Chunk
  namegen.py          # TapeNameGenerator
  store.py            # TapeStore loader + TapeIndex
  matchers.py         # Command/Env/Prompt/Stdin matchers
  normalize.py        # ANSI strip, whitespace, ID/timestamp scrub
  redact.py           # secret detection + masking
  decorators.py       # input/output/tape decorators + MatchingContext
  latency.py          # pacing policies
  errors.py           # error injection policies
  record.py           # Recorder + ChunkSink (uses pexpect.logfile_read)
  play.py             # Player transport (replay)
  summary.py          # exit summary accounting
  exceptions.py       # TapeMissError, SchemaError, RedactionError
```

---

## 3) Data model

### 3.1 Dataclasses (`model.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class Chunk:
    delay_ms: int
    data_b64: str
    is_utf8: bool = True

@dataclass
class IOInput:
    kind: str  # "line" | "raw"
    data_text: Optional[str] = None
    data_b64: Optional[str] = None

@dataclass
class IOOutput:
    chunks: List[Chunk] = field(default_factory=list)

@dataclass
class Exchange:
    pre: Dict[str, Any]                # prompt signature, optional state hash
    input: IOInput
    output: IOOutput
    exit: Optional[Dict[str, Any]] = None
    dur_ms: Optional[int] = None
    annotations: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TapeMeta:
    created_at: str
    program: str
    args: List[str]
    env: Dict[str, str]
    cwd: str
    pty: Dict[str, int] | None
    tag: Optional[str] = None
    latency: Any = 0
    errorRate: Any = 0
    seed: Optional[int] = None

@dataclass
class Tape:
    meta: TapeMeta
    session: Dict[str, Any]
    exchanges: List[Exchange]
```

### 3.2 JSON5 read/write

* Use `pyjson5` to `load`/`dump` JSON5.
* Preserve UTF‑8 text where possible; store base64 for binary. Parity with Talkback’s “human‑readable when possible.” ([GitHub][1])

---

## 4) Modes (`modes.py`)

```python
from enum import Enum, auto
from typing import Protocol, Any, Callable

class RecordMode(Enum):
    NEW = auto()
    OVERWRITE = auto()
    DISABLED = auto()

class FallbackMode(Enum):
    NOT_FOUND = auto()
    PROXY = auto()

# Optional dynamic policies: Callable[[MatchingContext], RecordMode | FallbackMode]
Policy = Callable[[Any], Any]
```

Talkback parity: `record`, `fallbackMode` accept constants or functions. ([GitHub][1])

---

## 5) Naming (`namegen.py`)

```python
from dataclasses import dataclass
from pathlib import Path
import re, time, hashlib

@dataclass
class TapeNameGenerator:
    root: Path

    def __call__(self, ctx) -> Path:
        prog = Path(ctx.program).name
        key = f"{prog} {ctx.args} {ctx.cwd} {ctx.input_preview}"
        h = hashlib.sha1(key.encode()).hexdigest()[:8]
        return self.root / prog / f"unnamed-{int(time.time()*1000)}-{h}.json5"
```

Expose via `Session(..., tape_name_generator=...)`. Talkback offers a tape name generator hook. ([GitHub][1])

---

## 6) Matching + normalization

### 6.1 Normalizers (`normalize.py`)

```python
import re

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)

def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

VOLATILE_PATTERNS = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\b"), "<TS>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<ID>"),
]

def scrub(s: str) -> str:
    for pat, repl in VOLATILE_PATTERNS:
        s = pat.sub(repl, s)
    return s
```

### 6.2 Matchers (`matchers.py`)

```python
from dataclasses import dataclass
from typing import Callable, List, Dict

@dataclass
class MatchingContext:
    program: str
    args: List[str]
    env: Dict[str, str]
    cwd: str
    prompt: str

StdinMatcher = Callable[[bytes, bytes, MatchingContext], bool]
CommandMatcher = Callable[[List[str], List[str], MatchingContext], bool]

def default_stdin_matcher(a: bytes, b: bytes, ctx: MatchingContext) -> bool:
    return a.rstrip(b"\r\n") == b.rstrip(b"\r\n")

def default_command_matcher(a: List[str], b: List[str], ctx: MatchingContext) -> bool:
    return a == b
```

Config switches mirror Talkback: `allowEnv`, `ignoreEnv`, `ignoreArgs`, `ignoreStdin`, custom `stdinMatcher`, `commandMatcher`. ([GitHub][1])

---

## 7) Redaction (`redact.py`)

```python
import re

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*[^ \r\n]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),              # AWS Access Key ID
    re.compile(r"(?i)secret[^ \r\n]{6,}"),
]

def redact_bytes(b: bytes) -> bytes:
    try:
        s = b.decode("utf-8", "ignore")
    except Exception:
        return b
    for pat in SECRET_PATTERNS:
        s = pat.sub(lambda m: f"{m.group(0).split(':')[0]}: ***", s)
    return s.encode("utf-8")
```

Default on; env flag to disable for debugging.

---

## 8) Tape store + index (`store.py`)

```python
from pathlib import Path
import pyjson5, base64, threading
from .model import Tape
from .exceptions import SchemaError

class TapeStore:
    def __init__(self, root: Path):
        self.root = root
        self.tapes: list[Tape] = []
        self.paths: list[Path] = []
        self._lock = threading.RLock()
        self.used: set[Path] = set()
        self.new: set[Path] = set()

    def load_all(self):
        for p in self.root.rglob("*.json5"):
            with p.open("r", encoding="utf-8") as fh:
                obj = pyjson5.load(fh)
            tape = self._from_json(obj)
            self.tapes.append(tape)
            self.paths.append(p)

    def mark_used(self, path: Path):
        with self._lock:
            self.used.add(path)

    def mark_new(self, path: Path):
        with self._lock:
            self.new.add(path)

    # build an index keyed by normalized (program,args,env,cwd,prompt,input)
    def build_index(self, normalizer) -> dict[tuple, tuple[int, int]]:
        idx = {}
        for ti, tape in enumerate(self.tapes):
            for ei, ex in enumerate(tape.exchanges):
                key = normalizer.build_key(tape, ex)
                idx[key] = (ti, ei)
        return idx

    # ... _from_json omitted for brevity
```

Tapes load recursively on startup; edits require restart to apply. Same as Talkback. ([GitHub][1])

---

## 9) Latency and error policies

```python
# latency.py
import random
def resolve_latency(cfg, ctx) -> int:
    if callable(cfg): return int(cfg(ctx))
    if isinstance(cfg, (tuple, list)) and len(cfg) == 2:
        return random.randint(int(cfg[0]), int(cfg[1]))
    return int(cfg or 0)

# errors.py
def should_inject_error(rate_cfg, ctx) -> bool:
    if callable(rate_cfg): v = float(rate_cfg(ctx))
    else: v = float(rate_cfg or 0)
    return v > 0 and random.random()*100 < v
```

Talkback allows global and per‑tape latency and errorRate. ([GitHub][1])

---

## 10) Decorators (`decorators.py`)

```python
from typing import Callable, Any
from .matchers import MatchingContext

InputDecorator = Callable[[MatchingContext, bytes], bytes]
OutputDecorator = Callable[[MatchingContext, bytes], bytes]
TapeDecorator   = Callable[[MatchingContext, dict], dict]
```

Expose via `Session` kwargs and CLI flags. Talkback offers request/response/tape decorators. ([GitHub][1])

---

## 11) Recorder (`record.py`)

### 11.1 Chunk sink using `pexpect.logfile_read`

`pexpect.spawn` can tee every read chunk into `logfile_read`. We wrap it to capture bytes and timestamps without threads. ([Pexpect][2])

```python
# record.py
import time, base64
from .model import Chunk, IOOutput

class ChunkSink:
    def __init__(self):
        self._last = time.monotonic()
        self.chunks: list[Chunk] = []

    def write(self, b: bytes):          # pexpect calls .write() on logfile_read
        now = time.monotonic()
        delay_ms = int((now - self._last) * 1000)
        self._last = now
        is_utf8 = True
        try:
            b.decode("utf-8")
        except UnicodeDecodeError:
            is_utf8 = False
        self.chunks.append(Chunk(delay_ms=delay_ms,
                                 data_b64=base64.b64encode(b).decode("ascii"),
                                 is_utf8=is_utf8))

    def flush(self):                     # pexpect may call it
        pass

    def to_output(self) -> IOOutput:
        return IOOutput(chunks=self.chunks)
```

### 11.2 Recorder wrapper

```python
from dataclasses import dataclass
from pathlib import Path
import pyjson5, portalocker, time
from .normalize import strip_ansi, collapse_ws, scrub
from .redact import redact_bytes
from .namegen import TapeNameGenerator
from .modes import RecordMode
from .model import Tape, TapeMeta, Exchange, IOInput

@dataclass
class Recorder:
    session: "Session"           # forward ref
    tapes_path: Path
    mode: RecordMode
    namegen: TapeNameGenerator

    def start(self):
        # attach chunk sink to spawned child
        sink = ChunkSink()
        self.session.child.logfile_read = sink  # pexpect hook
        self._sink = sink

    def on_send(self, data: bytes, kind: str, ctx, pre_prompt: str):
        self._start_ts = time.monotonic()
        self._cur_input = IOInput(kind, data_text=data.decode("utf-8", "ignore"))
        self._pre = {"prompt": pre_prompt}

    def on_exchange_end(self, exit_info=None):
        out = self._sink.to_output()
        dur_ms = int((time.monotonic() - self._start_ts) * 1000)
        ex = Exchange(pre=self._pre, input=self._cur_input, output=out, exit=exit_info, dur_ms=dur_ms)
        self._append_exchange(ex)

    def _append_exchange(self, ex: Exchange):
        # choose path
        path = self.namegen(self.session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tape = self._build_tape_skeleton()
        tape.exchanges.append(ex)
        self._write_tape(path, tape)

    def _build_tape_skeleton(self) -> Tape:
        meta = TapeMeta(
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
            program=self.session.program, args=self.session.args,
            env=self.session.env, cwd=str(self.session.cwd),
            pty={"rows": self.session.rows, "cols": self.session.cols},
            tag=None, latency=self.session.latency, errorRate=self.session.error_rate,
            seed=self.session.seed,
        )
        return Tape(meta=meta, session={"version": self.session.version}, exchanges=[])
```

Notes:

* Call `Recorder.start()` after spawning the child.
* Call `on_send()` before writing to child.
* Call `on_exchange_end()` after the prompt match or EOF.

---

## 12) Player transport (`play.py`)

We decouple IO via a `Transport` interface to avoid depending on `pexpect` in replay mode.

```python
# play.py
import re, base64, time, threading
from dataclasses import dataclass
from typing import Optional
from .store import TapeStore
from .latency import resolve_latency
from .modes import FallbackMode
from .exceptions import TapeMissError

class Transport:
    def send(self, b: bytes) -> int: ...
    def sendline(self, s: str) -> int: ...
    def expect(self, pattern, timeout=None): ...
    def isalive(self) -> bool: ...
    def close(self): ...
    before: bytes
    after: bytes
    match: Optional[re.Match]

@dataclass
class ReplayTransport(Transport):
    store: TapeStore
    index: dict
    ctx: any                 # MatchingContext
    latency_cfg: any
    _buffer: bytearray = bytearray()
    before: bytes = b""
    after: bytes = b""
    match: Optional[re.Match] = None
    _closed: bool = False

    def _stream_chunks(self, chunks):
        for c in chunks:
            time.sleep(resolve_latency(self.latency_cfg, self.ctx) / 1000.0 if self.latency_cfg else c.delay_ms/1000.0)
            self._buffer.extend(base64.b64decode(c.data_b64))

    def send(self, b: bytes) -> int:
        self.before = b
        # use ctx + input to find exchange
        key = self._build_key(b)
        hit = self.index.get(key)
        if not hit:
            raise TapeMissError(f"no tape for {key}")
        tape_i, ex_i = hit
        ex = self.store.tapes[tape_i].exchanges[ex_i]
        t = threading.Thread(target=self._stream_chunks, args=(ex.output.chunks,), daemon=True)
        t.start()
        return len(b)

    def sendline(self, s: str) -> int:
        return self.send((s + "\n").encode())

    def expect(self, pattern, timeout=None):
        deadline = time.time() + (timeout or 30)
        pat = re.compile(pattern) if isinstance(pattern, str) else pattern
        while time.time() < deadline:
            m = pat.search(self._buffer.decode("utf-8", "ignore"))
            if m:
                self.match = m
                self.after = self._buffer[m.end():]
                return 0
            time.sleep(0.01)
        raise TimeoutError("replay expect timeout")

    def isalive(self) -> bool:
        return not self._closed

    def close(self):
        self._closed = True
```

---

## 13) Session integration (`core.py`)

Introduce a transport seam. Keep defaults identical.

```python
# core.py (excerpt)
from pathlib import Path
from .replay.modes import RecordMode, FallbackMode
from .replay.store import TapeStore
from .replay.namegen import TapeNameGenerator
from .replay.record import Recorder, ChunkSink
from .replay.play import ReplayTransport
from .replay.summary import print_summary

class Session:
    def __init__(self, program: str, args=None, env=None, cwd=None,
                 tapes_path: str = "./tapes",
                 record: RecordMode = RecordMode.NEW,
                 fallback: FallbackMode = FallbackMode.NOT_FOUND,
                 tape_name_generator: TapeNameGenerator | None = None,
                 allow_env=None, ignore_env=None, ignore_args=None, ignore_stdin=False,
                 stdin_matcher=None, command_matcher=None,
                 input_decorator=None, output_decorator=None, tape_decorator=None,
                 latency=0, error_rate=0, summary=True, debug=False, silent=False, **kw):
        # existing init...
        self._replay_on = record != RecordMode.DISABLED or fallback == FallbackMode.PROXY
        self._tapes_path = Path(tapes_path)
        self._summary = summary
        self._recorder = None
        self._store = None
        self._index = None
        self._tape_name_gen = tape_name_generator or TapeNameGenerator(self._tapes_path)
        self.latency = latency
        self.error_rate = error_rate

    def _spawn_child(self):
        # existing pexpect.spawn(...)
        child = pexpect.spawn(self.program, self.args or [], cwd=self.cwd, env=self.env, encoding=None)
        if self._replay_on and self.record != RecordMode.DISABLED:
            self._recorder = Recorder(self, self._tapes_path, self.record, self._tape_name_gen)
            self._recorder.start()  # attaches logfile_read sink
        self.child = child

    def send(self, b: bytes) -> int:
        if self._recorder:
            self._recorder.on_send(b, "raw", self._ctx(), pre_prompt=self._current_prompt())
        return self.child.send(b)

    def sendline(self, s: str) -> int:
        if self._recorder:
            self._recorder.on_send(s.encode(), "line", self._ctx(), pre_prompt=self._current_prompt())
        return self.child.sendline(s)

    def expect(self, pat, timeout=None):
        idx = self.child.expect(pat, timeout=timeout)
        if self._recorder:
            exit_info = None
            if not self.child.isalive(): exit_info = {"code": self.child.exitstatus, "signal": self.child.signalstatus}
            self._recorder.on_exchange_end(exit_info)
        return idx

    def close(self):
        try:
            self.child.close()
        finally:
            if self._summary:
                print_summary(self._store)
```

Replay mode without spawning:

```python
    def _use_replay(self):
        self._store = TapeStore(self._tapes_path)
        self._store.load_all()
        self._index = self._store.build_index(normalizer=self._normalizer)
        self.child = ReplayTransport(self._store, self._index, self._ctx(), self.latency)
```

Load replay when `record == DISABLED` or CLI `play` subcommand selects it. Miss policy: if no match and `fallback==PROXY`, spawn live child and attach recorder; else raise. Mirrors Talkback fallback. ([GitHub][1])

---

## 14) CLI integration (`src/claudecontrol/cli.py`)

Add subcommands and flags.

```python
import argparse
from .core import Session
from .replay.modes import RecordMode, FallbackMode

def main():
    p = argparse.ArgumentParser("ccontrol")
    sub = p.add_subparsers(dest="cmd")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tapes", default="./tapes")
    common.add_argument("--record", choices=["new","overwrite","disabled"], default="new")
    common.add_argument("--fallback", choices=["not_found","proxy"], default="not_found")
    common.add_argument("--latency")
    common.add_argument("--error-rate", type=float, default=0)
    common.add_argument("--summary", action="store_true", default=True)
    # rec/play/proxy
    for name in ["rec","play","proxy"]:
        sp = sub.add_parser(name, parents=[common])
        sp.add_argument("program")
        sp.add_argument("progargs", nargs=argparse.REMAINDER)
    args = p.parse_args()

    rec = {"new":RecordMode.NEW, "overwrite":RecordMode.OVERWRITE, "disabled":RecordMode.DISABLED}[args.record]
    fb  = {"not_found":FallbackMode.NOT_FOUND, "proxy":FallbackMode.PROXY}[args.fallback]

    if args.cmd == "play":   rec = RecordMode.DISABLED
    if args.cmd == "proxy":  rec = RecordMode.NEW; fb = FallbackMode.PROXY

    with Session(args.program, args.progargs, tapes_path=args.tapes,
                 record=rec, fallback=fb, latency=_parse_latency(args.latency),
                 error_rate=args.error_rate, summary=args.summary) as s:
        # interactive passthrough, or run scripted flow
        s.interactive()
```

Talkback exposes similar options. ([GitHub][1])

---

## 15) Summary (`summary.py`)

```python
def print_summary(store):
    if not store: return
    print("===== SUMMARY (claude_control) =====")
    if store.new:
        print("New tapes:"); [print(f"- {p.name}") for p in sorted(store.new)]
    if store.used:
        unused = set(store.paths) - store.used
        if unused:
            print("Unused tapes:"); [print(f"- {p.name}") for p in sorted(unused)]
```

Exit summary mirrors Talkback. ([GitHub][1])

---

## 16) Miss policy

* `record=DISABLED`, `fallback=NOT_FOUND`: raise `TapeMissError` on match miss.
* `record=DISABLED`, `fallback=PROXY`: run live, do not persist.
* `record=NEW/OVERWRITE`: on miss match, proxy live; persist per mode.

Talkback semantics. ([GitHub][1])

---

## 17) Prompt segmentation

* Start a new **exchange** at process start and after every `send/sendline`.
* End an exchange when a known prompt matches `expect`, on timeout, or on process exit.
* Use `patterns.py` existing prompt helpers when available.

`pexpect.expect` supports EOF/TIMEOUT patterns and maintains `before/after/match`. Use those to implement robust boundaries. ([Pexpect][2])

---

## 18) Config

Extend `~/.claude-control/config.json` with default replay settings:

```json
{
  "replay": {
    "tapes_path": "~/claude-control/tapes",
    "record": "new",
    "fallback": "not_found",
    "latency": 0,
    "error_rate": 0,
    "summary": true
  }
}
```

Path and config location per README. ([GitHub][3])

---

## 19) Validation (optional)

```python
import fastjsonschema

SCHEMA = {...}  # from requirements.md Appendix B
validate = fastjsonschema.compile(SCHEMA)
validate(tape_obj)  # raise on violation
```

---

## 20) Tests

### 20.1 Unit: normalizers and matchers

```python
def test_strip_ansi():
    from claudecontrol.replay.normalize import strip_ansi
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"

def test_stdin_matcher():
    from claudecontrol.replay.matchers import default_stdin_matcher, MatchingContext
    ctx = MatchingContext("prog", [], {}, "/", ">")
    assert default_stdin_matcher(b"select 1\r\n", b"select 1\n", ctx)
```

### 20.2 Integration: record → replay

```python
def test_sqlite_record_then_replay(tmp_path):
    from claudecontrol import Session
    tapes = tmp_path/"tapes"

    # record
    with Session("sqlite3", args=["-batch"], tapes_path=tapes, record=RecordMode.NEW) as s:
        s.expect("sqlite>")
        s.sendline("select 1;")
        s.expect("sqlite>")
    # replay
    with Session("sqlite3", args=["-batch"], tapes_path=tapes,
                 record=RecordMode.DISABLED, fallback=FallbackMode.NOT_FOUND) as s:
        s.expect("sqlite>")
        s.sendline("select 1;")
        assert s.expect("sqlite>") == 0
```

### 20.3 CLI smoke

```bash
ccontrol rec --tapes ./tapes sqlite3 -batch
ccontrol play --tapes ./tapes --record disabled --fallback not_found sqlite3 -batch
```

---

## 21) Performance

* Build an in‑memory index once at startup.
* Latency resolution uses per‑chunk or global pacing. Keep jitter ≤50 ms.
* Avoid threads with live PTY. Use `logfile_read` for capture. Threading only in `ReplayTransport` to stream chunks because no PTY is involved; pexpect thread note requires single‑thread interaction with live child. ([Pexpect][5])

---

## 22) Security

* Redact secrets before persisting.
* Provide `CLAUDECONTROL_REDACT=0` to disable.
* Document risk for binary TTY apps.

---

## 23) Migration plan

1. Land `replay/` package and unit tests.
2. Refactor `Session` to use transport seam. Default behavior unchanged.
3. Attach recorder in live mode via `logfile_read`.
4. Add CLI subcommands.
5. Enable exit summaries.
6. Write docs and examples.

---

## 24) Developer checklist

* [ ] Add dependencies and import guards.
* [ ] Create `replay/` package files.
* [ ] Implement `Recorder` and hook into `Session`.
* [ ] Implement `ReplayTransport` + miss policy.
* [ ] Build `TapeStore` and index.
* [ ] Wire CLI and config.
* [ ] Add tests for record/replay and summary.
* [ ] Document limits (ncurses apps, Windows PTY).

---

## 25) Reference points

* Talkback options: `record`, `fallbackMode`, matchers, decorators, latency, errorRate, `silent`, `summary`; tape load behavior and edit‑and‑restart requirement; exit summary example. ([GitHub][1])
* `pexpect` spawn, `expect`, EOF/TIMEOUT, and `logfile_read` hooks used for capture. ([Pexpect][2])
* `claude_control` layout and config path used for integration points. ([GitHub][3])

---

## 26) Appendix A — Sample tape (JSON5)

```json5
{
  meta: {
    createdAt: "2025-09-23T12:34:56.789Z",
    program: "sqlite3",
    args: ["-batch"],
    env: { LANG: "en_US.UTF-8" },
    cwd: "/home/jim/project",
    pty: { rows: 24, cols: 120 },
    tag: "smoke",
    latency: 0,
    errorRate: 0,
    seed: 42
  },
  session: { version: "claude_control 0.1.0", platform: "darwin-arm64" },
  exchanges: [
    {
      pre: { prompt: "sqlite> " },
      input: { kind: "line", dataText: "select 1;" },
      output: {
        chunks: [
          { delay_ms: 5, data_b64: "MQo=", is_utf8: true },      // "1\n"
          { delay_ms: 3, data_b64: "c3FsaXRlPiA=", is_utf8: true } // "sqlite> "
        ]
      },
      exit: null,
      dur_ms: 12,
      annotations: {}
    }
  ]
}
```

---

## 27) Appendix B — Minimal diffs

**`src/claudecontrol/__init__.py`**

```diff
-from .core import Session, control
+from .core import Session, control
+from .replay.modes import RecordMode, FallbackMode
```

**`setup.py`**: no change to `console_scripts` if `ccontrol` exists; else add:

```python
entry_points={"console_scripts": ["ccontrol=claudecontrol.cli:main"]},
```

README add a short “Record & Replay” section to document `rec/play/proxy`.

---

## 28) Implementation notes

* Keep `encoding=None` in live spawn to capture raw bytes; decode only for matching and display. `pexpect` docs: `logfile_read` receives read chunks; provide encoding if you set `.logfile_read` to a text stream. We pass a binary writer object. ([Pexpect][2])
* Use `pexpect.EOF` and `pexpect.TIMEOUT` in `expect()` lists to avoid exceptions during segmentation when needed. ([Pexpect][2])
* Tapes are loaded once at startup; edit requires restart. Matches Talkback behavior. ([GitHub][1])

---

This file is self‑sufficient. Implement the listed modules, wire the seam in `Session`, add CLI entries, then run the integration test to verify record→replay parity.

[1]: https://github.com/ijpiantanida/talkback "GitHub - ijpiantanida/talkback: A simple HTTP proxy that records and playbacks requests"
[2]: https://pexpect.readthedocs.io/en/stable/api/pexpect.html "Core pexpect components — Pexpect 4.8 documentation"
[3]: https://github.com/jimmc414/claude_control "GitHub - jimmc414/claude_control: ClaudeControl is a Python library built on pexpect that automatically discovers, fuzz tests, and automates any command-line program using pattern matching and session management."
[4]: https://pyjson5.readthedocs.io/?utm_source=chatgpt.com "PyJSON5 1.6.9 documentation"
[5]: https://pexpect.readthedocs.io/en/stable/commonissues.html?utm_source=chatgpt.com "Common problems — Pexpect 4.8 documentation"
