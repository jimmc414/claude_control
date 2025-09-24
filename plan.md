# Implementation Plan for Talkback-style Record & Replay in claude_control

## Project Analysis Summary
After analyzing the codebase, I understand that `claude_control` is a Python library built on `pexpect` that provides elegant terminal process automation through a `Session` class. The project already has:
- A well-structured Session class using pexpect.spawn
- An existing `logfile_read` hook (_OutputCapture) for output capture
- CLI with subcommands using argparse
- Configuration management in ~/.claude-control/config.json
- Clean package structure under src/claudecontrol/

## Implementation Strategy

### Phase 1: Foundation (Dependencies & Package Structure)
1. **Add dependencies** to requirements.txt:
   - `pyjson5>=1.6.9` (for JSON5 tape format)
   - `fastjsonschema>=2.20` (for tape validation)
   - `portalocker>=2.8` (for cross-platform file locking)

2. **Create replay package** at `src/claudecontrol/replay/`:
   - Create all module files as specified in requirements
   - Establish proper Python package structure

### Phase 2: Core Data Model & Storage
3. **Implement data model** (model.py):
   - `Tape`, `Exchange`, `Chunk` dataclasses
   - JSON5 serialization/deserialization
   - Base64 encoding for binary data

4. **Implement tape storage** (store.py):
   - TapeStore for loading/saving tapes
   - TapeIndex for fast matching with normalized keys
   - Thread-safe operations with locks

### Phase 3: Matching & Normalization
5. **Implement matchers** (matchers.py):
   - CommandMatcher, EnvMatcher, StdinMatcher
   - MatchingContext for decorator integration
   - Support for allow/ignore lists

6. **Implement normalization** (normalize.py):
   - ANSI escape code stripping
   - Whitespace collapse
   - Timestamp/PID/UUID scrubbing

7. **Implement redaction** (redact.py):
   - Secret detection patterns
   - Password/token redaction

### Phase 4: Recording Infrastructure
8. **Implement Recorder** (record.py):
   - ChunkSink class leveraging pexpect's `logfile_read`
   - Exchange segmentation logic
   - Integration with existing Session._OutputCapture

### Phase 5: Replay Infrastructure
9. **Implement Player** (play.py):
   - Transport abstraction to decouple from pexpect
   - ReplayTransport for tape playback
   - Chunk streaming with latency support

### Phase 6: Session Integration
10. **Modify Session class** (core.py):
    - Add replay parameters to __init__
    - Inject Transport facade pattern
    - Hook Recorder into send/sendline/expect
    - Implement fallback logic for tape misses

### Phase 7: CLI Integration
11. **Add CLI subcommands** (cli.py):
    - `rec` - record with live execution
    - `play` - playback only (fail on miss)
    - `proxy` - playback with fallback to live
    - Tape management commands (list, validate, redact)

### Phase 8: Testing & Documentation
12. **Create comprehensive tests**:
    - Unit tests for all components
    - Integration tests with sqlite3, python -q, git
    - CI configuration for tape validation

## Key Technical Decisions

1. **Use existing `logfile_read` hook**: The Session class already has `_OutputCapture` using `logfile_read`, which we'll extend for recording without threads.

2. **Transport abstraction**: Introduce a Transport interface to cleanly separate live pexpect operation from replay mode.

3. **Backward compatibility**: All changes are additive with safe defaults - existing code continues to work unchanged.

4. **JSON5 format**: Human-editable tapes with comments, matching Talkback's approach.

5. **Load-once strategy**: Tapes load at startup; edits require restart (Talkback parity).

6. **Exchange segmentation**: Start new exchange on send/sendline, end on prompt match or timeout.

## Implementation Order
1. Foundation modules (modes, model, exceptions)
2. Storage and indexing
3. Matching and normalization
4. Recording infrastructure
5. Replay infrastructure
6. Session integration
7. CLI integration
8. Testing

## Risk Mitigation
- Maintain full backward compatibility
- Extensive testing at each phase
- Feature flag for gradual rollout
- Clear error messages for tape misses
- Documentation for limitations (curses apps, Windows PTY)

## Success Criteria
✓ Record sqlite3 session and replay byte-for-byte
✓ Modes behave as specified (NEW, OVERWRITE, DISABLED)
✓ Matchers and decorators programmable via API and CLI
✓ Latency and error injection work as configured
✓ Exit summary reports new/unused tapes
✓ All existing tests continue to pass

## File-by-File Implementation Details

### 1. requirements.txt
```
# Add to existing requirements
pyjson5>=1.6.9        # JSON5 read/write for human-editable tapes
fastjsonschema>=2.20  # Schema validation for tapes
portalocker>=2.8      # Cross-platform file locks
```

### 2. src/claudecontrol/replay/__init__.py
- Export main classes: Recorder, Player, TapeStore
- Export modes: RecordMode, FallbackMode
- Export exceptions: TapeMissError, SchemaError, RedactionError

### 3. src/claudecontrol/replay/modes.py
- RecordMode enum: NEW, OVERWRITE, DISABLED
- FallbackMode enum: NOT_FOUND, PROXY
- Policy type definitions for dynamic mode selection

### 4. src/claudecontrol/replay/model.py
- Chunk dataclass: delay_ms, data_b64, is_utf8
- IOInput dataclass: kind (line/raw), data_text, data_b64
- IOOutput dataclass: chunks list
- Exchange dataclass: pre, input, output, exit, dur_ms, annotations
- TapeMeta dataclass: created_at, program, args, env, cwd, pty, tag, latency, errorRate, seed
- Tape dataclass: meta, session, exchanges

### 5. src/claudecontrol/replay/namegen.py
- TapeNameGenerator class with __call__ method
- Default implementation: `{program}/unnamed-{timestamp}-{hash}.json5`
- Pluggable interface for custom naming strategies

### 6. src/claudecontrol/replay/store.py
- TapeStore class:
  - load_all(): recursive tape loading from directory
  - mark_used()/mark_new(): tracking for exit summary
  - build_index(): create normalized key -> (tape_idx, exchange_idx) map
  - write_tape(): atomic write with temp file + rename
  - Thread-safe operations with RLock

### 7. src/claudecontrol/replay/matchers.py
- MatchingContext dataclass: program, args, env, cwd, prompt
- CommandMatcher protocol and default implementation
- EnvMatcher with allow/ignore lists
- StdinMatcher with exact/normalized matching
- PromptMatcher with ANSI-aware comparison

### 8. src/claudecontrol/replay/normalize.py
- strip_ansi(): remove ANSI escape sequences
- collapse_ws(): normalize whitespace
- scrub(): replace timestamps, PIDs, UUIDs with placeholders
- VOLATILE_PATTERNS list for common dynamic values

### 9. src/claudecontrol/replay/redact.py
- SECRET_PATTERNS: regex list for passwords, tokens, keys
- redact_bytes(): replace secrets with *** markers
- Environment variable for disabling (CLAUDECONTROL_REDACT=0)

### 10. src/claudecontrol/replay/decorators.py
- InputDecorator protocol: transform input before matching
- OutputDecorator protocol: transform output before storage
- TapeDecorator protocol: modify tape metadata
- Composition helpers for chaining decorators

### 11. src/claudecontrol/replay/latency.py
- resolve_latency(): handle int, tuple, or callable configs
- Latency policies: constant, range, function-based
- Per-tape and global latency support

### 12. src/claudecontrol/replay/errors.py
- should_inject_error(): probabilistic error injection
- Error modes: early termination, chunk truncation
- Seeded RNG for determinism

### 13. src/claudecontrol/replay/record.py
- ChunkSink class:
  - Implements write()/flush() for pexpect.logfile_read
  - Captures chunks with timestamps
  - Base64 encoding for binary safety
- Recorder class:
  - start(): attach ChunkSink to session
  - on_send(): begin new exchange
  - on_exchange_end(): finalize and save exchange
  - Integration with decorators and redaction

### 14. src/claudecontrol/replay/play.py
- Transport abstract base class
- ReplayTransport implementation:
  - send()/sendline(): match tape and stream output
  - expect(): pattern matching on buffered output
  - _stream_chunks(): background thread for paced output
  - Tape miss handling per fallback mode

### 15. src/claudecontrol/replay/summary.py
- print_summary(): format and display new/unused tapes
- Track tape usage during session
- Exit hook integration

### 16. src/claudecontrol/replay/exceptions.py
- TapeMissError: no matching tape found
- SchemaError: invalid tape format
- RedactionError: secret detection failure

### 17. Modifications to src/claudecontrol/core.py
- Add replay parameters to Session.__init__()
- Create Transport abstraction layer
- Integrate Recorder with existing _OutputCapture
- Add replay mode switching logic
- Hook summary printing to session cleanup

### 18. Modifications to src/claudecontrol/cli.py
- Add rec/play/proxy subcommands
- Add tape management commands
- Map CLI flags to Session parameters
- Integrate with existing argparse structure

### 19. Modifications to src/claudecontrol/__init__.py
- Export RecordMode, FallbackMode
- Export Recorder, Player, TapeStore (optional)
- Maintain backward compatibility

### 20. Test files
- tests/test_replay_normalize.py: unit tests for normalization
- tests/test_replay_matchers.py: unit tests for matchers
- tests/test_replay_record.py: recording functionality
- tests/test_replay_play.py: replay functionality
- tests/test_replay_integration.py: end-to-end tests