# ClaudeControl Sequence Diagrams

The following sequence diagrams capture both the long-standing automation/investigation flows and the newly added Talkback-style recording & replay system. Sections are ordered to show how the replay stack integrates seamlessly with existing components.

---

## 1. Session Lifecycle with Record/Replay Transport
**Trigger:** Any `Session(...)` creation with default or replay-aware options  
**Outcome:** Session routes I/O through either a live `pexpect` process or the replay `Player`, optionally recording via the `Recorder`

```mermaid
sequenceDiagram
    participant Caller as Library/CLI User
    participant Session
    participant Modes as Record/Fallback Modes
    participant Store as TapeStore
    participant Recorder
    participant Player
    participant Live as pexpect.spawn Process

    Caller->>Session: Session(program, record=NEW, fallback=PROXY, ...)
    Session->>Modes: resolve(record, fallback)
    Modes-->>Session: {record_mode, fallback_mode}

    Session->>Store: load_index(tapes_path)
    Store-->>Session: TapeIndex + metadata

    alt playback enabled
        Session->>Player: configure(index, latency, error_rate, decorators)
        Player-->>Session: transport = ReplayTransport
    else live execution
        Session->>Live: spawn(program, args, env, cwd)
        Session->>Recorder: configure(tape_builder, decorators, normalizers)
        Recorder-->>Session: capture hooks (logfile_read, send intercepts)
    end

    Session-->>Caller: ready session (send/expect/close)

    Note over Session,Recorder,Player: Recorder & Player share MatchingContext, decorators, redactors
```

### Integration Notes
- `Session` now accepts replay parameters but keeps backward-compatible defaults.
- TapeStore loads tapes once at session startup, guarded by locks for thread-safety.
- Recorder attaches to the existing `logfile_read` sink; Player replaces the transport interface when replaying.

---

## 2. Tape Recording Pipeline
**Trigger:** Session operating in record or proxy mode while running against a live process  
**Outcome:** Exchanges are segmented, decorated, normalized, redacted, and persisted as JSON5 tapes

```mermaid
sequenceDiagram
    participant Session
    participant Recorder
    participant Capture as ChunkSink
    participant Normal as Normalizers
    participant Decor as Decorators
    participant Redact as Redactor
    participant Store as TapeStore
    participant FS as File System

    Session->>Recorder: start_exchange(input_context)
    Recorder->>Capture: attach(logfile_read)

    loop During output
        Session-->>Capture: output chunk bytes
        Capture->>Recorder: chunk(delay_ms, data)
        Recorder->>Normal: normalize(chunk)
        Normal-->>Recorder: normalized_chunk
        Recorder->>Redact: redact_if_needed(normalized_chunk)
        Redact-->>Recorder: safe_chunk
        Recorder->>Decor: apply_output_decorators(ctx, safe_chunk)
        Decor-->>Recorder: decorated_chunk
        Recorder->>Recorder: append_to_exchange(decorated_chunk)
    end

    alt Prompt detected or timeout
        Recorder->>Decor: finalize_exchange(ctx, annotations)
        Decor-->>Recorder: updated_exchange
        Recorder->>Store: persist(exchange, record_mode)
        Store->>Store: write_temp_then_rename()
        Store->>Store: mark_used_or_new()
        Store->>FS: save_json5(tape_path)
    else Process exits
        Recorder->>Recorder: close_exchange(exit_status)
        Recorder->>Store: persist(...)
    end
```

### Performance Notes
- Chunk capture reuses the existing Session buffer; per-chunk normalization stays under ~1 ms for 100-line windows.
- Tape writes are atomic (temp file + rename) and guarded by `portalocker`-backed locks.

### Failure Modes
- Redaction failure: raises `RedactionError`, aborting write to protect secrets.
- Schema validation errors: surfaced via `SchemaError`, leaving original tape untouched.

---

## 3. Tape Playback & Fallback Handling
**Trigger:** Session running with Player transport (e.g., `record=DISABLED`, `fallback=NOT_FOUND|PROXY`)  
**Outcome:** Matched exchanges stream recorded output with latency/error policies, with optional live fallback

```mermaid
sequenceDiagram
    participant Session
    participant Player
    participant Store as TapeIndex
    participant Matcher as Matchers
    participant Latency
    participant Errors as Error Injector
    participant Live as Live Process

    Session->>Player: sendline("select 1;")
    Player->>Matcher: build_context(program, args, env, prompt, stdin)
    Matcher->>Store: lookup(context)

    alt Match found
        Store-->>Matcher: tape_ref
        Matcher-->>Player: matched_exchange
        Player->>Latency: schedule(chunk.delay_ms, overrides)
        loop For each recorded chunk
            Latency->>Player: wait(delay)
            Player->>Session: deliver_output(chunk)
            Player->>Errors: maybe_inject(ctx)
            Errors-->>Player: continue | inject_failure
        end
        alt Recorded exit
            Player->>Session: propagate_exit(code)
        end
        Player->>Store: mark_used(tape_path)
    else No match
        alt fallback == NOT_FOUND
            Player-->>Session: raise TapeMissError
        else fallback == PROXY
            Player->>Live: spawn(program)
            Live-->>Session: live_output
            Session->>Recorder: (optional) record if record_mode allows
        end
    end
```

### Behavior Highlights
- Latency policies accept constants, ranges, or callables; Player enforces ≤50 ms jitter per chunk.
- Error injection may truncate output or raise synthetic failures with deterministic RNG seeding.
- Proxy fallback optionally records new tapes when `record != DISABLED`.

---

## 4. CLI Record/Replay Commands (`ccontrol`)
**Trigger:** User invokes new CLI subcommands (`rec`, `play`, `proxy`, `tapes ...`)  
**Outcome:** Commands configure Session defaults, run programs, and manage tape artifacts

```mermaid
sequenceDiagram
    participant User
    participant CLI as ccontrol
    participant Config as Config Loader
    participant SessionFactory
    participant Session
    participant Store as TapeStore

    User->>CLI: ccontrol rec -- sqlite3
    CLI->>Config: load(~/.claude-control/config.json)
    Config-->>CLI: defaults (replay section)
    CLI->>SessionFactory: build_options(flags, defaults)
    SessionFactory-->>CLI: resolved kwargs
    CLI->>Store: ensure_path(--tapes)
    CLI->>Session: Session(..., record=NEW, fallback=PROXY)
    Session-->>CLI: run program via Recorder
    CLI-->>User: exit summary (if enabled)

    User->>CLI: ccontrol tapes list --unused
    CLI->>Store: load_index()
    Store-->>CLI: {unused: [...]} 
    CLI-->>User: print table/json
```

### Supported Operations
- `rec`, `play`, and `proxy` toggle record/fallback defaults matching Talkback semantics.
- `tapes list|validate|redact` operate on TapeStore metadata with schema and secret checks.

---

## 5. Exit Summary Accounting
**Trigger:** Session or CLI process shutdown with summaries enabled  
**Outcome:** New and unused tapes are reported to stdout

```mermaid
sequenceDiagram
    participant Session
    participant Summary as ExitSummary
    participant Store as TapeStore
    participant User

    Session->>Summary: on_close(summary=True)
    Summary->>Store: collect_markers()
    Store-->>Summary: {new: [...], unused: [...]} 
    Summary->>User: print "===== SUMMARY (claude_control) =====" block

    alt summary disabled
        Session->>Summary: skip_report()
    end
```

### Notes
- TapeStore tracks `mark_used` and `mark_new` calls during record/playback.
- Summary respects `--silent` but still logs to debug when enabled.

---

## 6. Program Investigation Flow (Existing Feature)
**Trigger:** User runs `investigate_program("unknown_cli")`  
**Outcome:** Complete interface map and behavioral report of the CLI program, optionally recording tapes when enabled

```mermaid
sequenceDiagram
    participant User
    participant API as ProgramInvestigator
    participant Session
    participant Recorder
    participant Process as Target Process
    participant Pattern as Pattern Matcher
    participant State as State Tracker
    participant Report as Report Builder
    participant FS as File System

    User->>API: investigate_program("unknown_cli")
    API->>Session: create_session(timeout=10, record=cfg)
    Session->>Recorder: maybe_enable()
    Session->>Process: spawn or replay
    Process-->>Session: initial output
    Session-->>API: output buffer

    rect rgb(230, 245, 255)
        Note over API: Discovery Phase
        API->>Pattern: detect_prompt(output)
        Pattern-->>API: prompt pattern
        API->>State: register_state("initial", prompt)

        loop Probe Commands
            API->>Session: send(probe_cmd)
            Session->>Process: write stdin / replay chunk
            Process-->>Session: command output
            Session->>Pattern: classify_output(output)
            Pattern-->>Session: {errors, commands, format}

            alt New State Detected
                Session->>State: transition(from, to, trigger)
                State-->>API: state_map updated
            else Error Pattern
                Session->>API: mark_dangerous(cmd)
            else Timeout
                Session->>Session: mark_unresponsive()
                Session->>API: skip command
            end
        end
    end

    rect rgb(245, 255, 230)
        Note over API: Analysis Phase
        API->>State: get_state_map()
        State-->>API: states and transitions
        API->>Pattern: extract_commands(help_output)
        Pattern-->>API: command list
        API->>Report: build_report(findings)
        Recorder->>FS: optionally persist tapes
    end

    Report->>FS: save_json(~/.claude-control/investigations/)
    FS-->>Report: report_path
    Report-->>API: InvestigationReport
    API-->>User: report with summary()

    Note over Process: Process kept alive if persist=True
```

### Performance Notes
- Typical execution: 5-60 seconds depending on program complexity and replay mode.
- When replaying, latency policies ensure consistent pacing for learned prompts.

### Failure Modes
- Program doesn't start: ProcessError raised immediately.
- No prompt detected: Falls back to send-only mode (still records raw output).
- Hangs on input: Timeout protection (default 10s).
- Dangerous operations: Safe mode blocks execution.
- Tape miss when recording disabled: surfaces TapeMissError if fallback is `NOT_FOUND`.

---

## 7. Session Reuse and Registry Management (Existing Feature)
**Trigger:** Multiple calls to `control("server", reuse=True)`  
**Outcome:** Efficient session reuse across script runs with replay-aware cleanup

```mermaid
sequenceDiagram
    participant User1 as Script 1
    participant User2 as Script 2
    participant Control as control()
    participant Registry as Global Registry
    participant Lock as Thread Lock
    participant Session
    participant Process as Server Process
    participant Store as TapeStore
    participant FS as File System

    User1->>Control: control("npm run dev", reuse=True)
    Control->>Lock: acquire()
    Lock-->>Control: locked

    Control->>Registry: find_session("npm run dev")
    Registry-->>Control: None (not found)

    Control->>Session: new Session("npm run dev", record, fallback)
    Session->>Process: spawn(npm run dev)
    Process-->>Session: server starting...
    Session->>FS: create_log(~/.claude-control/sessions/{id}/)
    Session->>Store: initialize_if_enabled()
    Session->>Registry: register(self)
    Registry-->>Control: session registered

    Control->>Lock: release()
    Control-->>User1: session instance

    Note over Process: Server keeps running

    User2->>Control: control("npm run dev", reuse=True)
    Control->>Lock: acquire()
    Control->>Registry: find_session("npm run dev")

    alt Session alive
        Registry->>Session: is_alive()
        Session->>Process: poll()
        Process-->>Session: running (None)
        Session-->>Registry: True
        Registry-->>Control: existing session
        Control->>Lock: release()
        Control-->>User2: same session instance
    else Session dead
        Registry->>Session: is_alive()
        Session->>Process: poll()
        Process-->>Session: exit_code
        Session-->>Registry: False
        Registry->>Registry: remove(session)
        Control->>Session: new Session("npm run dev", record, fallback)
        Note over Control: Creates new session
        Control-->>User2: new session instance
    end

    Note over Registry: Cleanup on exit
    Registry->>Registry: atexit handler
    Registry->>Session: close_all()
    Session->>Process: terminate()
    Session->>Store: flush_summaries()
```

### Performance Notes
- Registry lookup: O(n) with typically <20 sessions
- Lock contention: Minimal, held briefly
- Session creation: ~10-100ms overhead

### Failure Modes
- Registry corruption: Rebuilt on next access
- Zombie sessions: Cleaned by psutil check
- Lock deadlock: Timeout protection (30s)
- TapeStore load failure: Falls back to live mode with warning

### Concurrency
- Thread-safe via global lock
- One writer at a time for registry
- Sessions themselves not thread-safe
- TapeStore guarded by RW locks for concurrent playback

---

## 8. Black Box Testing Flow (Existing Feature)
**Trigger:** `black_box_test("app", timeout=10)`  
**Outcome:** Comprehensive test report with pass/fail for multiple test categories

```mermaid
sequenceDiagram
    participant User
    participant BBT as BlackBoxTester
    participant Test as Test Suite
    participant Session as Session Pool
    participant Process as Test Process
    participant Monitor as psutil Monitor
    participant Report
    participant FS as File System

    User->>BBT: black_box_test("app")
    BBT->>BBT: initialize test suite

    rect rgb(255, 245, 230)
        Note over BBT: Startup Test
        BBT->>Test: test_startup()
        Test->>Session: create_session("app", record=DISABLED)
        Session->>Process: spawn(app)

        alt Successful start
            Process-->>Session: output
            Session->>Test: check_patterns(output)
            Test-->>BBT: PASS
        else Spawn failure
            Process-->>Session: error
            Test-->>BBT: FAIL + error
        end
    end

    rect rgb(230, 255, 245)
        Note over BBT: Resource Monitoring
        BBT->>Test: test_resource_usage()
        Test->>Monitor: get_process_info(pid)
        Test->>Session: run_workload()

        par Monitor CPU
            Monitor->>Process: cpu_percent()
            Process-->>Monitor: cpu_usage
        and Monitor Memory
            Monitor->>Process: memory_info()
            Process-->>Monitor: memory_usage
        and Monitor Threads
            Monitor->>Process: num_threads()
            Process-->>Monitor: thread_count
        end

        Monitor-->>Test: resource_metrics
        Test-->>BBT: PASS/FAIL + metrics
    end

    rect rgb(245, 230, 255)
        Note over BBT: Concurrent Session Test
        BBT->>Test: test_concurrent()

        par Session 1
            Test->>Session: create_session(1, record=DISABLED)
            Session->>Process: spawn(app)
        and Session 2
            Test->>Session: create_session(2, record=DISABLED)
            Session->>Process: spawn(app)
        and Session 3
            Test->>Session: create_session(3, record=DISABLED)
            Session->>Process: spawn(app)
        end

        Test->>Test: interact_with_all()
        Test-->>BBT: concurrency results
    end

    rect rgb(255, 230, 230)
        Note over BBT: Fuzz Testing
        BBT->>Test: run_fuzz_test()

        loop 50 inputs
            Test->>Test: generate_fuzz_input()
            Test->>Session: send(fuzz_input)
            Session->>Process: write stdin

            alt Normal response
                Process-->>Session: output
            else Crash
                Process-->>Session: SIGTERM/SEGV
                Test->>BBT: crash_found(input)
            else Hang
                Session-->>Test: timeout
                Test->>Session: kill()
            end
        end

        Test-->>BBT: fuzz_results
    end

    BBT->>Report: generate_report(all_results)
    Report->>FS: save(~/.claude-control/test-reports/)
    Report-->>BBT: report_path
    BBT-->>User: {results, report, report_path}
```

### Performance Notes
- Full test suite: 10-120 seconds
- Parallel tests: Limited by system resources
- Fuzz testing: Configurable iterations (default 50)

### Failure Modes
- Test process crash: Caught and reported
- Resource exhaustion: Killed with report
- Infinite loops: Timeout protection
- System limits: Graceful degradation
- Tape miss during replay: surfaces error immediately (CI default `record=DISABLED`, `fallback=NOT_FOUND`)

---

## 9. Command Chain Execution (Existing Feature)
**Trigger:** CommandChain with conditional execution  
**Outcome:** Sequential execution with condition-based flow control

```mermaid
sequenceDiagram
    participant User
    participant Chain as CommandChain
    participant Session
    participant Process
    participant Results as Result Store

    User->>Chain: add("git pull")
    User->>Chain: add("npm install", condition=has_package_json)
    User->>Chain: add("npm test", on_success=True)
    User->>Chain: add("npm build", on_success=True)
    User->>Chain: run()

    Chain->>Session: create_session("bash", record=cfg)
    Session->>Process: spawn(bash)

    rect rgb(230, 245, 255)
        Note over Chain: Command 1: git pull
        Chain->>Session: sendline("git pull")
        Session->>Process: execute
        Process-->>Session: output + exit_code
        Session-->>Chain: success=True
        Chain->>Results: store(cmd1, output)
    end

    rect rgb(245, 255, 230)
        Note over Chain: Command 2: Conditional
        Chain->>Chain: evaluate condition
        Chain->>Results: get_previous()
        Results-->>Chain: git pull output

        alt package.json changed
            Chain->>Session: sendline("npm install")
            Session->>Process: execute
            Process-->>Session: output
            Session-->>Chain: success=True
            Chain->>Results: store(cmd2, output)
        else package.json unchanged
            Chain->>Chain: skip command
            Chain->>Results: store(cmd2, skipped)
        end
    end

    rect rgb(255, 245, 230)
        Note over Chain: Command 3: on_success
        Chain->>Results: check_previous_success()

        alt Previous succeeded
            Chain->>Session: sendline("npm test")
            Session->>Process: execute

            alt Tests pass
                Process-->>Session: exit_code=0
                Session-->>Chain: success=True
            else Tests fail
                Process-->>Session: exit_code=1
                Session-->>Chain: success=False
                Note over Chain: Stop chain
            end
        else Previous failed
            Chain->>Chain: skip remaining
        end
    end

    Chain->>Session: close()
    Session->>Process: terminate()
    Session->>Store: flush_pending_tapes()
    Chain->>Results: get_all()
    Results-->>Chain: [{cmd, output, success}, ...]
    Chain-->>User: execution results
```

### Performance Notes
- Sequential execution: No parallelization
- Condition evaluation: <1ms overhead
- State preserved between commands

### Failure Modes
- Command failure: Stops chain if on_success=True
- Condition error: Treated as False, command skipped
- Session death: Chain aborts with error
- Tape write failure: Rolls back to live execution and logs warning

---

## 10. Pattern Detection and State Transition (Existing Feature)
**Trigger:** Output from CLI program triggers state change  
**Outcome:** Accurate state tracking and pattern extraction

```mermaid
sequenceDiagram
    participant Session
    participant Buffer as Output Buffer
    participant Detector as Pattern Detector
    participant Classifier as Output Classifier
    participant State as State Machine
    participant Registry as Pattern Registry
    participant Recorder

    Session->>Buffer: append(new_output)
    Buffer->>Buffer: maintain_window(10k_lines)

    Session->>Detector: detect_patterns(output)

    par Prompt Detection
        Detector->>Registry: get(COMMON_PROMPTS)
        Registry-->>Detector: prompt_patterns
        Detector->>Detector: match_all(output)
    and Error Detection
        Detector->>Registry: get(COMMON_ERRORS)
        Registry-->>Detector: error_patterns
        Detector->>Detector: find_errors(output)
    and Format Detection
        Detector->>Classifier: detect_format(output)
        Classifier->>Classifier: try_json()
        Classifier->>Classifier: try_xml()
        Classifier->>Classifier: detect_table()
    end

    alt Prompt Found
        Detector->>State: new_prompt(pattern)
        State->>State: update_state("prompt_wait")
        State-->>Session: state_changed
    else Error Found
        Detector->>State: error_detected(pattern)
        State->>State: update_state("error")
        State-->>Session: needs_recovery
    else Data Format Found
        Classifier-->>Session: {format: "json", data: parsed}
        Session->>Session: store_structured_data()
    end

    rect rgb(255, 230, 230)
        Note over State: State Transition
        State->>State: check_transitions(current, output)

        alt Valid Transition
            State->>State: move_to(new_state)
            State->>State: log_transition(from, to, trigger)
            State-->>Session: state = new_state
            Session-->>Recorder: annotate_exchange(state_change)
        else Invalid Transition
            State->>State: log_invalid(attempted)
            State-->>Session: state unchanged
        end
    end

    Session-->>Session: continue or react to state
```

### Performance Notes
- Pattern matching: ~1ms per 100 lines
- JSON parsing: Cached if unchanged
- State transitions: O(1) lookup

### Failure Modes
- Ambiguous patterns: First match wins
- Malformed data: Logged, processing continues
- State loops: Detected and broken
- Annotation failure: Recorder keeps raw output without extra metadata

---

## 11. Parallel Command Execution (Existing Feature)
**Trigger:** `parallel_commands(["cmd1", "cmd2", "cmd3"])`  
**Outcome:** Concurrent execution with result aggregation

```mermaid
sequenceDiagram
    participant User
    participant Parallel as parallel_commands
    participant Pool as ThreadPool
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant W3 as Worker 3
    participant S1 as Session 1
    participant S2 as Session 2
    participant S3 as Session 3
    participant Results

    User->>Parallel: parallel_commands([...])
    Parallel->>Pool: submit(tasks)

    par Worker dispatch
        Pool->>W1: run(cmd1)
        W1->>S1: Session(cmd1, record=cfg)
        S1->>S1: execute()

        Pool->>W2: run(cmd2)
        W2->>S2: Session(cmd2, record=cfg)
        S2->>S2: execute()

        Pool->>W3: run(cmd3)
        W3->>S3: Session(cmd3, record=cfg)
        S3->>S3: execute()
    end

    alt S1 succeeds
        S1-->>W1: {success: true, output: "..."}
        W1->>Results: store(cmd1, result)
    else S1 fails
        S1-->>W1: {success: false, error: "..."}
        W1->>Results: store(cmd1, result)
    end

    alt S2 succeeds
        S2-->>W2: {success: true, output: "..."}
        W2->>Results: store(cmd2, result)
    else S2 fails
        S2-->>W2: {success: false, error: "..."}
        W2->>Results: store(cmd2, result)
    end

    S3-->>W3: result
    W3->>Results: store(cmd3, result)

    Pool->>Pool: wait_all_complete()
    Pool->>Parallel: all_futures_done

    Parallel->>Results: aggregate()
    Results-->>Parallel: {cmd1: {...}, cmd2: {...}, cmd3: {...}}

    Parallel->>Pool: shutdown()
    Parallel-->>User: aggregated_results
```

### Performance Notes
- Parallel speedup: Limited by slowest command
- Thread pool overhead: ~1ms per worker
- Max concurrent: System dependent (default 10)

### Failure Modes
- Worker crash: Caught, error in result
- Resource exhaustion: Queued execution
- Deadlock: Timeout on all operations
- TapeStore contention: Background index reads share RW locks safely

### Concurrency
- Thread-safe result aggregation
- Independent sessions per worker
- No shared state between commands
- Per-session TapeStore handles mark_used/new independently

---

## 12. Real-time Stream Processing (Existing Feature)
**Trigger:** Session with `stream=True` creating named pipe  
**Outcome:** Real-time output streaming to external consumers

```mermaid
sequenceDiagram
    participant User
    participant Session
    participant Process
    participant Writer as Pipe Writer Thread
    participant Pipe as Named Pipe
    participant Reader as External Reader
    participant Recorder

    User->>Session: control("server", stream=True)
    Session->>Session: create_pipe(/tmp/claudecontrol/{id})
    Session->>Writer: start_thread()
    Session->>Process: spawn(server)
    Session-->>User: session with pipe_path

    Note over User: User starts reader
    User->>Reader: tail -f {pipe_path}
    Reader->>Pipe: open(read)

    loop Output Stream
        Process-->>Session: stdout/stderr data
        Session->>Session: buffer.append(data)
        Session->>Writer: queue.put(data)

        Writer->>Writer: format([timestamp][TYPE])
        Writer->>Pipe: write(formatted)
        Pipe-->>Reader: stream data
        Reader-->>Reader: display

        alt Buffer full
            Session->>Session: rotate_buffer()
            Session->>Session: keep_recent(10k)
        end
    end

    par User sends input
        User->>Session: sendline("command")
        Session->>Process: write(stdin)
        Session->>Writer: queue.put([IN] command)
        Writer->>Pipe: write([timestamp][IN] command)
        Pipe-->>Reader: show input
    end

    Note over Session: Session closes
    User->>Session: close()
    Session->>Writer: stop_thread()
    Writer->>Pipe: close()
    Session->>Process: terminate()
    Session->>Recorder: flush_streaming_exchange()
    Session->>Session: unlink(pipe_path)
```

### Performance Notes
- Stream latency: <1ms typically
- Buffer size: 64KB OS pipe buffer
- No persistence: Real-time only

### Failure Modes
- Reader disconnects: Writer continues
- Pipe full: Blocks writer (rare)
- No reader: Data discarded
- Recording disabled: Recorder skips streaming exchange gracefully

---

## Summary of Complex Interactions

These sequence diagrams illustrate ClaudeControl's most complex flows:

1. **Session Lifecycle** - Unified record/replay transport selection
2. **Tape Recording** - Deterministic capture, normalization, and persistence
3. **Tape Playback** - Match-driven output streaming with latency/error policies
4. **CLI Record/Replay** - User-facing orchestration and tape tooling
5. **Exit Summary** - Accounting for new and unused tapes
6. **Investigation** - Multi-phase discovery with optional tape capture
7. **Session Reuse** - Thread-safe registry with replay-aware cleanup
8. **Black Box Testing** - Parallel test execution with explicit record modes
9. **Command Chains** - Conditional sequential execution with tape flushes
10. **Pattern Detection** - Real-time classification feeding Recorder annotations
11. **Parallel Execution** - Concurrent command processing across sessions
12. **Stream Processing** - Real-time output streaming compatible with Recorder

Each flow demonstrates:
- Multiple component coordination (3+ actors)
- Asynchronous or parallel operations
- Complex error handling and recovery
- Critical timing and ordering constraints

The diagrams focus on the non-obvious interactions that make ClaudeControl powerful yet reliable for CLI automation, testing, discovery, and deterministic record/replay.
