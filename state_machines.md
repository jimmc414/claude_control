# ClaudeControl State Machine Diagrams

The following state machines capture the complete control flow of ClaudeControl after adding Talkback-style record & replay
capabilities while preserving the original investigation, testing, and automation behaviors. They show how the new replay
package (tapes, matchers, decorators, latency/error injection, summaries) integrates seamlessly with the existing session
management stack built on `pexpect`.

---

## 1. Session Lifecycle State Machine (Live & Replay)
**Context:** Manages the lifecycle of a `Session` from construction through shutdown, covering both live subprocess control and
replay-mode transport selection.
**State Storage:** Session object (in-memory), TapeStore cache on disk, and summary accounting in `~/.claude-control/sessions/`.

```mermaid
stateDiagram-v2
    [*] --> Initializing: Session() called

    state Initializing {
        [*] --> LoadingConfig
        LoadingConfig --> LoadingTapes: replay options enabled
        LoadingConfig --> SelectingTransport: replay disabled
        LoadingTapes --> SelectingTransport: TapeStore ready
    }

    SelectingTransport --> LiveSpawning: RecordMode != DISABLED or fallback proxy
    SelectingTransport --> ReplayPrimed: FallbackMode == NOT_FOUND and tape hit
    SelectingTransport --> ReplayPrimed: FallbackMode == PROXY and tape hit
    SelectingTransport --> LiveSpawning: No tape match and proxy allowed
    SelectingTransport --> Failed: No tape match and fallback NOT_FOUND

    LiveSpawning --> RecorderArmed: Process started
    LiveSpawning --> Failed: Spawn error

    ReplayPrimed --> StreamingReplay: Player engaged

    RecorderArmed --> Active: Recorder attached
    StreamingReplay --> Active: Player output buffered

    Active --> Active: send/expect commands
    Active --> Waiting: expect() pending
    Active --> Streaming: stream=True from live process
    Active --> StreamingReplay: replay chunk pacing continues
    Active --> Suspended: pause() called
    Active --> Closing: close() called

    Waiting --> Active: Pattern matched
    Waiting --> TimedOut: Timeout exceeded
    Waiting --> Dead: Process died

    TimedOut --> Active: Retry/Continue
    TimedOut --> Failed: Max retries

    Streaming --> Active: stop streaming
    Streaming --> Closing: Session ends

    StreamingReplay --> Active: Replay chunk drained
    StreamingReplay --> Closing: Replay complete

    Suspended --> Active: resume() called
    Suspended --> Closing: timeout/close()

    Dead --> RecorderFlush: Live mode cleanup pending
    Dead --> ReplayFlush: Replay mode cleanup pending

    RecorderFlush --> Closing: exchanges persisted
    ReplayFlush --> Closing: final tape usage recorded

    Closing --> PrintingSummary: summary=True
    Closing --> Closed: summary disabled

    PrintingSummary --> Closed: summary emitted

    Closed --> [*]: Resources freed
    Failed --> [*]: Error handled
```

### Key Additions
- **LoadingTapes**: Loads JSON5 tapes via `TapeStore`, validates schema, applies normalization/redaction defaults.
- **SelectingTransport**: Chooses between live `pexpect` transport and replay `Player` based on Record/Fallback modes.
- **ReplayPrimed / StreamingReplay**: Model deterministic playback with latency/error injection policies.
- **RecorderArmed / RecorderFlush**: Capture exchanges through `Recorder` with decorators, redaction, and name generation.
- **PrintingSummary**: Emits exit summary of new and unused tapes when enabled.

### Transition Guards
- `SelectingTransport → ReplayPrimed`: Tape match found by matchers after normalization and decorators.
- `SelectingTransport → LiveSpawning`: No tape match or proxy mode selected.
- `Active → StreamingReplay`: Player still streaming recorded chunks with pacing.
- `Dead → RecorderFlush`: RecordMode allows writing tapes.
- `Closing → PrintingSummary`: `summary=True` and TapeStore has accounting events.

### Transition Actions
- `Initializing → LoadingConfig`: Load config and CLI flags, seed RNG for deterministic latency/error injection.
- `LoadingTapes → SelectingTransport`: Build TapeIndex with match keys and mark tapes unused.
- `SelectingTransport → ReplayPrimed`: Prepare Player buffer, resolve latency/error policies.
- `LiveSpawning → RecorderArmed`: Attach `Recorder` via `logfile_read`, start exchange timer.
- `RecorderFlush → Closing`: Serialize exchanges to JSON5, apply tape decorators, acquire file lock, write via `TapeStore`.
- `PrintingSummary → Closed`: Render exit summary listing new/unused tapes.

### Timeout Behaviors
- **Waiting**: Configurable `expect` timeout (default 30s) with recorder capturing TIMEOUT output.
- **StreamingReplay**: Latency policies enforce pacing; global timeout aborts playback if Player stalls.
- **Suspended**: Session inactivity timeout (default 300s).

### Concurrency Control
- TapeStore read/write locks, Recorder exchange lock, session-level mutex around transport operations.

---

## 2. Recorder Exchange State Machine
**Context:** Tracks how the Recorder segments live I/O into exchanges and persists tapes according to RecordMode.
**State Storage:** Recorder buffer (memory), TapeStore staging area on disk.

```mermaid
stateDiagram-v2
    [*] --> Idle

    Idle --> PreparingExchange: on_send()/sendline()
    PreparingExchange --> CapturingOutput: expect() monitoring
    CapturingOutput --> CapturingOutput: more output chunks
    CapturingOutput --> Finalizing: prompt matched or session closed
    Finalizing --> Redacting: secrets detected
    Finalizing --> Decorating: no redaction needed
    Redacting --> Decorating: redact applied
    Decorating --> Persisting: RecordMode != DISABLED
    Decorating --> Discarding: RecordMode == DISABLED
    Persisting --> Idle: TapeStore.write_tape()
    Discarding --> Idle

    Finalizing --> Idle: recorder disabled mid-session
```

### Guards & Policies
- `PreparingExchange → CapturingOutput`: Recorder armed and TIMEOUT guard registered.
- `CapturingOutput → Finalizing`: Prompt pattern matched via detectors or expect() completion.
- `Finalizing → Redacting`: Secret detectors trigger (passwords, tokens, keys).
- `Decorating → Persisting`: RecordMode in {NEW, OVERWRITE} and TapeNameGenerator resolved.

### Actions
- `PreparingExchange`: Snapshot pre-state (prompt signature, env hash).
- `CapturingOutput`: Buffer chunk with timestamps, encode as base64 when non-text.
- `Redacting`: Apply redact rules unless `CLAUDECONTROL_REDACT=0`.
- `Decorating`: Run input/output/tape decorators.
- `Persisting`: Acquire portalocker lock, dump JSON5 via pyjson5.

---

## 3. Replay Player State Machine
**Context:** Controls tape playback, matcher resolution, latency/error injection, and fallback to live execution.
**State Storage:** Player buffer, TapeStore usage ledger, optional live transport when proxying.

```mermaid
stateDiagram-v2
    [*] --> MatchingExchange

    MatchingExchange --> StreamingChunks: tape match found
    MatchingExchange --> Missed: no match

    Missed --> ProxyLive: FallbackMode == PROXY
    Missed --> Failing: FallbackMode == NOT_FOUND

    ProxyLive --> MatchingExchange: live output recorded for next input (optional NEW mode)
    Failing --> [*]

    StreamingChunks --> InjectingLatency: latency policy active
    StreamingChunks --> InjectingError: error policy triggers
    StreamingChunks --> AwaitingNextInput: output complete

    InjectingLatency --> AwaitingNextInput: pacing finished
    InjectingError --> Failing: injected failure

    AwaitingNextInput --> MatchingExchange: next send()
    AwaitingNextInput --> Completed: process exit recorded

    Completed --> [*]
```

### Guards & Actions
- `MatchingExchange → StreamingChunks`: Matchers (command, env, prompt, stdin, state hash) succeed after normalization.
- `StreamingChunks → InjectingLatency`: Latency policy returns >0 delay.
- `StreamingChunks → InjectingError`: Error policy hits probabilistic threshold.
- `ProxyLive → MatchingExchange`: Live subprocess output captured to Recorder when RecordMode permits NEW/OVERWRITE.
- `AwaitingNextInput → Completed`: Recorded exit metadata applied to session termination.

### Error Handling
- `Missed → Failing`: Raises `TapeMissError` with diff summary for debugging.
- `InjectingError → Failing`: Synthesizes failures (truncate output, raise signal) for resilience testing.

---

## 4. Tape Store & Summary State Machine
**Context:** Oversees tape discovery, indexing, usage accounting, and exit summary reporting.
**State Storage:** TapeStore in-memory index, filesystem tape directory, summary tracker.

```mermaid
stateDiagram-v2
    [*] --> Scanning
    Scanning --> Validating: JSON5 loaded
    Validating --> Indexing: schema ok
    Validating --> Quarantined: schema error

    Quarantined --> [*]: manual fix required

    Indexing --> Ready

    Ready --> MarkingUsed: tape hit during replay
    Ready --> MarkingNew: tape written during record
    Ready --> Ready: idle wait

    MarkingUsed --> Ready
    MarkingNew --> Ready

    Ready --> Summarizing: session closing && summary=True
    Summarizing --> [*]: summary printed
```

### Actions
- `Scanning`: Walk tape directory recursively once at startup.
- `Validating`: Parse JSON5, apply normalization previews, run fastjsonschema if available.
- `Indexing`: Build normalized keys, register decorators, seed RNG for deterministic ordering.
- `MarkingUsed`: Flag tape/exchange as used for summary and optional eviction heuristics.
- `MarkingNew`: Cache pending writes, commit atomically, refresh index lazily.
- `Summarizing`: Emit new vs unused tape report.

---

## 5. Program Investigation State Machine
**Context:** Tracks discovery progress for unknown CLI programs. Updated to note replay hooks for deterministic automation.
**State Storage:** InvestigationReport object with persisted JSON snapshots and optional tapes for reproducibility.

```mermaid
stateDiagram-v2
    [*] --> Starting: investigate_program()

    Starting --> Probing: Process spawned
    Starting --> Aborted: Spawn failed

    state Investigation {
        Probing --> DiscoveringPrompt: Initial output captured (tape optional)
        DiscoveringPrompt --> Classifying: Analyze prompt patterns
        Classifying --> RecordingBaseline: RecordMode NEW to capture golden path
        RecordingBaseline --> ExploringCommands: Replay-enabled fuzz harness
        ExploringCommands --> DetectingStates: Identify nested prompts
        DetectingStates --> MappingTransitions: Build state graph
        MappingTransitions --> CapturingArtifacts: Save tapes & JSON report
        CapturingArtifacts --> Finalizing: Close sessions, print summary
    }

    Finalizing --> [*]
    Aborted --> [*]
```

### Notable Behaviors
- Baseline discoveries can be replayed deterministically to compare future runs.
- Tape summary output highlights unused explorations to revisit.
- Investigation artifacts include both report JSON and tapes.

---

## 6. Black Box Test Execution State Machine
**Context:** Orchestrates automated testing of discovered CLIs with optional replay for deterministic CI.
**State Storage:** TestPlan, TapeStore references, result ledger.

```mermaid
stateDiagram-v2
    [*] --> PreparingPlan
    PreparingPlan --> SelectingMode: choose live vs replay
    SelectingMode --> StartupTest
    SelectingMode --> ReplayWarmup: preload tapes

    StartupTest --> StartupPassed
    StartupTest --> StartupFailed

    StartupPassed --> ResourceTest
    ResourceTest --> MonitoringResources

    MonitoringResources --> ConcurrentTest: thresholds ok
    MonitoringResources --> SkipConcurrent: resources exceeded

    ConcurrentTest --> RunningParallel
    RunningParallel --> CollatingResults

    ReplayWarmup --> RunningReplay: Player mode for deterministic suites
    RunningReplay --> CollatingResults

    CollatingResults --> FuzzTest
    SkipConcurrent --> FuzzTest

    FuzzTest --> Fuzzing
    Fuzzing --> CrashFound
    Fuzzing --> FuzzComplete

    CrashFound --> RecordingCrash: record new tape if allowed
    RecordingCrash --> Fuzzing

    FuzzComplete --> TestsComplete
    TestsComplete --> GeneratingReport
    GeneratingReport --> SavingResults
    SavingResults --> PrintingSummary
    PrintingSummary --> [*]

    StartupFailed --> Abort
    Abort --> [*]
```

### Replay Integrations
- `SelectingMode`: Chooses Record/Replay settings per test run.
- `ReplayWarmup`: Loads required tapes upfront; fails fast if missing in strict CI.
- `RecordingCrash`: Ensures reproducible crash tapes for debugging.
- `PrintingSummary`: Emits tape summary alongside test report.

---

## 7. Discovered CLI Program State Machine
**Context:** Represents the inferred state model of an investigated CLI program. Unchanged structurally, but tapes can document
transitions for regression checks.
**State Storage:** ProgramState objects within InvestigationReport plus optional tape references per edge.

```mermaid
stateDiagram-v2
    [*] --> Initial: Program starts

    Initial --> MainPrompt: Initialization complete
    Initial --> ErrorState: Startup failure

    MainPrompt --> MainPrompt: Unrecognized command
    MainPrompt --> HelpMode: help/? command
    MainPrompt --> ConfigMode: config command
    MainPrompt --> DataMode: data entry command
    MainPrompt --> Processing: Valid action command
    MainPrompt --> Exiting: exit/quit command

    HelpMode --> MainPrompt: Any key/command

    ConfigMode --> ConfigPrompt: Enter config mode
    ConfigPrompt --> ConfigPrompt: Set values
    ConfigPrompt --> MainPrompt: exit/done
    ConfigPrompt --> ErrorState: Invalid config

    DataMode --> DataPrompt: Ready for input
    DataPrompt --> DataPrompt: Enter data
    DataPrompt --> Processing: Process data
    DataPrompt --> MainPrompt: Cancel/escape

    Processing --> MainPrompt: Success
    Processing --> ErrorState: Failure
    Processing --> Processing: Long operation

    ErrorState --> MainPrompt: Recover command
    ErrorState --> ErrorState: More errors
    ErrorState --> Exiting: Fatal error

    Exiting --> CleaningUp: Shutdown initiated
    CleaningUp --> [*]: Exit complete
```

### Tape Annotations
- Each transition can point to a tape exchange capturing expected prompts and outputs.
- Replay ensures consistent prompts for regression and automation scripts.

---

## Summary

These state machines integrate ClaudeControl’s legacy capabilities with the new replay subsystem:

1. **Session Lifecycle** now branches into live or replay transports, handles recorder flushes, and prints exit summaries.
2. **Recorder**, **Player**, and **TapeStore** state machines model tape creation, deterministic playback, and accounting.
3. **Program Investigation** and **Black Box Testing** leverage tapes for reproducible exploration, fuzzing, and CI runs.
4. **Discovered CLI Program** models remain, now augmented by tape references for regression safety.

Together they describe how ClaudeControl deterministically manages CLI processes across Discover, Test, Automate, and the new
Record/Replay workflows.
