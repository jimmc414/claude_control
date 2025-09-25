# ClaudeControl API & Interface Documentation

This guide describes the primary public surfaces of `claude_control`, covering the core session API, record/replay extensions, supporting utilities, CLI entry points, configuration, and error types. It reflects the Talkback-style recording enhancements while preserving existing automation and investigation capabilities.

---

## Core Session Interface (`src/claudecontrol/core.py`)

### `Session`
Creates and manages an interactive subprocess controlled through `pexpect`. Replay is optional and off by default; enabling it adds deterministic tape playback and recording.

```python
Session(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    encoding: str = "utf-8",
    dimensions: tuple[int, int] = (24, 80),
    session_id: Optional[str] = None,
    persist: bool = True,
    stream: bool = False,
    *,
    replay: bool = False,
    tapes_path: Optional[str] = None,
    record: RecordMode = RecordMode.DISABLED,
    fallback: FallbackMode = FallbackMode.NOT_FOUND,
    summary: bool = True,
    name: Optional[str] = None,
    tape_name_generator: Optional[TapeNameGenerator] = None,
    allow_env: Optional[List[str]] = None,
    ignore_env: Optional[List[str]] = None,
    ignore_args: Optional[List[Union[int, str]]] = None,
    ignore_stdin: bool = False,
    stdin_matcher: Optional[StdinMatcher] = None,
    command_matcher: Optional[CommandMatcher] = None,
    input_decorator: Optional[InputDecorator] = None,
    output_decorator: Optional[OutputDecorator] = None,
    tape_decorator: Optional[TapeDecorator] = None,
    latency: Union[int, tuple[int, int], Callable] = 0,
    error_rate: Union[int, Callable] = 0,
)
```

**Key parameters**
- **Core execution:** `command`, `timeout`, `cwd`, `env`, `encoding`, `dimensions` describe the subprocess to spawn and its terminal geometry.【F:src/claudecontrol/core.py†L44-L91】
- **Session identity:** `session_id`, `persist`, and `name` control lifecycle tracking via the global registry and optional naming for summaries.【F:src/claudecontrol/core.py†L60-L115】
- **Streaming:** `stream=True` creates a named pipe that mirrors input/output events and tags errors using compiled regexes.【F:src/claudecontrol/core.py†L118-L220】
- **Replay root:** `replay=True` switches the initial transport to tape playback when `record` is disabled; otherwise live processes are spawned and optionally recorded to `tapes_path` (defaults to `./tapes`).【F:src/claudecontrol/core.py†L196-L224】【F:src/claudecontrol/core.py†L231-L276】
- **Record & fallback modes:** `record` selects how new exchanges are persisted (`NEW`, `OVERWRITE`, `DISABLED`), while `fallback` dictates behavior on tape misses (`NOT_FOUND` raises, `PROXY` runs the real program).【F:src/claudecontrol/core.py†L69-L88】【F:src/claudecontrol/core.py†L296-L352】
- **Matching controls:** `allow_env`, `ignore_env`, `ignore_args`, `ignore_stdin`, `stdin_matcher`, and `command_matcher` customize key construction when resolving exchanges, mirroring Talkback’s matcher knobs.【F:src/claudecontrol/core.py†L92-L111】【F:src/claudecontrol/replay/store.py†L112-L204】
- **Decorators & normalization:** `input_decorator`, `output_decorator`, and `tape_decorator` hook into recording to mutate payloads, redact data, or tag metadata.【F:src/claudecontrol/core.py†L104-L110】【F:src/claudecontrol/replay/record.py†L53-L194】
- **Simulation:** `latency` and `error_rate` configure synthetic pacing and probabilistic error injection for playback, with per-tape overrides available in metadata.【F:src/claudecontrol/core.py†L86-L89】【F:src/claudecontrol/replay/play.py†L19-L105】
- **Summary:** `summary=True` prints a Talkback-style exit report listing new and unused tapes when the session closes.【F:src/claudecontrol/core.py†L602-L640】

**Side effects**
- Spawns a `pexpect.spawn` process or a `ReplayTransport` surrogate.
- Registers the session globally when `persist=True`.
- Initializes a `TapeStore`, builds tape indexes, and attaches a `Recorder` when recording is enabled.【F:src/claudecontrol/core.py†L200-L233】【F:src/claudecontrol/replay/record.py†L59-L133】

### Core Methods
- `send(text: str, delay: float = 0) -> None`: Sends raw input. When replay is active, resolves the exchange against tapes and either streams recorded output or proxies to a live child on misses (per fallback). Live sessions optionally record the exchange and can simulate slow typing via `delay`.【F:src/claudecontrol/core.py†L320-L372】
- `sendline(line: str = "") -> None`: Convenience wrapper adding a newline; records exchanges when live sessions are capturing.【F:src/claudecontrol/core.py†L374-L383】
- `expect(patterns, timeout=None, searchwindowsize=None) -> int`: Waits for regex patterns. Works against both live `pexpect` children and the replay transport. Records exchange completions, captures exit codes, and retries automatically on timeouts before raising `TimeoutError`.【F:src/claudecontrol/core.py†L385-L479】
- `expect_exact(patterns, timeout=None) -> int`: Exact-string variant delegating to `pexpect.expect_exact` or replay search; returns matched index.【F:src/claudecontrol/core.py†L481-L527】
- `get_recent_output(lines: int = 100) -> str` and `get_full_output() -> str`: Read buffered output maintained via `_OutputCapture` (used for both logging and recording).【F:src/claudecontrol/core.py†L118-L188】【F:src/claudecontrol/core.py†L528-L589】
- `is_alive() -> bool`: Indicates whether the underlying transport is active, handling both live and replay children.【F:src/claudecontrol/core.py†L544-L589】
- `close(force: bool = False) -> Optional[int]`: Terminates the session, flushes pending recorder data, and prints the exit summary exactly once when enabled.【F:src/claudecontrol/core.py†L590-L640】
- `interact() -> None`: Hands terminal control to the operator for ad-hoc debugging across live and replay sessions.【F:src/claudecontrol/core.py†L642-L660】
- `save_state() -> Dict[str, Any]`: Persists session metadata (including PID, command, recent output counts) under `~/.claude-control/sessions/<id>/state.json`.【F:src/claudecontrol/core.py†L662-L705】
- `save_program_config(name: str, include_output: bool = False) -> None`: Serializes an interaction template for reuse, automatically deriving expect sequences from recorded history.【F:src/claudecontrol/core.py†L707-L780】

### Convenience Helpers (`src/claudecontrol/core.py`)
- `control(...) -> Session`: Retrieves or creates a persistent session matching the command and configuration, reusing active sessions when `reuse=True`.
- `run(...) -> str`: Executes a one-off command, optionally expecting and sending scripted input before returning the final output.

---

## Replay Subsystem (`src/claudecontrol/replay/`)

### Modes & Matching
- `RecordMode` (`modes.py`): `NEW`, `OVERWRITE`, `DISABLED` determine how new exchanges are persisted when recording.【F:src/claudecontrol/replay/modes.py†L1-L22】
- `FallbackMode` (`modes.py`): `NOT_FOUND` raises on misses; `PROXY` executes the real program without saving when `record` is disabled.【F:src/claudecontrol/replay/modes.py†L14-L22】
- `MatchingContext` (`matchers.py`): Captures program, args, environment, CWD, and prompt for deterministic lookups.【F:src/claudecontrol/replay/matchers.py†L7-L23】
- `StdinMatcher` / `CommandMatcher`: Callables customizing stdin and argv comparisons; defaults normalize ANSI, whitespace, timestamps, and trailing newlines.【F:src/claudecontrol/replay/matchers.py†L25-L43】
- `KeyBuilder` (`store.py`): Normalizes commands, env vars, prompts, and stdin into deterministic keys for the tape index and handles allow/ignore lists and stdin omission.【F:src/claudecontrol/replay/store.py†L95-L204】

### Data Model (`model.py`)
- `TapeMeta`: Program metadata, environment snapshot, terminal geometry, latency/error overrides, optional tag/seed.【F:src/claudecontrol/replay/model.py†L27-L43】
- `Chunk`, `IOInput`, `IOOutput`, `Exchange`, `Tape`: Represent structured terminal exchanges with chunked output (delay + base64 payload) and optional exit annotations.【F:src/claudecontrol/replay/model.py†L1-L26】【F:src/claudecontrol/replay/model.py†L45-L55】

### Decorators & Policies
- `InputDecorator`, `OutputDecorator`, `TapeDecorator` allow byte-level transformation of inputs, outputs, or metadata; `compose_decorators` chains them left-to-right.【F:src/claudecontrol/replay/decorators.py†L1-L17】
- `resolve_latency(config, ctx)` resolves constant, range, or callable latency specs to milliseconds.【F:src/claudecontrol/replay/latency.py†L1-L16】
- `should_inject_error(config, ctx)` probabilistically raises `TapeMissError` to simulate faults according to global or per-tape rates.【F:src/claudecontrol/replay/errors.py†L1-L16】【F:src/claudecontrol/replay/play.py†L57-L100】
- `redact_bytes` (`redact.py`) scrubs sensitive tokens and password patterns before persistence and during mass redaction passes.【F:src/claudecontrol/replay/redact.py†L1-L31】
- Normalizers in `normalize.py` strip ANSI sequences, collapse whitespace, and scrub volatile tokens for consistent matching.【F:src/claudecontrol/replay/normalize.py†L1-L27】

### TapeStore & Utilities (`store.py`)
- `TapeStore(root: Path)`: Loads JSON5 tapes, validates schema, tracks usage, and writes updated tapes atomically with file locking.【F:src/claudecontrol/replay/store.py†L69-L176】【F:src/claudecontrol/replay/store.py†L205-L261】
  - `load_all()` / `iter_tapes()` enumerate `*.json5` tapes recursively.
  - `build_index(builder)` constructs normalized key maps and secondary prompt buckets for fuzzy matching.【F:src/claudecontrol/replay/store.py†L130-L189】
  - `find_matches(builder, ctx, stdin)` resolves candidate exchanges given the current context and input payload.【F:src/claudecontrol/replay/store.py†L191-L233】
  - `write_tape(path, tape, mark_new=True)` performs atomic writes with `portalocker` and temp files, updating in-memory caches and marking newly created tapes for the exit summary.【F:src/claudecontrol/replay/store.py†L235-L275】
  - `validate(strict=False)` runs JSON schema validation (strict mode enforces exchange shape) returning `(path, error)` tuples.【F:src/claudecontrol/replay/store.py†L287-L311】
  - `redact_all(inplace=False)` scans inputs and outputs for redactable secrets and optionally rewrites files in place.【F:src/claudecontrol/replay/store.py†L313-L358】

### Recorder (`record.py`)
- Captures terminal output via a composite `logfile_read` writer that tees into `ChunkSink` while preserving existing logging behavior.【F:src/claudecontrol/replay/record.py†L19-L74】
- `on_send(...)` snapshots decorated input payloads and prompt context, resetting the sink for a new exchange.【F:src/claudecontrol/replay/record.py†L94-L144】
- `on_exchange_end(...)` builds an `Exchange`, applies output decorators, and queues it for persistence with duration metadata.【F:src/claudecontrol/replay/record.py†L146-L194】
- `finalize(store)` reconciles pending exchanges with existing tapes according to `RecordMode`, performing overwrites or appends and writing JSON5 artifacts via the shared `TapeStore`. Callers invoke this during `Session.close()`.【F:src/claudecontrol/replay/record.py†L196-L233】

### ReplayTransport (`play.py`)
- Acts as a drop-in stand-in for `pexpect.spawn` when replaying tapes. `send`/`sendline` look up matches via `TapeStore`, stream recorded chunks (respecting latency/error policies), and surface exit codes and buffers compatible with `expect` and `expect_exact`.【F:src/claudecontrol/replay/play.py†L17-L118】
- Maintains `before`, `after`, and `match` attributes mirroring `pexpect` semantics for downstream consumers.【F:src/claudecontrol/replay/play.py†L30-L105】

### Summary Reporter (`summary.py`)
- `print_summary(store)` emits Talkback-style summaries of new tapes and unused tapes at shutdown when `Session.summary` is `True`. The recorder marks new writes; the replay transport marks used entries during playback.【F:src/claudecontrol/replay/summary.py†L1-L22】【F:src/claudecontrol/replay/store.py†L262-L269】

### Exceptions (`replay/exceptions.py`)
- `ReplayError` base class.
- `TapeMissError`: raised on unmatched input during playback or deliberate error injection.【F:src/claudecontrol/replay/exceptions.py†L1-L13】
- `SchemaError`: indicates schema validation failures.
- `RedactionError`: surfaces unrecoverable masking issues.【F:src/claudecontrol/replay/exceptions.py†L15-L19】

---

## High-Level Helper Functions & Utilities

### Automation Helpers (`src/claudecontrol/claude_helpers.py`)
- `interactive_command(command, interactions, timeout=30, cwd=None) -> str`: Runs scripted expect/send sequences and returns the combined output.
- `parallel_commands(commands, timeout=30, max_concurrent=10) -> Dict[str, Dict[str, Any]]`: Executes multiple commands concurrently, returning success/error status per command.
- `watch_process(command, watch_for, callback=None, timeout=300, cwd=None) -> List[str]`: Monitors output for patterns and optionally invokes `callback(session, pattern)` when matches occur.
- `test_command(command, expected_output, timeout=30, cwd=None) -> Tuple[bool, Optional[str]]`: Validates that expected patterns appear, returning `(False, error)` on failure.

### Pattern Utilities (`src/claudecontrol/patterns.py`)
- `extract_json(output) -> Optional[Union[dict, list]]`: Parses embedded JSON.
- `detect_prompt_pattern(output) -> Optional[str]`: Heuristically discovers prompt strings.
- `is_error_output(output) -> bool`: Uses curated regexes to identify error conditions.
- `classify_output(output) -> Dict[str, Any]`: Summarizes structure (data formats, prompt presence, table detection, etc.).

---

## Investigation & Testing Interfaces

### Investigation (`src/claudecontrol/investigate.py`)
- `investigate_program(program, timeout=10, safe_mode=True, save_report=True) -> InvestigationReport`: Automatically probes unknown CLIs, mapping states, prompts, transitions, help commands, and data formats. Reports save to `~/.claude-control/investigations/` when enabled.
- `InvestigationReport`: Contains session metadata, discovered states, commands, prompts, safety notes, and optional JSON serialization for downstream analysis.

### Testing (`src/claudecontrol/testing.py`)
- `black_box_test(program, timeout=10, save_report=True) -> Dict[str, Any]`: Performs startup/help/error/fuzz/concurrency/resource scenarios, returning structured results and optionally persisting a report under `~/.claude-control/test-reports/`.

---

## CLI (`ccontrol` entry point)

### Interactive Menu
```bash
ccontrol
```
Opens the guided menu-driven interface for session management, automation, and reporting.

### Command Groups

#### Core automation
```bash
ccontrol run "command" [--expect PATTERN] [--send TEXT] [--timeout 30] [--output file] [--keep-alive]
ccontrol investigate PROGRAM [--timeout 10] [--unsafe] [--no-save]
ccontrol probe PROGRAM [--timeout 5] [--json]
ccontrol fuzz PROGRAM [--max-inputs 50] [--timeout 5]
ccontrol learn PROGRAM [--timeout 10]
```

#### Session management
```bash
ccontrol list [--all] [--json]
ccontrol status
ccontrol attach SESSION_ID
ccontrol clean [--force]
ccontrol config list
ccontrol config show NAME
ccontrol config delete NAME
```

#### Replay workflows
```bash
ccontrol rec   [--tapes DIR] [--record new|overwrite|disabled] [--fallback not_found|proxy]
              [--latency MS|MIN,MAX] [--error-rate PCT] [--summary/--no-summary] PROGRAM [ARGS...]
ccontrol play  [--tapes DIR] [--fallback not_found|proxy] [--latency ...] [--error-rate ...]
              PROGRAM [ARGS...]
ccontrol proxy [--tapes DIR] [--record ...] [--latency ...] [--error-rate ...] PROGRAM [ARGS...]
```
`rec` launches a live session with recording enabled (`NEW` by default). `play` disables recording and relies exclusively on tapes, failing on misses unless `--fallback proxy` is specified. `proxy` replays when possible and proxies to live execution on misses while still honoring the selected record mode.【F:src/claudecontrol/cli.py†L1-L126】

#### Tape utilities
```bash
ccontrol tapes list [--tapes DIR] [--used] [--unused]
ccontrol tapes validate [--tapes DIR] [--strict]
ccontrol tapes redact [--tapes DIR] [--inplace]
ccontrol tapes diff [--tapes DIR] LEFT.json5 RIGHT.json5 [--ignore-ansi] [--collapse-ws]
```
These commands surface TapeStore capabilities: listing exchange counts, schema validation, redaction previews or rewrites, and normalized diffs between tapes.【F:src/claudecontrol/cli.py†L128-L226】

---

## Configuration (`~/.claude-control/config.json`)

Global defaults are loaded via `_load_config()` and merged with runtime parameters.【F:src/claudecontrol/core.py†L19-L72】

```json
{
  "session_timeout": 300,
  "max_sessions": 20,
  "auto_cleanup": true,
  "log_level": "INFO",
  "output_limit": 10000,
  "max_session_runtime": 3600,
  "max_output_size": 104857600,
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
Values in the `replay` section provide defaults for CLI invocations and programmatic sessions but are overridden by explicit arguments.

---

## Error Handling

### Core Exceptions (`src/claudecontrol/exceptions.py`)
- `SessionError`: Raised for invalid session states (e.g., sending to a closed process).
- `TimeoutError`: Produced when `expect` fails within the deadline; includes recent output for diagnostics.
- `ProcessError`: Indicates spawn failures or unexpected process exits; typically surfaced with command context.
- `ConfigNotFoundError`: Raised when requested stored configurations are missing.

### Replay Exceptions (`src/claudecontrol/replay/exceptions.py`)
- `ReplayError`: Base class for replay-specific failures.
- `TapeMissError`: Thrown on unmatched inputs during playback or injected errors based on `error_rate`.
- `SchemaError`: Indicates invalid tape structure when loading or validating.
- `RedactionError`: Signals that automatic masking could not be applied safely.

These exceptions propagate through both the library API and CLI commands, enabling deterministic handling in automated workflows.【F:src/claudecontrol/replay/exceptions.py†L1-L19】【F:src/claudecontrol/core.py†L231-L352】

---

## Tape Summary & Reporting

When `summary=True`, closing a session invokes `print_summary`, showing newly written tapes and tapes that were loaded but unused—mirroring Talkback’s exit report. Tapes are marked as used during replay and as new when written, ensuring accurate bookkeeping across multiple sessions.【F:src/claudecontrol/core.py†L602-L640】【F:src/claudecontrol/replay/summary.py†L1-L22】

---

## Testing Guidance

The record/replay system is exercised by unit tests for normalization, matching, recording, and playback, along with integration tests that cover real CLI sessions (e.g., `sqlite3`, `python -q`, `git`). The CLI smoke tests mirror typical `rec`, `play`, and `proxy` flows to guarantee parity with Talkback semantics. Consult the `tests/` directory for concrete examples of authoring and replaying tapes under different modes.

---

This document should serve as a single reference for both existing automation APIs and the newly integrated Talkback-style recording features.
