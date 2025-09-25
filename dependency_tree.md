# ClaudeControl Dependency Tree

## Overview
ClaudeControl combines `pexpect`-driven process automation with deterministic record & replay. The library still supports its ori
ginal investigation, testing, and automation helpers, and now layers a Talkback-inspired tape system on top. The dependency tree
below highlights how new replay components integrate with existing modules and the external packages they rely on.

## External Dependencies

### Core Runtime
- **pexpect** (>=4.8.0)
  - Terminal process spawning, PTY control, expect/send primitives.
  - Used by: `core.Session`, `testing`, `investigate`, recorder integration.
- **psutil** (>=5.9.0)
  - Process/resource monitoring, cleanup of orphaned children.
  - Used by: `core.Session` cleanup, `testing` utilities.
- **pyjson5** (>=1.6.9)
  - JSON5 parser/writer for human-editable tape files.
  - Used by: `replay.store`, `replay.record`, CLI tape tooling.
- **portalocker** (>=2.8.0)
  - Cross-platform file locking for atomic tape writes and updates.
  - Used by: `replay.store`, `replay.record`.

### Optional / Feature-Specific
- **fastjsonschema** (>=2.20)
  - Optional JSON schema validation for tapes (CLI `validate`, CI checks).
  - Used by: `replay.store` when strict validation is enabled.
- **watchdog** (>=2.1.0)
  - Optional file watching for future tape hot-reload features.
  - Currently unused; CLI falls back to polling when absent.

### Development & Tooling
- **pytest**, **pytest-asyncio**, **black**, **mypy**
  - Testing, async support, formatting, static typing during development.

### Python Standard Library Highlights
- **json**, **pathlib**, **os**, **signal**, **threading**, **collections**, **tempfile**, **datetime**, **logging**, **typing**
  - Core infrastructure for configuration, filesystem access, process signalling, thread-safe registries, temporary resources, a
nd diagnostics.
- **re**, **dataclasses**, **contextlib**, **time**, **hashlib**, **base64**, **random**
  - Text normalization, structured models, context managers, timing, hashing, encoding, and deterministic randomisation used ac
ross replay components.

## Internal Package Structure & Dependencies

```text
src/claudecontrol/
├── __init__.py
│   └─ Re-exports Session, helpers, and replay enums for consumers.
├── core.py
│   ├─ Wraps `pexpect.spawn` and process lifecycle management.
│   ├─ Maintains session registry, prompt tracking, and automation APIs.
│   ├─ Integrates replay features via:
│   │   ├─ `replay.modes.RecordMode` / `FallbackMode`
│   │   ├─ `replay.record.Recorder` (attaches to `pexpect.logfile_read`)
│   │   ├─ `replay.play.ReplayTransport` (virtual child process)
│   │   ├─ `replay.store.TapeStore` + `TapeIndex`
│   │   ├─ `replay.namegen.TapeNameGenerator`
│   │   ├─ `replay.summary.print_summary`
│   │   └─ `replay.matchers`, `normalize`, `decorators`, `latency`, `errors`, `redact`
│   ├─ Continues to power investigation (`investigate.py`), automation helpers (`claude_helpers.py`), and testing workflows (`te
sting.py`).
├── cli.py
│   ├─ Provides `ccontrol` entry point.
│   ├─ Existing investigation/testing automation commands.
│   └─ New `rec`, `play`, `proxy`, and tape management subcommands that configure `core.Session` replay options.
├── investigate.py / patterns.py / testing.py / claude_helpers.py
│   └─ Reuse `core.Session` APIs; automatically benefit from replay modes without code changes.
└── replay/
    ├── __init__.py              (exports primary replay interfaces)
    ├── modes.py                 (RecordMode, FallbackMode enums)
    ├── exceptions.py            (TapeMissError, SchemaError, RedactionError)
    ├── model.py                 (Tape, Exchange, Chunk dataclasses)
    ├── normalize.py             (ANSI stripping, whitespace collapse, volatile value scrubbing)
    ├── matchers.py              (MatchingContext, command/env/prompt/stdin matchers)
    ├── decorators.py            (Input/Output/Tape decorator protocols and composition helpers)
    ├── redact.py                (Secret detectors and redaction utilities)
    ├── namegen.py               (Tape naming strategies, default hash/timestamp generator)
    ├── store.py                 (TapeStore loader, TapeIndex builder, portalocker-protected writes, optional schema validation)
    ├── record.py                (Recorder, ChunkSink; uses namegen, normalize, decorators, redact)
    ├── play.py                  (ReplayTransport; streams chunks with latency/error injection)
    ├── latency.py               (Latency resolution helpers)
    ├── errors.py                (Probabilistic error injection policies)
    └── summary.py               (Exit summary reporting for new/unused tapes)
```

### Replay Flow Dependencies
1. **Session setup (`core.py`)**
   - Determines record vs. replay mode using `RecordMode` / `FallbackMode`.
   - When recording, instantiates `Recorder`, which:
     - Hooks `ChunkSink` into the `pexpect` child to capture output chunks.
     - Builds `Exchange` objects via `model.py` dataclasses.
     - Normalizes prompts/input with `normalize.py` and applies decorators (`decorators.py`).
     - Uses `portalocker` and `pyjson5` through `store.py` to persist tapes atomically.
   - When replaying, loads `TapeStore` which:
     - Recursively parses JSON5 tapes (`pyjson5`).
     - Builds an in-memory `TapeIndex` keyed via matchers/normalizers.
     - Optionally validates against JSON Schema (`fastjsonschema`).
   - `ReplayTransport` streams chunk data, applying pacing from `latency.py` and synthetic errors from `errors.py`.
   - Tape usage is tracked so `summary.print_summary` can emit new/unused tape lists on shutdown.

2. **Matchers & Normalizers**
   - `matchers.py` consumes configuration from `Session` (allow/ignore lists, custom callables).
   - `normalize.py` and `redact.py` sanitize prompts, inputs, and outputs before comparing or writing to disk.
   - Decorators provide last-mile hooks for teams to customise behaviour (e.g., redact, tag, mutate).

3. **CLI Integration**
   - `cli.py` maps `ccontrol rec/play/proxy` subcommands to the appropriate `RecordMode`/`FallbackMode` combinations.
   - Tape management commands (`tapes list`, `tapes validate`, `tapes redact`) call into `replay.store` and `replay.redact` util
ities, leveraging `pyjson5`, `fastjsonschema`, and `portalocker` under the hood.

4. **Testing & Tooling**
   - New tests under `tests/test_replay_*.py` exercise `normalize`, `matchers`, `record`, `play`, and integration flows, dependi
ng on the replay modules and optional fixtures in `testing.py`.
   - Existing test harnesses continue to rely on `pytest` and related dev dependencies.

## Version Requirements
- **Python** >= 3.9 recommended (3.8 compatible with dataclasses/typing backports), ensuring availability of the standard libra
ry features used by replay modules.
- Replay features remain opt-in; disabling them leaves legacy automation pipelines untouched.

## Summary
The new replay subsystem adds a focused set of dependencies (`pyjson5`, `portalocker`, optional `fastjsonschema`) and a self-contained package (`src/claudecontrol/replay/`) that plugs into the existing Session, CLI, and testing layers without disrupting legacy workflows.
Together with longstanding modules (`investigate`, `patterns`, `testing`), ClaudeControl now offers a unified automation, investigation, and deterministic replay stack.
