# ClaudeControl Sequence Diagrams

## 1. Program Investigation Flow
**Trigger:** User runs `investigate_program("unknown_cli")`
**Outcome:** Complete interface map and behavioral report of the CLI program

```mermaid
sequenceDiagram
    participant User
    participant API as ProgramInvestigator
    participant Session
    participant Process as Target Process
    participant Pattern as Pattern Matcher
    participant State as State Tracker
    participant Report as Report Builder
    participant FS as File System

    User->>API: investigate_program("unknown_cli")
    API->>Session: create_session(timeout=10)
    Session->>Process: spawn(unknown_cli)
    Process-->>Session: initial output
    Session-->>API: output buffer
    
    rect rgb(230, 245, 255)
        Note over API: Discovery Phase
        API->>Pattern: detect_prompt(output)
        Pattern-->>API: prompt pattern
        API->>State: register_state("initial", prompt)
        
        loop Probe Commands
            API->>Session: send(probe_cmd)
            Session->>Process: write to stdin
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
    end

    Report->>FS: save_json(~/.claude-control/investigations/)
    FS-->>Report: report_path
    Report-->>API: InvestigationReport
    API-->>User: report with summary()

    Note over Process: Process kept alive if persist=True
```

### Performance Notes
- Typical execution: 5-60 seconds depending on program complexity
- Bottleneck: Waiting for program responses (timeout critical)
- Optimization: Parallel probing when safe

### Failure Modes
- Program doesn't start: ProcessError raised immediately
- No prompt detected: Falls back to send-only mode
- Hangs on input: Timeout protection (default 10s)
- Dangerous operations: Safe mode blocks execution

---

## 2. Session Reuse and Registry Management
**Trigger:** Multiple calls to `control("server", reuse=True)`
**Outcome:** Efficient session reuse across script runs

```mermaid
sequenceDiagram
    participant User1 as Script 1
    participant User2 as Script 2
    participant Control as control()
    participant Registry as Global Registry
    participant Lock as Thread Lock
    participant Session
    participant Process as Server Process
    participant FS as File System

    User1->>Control: control("npm run dev", reuse=True)
    Control->>Lock: acquire()
    Lock-->>Control: locked
    
    Control->>Registry: find_session("npm run dev")
    Registry-->>Control: None (not found)
    
    Control->>Session: new Session("npm run dev")
    Session->>Process: spawn(npm run dev)
    Process-->>Session: server starting...
    Session->>FS: create_log(~/.claude-control/sessions/{id}/)
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
        Control->>Session: new Session("npm run dev")
        Note over Control: Creates new session
        Control-->>User2: new session instance
    end

    Note over Registry: Cleanup on exit
    Registry->>Registry: atexit handler
    Registry->>Session: close_all()
    Session->>Process: terminate()
```

### Performance Notes
- Registry lookup: O(n) with typically <20 sessions
- Lock contention: Minimal, held briefly
- Session creation: ~10-100ms overhead

### Failure Modes
- Registry corruption: Rebuilt on next access
- Zombie sessions: Cleaned by psutil check
- Lock deadlock: Timeout protection (30s)

### Concurrency
- Thread-safe via global lock
- One writer at a time for registry
- Sessions themselves not thread-safe

---

## 3. Black Box Testing Flow
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
        Test->>Session: create_session("app")
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
            Test->>Session: create_session(1)
            Session->>Process: spawn(app)
        and Session 2
            Test->>Session: create_session(2)
            Session->>Process: spawn(app)
        and Session 3
            Test->>Session: create_session(3)
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

---

## 4. Command Chain Execution
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

    Chain->>Session: create_session("bash")
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

---

## 5. Pattern Detection and State Transition
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

---

## 6. Parallel Command Execution
**Trigger:** `parallel_commands(["cmd1", "cmd2", "cmd3"])`
**Outcome:** Concurrent execution with result aggregation

```mermaid
sequenceDiagram
    participant User
    participant Parallel as parallel_commands()
    participant Pool as ThreadPoolExecutor
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant W3 as Worker 3
    participant S1 as Session 1
    participant S2 as Session 2
    participant S3 as Session 3
    participant Results

    User->>Parallel: parallel_commands(cmds, max=3)
    Parallel->>Pool: create(max_workers=3)
    
    par Worker 1
        Pool->>W1: execute(cmd1)
        W1->>S1: create_session()
        S1->>S1: run_command(cmd1)
        Note over S1: Executing...
    and Worker 2
        Pool->>W2: execute(cmd2)
        W2->>S2: create_session()
        S2->>S2: run_command(cmd2)
        Note over S2: Executing...
    and Worker 3
        Pool->>W3: execute(cmd3)
        W3->>S3: create_session()
        S3->>S3: run_command(cmd3)
        Note over S3: Executing...
    end

    alt S1 completes first
        S1-->>W1: {success: true, output: "..."}
        W1->>Results: store(cmd1, result)
    else S1 times out
        S1-->>W1: TimeoutError
        W1->>Results: store(cmd1, {success: false, error: "timeout"})
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

### Concurrency
- Thread-safe result aggregation
- Independent sessions per worker
- No shared state between commands

---

## 7. Real-time Stream Processing
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

---

## Summary of Complex Interactions

These sequence diagrams illustrate ClaudeControl's most complex flows:

1. **Investigation** - Multi-phase discovery with state tracking
2. **Session Reuse** - Thread-safe registry with lifecycle management  
3. **Black Box Testing** - Parallel test execution with monitoring
4. **Command Chains** - Conditional sequential execution
5. **Pattern Detection** - Real-time classification and state management
6. **Parallel Execution** - Concurrent command processing
7. **Stream Processing** - Real-time output streaming via named pipes

Each flow demonstrates:
- Multiple component coordination (3+ actors)
- Asynchronous or parallel operations
- Complex error handling and recovery
- Critical timing and ordering constraints

The diagrams focus on the non-obvious interactions that make ClaudeControl powerful yet reliable for CLI automation, testing, and discovery.