# requirements.md — Add Talkback‑style record & replay to `claude_control`

## Goal

Add deterministic recording and playback of interactive CLI sessions to `claude_control`, mirroring Talkback’s “tapes + matchers + modes + decorators + latency/error injection + exit summary,” adapted from HTTP to terminal I/O. Preserve all current capabilities (investigation, testing, automation) and make record/replay a first‑class feature. ([GitHub][1]) ([GitHub][2])

---

## Scope

* Record interactive sessions driven through `pexpect` into human‑editable “tapes.”
* Replay sessions without launching the real program, or fall back to the real program and optionally create/overwrite tapes.
* Provide matchers, normalizers, and decorators for CLI context (program, args, env, cwd, prompt, stdin).
* Support synthetic latency and probabilistic error injection.
* Emit an exit summary listing new and unused tapes.
* Expose both library API and CLI flags to control the feature. ([GitHub][1])

Out of scope (v1): filesystem virtualization, full TTY app virtualization (ncurses editors like `vim`), Windows PTY parity. See “Limits”.

---

## Design overview

### Concepts (HTTP → CLI mapping)

| Talkback                                     | CLI analogue                                                                                |               |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------- |
| Request                                      | One **exchange**: agent input -> program output until the next stable prompt or termination |               |
| Response                                     | The captured output chunk stream plus exit status (if process ended)                        |               |
| Tape file (JSON5)                            | Tape file (JSON5) storing `meta`, `session`, `exchanges[]`                                  |               |
| url/body matchers                            | command/env/cwd/prompt matchers and stdin matchers                                          |               |
| request/response/tape decorators             | input/output/tape decorators                                                                |               |
| Record modes: `NEW`, `OVERWRITE`, `DISABLED` | Same semantics                                                                              |               |
| Fallback modes: `NOT_FOUND`, `PROXY`         | Same semantics: error vs run real program                                                   |               |
| Latency / errorRate                          | Synthetic output pacing and injected failures                                               |               |
| Exit summary                                 | List new and unused tapes on process exit                                                   | ([GitHub][1]) |

### High‑level flow

1. **Session start**: wrap `claude_control.Session` spawn with a **Recorder/Player**.
2. **Recording**: segment terminal I/O into exchanges keyed by context; write JSON5 tapes at close.
3. **Playback**: on each input, match to a stored exchange; stream recorded output with optional latency; return recorded exit code on termination.
4. **Miss policy**: controlled by record/fallback modes.
5. **Summary**: at shutdown, print new/unused tapes. ([GitHub][1])

---

## New modules

```
src/claudecontrol/replay/
  __init__.py
  modes.py           # RecordMode, FallbackMode enums
  tapes.py           # Tape, Exchange, TapeStore, TapeIndex
  record.py          # Recorder (wraps pexpect spawn & I/O)
  play.py            # Player (replay engine, output pacing)
  matchers.py        # CommandMatcher, EnvMatcher, PromptMatcher, StdinMatcher
  normalize.py       # ANSI stripping, whitespace, timestamp/PID scrubbers
  decorators.py      # InputDecorator, OutputDecorator, TapeDecorator hooks
  latency.py         # Latency policies
  errors.py          # Error injection policies
  redact.py          # Secret detectors/redactors
  summary.py         # ExitSummary (new/unused)
  namegen.py         # TapeNameGenerator interface + defaults
```

---

## Data model

### Tape file format (JSON5)

Use JSON5 for human‑editable tapes with comments and trailing commas. Same justification as Talkback. ([GitHub][1])

```json5
{
  meta: {
    createdAt: "2025-09-23T12:34:56.789Z",
    program: "sqlite3",
    args: ["-batch"],
    env: {LANG: "en_US.UTF-8"},
    cwd: "/Users/jim/proj",
    pty: {rows: 24, cols: 120},
    tag: "happy-path",
    latency: 0,            // global per-tape override
    errorRate: 0           // 0..100 probability
  },
  session: {
    platform: "darwin-arm64",
    version: "claude_control 0.1.0",
    seed: 12345
  },
  exchanges: [
    {
      pre: {prompt: "sqlite> ", stateHash: "ab12..."},
      input: {type: "line", dataText: "select 1;", dataBytesB64: null},
      output: {
        chunks: [
          {"delay_ms": 12, "dataB64": "MQo=", "isUtf8": true}, // "1\n"
          {"delay_ms": 3,  "dataB64": "c3FsaXRlPiA=", "isUtf8": true} // "sqlite> "
        ]
      },
      exit: null,               // or {code: 0, signal: null}
      dur_ms: 25,
      annotations: {note: "baseline query"}
    }
  ]
}
```

Rules:

* Prefer text if UTF‑8; store base64 for binary. Keep ANSI by default; allow normalization on match. ([GitHub][1])
* Pretty‑print JSON bodies when detected (parity with Talkback “pretty printing” intent). ([GitHub][1])

### Index

`TapeIndex` builds a hash → exchange map using normalized `(program, args*, env*, cwd*, prompt*, input)`.

---

## Matching

### Defaults

* **CommandMatcher**: normalize whitespace, expand `~`, resolve relative paths against `cwd`, strip volatile arg values via regex list (timestamps, UUIDs).
* **EnvMatcher**: honor `allowEnv` / `ignoreEnv` lists. Default ignores `PWD`, `SHLVL`, `RANDOM` equivalents.
* **PromptMatcher**: exact text or regex; optional ANSI‑stripped compare.
* **StdinMatcher**: exact for `sendline`; byte‑for‑byte for raw `send`. Optional normalizers (trim trailing CRLF).
* **StateHash**: optional extra key (user‑supplied function) to encode app mode.

### Configuration knobs (Talkback parity)

* `allowEnv`, `ignoreEnv` (like `allowHeaders`/`ignoreHeaders`). ([GitHub][1])
* `ignoreArgs`, `ignoreStdin` (like `ignoreQueryParams` / `ignoreBody`). ([GitHub][1])
* `stdinMatcher`, `commandMatcher` (like `bodyMatcher` / `urlMatcher`). ([GitHub][1])

---

## Decorators and hooks

* `inputDecorator(ctx, input) -> input`
* `outputDecorator(ctx, output) -> output`
* `tapeDecorator(ctx, tape) -> tape`
  `ctx` includes `(program, args, env, cwd, prompt, exchangeIndex, tapePath)`. Mirrors Talkback request/response/tape decorators. ([GitHub][1])

---

## Modes

### RecordMode

* `NEW`: record only when no match. Keep existing exchanges.
* `OVERWRITE`: replace on match.
* `DISABLED`: never write. Use `fallbackMode` to handle misses. Mirrors Talkback. ([GitHub][1])

### FallbackMode

* `NOT_FOUND`: raise `TapeMissError`.
* `PROXY`: run the real program, capture, and either:

  * if `record=DISABLED`: return live output only;
  * if `record=NEW/OVERWRITE`: also persist a new/updated exchange.
    Parallels Talkback’s fallback behavior. ([GitHub][1])

---

## Latency and error injection

* **Latency**: global or per‑tape. Accept `int | [min,max] | callable(ctx)->ms`. Pacing applies between chunks to simulate streaming. ([GitHub][1])
* **ErrorRate**: `0..100 | callable(ctx)->0..100`. Inject by:

  * emitting recorded output up to a point and then raising a synthetic error,
  * or returning a configured non‑zero exit code.
    Parities Talkback semantics. ([GitHub][1])

---

## Exit summary

On process exit print:

* New tapes created this run.
* Unused tapes (loaded but never matched). Mirrors Talkback’s exit summary. Toggle via `summary=True/False`. ([GitHub][1])

Format:

```
===== SUMMARY (claude_control) =====
New tapes:
- sqlite3/select-1.json5
Unused tapes:
- git/status.json5
```

---

## Library API changes

### `Session(...)` additions

```python
Session(
  program: str,
  args: list[str] = ...,
  env: dict[str, str] | None = None,
  cwd: str | None = None,
  # recording/replay
  tapes_path: str = "./tapes",
  record: RecordMode = RecordMode.NEW,
  fallback: FallbackMode = FallbackMode.NOT_FOUND,
  name: str | None = None,                 # server name analogue
  tape_name_generator: TapeNameGenerator | None = None,
  # matching
  allow_env: list[str] | None = None,
  ignore_env: list[str] | None = None,
  ignore_args: list[int | str] | None = None,
  ignore_stdin: bool = False,
  stdin_matcher: Callable[[bytes, bytes, MatchingContext], bool] | None = None,
  command_matcher: Callable[[list[str], list[str], MatchingContext], bool] | None = None,
  # decorators
  input_decorator: Callable[..., bytes] | None = None,
  output_decorator: Callable[..., bytes] | None = None,
  tape_decorator: Callable[..., dict] | None = None,
  # simulation
  latency: int | tuple[int, int] | Callable = 0,
  error_rate: int | Callable = 0,
  # logging
  silent: bool = False,
  summary: bool = True,
  debug: bool = False,
)
```

Notes:

* Backward compatible defaults.
* When `record is DISABLED` and `fallback is NOT_FOUND`, `Session.send*` raises on miss.

### Programmatic recorder/player

```python
from claudecontrol.replay import Recorder, Player, TapeStore
```

* `Recorder(session).enable()` to start capturing.
* `Player(session).enable()` to override process with replay.

---

## CLI changes (`ccontrol`)

New subcommands and flags:

```
ccontrol rec -- program [args...]         # record with defaults
ccontrol play -- program [args...]        # playback only (fail on miss)
ccontrol proxy -- program [args...]       # playback, miss -> run real program
ccontrol tapes list [--used|--unused]
ccontrol tapes validate [--strict]
ccontrol tapes redact --inplace
# global flags
--tapes <dir> --record {new,overwrite,disabled} --fallback {not_found,proxy}
--latency <ms|min,max> --error-rate <0-100> --silent --summary[=1|0] --debug
```

* Defaults mirror Talkback (`record=NEW`, `fallback=NOT_FOUND`, `summary=True`). ([GitHub][1])

---

## Segmentation strategy (exchanges)

* Start a new exchange when:

  * we call `send`/`sendline`, or
  * the process starts (implicit first exchange for startup banner), or
  * the previous exchange ended in termination.
* End an exchange when:

  * a prompt pattern is observed (`expect` success on configured prompts), or
  * timeout elapses and no more output, or
  * process exits.
* Capture timings between output chunks for realistic replay.

Prompt sources:

* Explicit prompts passed to `Session.expect`.
* Configured `default_prompts` per program.
* Heuristics during “investigation” mode to auto‑learn prompts.

---

## Normalization

Built‑in transforms for matching and diff/pretty‑print:

* Strip ANSI escape codes (optional).
* Collapse whitespace runs to a single space (optional).
* Regex redactions for timestamps, PIDs, hex IDs.
* JSON pretty‑print detection for lines that parse as JSON.

---

## Secret handling

* `redact.py` with default detectors: password prompts, tokens, AWS keys.
* Replace secrets with `***` before persisting.
* Provide `CLAUDECONTROL_REDACT=0` to disable for debugging.

---

## Tape naming

Default: `tapes/{program}/{verb-or-hash}/unnamed-<epoch>.json5`.
Pluggable `TapeNameGenerator(ctx) -> relpath` to customize, mirroring Talkback’s generator concept. ([GitHub][1])

---

## Concurrency and locking

* Atomic writes: write to temp file then `rename`.
* File lock per tape on overwrite.
* In‑memory `TapeIndex` guarded by RW lock.

---

## Performance targets

* Index load ≤ 200 ms per 1,000 exchanges.
* Match time ≤ 2 ms per exchange with hashing + normalized keys.
* Streaming replay keeps ≤ 50 ms jitter per chunk with latency enabled.

---

## Telemetry

* Debug logs for: match hits/misses, normalizations applied, decorators called, error injections.
* `--silent` suppresses mid‑request logs (Talkback parity). ([GitHub][1])

---

## Testing

### Unit

* Matchers with dynamic values ignored.
* Decorators compose and run in order.
* Latency and error policies deterministic with seeded RNG.

### Integration

* Record/playback for:

  * `python -q` REPL basic I/O,
  * `sqlite3` simple query,
  * `git status` and `git log -1`,
  * `ssh` dry‑run or mock server.
* CI config:

  * Default `record=DISABLED`, `fallback=NOT_FOUND` to fail on missing tapes (mirrors best practice in Talkback usage). ([GitHub][1])

### Tooling

* `tapes validate`: schema check, orphan exchanges, decoding errors.
* `tapes diff`: compare two tapes after normalization.

---

## Migration plan

1. Introduce new modules and wire behind feature flags.
2. Land `Session` API additions with defaults that preserve current behavior.
3. Add CLI subcommands.
4. Ship with experimental label. Dogfood on `tests/` using `sqlite3` and `git`.
5. Flip default `summary=True` once stable. ([GitHub][1])

---

## Limits and mitigations

* **Curses/full‑screen UIs**: Supported only as raw stream; matching is command‑line oriented. Document best effort.
* **Windows**: PTY support is limited; prioritize POSIX. Suggest `wexpect` in a later phase.
* **Filesystem side effects**: Not captured. Recommend running in temp `cwd` and snapshotting dirs externally if needed.

---

## Acceptance criteria

* Record a session with `sqlite3` and replay it offline with byte‑for‑byte output match under default normalizers.
* Modes behave as specified:

  * `NEW` adds tape on miss, `OVERWRITE` replaces, `DISABLED` never writes.
  * `NOT_FOUND` raises on miss; `PROXY` executes real program.
* Matchers and decorators programmable via API and CLI.
* Latency and errorRate influence playback as configured.
* Exit summary reports new and unused tapes.
* Tapes are JSON5, load at startup, edits require restart (parity). ([GitHub][1])

---

## References

* Talkback README: options, matchers, decorators, latency/errorRate, summary, JSON5 tapes with `meta/req/res`, and load/edit behavior. ([GitHub][1])
* `claude_control` current goals and `pexpect` foundation, interactive menu `ccontrol`, session automation and testing claims. ([GitHub][2])

---

## Appendix A — Minimal examples

### Record

```bash
ccontrol rec -- --tapes ./tapes --record new sqlite3 -batch
# interact...
# Ctrl-D to exit -> summary prints
```

### Playback only

```bash
ccontrol play -- --tapes ./tapes --record disabled --fallback not_found sqlite3 -batch
```

### Library

```python
from claudecontrol import Session
from claudecontrol.replay import RecordMode, FallbackMode

with Session(
    "sqlite3", args=["-batch"],
    tapes_path="./tapes",
    record=RecordMode.NEW,
    fallback=FallbackMode.NOT_FOUND,
    summary=True,
) as s:
    s.expect("sqlite>")
    s.sendline("select 1;")
    s.expect("sqlite>")
```

---

## Appendix B — JSON Schema (draft, abbreviated)

```json
{
  "$id": "https://claudecontrol.io/schemas/cli-tape.json",
  "type": "object",
  "required": ["meta","session","exchanges"],
  "properties": {
    "meta": {
      "type": "object",
      "required": ["createdAt","program","cwd"],
      "properties": {
        "createdAt": {"type":"string","format":"date-time"},
        "program": {"type":"string"},
        "args": {"type":"array","items":{"type":"string"}},
        "env": {"type":"object","additionalProperties":{"type":"string"}},
        "cwd": {"type":"string"},
        "pty": {"type":"object","properties":{"rows":{"type":"integer"},"cols":{"type":"integer"}}},
        "tag": {"type":"string"},
        "latency": {},
        "errorRate": {}
      }
    },
    "session": {"type":"object"},
    "exchanges": {
      "type":"array",
      "items": {
        "type":"object",
        "required": ["input","output"],
        "properties": {
          "pre": {"type":"object"},
          "input": {"type":"object","required":["type"],"properties":{
            "type":{"enum":["line","raw"]},
            "dataText":{"type":["string","null"]},
            "dataBytesB64":{"type":["string","null"]}
          }},
          "output": {"type":"object","properties":{
            "chunks":{"type":"array","items":{"type":"object","properties":{
              "delay_ms":{"type":"integer"},
              "dataB64":{"type":"string"},
              "isUtf8":{"type":"boolean"}
            }}}
          }},
          "exit": {"type":["object","null"],"properties":{"code":{"type":"integer"},"signal":{"type":["string","null"]}}},
          "dur_ms": {"type":"integer"}
        }
      }
    }
  }
}
```

---

[1]: https://github.com/ijpiantanida/talkback "GitHub - ijpiantanida/talkback: A simple HTTP proxy that records and playbacks requests"
[2]: https://github.com/jimmc414/claude_control "GitHub - jimmc414/claude_control: ClaudeControl is a Python library built on pexpect that automatically discovers, fuzz tests, and automates any command-line program using pattern matching and session management."
