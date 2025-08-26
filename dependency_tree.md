# ClaudeControl Dependency Tree

## Overview
ClaudeControl has minimal external dependencies, relying primarily on two critical libraries for its core functionality. The project emphasizes simplicity with smart defaults rather than heavy dependency chains.

## Core Dependencies

### Process Control & Automation
- **pexpect** (>=4.8.0)
  - Purpose: Core process spawning and PTY control for CLI interaction
  - Used in: `core.py` (Session class), throughout the codebase
  - Critical: **Yes** - Fundamental to all three capabilities (Discover, Test, Automate)
  - Features enabled:
    - Process spawning with pseudo-terminal (PTY)
    - Pattern matching with expect/send operations
    - Timeout handling for unresponsive processes
    - Process lifecycle management

### System & Process Management  
- **psutil** (>=5.9.0)
  - Purpose: Process monitoring, resource usage tracking, and zombie cleanup
  - Used in: `core.py` (cleanup), `testing.py` (resource monitoring)
  - Critical: **Yes** - Required for safe process management and testing
  - Features enabled:
    - CPU and memory usage monitoring
    - Process tree management
    - Zombie process detection and cleanup
    - Resource limit enforcement

## Standard Library Dependencies

### Essential Python Modules
These are part of Python's standard library but are critical to ClaudeControl's operation:

#### Data & Configuration
- **json** (stdlib)
  - Purpose: Configuration files, report generation, data serialization
  - Used in: All modules for config/report handling
  - Critical: **Yes** - Required for persistence and reporting

- **pathlib** (stdlib)
  - Purpose: Cross-platform file system operations
  - Used in: Throughout for file/directory management
  - Critical: **Yes** - Required for data storage

#### Process & Threading
- **threading** (stdlib)
  - Purpose: Thread-safe session registry, parallel execution
  - Used in: `core.py` (registry lock), `claude_helpers.py` (parallel_commands)
  - Critical: **Yes** - Required for concurrent operations

- **subprocess** (stdlib, indirect)
  - Purpose: Used by pexpect for process spawning
  - Used in: Via pexpect
  - Critical: **Yes** - Core process control

#### Pattern Matching
- **re** (stdlib)
  - Purpose: Regular expression pattern matching
  - Used in: `patterns.py`, throughout for text processing
  - Critical: **Yes** - Required for output analysis

#### System Operations
- **os** (stdlib)
  - Purpose: Environment variables, file permissions, system operations
  - Used in: `core.py`, `setup.py`
  - Critical: **Yes** - Required for system integration

- **signal** (stdlib)
  - Purpose: Process signal handling (SIGCHLD, SIGTERM)
  - Used in: `core.py` for process management
  - Critical: **Yes** - Required for proper cleanup

- **fcntl** (stdlib)
  - Purpose: File locking for concurrent access safety
  - Used in: `core.py` for session file locks
  - Critical: **Yes** - Required for data consistency

#### Utilities
- **time** (stdlib)
  - Purpose: Delays, timeouts, timestamps
  - Used in: Throughout for timing operations
  - Critical: **Yes** - Required for timeout handling

- **logging** (stdlib)
  - Purpose: Diagnostic output and debugging
  - Used in: All modules for error tracking
  - Critical: **No** - But highly recommended for production

- **dataclasses** (stdlib)
  - Purpose: Structured data models for reports
  - Used in: `investigate.py` for InvestigationReport
  - Critical: **No** - Convenience feature

- **collections** (stdlib)
  - Purpose: deque for output buffering, defaultdict for state tracking
  - Used in: `core.py`, `investigate.py`
  - Critical: **Yes** - Required for efficient buffering

- **contextlib** (stdlib)
  - Purpose: Context managers for resource management
  - Used in: `core.py` for session cleanup
  - Critical: **No** - Convenience feature

- **tempfile** (stdlib)
  - Purpose: Temporary file creation for testing
  - Used in: `testing.py`, `core.py`
  - Critical: **No** - Testing support

- **datetime** (stdlib)
  - Purpose: Timestamps, session timeouts
  - Used in: Throughout for time tracking
  - Critical: **Yes** - Required for session management

- **typing** (stdlib)
  - Purpose: Type hints for better code documentation
  - Used in: All modules
  - Critical: **No** - Development aid only

## Optional Dependencies

### File Monitoring Enhancement
- **watchdog** (>=2.1.0)
  - Purpose: Efficient file system monitoring
  - Used in: Not currently implemented (planned feature)
  - Critical: **No** - Falls back to polling without it
  - Install: `pip install claudecontrol[watch]`

## Development Dependencies

### Testing & Quality
- **pytest** (>=7.0.0)
  - Purpose: Test framework
  - Used in: `tests/*.py`
  - Critical: **No** - Development only
  - Install: `pip install claudecontrol[dev]`

- **pytest-asyncio** (>=0.18.0)
  - Purpose: Async test support
  - Used in: Future async tests
  - Critical: **No** - Development only

- **black** (>=22.0.0)
  - Purpose: Code formatting
  - Used in: Development workflow
  - Critical: **No** - Development only

- **mypy** (>=0.950)
  - Purpose: Static type checking
  - Used in: Development workflow
  - Critical: **No** - Development only

## Version Requirements

### Python Version
- **Python** >=3.8
  - Required for: dataclasses, typing features, pathlib enhancements
  - Tested on: Python 3.8, 3.9, 3.10, 3.11

### Critical Version Notes
- **pexpect >=4.8.0**: Required for improved Windows support and bug fixes
- **psutil >=5.9.0**: Required for modern process management APIs
- **Python >=3.8**: Required for dataclasses and modern typing support

## Dependency Impact Analysis

### What Happens If Dependencies Are Missing

#### Missing pexpect
- **Impact**: Complete failure - no functionality available
- **Error**: ImportError on module load
- **Mitigation**: None - this is the core dependency

#### Missing psutil
- **Impact**: Degraded functionality
- **Features lost**:
  - Resource monitoring in tests
  - Automatic zombie cleanup
  - Process tree operations
  - Memory/CPU usage tracking
- **Mitigation**: Could theoretically work without it but not recommended

#### Missing watchdog (optional)
- **Impact**: Minor performance degradation
- **Features lost**: Efficient file monitoring
- **Mitigation**: Falls back to polling-based monitoring

## Security Considerations

### Dependency Security
- **pexpect**: Handles process I/O - keep updated for security patches
- **psutil**: System access - update regularly for security fixes
- Both dependencies are mature, well-maintained projects with good security track records

### Update Schedule
- **Critical updates**: pexpect and psutil should be updated quarterly
- **Development dependencies**: Update as needed, not security critical

## Dependency Minimalism Philosophy

ClaudeControl intentionally maintains minimal dependencies because:

1. **Reliability**: Fewer dependencies = fewer breaking changes
2. **Security**: Smaller attack surface
3. **Portability**: Easier to install and deploy
4. **Performance**: Faster installation and startup
5. **Maintenance**: Simpler to debug and maintain

The project philosophy is to:
- Use standard library when possible
- Only add dependencies that provide significant value
- Prefer well-established, stable libraries
- Avoid dependency chains and version conflicts

## Installation Size

### Typical Installation Footprint
```
claudecontrol: ~200 KB
├── pexpect: ~300 KB
│   └── ptyprocess: ~50 KB (transitive)
└── psutil: ~500 KB

Total: ~1.05 MB (minimal installation)
```

### With Development Dependencies
```
+ pytest: ~2 MB
+ black: ~3 MB  
+ mypy: ~15 MB
+ pytest-asyncio: ~100 KB

Total with dev: ~21 MB
```

## Platform-Specific Notes

### Linux/Unix
- All features fully supported
- Named pipes work natively
- PTY operations are most efficient

### macOS
- All features fully supported
- Some process operations may require permissions
- File system monitoring works best with watchdog

### Windows
- Requires Windows 10+ with WSL or native Python
- pexpect works via ConPTY on Windows 10+
- Some Unix-specific features may have limitations
- Named pipes have different paths (\\\\.\\pipe\\)

### Docker/Containers
- Works well in containers
- May need `--init` flag for proper signal handling
- Consider mounting ~/.claude-control as volume

## Future Dependencies Under Consideration

These are not current dependencies but may be added for specific features:

### Potential Additions
- **rich**: For better terminal UI in interactive mode
- **click**: To replace argparse for CLI if it grows complex
- **asyncio**: For async session management (stdlib)
- **aiofiles**: For async file operations
- **redis**: For distributed session management
- **fastapi**: If REST API is added

### Explicitly Avoided
- **numpy/pandas**: Too heavy for current needs
- **requests**: subprocess and pexpect handle our needs
- **docker**: Would add significant complexity
- **kubernetes**: Out of scope for CLI tool

## Dependency Tree Visualization

```
claudecontrol
├── CRITICAL (must have)
│   ├── pexpect >=4.8.0
│   │   └── ptyprocess (transitive)
│   └── psutil >=5.9.0
│
├── STDLIB (included with Python)
│   ├── Essential
│   │   ├── json
│   │   ├── pathlib
│   │   ├── threading
│   │   ├── re
│   │   ├── os
│   │   ├── signal
│   │   └── fcntl
│   └── Utilities
│       ├── logging
│       ├── time
│       ├── datetime
│       ├── collections
│       └── dataclasses
│
└── OPTIONAL
    ├── Runtime
    │   └── watchdog >=2.1.0 [not yet used]
    └── Development
        ├── pytest >=7.0.0
        ├── pytest-asyncio >=0.18.0
        ├── black >=22.0.0
        └── mypy >=0.950
```

## Conclusion

ClaudeControl maintains an extremely lean dependency footprint with just two critical external dependencies (pexpect and psutil), relying heavily on Python's robust standard library. This design choice ensures:

- Easy installation and deployment
- Minimal security surface area  
- Excellent stability and compatibility
- Fast startup and low resource usage
- Simple debugging and maintenance

The project can theoretically run with just pexpect, though psutil is strongly recommended for production use to enable proper process management and monitoring capabilities.