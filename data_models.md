# ClaudeControl Data Models

```mermaid
erDiagram
    SESSION {
        string session_id PK
        string program
        json args
        int timeout
        datetime created_at
        datetime last_activity
        bool persist
        string encoding
        int pid
        int exitstatus
        string state "alive|dead|zombie"
    }

    PROGRAM_CONFIG {
        string name PK
        string command_template
        int typical_timeout
        json expect_sequences
        json success_indicators
        json ready_indicators
        string notes
        json sample_output
    }

    INVESTIGATION_REPORT {
        string id PK
        string program
        datetime started_at
        datetime completed_at
        string entry_state_id FK
        json commands
        json prompts
        json error_messages
        json help_commands
        json exit_commands
        json data_formats
        json safety_notes
    }

    PROGRAM_STATE {
        string id PK
        string report_id FK
        string name
        string prompt
        json commands
        json transitions
        json output_samples
        json error_patterns
    }

    TEST_RESULT {
        string id PK
        string program
        datetime timestamp
        string test_type "startup|help|invalid_input|exit|resource|concurrent|fuzz"
        bool passed
        json details
        string error
    }

    SESSION_OUTPUT {
        string session_id FK
        string log_path
        int output_lines
        int buffer_size
        datetime rotated_at
    }

    INTERACTION_LOG {
        string id PK
        string session_id FK
        datetime timestamp
        string action "START|SEND|RECV|EXPECT|ERROR"
        string input_text
        string output_text
        string pattern_matched
    }

    NAMED_PIPE {
        string session_id FK
        string pipe_path
        string state "active|closed"
        datetime created_at
    }

    COMMAND_CHAIN {
        string id PK
        string name
        json commands
        string cwd
        int timeout
    }

    CHAIN_COMMAND {
        string chain_id FK
        int sequence_order
        string command
        string expect_pattern
        string send_text
        json condition
        bool on_success
        bool on_failure
    }

    PATTERN_LIBRARY {
        string pattern_type PK "prompt|error|help|data_format|state"
        string category
        json patterns
        string description
    }

    GLOBAL_CONFIG {
        string key PK
        json value
        string category "session|investigation|testing|logging|replay"
    }

    TAPE_META {
        string tape_id PK
        string program
        json args
        json env
        string cwd
        json pty
        string tag
        int latency
        int error_rate
        int seed
        datetime created_at
    }

    TAPE_SESSION {
        string tape_id FK
        string platform
        string version
        json flags
    }

    TAPE_EXCHANGE {
        string tape_id FK
        int exchange_index PK
        json prompt_signature
        json input
        json output
        json exit
        int duration_ms
        json annotations
    }

    TAPE_CHUNK {
        string tape_id FK
        int exchange_index FK
        int chunk_index PK
        int delay_ms
        string data_b64
        bool is_utf8
    }

    TAPE_INDEX_ENTRY {
        string tape_id FK
        int exchange_index FK
        string normalized_key PK
        json raw_key_components
    }

    SESSION ||--o{ SESSION_OUTPUT : generates
    SESSION ||--o{ INTERACTION_LOG : records
    SESSION ||--o| NAMED_PIPE : "may create"
    SESSION ||--o| PROGRAM_CONFIG : "may use"
    SESSION ||--|{ TAPE_INDEX_ENTRY : "matches against"

    INVESTIGATION_REPORT ||--|{ PROGRAM_STATE : contains
    INVESTIGATION_REPORT ||--|| PROGRAM_STATE : "has entry"

    COMMAND_CHAIN ||--|{ CHAIN_COMMAND : contains

    TAPE_META ||--|| TAPE_SESSION : describes
    TAPE_META ||--|{ TAPE_EXCHANGE : contains
    TAPE_EXCHANGE ||--|{ TAPE_CHUNK : streams
    TAPE_EXCHANGE ||--|| TAPE_INDEX_ENTRY : indexedBy

    SESSION }o--|| GLOBAL_CONFIG : "configured by"
    INVESTIGATION_REPORT }o--|| GLOBAL_CONFIG : "configured by"
    TAPE_META }o--|| GLOBAL_CONFIG : "defaults from"
```

## Data Structure Details

### Core Entities

#### SESSION
- **Purpose**: Represents an active or historical process control session
- **Persistence**: In-memory with optional file system backing and tape-aware metadata
- **Key Relationships**:
  - Generates output logs
  - Records interaction history
  - May create named pipes for streaming
  - May load from saved configurations or replay tapes

#### PROGRAM_CONFIG
- **Purpose**: Reusable configuration templates for known programs
- **Storage**: `~/.claude-control/programs/{name}.json`
- **Usage**: Sessions can be created from configs for consistent behavior or combined with replay defaults

#### INVESTIGATION_REPORT
- **Purpose**: Complete findings from program investigation
- **Storage**: `~/.claude-control/investigations/{program}_{timestamp}.json`
- **Key Fields**:
  - `commands`: Dict of discovered commands with descriptions
  - `data_formats`: List of detected output formats (JSON, XML, CSV, etc.)
  - `safety_notes`: Warnings about dangerous operations

#### PROGRAM_STATE
- **Purpose**: Represents different states/modes within a program
- **Examples**: Main menu, config mode, data entry mode
- **Transitions**: Maps commands that move between states

#### TAPE_META
- **Purpose**: Top-level metadata for a recorded session tape (JSON5)
- **Contents**: Program identity, args, filtered environment, working directory, PTY geometry, redaction flags, latency/error overrides, RNG seed, creation time
- **Persistence**: Stored inline in the tape file under `meta`

#### TAPE_SESSION
- **Purpose**: Captures runtime information about the recorder itself
- **Contents**: Platform triple, `claude_control` version, enabled feature flags, tape format version
- **Persistence**: Stored under `session` in each tape file

#### TAPE_EXCHANGE
- **Purpose**: Represents a single request/response pair within a tape
- **Segmentation Rules**: Start at process launch or each send/sendline, end on prompt match, timeout, or process exit
- **Stored Fields**: Prompt signature/state hash, normalized input payload, captured output stream, optional exit status, durations, annotations

#### TAPE_CHUNK
- **Purpose**: Preserve output pacing and byte fidelity
- **Structure**: Delay in milliseconds, base64-encoded data, UTF-8 flag for human readability
- **Playback**: Used by replay transport to stream with synthetic or recorded latency

#### TAPE_INDEX_ENTRY
- **Purpose**: Materialized index entries for matching tape exchanges
- **Key**: Normalized tuple derived from `(program, args*, env*, cwd*, prompt signature, input fingerprint, state hash)`
- **Usage**: Enables deterministic replay and miss detection within `TapeStore`

### Data Constraints

#### Business Rules
1. **Session Limits**: Maximum 20 concurrent sessions (configurable)
2. **Output Rotation**: Log files rotate at 10MB
3. **Buffer Limits**: Output buffer limited to 10,000 lines in memory
4. **Timeout Defaults**: 30 seconds for most operations, 300 seconds for session timeout
5. **Resource Limits**: Maximum runtime per session (default 3600 seconds)
6. **Tape Write Modes**: Recording obeys `RecordMode` (`NEW`, `OVERWRITE`, `DISABLED`) for exchange persistence
7. **Fallback Policy**: Tape misses handled by `FallbackMode` (`NOT_FOUND`, `PROXY`); CI defaults to strict failure
8. **Summary Reporting**: Exit summaries must enumerate new and unused tapes when enabled

#### Unique Constraints
- `SESSION.session_id` must be unique across active sessions
- `PROGRAM_CONFIG.name` must be unique
- `NAMED_PIPE.pipe_path` must be unique when active
- Combination of `(tape_id, exchange_index, chunk_index)` uniquely identifies a chunk
- `TAPE_INDEX_ENTRY.normalized_key` must be unique per tape root to avoid ambiguous matches

#### Required Relationships
- Every `PROGRAM_STATE` must belong to an `INVESTIGATION_REPORT`
- Every `CHAIN_COMMAND` must belong to a `COMMAND_CHAIN`
- Every `INTERACTION_LOG` entry must reference a valid `SESSION`
- Every `TAPE_EXCHANGE` must belong to a `TAPE_META`
- Every `TAPE_CHUNK` must belong to a `TAPE_EXCHANGE`
- Every `TAPE_INDEX_ENTRY` must reference an existing exchange

### Data Types Notes

#### JSON Field Structures

**PROGRAM_CONFIG.expect_sequences**:
```json
[
  {"pattern": "login:", "response": "admin"},
  {"pattern": "password:", "response": "secret"}
]
```

**INVESTIGATION_REPORT.commands**:
```json
{
  "help": {
    "description": "Show help message",
    "tested": true,
    "output_length": 523
  }
}
```

**TEST_RESULT.details**:
```json
{
  "started": true,
  "has_output": true,
  "has_errors": false,
  "has_prompt": true,
  "cpu_percent": 2.5,
  "memory_mb": 45.2
}
```

**TAPE.meta**:
```json5
{
  createdAt: "2025-09-23T12:34:56.789Z",
  program: "sqlite3",
  args: ["-batch"],
  env: { LANG: "en_US.UTF-8" },
  cwd: "/Users/dev/project",
  pty: { rows: 24, cols: 120 },
  tag: "happy-path",
  latency: 0,
  errorRate: 0,
  seed: 12345
}
```

**TAPE.exchanges[]**:
```json5
{
  pre: { prompt: "sqlite> ", stateHash: "ab12..." },
  input: { type: "line", dataText: "select 1;", dataBytesB64: null },
  output: {
    chunks: [
      { delay_ms: 12, dataB64: "MQo=", isUtf8: true },
      { delay_ms: 3, dataB64: "c3FsaXRlPiA=", isUtf8: true }
    ]
  },
  exit: null,
  dur_ms: 25,
  annotations: { note: "baseline query" }
}
```

#### Enum Values

**SESSION.state**:
- `alive`: Process is running
- `dead`: Process has terminated
- `zombie`: Process terminated but not cleaned up

**TEST_RESULT.test_type**:
- `startup`: Program initialization test
- `help`: Help system discovery
- `invalid_input`: Error handling test
- `exit`: Clean shutdown test
- `resource`: CPU/memory usage test
- `concurrent`: Multiple session test
- `fuzz`: Random input testing

**PATTERN_LIBRARY.pattern_type**:
- `prompt`: Command prompt patterns
- `error`: Error message patterns
- `help`: Help output indicators
- `data_format`: JSON/XML/CSV patterns
- `state`: State transition patterns

**Record & Replay enums**:

- `RecordMode`: `NEW`, `OVERWRITE`, `DISABLED`
- `FallbackMode`: `NOT_FOUND`, `PROXY`

**Exchange input types**:
- `line`: High-level `sendline` interactions
- `raw`: Byte-oriented `send` payloads

### Data Flow Context

#### Creation Points
- **SESSION**: Created by `control()` or `Session()` constructor
- **TAPE_META**: Instantiated by `Recorder` when a session enters record mode
- **TAPE_EXCHANGE**: Emitted at the end of each segmented interaction
- **TAPE_CHUNK**: Captured by `ChunkSink.write()` for every read from the child process
- **INVESTIGATION_REPORT**: Generated by `ProgramInvestigator`
- **TEST_RESULT**: Created by `BlackBoxTester`
- **PROGRAM_CONFIG**: Saved via `Session.save_program_config()`

#### Consumption Points
- **SESSION**: Used by all helper functions and frameworks
- **PROGRAM_CONFIG**: Loaded by `Session.from_config()`
- **INVESTIGATION_REPORT**: Read for understanding program behavior
- **PATTERN_LIBRARY**: Used by pattern matching functions
- **TapeStore/TapeIndex**: Consumed by `ReplayTransport` and CLI `play`/`proxy` commands for deterministic playback
- **ExitSummary**: Reads TapeStore `new` and `used` sets for reporting

#### Data Lifecycle
1. **Sessions**: Created on demand, persist optionally, cleaned up by timeout or force
2. **Configs**: Saved explicitly, persist indefinitely, deleted manually
3. **Reports**: Generated during investigation/testing, persist indefinitely
4. **Logs**: Append-only during session, rotate at size limit
5. **Pipes**: Created with stream=True, deleted on session close
6. **Tapes**: Written atomically at session end, loaded at process start, edits require restart for replay index regeneration
7. **Tape Index**: Built in-memory on startup, invalidated when tapes change

### Storage Locations

| Entity | Storage Type | Location |
|--------|-------------|----------|
| SESSION | In-memory + logs | `~/.claude-control/sessions/{id}/` |
| PROGRAM_CONFIG | JSON file | `~/.claude-control/programs/{name}.json` |
| INVESTIGATION_REPORT | JSON file | `~/.claude-control/investigations/` |
| TEST_RESULT | JSON file | `~/.claude-control/test-reports/` |
| SESSION_OUTPUT | Log file | `~/.claude-control/sessions/{id}/output.log` |
| NAMED_PIPE | Named pipe | `/tmp/claudecontrol/{id}.pipe` |
| GLOBAL_CONFIG | JSON file | `~/.claude-control/config.json` |
| TAPE (meta + session + exchanges) | JSON5 file | `<tapes_path>/{program}/.../*.json5` |
| TAPE_INDEX | In-memory dict | Constructed at runtime by `TapeStore.build_index()` |
| EXIT_SUMMARY | Derived data | Printed to stdout on shutdown |

### Performance Considerations

- **In-Memory Caching**: Active sessions kept in global registry
- **Lazy Loading**: Configs and reports loaded on demand
- **Streaming**: Named pipes for real-time output without buffering
- **Rotation**: Automatic log rotation prevents unbounded growth
- **Cleanup**: Automatic cleanup of dead sessions and old files
- **Replay Index**: Built once at startup with target ≤200 ms per 1,000 exchanges; lookups ≤2 ms using normalized keys
- **Latency Simulation**: Replay transport applies recorded or synthetic pacing with ≤50 ms jitter per chunk
- **Locking**: Tape writes use per-file locks (via `portalocker`) and atomic rename to avoid corruption

### Operational Policies

- **Redaction**: Sensitive data scrubbed before persistence using `redact.py`; can be disabled with `CLAUDECONTROL_REDACT=0`
- **Decorators**: Input/output/tape decorators transform data via hooks recorded in annotations for traceability
- **Error Injection**: Configurable probability to truncate output or set non-zero exit statuses during replay
- **Telemetry**: Structured logs capture match decisions, normalization steps, decorators, and injected behaviors when `debug` is enabled
