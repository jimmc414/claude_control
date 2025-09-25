# ClaudeControl Data Flow Diagram

## Main Data Flow Architecture

```mermaid
graph TD
    subgraph "Input Sources"
        USER_CMD[/User Commands<br/>CLI Args/]
        USER_INPUT[/Interactive Input<br/>stdin/]
        CONFIG_FILE[/Config Files<br/>JSON/]
        TARGET_PROG[/Target Program<br/>Process Output/]
    end
    
    subgraph "Entry Points & Routing"
        CLI[CLI Parser<br/>argparse]
        MENU[Interactive Menu<br/>User Selection]
        API[Python API<br/>Direct Import]
        
        ROUTER{Route to<br/>Operation}
    end
    
    subgraph "Core Operations"
        subgraph "Discovery Flow"
            INVESTIGATE[Program<br/>Investigator]
            PROBE[Quick Probe<br/>Interface Check]
            STATE_MAP[State Mapper<br/>FSM Discovery]
            FUZZ[Fuzzer<br/>Input Generator]
        end
        
        subgraph "Testing Flow"
            BLACKBOX[Black Box<br/>Tester]
            TEST_SUITE[Test Suite<br/>Runner]
            RESOURCE_MON[Resource<br/>Monitor]
        end
        
        subgraph "Automation Flow"
            SESSION[Session<br/>Controller]
            CHAIN[Command<br/>Chain]
            PARALLEL[Parallel<br/>Executor]
        end
    end
    
    subgraph "Processing Pipeline"
        SPAWN[Process<br/>Spawner<br/>pexpect]
        PATTERN_MATCH{Pattern<br/>Matcher}
        OUTPUT_BUFFER[Output<br/>Buffer<br/>10K lines]
        CLASSIFIER[Output<br/>Classifier]
    end

    subgraph "Replay Orchestration"
        RECORDER[Recorder<br/>Exchange Builder]
        PLAYER[Player<br/>Replay Transport]
        MATCHERS[Matchers<br/>Command/Env/Stdin]
        NORMALIZER[Normalizers<br/>ANSI/Volatile]
        DECORATORS[Decorators<br/>Input/Output/Tape]
        REDACTOR[Redactor<br/>Secret Filters]
        LATENCY[Latency Policy<br/>Chunk Pacing]
        ERRORS[Error Injector<br/>Probabilistic]
    end
    
    subgraph "Data Storage"
        REGISTRY[(Session<br/>Registry<br/>In-Memory)]
        SESSION_LOG[(Session Logs<br/>~/.claude-control/<br/>sessions/)]
        INVESTIGATION_DB[(Investigation<br/>Reports<br/>JSON)]
        TEST_REPORTS[(Test Reports<br/>JSON)]
        PROG_CONFIGS[(Program<br/>Configs<br/>JSON)]
        NAMED_PIPE[(Named Pipes<br/>/tmp/claudecontrol/)]
        TAPE_STORE[(TapeStore Cache<br/>In-Memory)]
        TAPE_INDEX[(Tape Index<br/>Normalized Keys)]
        TAPE_FILES[(Tape Files<br/>JSON5)]
    end

    subgraph "Output Destinations"
        CONSOLE[/Console Output<br/>stdout/]
        REPORT_FILE[/Report Files<br/>JSON/Markdown/]
        PIPE_STREAM[/Stream Output<br/>Named Pipe/]
        CALLBACK[/User Callbacks<br/>Python Functions/]
        SUMMARY_OUT[/Exit Summary<br/>Console Report/]
    end
    
    %% Input Flow
    USER_CMD -->|CLI args| CLI
    USER_INPUT -->|stdin| MENU
    USER_CMD -->|import| API
    CONFIG_FILE -->|JSON config| SESSION
    
    CLI --> ROUTER
    MENU --> ROUTER
    API --> ROUTER
    
    %% Route to Operations
    ROUTER -->|investigate cmd| INVESTIGATE
    ROUTER -->|test cmd| BLACKBOX
    ROUTER -->|run/control cmd| SESSION
    ROUTER -->|probe cmd| PROBE
    ROUTER -->|chain cmd| CHAIN
    
    %%invaded Discovery Flow
    INVESTIGATE -->|spawn| SPAWN
    PROBE -->|spawn| SPAWN
    STATE_MAP -->|spawn| SPAWN
    FUZZ -->|random inputs| SPAWN
    
    SPAWN -->|PTY output| OUTPUT_BUFFER
    TARGET_PROG -->|stdout/stderr| OUTPUT_BUFFER
    
    OUTPUT_BUFFER -->|text lines| PATTERN_MATCH
    PATTERN_MATCH -->|matches| CLASSIFIER
    
    CLASSIFIER -->|prompts| INVESTIGATE
    CLASSIFIER -->|errors| INVESTIGATE
    CLASSIFIER -->|JSON/XML| INVESTIGATE
    CLASSIFIER -->|state change| STATE_MAP

    %% Replay orchestration wiring
    SESSION -->|attach recorder| RECORDER
    SESSION -->|replay transport| PLAYER
    RECORDER -->|normalize inputs| NORMALIZER
    RECORDER -->|redact secrets| REDACTOR
    RECORDER -->|apply decorators| DECORATORS
    DECORATORS -->|enriched exchange| RECORDER
    NORMALIZER -->|build key| MATCHERS
    PLAYER -->|lookup| MATCHERS
    MATCHERS -->|normalized key| TAPE_INDEX
    TAPE_INDEX -->|resolve exchange| TAPE_STORE
    TAPE_STORE -->|chunks| PLAYER
    PLAYER -->|pacing config| LATENCY
    LATENCY -->|delay chunks| PLAYER
    ERRORS -->|inject failure| PLAYER
    PLAYER -->|output chunks| OUTPUT_BUFFER

    INVESTIGATE -->|report JSON| INVESTIGATION_DB
    STATE_MAP -->|state graph| INVESTIGATION_DB
    
    %% Testing Flow
    BLACKBOX -->|test commands| TEST_SUITE
    TEST_SUITE -->|spawn multiple| SPAWN
    TEST_SUITE -->|monitor| RESOURCE_MON
    RESOURCE_MON -->|psutil data| TEST_SUITE
    
    TEST_SUITE -->|results| TEST_REPORTS
    BLACKBOX -->|summary| REPORT_FILE
    
    %% Automation Flow
    SESSION -->|spawn| SPAWN
    SESSION -->|register| REGISTRY
    SESSION -->|logs| SESSION_LOG
    SESSION -->|stream| NAMED_PIPE
    SESSION -->|persist exchanges| TAPE_STORE

    CHAIN -->|sequential| SESSION
    PARALLEL -->|concurrent| SESSION

    REGISTRY -->|reuse session| SESSION
    TAPE_STORE -->|persist JSON5| TAPE_FILES
    TAPE_FILES -->|load at startup| TAPE_STORE
    TAPE_STORE -->|build| TAPE_INDEX
    TAPE_STORE -->|usage stats| SUMMARY_OUT
    SESSION_LOG -->|rotation at 10MB| SESSION_LOG

    %% Output Flow
    SESSION -->|get_output| CONSOLE
    INVESTIGATE -->|summary| CONSOLE
    BLACKBOX -->|report| CONSOLE
    SUMMARY_OUT -->|print| CONSOLE

    NAMED_PIPE -->|real-time| PIPE_STREAM
    SESSION -->|watch events| CALLBACK
    
    %% Data persistence
    INVESTIGATION_DB -->|load| INVESTIGATE
    PROG_CONFIGS -->|load| SESSION
    TEST_REPORTS -->|load| BLACKBOX
    TAPE_FILES -->|hydrate| TAPE_STORE
    TAPE_STORE -->|build index| TAPE_INDEX
```

Record/replay capabilities sit alongside the existing investigation, testing, and automation flows. Recorder hooks capture chunked terminal exchanges into JSON5 tapes with optional normalization, redaction, and decorator pipelines, while the Player rehydrates those tapes via the TapeStore and latency/error policies to satisfy future `Session` interactions without spawning real processes.

## Detailed Data Flow Patterns

### 1. Discovery Data Flow

```mermaid
graph LR
    subgraph "Discovery Pipeline"
        INPUT[/User: investigate cmd/]
        INIT[Initialize<br/>Investigator]
        
        subgraph "Probing Loop"
            SEND_CMD[Send Test<br/>Commands]
            CAPTURE[Capture<br/>Output]
            ANALYZE[Analyze<br/>Patterns]
            UPDATE[Update<br/>State Model]
        end
        
        BUILD[Build<br/>Report]
        SAVE[/Save Report<br/>JSON/]
    end
    
    INPUT -->|program name| INIT
    INIT -->|spawn process| SEND_CMD
    SEND_CMD -->|?, help, --help| CAPTURE
    CAPTURE -->|raw output| ANALYZE
    ANALYZE -->|detected patterns| UPDATE
    UPDATE -->|more to test?| SEND_CMD
    UPDATE -->|complete| BUILD
    BUILD -->|JSON report| SAVE
```

### 2. Testing Data Flow

```mermaid
graph LR
    subgraph "Testing Pipeline"
        START[/Test Command/]
        
        subgraph "Test Execution"
            SPAWN_TEST[Spawn<br/>Test Instance]
            RUN_TEST[Execute<br/>Test Case]
            MONITOR[Monitor<br/>Resources]
            COLLECT[Collect<br/>Results]
        end
        
        AGGREGATE[Aggregate<br/>Results]
        REPORT[/Test Report<br/>JSON/]
    end
    
    START -->|test config| SPAWN_TEST
    SPAWN_TEST -->|process| RUN_TEST
    RUN_TEST -->|CPU/memory| MONITOR
    MONITOR -->|metrics| COLLECT
    COLLECT -->|test result| AGGREGATE
    AGGREGATE -->|all tests| REPORT
```

### 3. Automation Data Flow

```mermaid
graph LR
    subgraph "Automation Pipeline"
        CMD[/User Script/]
        GET_SESSION[Get/Create<br/>Session]

        subgraph "Interaction Loop"
            SEND[Send Input]
            EXPECT[Wait for<br/>Pattern]
            MATCH{Pattern<br/>Match?}
            TIMEOUT{Timeout?}
        end

        OUTPUT[/Return Output/]
        ERROR[/Raise Exception/]
    end

    CMD -->|"control()"| GET_SESSION
    GET_SESSION -->|session| SEND
    SEND -->|text to stdin| EXPECT
    EXPECT --> MATCH
    MATCH -->|yes| OUTPUT
    MATCH -->|no| TIMEOUT
    TIMEOUT -->|no| EXPECT
    TIMEOUT -->|yes| ERROR
```

### 4. Record Mode Data Flow

```mermaid
graph LR
    subgraph "Record Pipeline"
        CALL[/Session.send*/]
        DECORATE_REC[Input Decorators]
        NORMALIZE_REC[Normalizers<br/>ANSI/Volatile]
        REDACT_REC[Redactor]
        SEGMENT[Recorder<br/>Exchange Builder]
        CHUNK[Chunk Sink<br/>logfile_read]
        STORE_REC[(TapeStore)]
        WRITE_REC[/Tape File JSON5/]
        INDEX_REC[(Tape Index)]
        SUMMARY_REC[/Exit Summary/]
    end

    CALL --> DECORATE_REC
    DECORATE_REC --> NORMALIZE_REC
    NORMALIZE_REC --> REDACT_REC
    REDACT_REC --> SEGMENT
    SEGMENT --> CHUNK
    CHUNK --> STORE_REC
    STORE_REC --> WRITE_REC
    STORE_REC --> INDEX_REC
    STORE_REC --> SUMMARY_REC
```

### 5. Replay Data Flow

```mermaid
graph LR
    subgraph "Replay Pipeline"
        SEND_REQ[/Session.send*/]
        MATCH_KEY[Matchers<br/>Command/Env/Stdin]
        INDEX_LOOKUP[(Tape Index)]
        STORE_LOOK[(TapeStore)]
        PLAYER_CORE[Player<br/>Replay Transport]
        LATENCY_APPLY[Latency Policy]
        ERROR_APPLY[Error Injector]
        STREAM_OUT[/Buffered Output/]
        EXPECT_CALL[/Session.expect/]
    end

    SEND_REQ --> MATCH_KEY
    MATCH_KEY --> INDEX_LOOKUP
    INDEX_LOOKUP --> STORE_LOOK
    STORE_LOOK --> PLAYER_CORE
    PLAYER_CORE --> LATENCY_APPLY
    LATENCY_APPLY --> PLAYER_CORE
    PLAYER_CORE --> ERROR_APPLY
    ERROR_APPLY --> PLAYER_CORE
    PLAYER_CORE --> STREAM_OUT
    STREAM_OUT --> EXPECT_CALL
```

### 6. Tape Management CLI Flow

```mermaid
graph LR
    USER[/User/]
    CLI_REC[ccontrol rec]
    CLI_PLAY[ccontrol play]
    CLI_PROXY[ccontrol proxy]
    TAPES_DIR[/--tapes Dir/]
    SESSION_REC[Session<br/>record mode]
    SESSION_PLAY[Session<br/>replay mode]
    SUMMARY_NODE[/Summary Toggle/]

    USER --> CLI_REC
    USER --> CLI_PLAY
    USER --> CLI_PROXY
    CLI_REC --> TAPES_DIR
    CLI_PLAY --> TAPES_DIR
    CLI_PROXY --> TAPES_DIR
    CLI_REC --> SESSION_REC
    CLI_PLAY --> SESSION_PLAY
    CLI_PROXY --> SESSION_PLAY
    SESSION_REC --> SUMMARY_NODE
    SESSION_PLAY --> SUMMARY_NODE
```

## Data Transformations

### Input Transformations
| Stage | Input Format | Output Format | Transformation |
|-------|--------------|---------------|----------------|
| CLI Parsing | Raw argv | Parsed args dict | argparse validation |
| Config Loading | JSON file | Python dict | JSON deserialization + defaults |
| Pattern Compilation | String patterns | Regex objects | re.compile() |
| Command Template | Template string | Formatted command | String interpolation |
| Replay Context Normalization | Session metadata | Normalized key tuple | ANSI stripping + volatile scrub |
| Secret Redaction | Raw bytes | Sanitized bytes | Regex redaction + policy gates |

### Output Transformations
| Stage | Input Format | Output Format | Transformation |
|-------|--------------|---------------|----------------|
| Output Buffering | Byte stream | UTF-8 strings | Decode + line splitting |
| Pattern Extraction | Raw text | Structured data | Regex groups extraction |
| JSON Detection | Mixed text | JSON objects | JSON parsing |
| State Detection | Output + patterns | State name | FSM transition logic |
| Report Generation | Raw findings | Markdown/JSON | Template rendering |
| Tape Chunking | Live stream | Chunk list | Recorder delay capture + base64 |
| Tape Serialization | Tape dataclasses | JSON5 file | pyjson5 dump with pretty print |
| Replay Pacing | Stored chunks | Timed output | Latency policy application |
| Error Injection | Replay stream | Synthetic failure | Probabilistic injector |

### Data Aggregations
| Operation | Input Data | Output Data | Aggregation Method |
|-----------|------------|-------------|-------------------|
| Investigation | Multiple probes | Single report | Merge findings + dedupe |
| Testing | Individual tests | Test suite results | Group by test type |
| Parallel Commands | Multiple outputs | Results dict | Keyed by command |
| Resource Monitoring | Time series data | Statistics | Min/max/avg calculation |
| Tape Index Build | Tape exchanges | Normalized key map | Hash + matcher normalization |
| Summary Accounting | Tape usage flags | Exit summary report | Track new/used via sets |

## Replay Feature Integration

### Modes & Fallback Policies
- **RecordMode**: `NEW` appends fresh exchanges, `OVERWRITE` replaces matches, `DISABLED` skips writes while still enabling playback.
- **FallbackMode**: `NOT_FOUND` surfaces `TapeMissError` for CI-fast failures, `PROXY` launches the real program and optionally records depending on the record mode.
- Modes can be supplied statically or via callables, enabling environment-driven overrides.

### Matching & Normalization Pipeline
- Matcher inputs use normalized `(program, args, env, cwd, prompt, stdin[, state_hash])` tuples.
- Normalizers strip ANSI, collapse whitespace, and scrub volatile tokens (timestamps, IDs) before hashing.
- Allow/ignore lists (`allow_env`, `ignore_env`, `ignore_args`, `ignore_stdin`) prune dynamic context prior to comparison.
- Custom matcher hooks mirror Talkback semantics for parity across transports.

### Decorators, Redaction, and Secret Handling
- Input/output/tape decorators receive a shared context object, enabling tagging, pretty-printing, or metadata enrichment before persistence.
- Redaction runs prior to writes, masking passwords, API keys, and other detector hits unless explicitly disabled via environment flag.
- Tape decorators can adjust latency/error metadata or annotate tape tags prior to JSON5 serialization.

### Latency & Error Injection Controls
- Global and per-tape latency values support constants, ranges, or callables; Player resolves them per chunk to reproduce pacing.
- Error injection policies evaluate probabilities (0-100%) to raise synthetic failures, truncate output, or override exit codes for resilience testing.
- Both features share deterministic RNG seeding to keep replay runs repeatable.

### Tape Lifecycle & Exit Summary
- TapeStore loads all JSON5 tapes at session startup, builds an in-memory index, and tracks `used` vs `new` sets.
- Recorder writes tapes via temp-file + rename to remain crash-safe and marks new files for the exit summary.
- On shutdown, the summary reporter lists new tapes created and any loaded but unused tapes, mirroring Talkback’s UX.

### CLI & Configuration Touchpoints
- `ccontrol rec|play|proxy` map to record, playback, and proxy workflows, inheriting global flags like `--tapes`, `--record`, `--fallback`, `--latency`, and `--error-rate`.
- Library usage flows through `Session(...)` keyword arguments with identical defaults, keeping backwards compatibility when options are omitted.
- Tape management commands (`ccontrol tapes list|validate|redact`) operate on the same tape directory, enabling validation and cleanup tooling.
- User configuration in `~/.claude-control/config.json` gains a `replay` section that seeds defaults without overriding explicit CLI or API parameters.

## Data Volume & Performance

### Typical Data Sizes
- **Session Output Buffer**: 10,000 lines (configurable)
- **Log File Rotation**: 10MB per file
- **Investigation Reports**: 5-50KB JSON
- **Test Reports**: 10-100KB JSON
- **Named Pipe Buffer**: 64KB (OS default)
- **Pattern Cache**: ~100 compiled patterns
- **Tape Files**: 5-200KB JSON5 per tape (chunked exchanges)
- **Tape Index Cache**: ~1-5MB per 1,000 exchanges (normalized keys)

### Processing Times
- **Session Spawn**: 10-100ms
- **Pattern Matching**: <1ms per line
- **Investigation**: 5-60 seconds (depends on program)
- **Black Box Testing**: 10-120 seconds
- **Parallel Commands**: Limited by slowest command
- **Tape Index Build**: ≤200ms per 1,000 exchanges
- **Replay Match**: ≤2ms per exchange lookup
- **Latency Injection**: Adds 0-50ms jitter per chunk by policy

### Bottlenecks
1. **Process Spawning**: PTY allocation can be slow
2. **Pattern Matching**: Complex regex on large outputs
3. **File I/O**: Log rotation during heavy output
4. **Named Pipes**: Reader must keep up with writer
5. **Tape Hydration**: Loading many JSON5 tapes on cold start
6. **Replay Streaming**: High latency or error injection policies delay completion

## Data Consistency

### Transaction Boundaries
- **Session Operations**: Each expect/send is atomic
- **Investigation**: Complete report or rollback
- **Testing**: Each test case is independent
- **Config Save**: Atomic file write with temp file
- **Tape Write**: Recorder writes to temp file then rename for atomicity

### Eventual Consistency Points
- **Session Registry**: In-memory, lost on crash
- **Log Files**: Buffered writes, may lose last lines
- **Named Pipes**: No persistence, real-time only
- **TapeStore Cache**: In-memory index rebuilt on restart

### Data Synchronization
- **Registry Lock**: Thread-safe session access
- **File Locks**: Prevent concurrent config writes
- **Process Groups**: Ensure child cleanup
- **Tape Locks**: portalocker guards overwrites during record mode

## Error Handling Data Flows

### Failed Pattern Match
```
Expect Pattern → Timeout → Capture Recent Output → TimeoutError(output)
```

### Process Death
```
Send Command → SIGCHLD → Check Exit Status → ProcessError(exitcode)
```

### Resource Exhaustion
```
Monitor Resources → Threshold Exceeded → Kill Process → ResourceError
```

### Tape Miss (Replay)
```
Send Input → Normalize Context → Index Lookup → Miss? → TapeMissError | Proxy Live Spawn
```

### Tape Load Failure
```
Read JSON5 → Parse → Schema Validate → SchemaError (exit with diagnostics)
```

### Injected Failure
```
Replay Chunk → should_inject_error? → Inject Exit Code/Exception → Surface to Session
```

### Recovery Mechanisms
- **Session Retry**: Respawn dead sessions
- **Pattern Fallback**: Try alternative patterns
- **Timeout Extension**: Adaptive timeout adjustment
- **Output Truncation**: Prevent memory overflow
- **Tape Proxy Fallback**: Switch to live process when fallback=PROXY
- **Tape Validation CLI**: `ccontrol tapes validate` checks schema issues before replay

## Stream Processing (Named Pipes)

### Real-time Data Flow
```mermaid
graph LR
    SESSION[Session<br/>Process]
    PIPE_WRITER[Pipe Writer<br/>Thread]
    NAMED_PIPE[(Named Pipe<br/>/tmp/...)]
    EXTERNAL[External<br/>Reader]

    SESSION -->|output| PIPE_WRITER
    PIPE_WRITER -->|formatted| NAMED_PIPE
    NAMED_PIPE -->|stream| EXTERNAL
```

Replay mode feeds the same pipe writer through the Player buffer, ensuring recorded chunks and live streams share formatting and timestamp envelopes before reaching external consumers.

### Pipe Data Format
```
[2024-01-10T10:30:45][OUT] Normal output line
[2024-01-10T10:30:46][ERR] Error output line
[2024-01-10T10:30:47][IN] User input sent
[2024-01-10T10:30:48][MTX] Session metadata
```

## Performance Optimizations

### Caching Strategies
- **Compiled Patterns**: Cache regex compilation
- **Session Reuse**: Keep sessions alive across calls
- **Config Cache**: Load configs once per run
- **Output Windows**: Sliding window buffer
- **TapeStore Index**: Precompute normalized keys at startup
- **Summary Sets**: Maintain in-memory `used`/`new` tape trackers

### Batch Processing
- **Parallel Execution**: ThreadPoolExecutor for concurrent commands
- **Bulk Pattern Matching**: Match multiple patterns in one pass
- **Deferred Writes**: Batch log writes
- **Tape Hydration**: Load and validate JSON5 tapes once per session start

### Resource Management
- **Lazy Loading**: Load patterns on demand
- **Stream Processing**: Process output line by line
- **Garbage Collection**: Explicit cleanup of dead sessions
- **Memory Limits**: Configurable buffer sizes
- **Replay Budgeting**: Cap latency/error policies to avoid runaway waits
- **Tape Cleanup**: Prune old tapes or rotate directories per config

## Security Considerations

### Data Sanitization
- **Command Injection**: Escape shell metacharacters
- **Path Traversal**: Validate file paths
- **Sensitive Data**: Avoid logging passwords
- **Safe Mode**: Block dangerous commands
- **Tape Redaction**: Mask detected secrets before persistence
- **Schema Validation**: Reject malformed JSON5 tapes before use

### Isolation
- **Process Isolation**: Separate PTY per session
- **File Permissions**: User-only access to logs
- **Network Isolation**: No network access by default
- **Resource Limits**: CPU/memory quotas
- **Tape Directory Locks**: portalocker prevents concurrent writers

## Monitoring & Observability

### Data Collection Points
- Session creation/destruction events
- Pattern match success/failure rates
- Resource usage metrics
- Error frequency and types
- Tape index hits/misses and fallback usage
- Decorator, normalization, and redaction activity logs
- Latency/error injection statistics

### Metrics Flow
```
Session Events → Registry → Status API → Monitoring Tools
Process Metrics → psutil → Resource Monitor → Test Reports
Error Events → Logger → Log Files → Analysis Tools
Replay Events → TapeStore → Summary Reporter → Console
```

