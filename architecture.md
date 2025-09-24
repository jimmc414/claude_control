# architecture.md — Record & Replay for `claude_control`

## Purpose

Deterministic recording and playback of interactive CLI sessions. Parity with Talkback features: tapes, matchers, modes, decorators, latency/error injection, and exit summaries. Integrated into the current `claude_control` stack which is built on `pexpect`. ([GitHub][1])

---

## Context and constraints

* `claude_control` provides investigation, testing, and automation of CLIs through a `Session` abstraction, helpers, patterns, a CLI (`ccontrol`), and docs. We extend rather than replace. ([GitHub][2])
* It already uses `pexpect` to spawn and control processes. Replay must sit at this boundary. ([Pexpect][3])
* Project structure exposes `core.py` (Session), `testing.py`, `patterns.py`, `cli.py`, and docs. New code must mount cleanly under `src/claudecontrol/`. ([GitHub][2])
* User config location exists (`~/.claude-control/config.json`). Extend it, keep defaults safe. ([GitHub][2])

---

## Design principles

* Library first. CLI as a thin wrapper.
* No behavior change unless features are enabled.
* Human‑editable artifacts. Tapes must be JSON5 for comments and trailing commas, matching Talkback. ([GitHub][1])
* Deterministic by default. All randomness seeded.
* Clear failure on tape miss when recording is disabled (mirrors Talkback guidance for CI). ([GitHub][1])

---

## High‑level architecture

### New package

`src/claudecontrol/replay/`
Components:

* `modes`: enums and policies for RecordMode and FallbackMode.
* `tapes`: tape model, schema checks, serialization, migration.
* `namegen`: pluggable tape naming.
* `store`: TapeStore, TapeIndex, change monitor (load‑on‑start).
* `matchers`: command/env/prompt/stdin matchers, user‑supplied hooks.
* `normalize`: ANSI stripping, whitespace, timestamp/ID scrubbing.
* `decorators`: input/output/tape decorators, MatchingContext.
* `latency`: global and per‑exchange pacing policies.
* `errors`: probabilistic error injection.
* `record`: Recorder intercepting `Session` I/O and segmenting exchanges.
* `play`: Player replacing the child process with a tape stream.
* `redact`: secret detection and redaction.
* `summary`: usage accounting and exit report.

### Integration points

* `core.Session`: inject a `Transport` facade. Backed by either `pexpect.spawn` (live) or `Player` (replay). No API break. ([GitHub][2])
* `patterns.py`: reuse prompt detectors; surface default prompt patterns per program.
* `testing.py`: add fixtures to run tests with recording disabled by default; opt‑in record for authoring. ([GitHub][1])
* `cli.py` (`ccontrol`): add subcommands `rec`, `play`, `proxy`. Flags map to library options.
* Config: extend `~/.claude-control/config.json` with a `replay` section. ([GitHub][2])

---

## Data model

### Tape file (JSON5)

Top‑level fields:

* `meta`: createdAt, program, args, env (filtered), cwd, pty geometry, tag, latency, errorRate, RNG seed, human‑readable flags.
* `session`: platform info, tool version, feature flags.
* `exchanges`: ordered list of interactive steps.

Exchange fields:

* `pre`: prompt text or regex snapshot and optional state hash.
* `input`: type (`line` vs `raw`), canonical text or base64 bytes.
* `output`: chunk stream. Each chunk stores delay and bytes. Mark text vs bytes for debug and pretty‑print.
* `exit`: code and signal if the process ended.
* `metrics`: durations and byte counts.

Rationales:

* Chunked output preserves terminal pacing during replay.
* Base64 storage guarantees lossless binary capture; UTF‑8 flag enables pretty printing when safe. Mirrors Talkback’s human‑readable preference. ([GitHub][1])

### Index

* Keyed by normalized `(program, args*, env*, cwd*, prompt signature, input fingerprint, optional state hash)`.
* Secondary keys for fuzzy matching when normalizers are active.
* In‑memory map plus on‑disk file path reference.

---

## Matching strategy

Order of operations on input:

1. Build `MatchingContext` with session metadata.
2. Apply `commandMatcher` over `(program, args)` after normalization.
3. Apply `envMatcher` with `allowEnv` and `ignoreEnv` filters.
4. Compare prompt signature. ANSI‑aware and regex‑aware.
5. Apply `stdinMatcher` on the canonical input.
6. Optional `stateHash` gate if provided by the user.

Configurables mirror Talkback controls:

* `allowEnv` and `ignoreEnv` akin to `allowHeaders` and `ignoreHeaders`. ([GitHub][1])
* `ignoreArgs`, `ignoreStdin` akin to `ignoreQueryParams` and `ignoreBody`. ([GitHub][1])
* `stdinMatcher` and `commandMatcher` align with Talkback’s body and URL matchers. ([GitHub][1])

---

## Normalization and redaction

* ANSI sequence stripping toggle. Keep raw bytes in tape; normalize only for matching.
* Whitespace collapse option for prompts and echoed inputs.
* Regex scrubbing of timestamps, PIDs, ephemeral IDs, memory addresses.
* Secret redaction for passwords, tokens, known key formats. Redaction occurs before persistence; markers stored in `annotations`.

---

## Segmentation (exchange boundaries)

Start a new exchange at process start, after every `send` or `sendline`, or at process exit.
End an exchange when a configured prompt is matched, on timeout, or at process exit.
Recorder tracks inter‑chunk delays with a monotonic timer to avoid wall‑clock skew.

---

## Modes and miss policy

Record modes:

* `NEW`: on miss, run live and append a new exchange to the current tape.
* `OVERWRITE`: on match, re‑run live and replace the exchange.
* `DISABLED`: never write.

Fallback modes when `DISABLED` and no match:

* `NOT_FOUND`: raise a tape miss error.
* `PROXY`: run live, return live output, do not persist.

Parallels Talkback semantics for predictability in CI. Recommended default in CI: recording disabled with `NOT_FOUND`. ([GitHub][1])

---

## Decorators

Hook points:

* Input decorator: last mile normalization or tagging.
* Output decorator: dynamic field updates, masking, or format tweaks.
* Tape decorator: add tags, latency, errorRate, or custom metadata before write.

`MatchingContext` ties decorators together, mirroring Talkback’s context object. ([GitHub][1])

---

## Latency and error injection

Latency:

* Global default at the `Session` level.
* Per‑tape `meta.latency` override.
* Policies: constant, min–max range, or function on context.

Error injection:

* Global probability or context function.
* Modes: early termination with configured exit code, or chunk truncation plus error.
* Per‑tape `meta.errorRate` override.

Matches Talkback’s latency and errorRate semantics. ([GitHub][1])

---

## Storage layout and naming

* Default root: `./tapes`.
* Default naming: `program/unnamed-<epoch>.json5`.
* Customizable via `tapeNameGenerator` that can use content to derive paths. Mirrors Talkback’s generator. ([GitHub][1])
* Atomic write: temp file then rename.
* Strict file locks on overwrites.

---

## Runtime flow

Record flow:

1. Session enters record mode and opens TapeStore.
2. On each input, Recorder segments an exchange.
3. Live process runs through `pexpect`; Recorder captures chunked output and timing. ([Pexpect][3])
4. Decorators run.
5. Tape is written or updated per mode.
6. Summary marks “used” and “new”.

Replay flow:

1. Player loads index at startup. Tapes are loaded recursively once; edits require restart, same as Talkback. ([GitHub][1])
2. On each input, match an exchange.
3. Stream recorded chunks with latency policy.
4. On termination, apply recorded exit status.

Exit summary:

* Print new and unused tapes. Toggle with `summary`. Mirrors Talkback. ([GitHub][1])

---

## Public surfaces

Library:

* New `replay` options on `Session` for modes, matchers, decorators, pacing, and paths.
* `Recorder` and `Player` helpers for advanced users.
* Exceptions for tape miss, schema errors, and redaction failures.

CLI (`ccontrol`):

* `rec`, `play`, `proxy` subcommands.
* Flags for `--tapes`, `--record`, `--fallback`, `--latency`, `--error-rate`, `--summary`, `--silent`, `--debug`.

Config (`~/.claude-control/config.json`):

* Add `replay` object to set defaults for the above. Do not override explicit flags. ([GitHub][2])

---

## Concurrency and performance

* One TapeStore per process. Thread‑safe reads. Write lock per tape.
* Index build target: ≤200 ms per 1,000 exchanges.
* Match target: ≤2 ms with normalized key hashing.
* Stream replay with ≤50 ms jitter per chunk under pacing.

---

## Error handling

* Schema validation on load with clear diagnostics.
* Strict mode to fail on unknown fields.
* Soft mode to warn and continue, recording a migration hint in `annotations`.
* On partial match, emit a diff to logs to aid matcher tuning.

---

## Observability

* Levels: silent, info, debug.
* Structured logs for: match hit/miss, decorators applied, normalization decisions, latency and error injections.
* Session and tape IDs in every log line for correlation.

---

## Security and privacy

* Redaction defaults on. Environment opt‑out for development.
* Secret detectors for common key formats and password prompts.
* Tape headers flag redacted fields.
* Optional encryption at rest via user‑supplied filter.

---

## Backward compatibility

* Default behavior unchanged when replay is off.
* All new options are additive and optional.
* Tests continue to run without tapes present.

---

## Testing strategy

* Unit tests for matchers, normalizers, name generation, redaction, decorators, and modes.
* Integration tests on simple CLIs (`python -q`, `sqlite3`, `git`) to validate record→replay parity.
* CLI smoke tests for `rec`, `play`, `proxy`.
* CI default: recording disabled, fallback not found, to surface missing artifacts fast. Mirrors Talkback guidance. ([GitHub][1])

---

## Alternatives considered

* VCRpy or cassettes for subprocess I/O: optimized for HTTP, not PTY streams.
* Full TTY virtualization: high complexity; not needed for line‑oriented CLIs.
* Event log instead of exchange model: harder to match and maintain by hand.

---

## Known limits

* Curses/full‑screen UIs: best‑effort stream capture only.
* Windows PTY differences: plan POSIX first. Document wexpect parity later.
* Filesystem side effects are out of scope; recommend temp dirs and external snapshotting.

---

## Future extensions

* Live tape hot‑reload with a watcher.
* Multi‑program sessions with per‑program sub‑tapes.
* Tape diff and minimization tools.
* Deterministic random data provider for fuzzing integration.

---

## References

* Talkback README: modes, matchers, decorators, JSON5 tapes, pretty printing, latency/errorRate, summary, load‑on‑start. ([GitHub][1])
* `claude_control` README: purpose, structure, config path, Session concept. ([GitHub][2])
* `pexpect` docs: spawn, expect, send model for CLI automation. ([Pexpect][3])

[1]: https://github.com/ijpiantanida/talkback "GitHub - ijpiantanida/talkback: A simple HTTP proxy that records and playbacks requests"
[2]: https://github.com/jimmc414/claude_control "GitHub - jimmc414/claude_control: ClaudeControl is a Python library built on pexpect that automatically discovers, fuzz tests, and automates any command-line program using pattern matching and session management."
[3]: https://pexpect.readthedocs.io/en/stable/api/pexpect.html?utm_source=chatgpt.com "Core pexpect components - Read the Docs"
