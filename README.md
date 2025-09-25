# ClaudeControl

**Give Claude control of your terminal** - A powerful Python library for four essential CLI tasks:

## 🎯 Four Core Capabilities

### 1. 🔍 **Discover** - Investigate Unknown Programs
Automatically explore and understand any CLI tool's interface, commands, and behavior - even without documentation.

### 2. 🧪 **Test** - Comprehensive Black-Box Testing  
Thoroughly test CLI programs for reliability, error handling, performance, and edge cases without access to source code.

### 3. 🤖 **Automate** - Intelligent CLI Interaction
Create robust automation for any command-line program with session persistence, error recovery, and parallel execution.

### 4. 🎞️ **Record & Replay** - Talkback-Style Session Tapes
Capture interactive CLI sessions into human-editable JSON5 "tapes" and deterministically replay them with Talkback-style modes,
matchers, decorators, latency control, and exit summaries.

---

ClaudeControl excels at all four tasks with zero configuration and intelligent defaults, making it the Swiss Army knife for CLI program interaction.

## 📊 What Can ClaudeControl Do?

| Task | Without ClaudeControl | With ClaudeControl |
|------|----------------------|-------------------|
| **Discovering CLI interfaces** | Hours of manual trial-and-error | Automatic in seconds |
| **Testing CLI reliability** | Manual test scripts, incomplete coverage | Comprehensive automated test suite |
| **Automating CLI workflows** | Fragile bash scripts, no error handling | Robust Python automation with retries |
| **Understanding legacy tools** | Reading old docs or source code | Automatic interface mapping |
| **Parallel CLI operations** | Complex threading code | Simple one-liner |
| **Monitoring CLI processes** | Constant manual checking | Automated pattern watching |
| **Recording & Replaying sessions** | Ad-hoc screen captures, brittle mocks | Deterministic JSON5 tapes with Talkback-style controls |

## ✨ Key Features

- **🔍 Program Investigation** - Automatically explore and understand unknown CLI tools
- **🎯 Interactive Menu** - User-friendly interface when run without arguments
- **🚀 Zero Configuration** - Works immediately with smart defaults
- **🔄 Session Persistence** - Reuse sessions across script runs
- **🛡️ Safety First** - Built-in protections for dangerous operations
- **📊 Comprehensive Reports** - Detailed analysis of program behavior
- **🧪 Black-Box Testing** - Test programs without source code access
- **⚡ Parallel Execution** - Run multiple commands concurrently
- **📡 Real-time Streaming** - Named pipe support for output monitoring
- **🔐 SSH Operations** - Automated SSH command execution
- **📈 Process Monitoring** - Watch for patterns and react to events
- **🎨 Pattern Matching** - Advanced text extraction and classification
- **🎞️ Replay Modes & Matchers** - Talkback-style `RecordMode`, `FallbackMode`, and configurable matchers/normalizers
- **⏱️ Latency & Error Injection** - Simulate streaming pace or injected failures during replay
- **📝 Exit Summaries** - Automatic report of new and unused tapes for CI hygiene

## 🚀 Quick Start

### Installation

```bash
pip install -e .
```

### Enable Record & Replay Support (optional)

Install the additional dependencies that power JSON5 tapes, validation, and cross-platform file locking:

```bash
pip install -r requirements.txt
```

### Interactive Menu (Recommended for First Time)

Simply run without arguments to get the interactive menu:

```bash
ccontrol
```

This opens a guided interface that walks you through all features:
- Quick command execution
- Program investigation
- Session management
- Testing and fuzzing
- Interactive tutorials

## 🎯 Quick Decision Guide

**Choose the right tool for your task:**

| If you need to... | Use this feature | Command/Function |
|-------------------|------------------|------------------|
| Learn how a CLI program works | **Investigation** | `investigate_program("app")` |
| Test if a CLI is production-ready | **Black-box Testing** | `black_box_test("app")` |
| Automate CLI interactions | **Session Control** | `Session("app")` or `control("app")` |
| Run multiple CLIs at once | **Parallel Execution** | `parallel_commands([...])` |
| Monitor a CLI for errors | **Process Watching** | `watch_process("app", patterns)` |
| Chain dependent commands | **Command Chains** | `CommandChain()` |
| Record a live session | **Recorder** | `Session(..., record=RecordMode.NEW)` |
| Replay deterministically | **Player** | `Session(..., record=RecordMode.DISABLED, fallback=FallbackMode.NOT_FOUND)` |

## 📚 Core Use Cases

### Use Case 1: Discover Unknown Program Interfaces

```python
from claudecontrol import investigate_program

# Automatically discover everything about an unknown program
report = investigate_program("mystery_cli_tool")
print(report.summary())

# Output:
# ✓ Found 23 commands
# ✓ Detected 3 different states/modes
# ✓ Identified help commands: ['help', '?', '--help']
# ✓ Exit commands: ['quit', 'exit', 'q']
# ✓ Data formats: JSON, CSV
# ✓ Generated complete interface map
```

### Use Case 2: Thoroughly Test CLI Programs

```python
from claudecontrol.testing import black_box_test

# Run comprehensive test suite on any CLI program
results = black_box_test("your_cli_app", timeout=10)

# Tests performed:
# ✓ Startup behavior
# ✓ Help system discovery
# ✓ Invalid input handling
# ✓ Exit behavior
# ✓ Resource usage (CPU/memory)
# ✓ Concurrent session handling
# ✓ Fuzz testing with edge cases

print(results["report"])
```

### Use Case 3: Automate CLI Interactions

```python
from claudecontrol import Session, control

# Create persistent, reusable sessions
with Session("database_cli") as session:
    session.expect("login:")
    session.sendline("admin")
    session.expect("password:")
    session.sendline("secret")
    session.expect("db>")
    
    # Run queries
    session.sendline("SELECT * FROM users")
    session.expect("db>")
    results = session.get_recent_output()

# Or use high-level helpers
from claudecontrol.claude_helpers import test_command, parallel_commands

# Test if command works
success, error = test_command("npm test", expected_output="passing")
if success:
    print("Tests passed!")
else:
    print(f"Tests failed: {error}")

# Run multiple commands in parallel
results = parallel_commands([
    "npm test",
    "python -m pytest",
    "cargo test"
])
```

### CLI Usage

```bash
# Interactive menu (recommended)
ccontrol

# Investigate unknown program
ccontrol investigate unknown_tool

# Quick probe
ccontrol probe mysterious_app --json

# Run command
ccontrol run "npm test" --expect "passing"

# Fuzz testing
ccontrol fuzz target_app --max-inputs 50
```

## 🔍 Program Investigation (Main Use Case)

ClaudeControl excels at exploring and understanding unknown CLI programs:

### Automatic Investigation

```python
from claudecontrol import investigate_program

# Fully automated investigation
report = investigate_program("unknown_app")
print(report.summary())

# Report includes:
# - Detected prompts and commands
# - Help system analysis
# - State mapping
# - Exit commands
# - Data formats (JSON, XML, tables)
# - Safety warnings
```

### Interactive Learning

Learn from user demonstrations:

```python
from claudecontrol.investigate import ProgramInvestigator

investigator = ProgramInvestigator("complex_app")
report = investigator.learn_from_interaction()
# User demonstrates, system learns
```

### Quick Probing

Fast check if a program is interactive:

```python
from claudecontrol import probe_interface

result = probe_interface("some_tool")
if result["interactive"]:
    print(f"Found prompt: {result['prompt']}")
    print(f"Commands: {result['commands_found']}")
```

### State Mapping

Map program states and transitions:

```python
from claudecontrol import map_program_states

states = map_program_states("database_cli")
for state, info in states["states"].items():
    print(f"State {state}: entered via '{info['entered_from']}'")
```

### Fuzz Testing

Test program boundaries:

```python
from claudecontrol import fuzz_program

findings = fuzz_program("target_app", max_inputs=100)
for finding in findings:
    if finding["type"] == "error":
        print(f"Input caused error: {finding['input']}")
```

## 🎮 Core Features

### Session Management

```python
from claudecontrol import Session, control

# Context manager for auto-cleanup
with Session("python") as s:
    s.expect(">>>")
    s.sendline("print('Hello')")
    output = s.get_recent_output()

# Persistent sessions
server = control("npm run dev", reuse=True)
# Session persists across script runs!
```

### Pattern Matching

```python
session.expect([">>>", "...", pexpect.EOF])  # Multiple patterns
index = session.expect_exact("Login:")        # Exact string
match = session.wait_for_regex(r"\d+")       # Regex with match object
```

### Test Commands

```python
from claudecontrol.claude_helpers import test_command

success, error = test_command("npm test", ["✓", "passing"])
if success:
    print("All tests passed!")
else:
    print(f"Tests failed: {error}")
```

### Interactive Sessions

```python
from claudecontrol import control

# Take control of a Python session
session = control("python")
session.expect(">>>")
session.sendline("print('Claude is in control!')")
response = session.read_until(">>>")
print(response)
```

### Session Reuse

```python
# First script
session = control("npm run dev", reuse=True)
session.expect("Server running")

# Later script - gets the same session!
session = control("npm run dev", reuse=True)
print("Server still running:", session.is_alive())
```

### Parallel Execution

```python
from claudecontrol.claude_helpers import parallel_commands

results = parallel_commands([
    "npm test",
    "python -m pytest",
    "cargo test"
])

for cmd, result in results.items():
    if result["success"]:
        print(f"✓ {cmd}")
```

### Command Chains

```python
from claudecontrol.claude_helpers import CommandChain

chain = CommandChain()
chain.add("git pull")
chain.add("npm install", condition=lambda r: "package.json" in r[-1])
chain.add("npm test", on_success=True)
results = chain.run()
```

### Record & Replay Sessions

```python
from claudecontrol import Session, RecordMode, FallbackMode

tapes_dir = "./tapes"

# Record live interaction using Talkback-style NEW mode
with Session("sqlite3", args=["-batch"], tapes_path=tapes_dir,
             record=RecordMode.NEW, fallback=FallbackMode.PROXY) as session:
    session.expect("sqlite>")
    session.sendline("select 1;")
    session.expect("sqlite>")

# Replay deterministically with strict matching
with Session("sqlite3", args=["-batch"], tapes_path=tapes_dir,
             record=RecordMode.DISABLED, fallback=FallbackMode.NOT_FOUND,
             latency=0, summary=True) as session:
    session.expect("sqlite>")
    session.sendline("select 1;")
    session.expect("sqlite>")
```

Tapes are human-editable JSON5 artifacts that capture prompts, inputs, chunked outputs with timing, exit codes, annotations, and
session metadata. Matchers mirror Talkback concepts: allow/ignore lists for env vars and args, pluggable `stdinMatcher` /
`commandMatcher`, prompt normalization, and optional state hashes. Decorators (`input_decorator`, `output_decorator`,
`tape_decorator`) enable last-mile transformations, while built-in redaction scrubs secrets by default.

### Latency & Error Simulation

```python
with Session("python", tapes_path=tapes_dir,
             record=RecordMode.DISABLED,
             fallback=FallbackMode.NOT_FOUND,
             latency=(25, 75),           # ms range per chunk
             error_rate=5) as session:   # 5% chance to inject replay failure
    session.expect(">>>")
```

Latency policies accept ints, ranges, or callables and fall back to per-tape overrides. Error policies allow probabilistic exit
code injection or truncated output so CI can harden workflows against flaky behavior.

## 🛡️ Safety Features

ClaudeControl prioritizes safety when investigating unknown programs:

- **Safe Mode** (default) - Blocks potentially dangerous commands
- **Timeout Protection** - Prevents hanging on unresponsive programs
- **Resource Limits** - Controls memory and CPU usage
- **Session Isolation** - Programs run in isolated sessions
- **Audit Trail** - All interactions are logged
- **Zombie Cleanup** - Automatic cleanup of dead processes

## 📁 Project Structure

```
claudecontrol/
├── src/claudecontrol/
│   ├── core.py              # Core Session class
│   ├── investigate.py        # Program investigation engine
│   ├── claude_helpers.py     # High-level helper functions
│   ├── patterns.py           # Pattern matching utilities
│   ├── testing.py            # Black box testing framework
│   ├── interactive_menu.py   # Interactive menu system
│   ├── cli.py               # Command-line interface
│   ├── exceptions.py        # Custom exceptions
│   └── replay/              # Talkback-style record & replay package
│       ├── __init__.py
│       ├── modes.py         # RecordMode / FallbackMode enums
│       ├── model.py         # Tape, Exchange, Chunk dataclasses
│       ├── store.py         # TapeStore loader + TapeIndex
│       ├── matchers.py      # Command/env/prompt/stdin matchers
│       ├── normalize.py     # ANSI strip & volatile value scrubbers
│       ├── decorators.py    # Input/output/tape decorator hooks
│       ├── record.py        # Recorder using pexpect.logfile_read
│       ├── play.py          # Replay transport & latency policies
│       ├── latency.py       # Latency resolution helpers
│       ├── errors.py        # Error injection helpers
│       ├── summary.py       # Exit summary printer
│       └── redact.py        # Secret detection and masking
├── tests/                   # Comprehensive test suite
│   ├── test_core.py         # Core functionality tests
│   ├── test_helpers.py      # Helper function tests
│   ├── test_patterns.py     # Pattern matching tests
│   ├── test_investigate.py  # Investigation tests
│   ├── test_testing.py      # Testing framework tests
│   ├── test_integration.py  # Integration tests
│   └── test_replay_*        # Tape model, recorder, player, CLI tests
├── backup/
│   └── examples/            # Example scripts
├── docs/                    # Additional documentation
├── CLAUDE.md               # Detailed Claude Code guide
└── README.md              # This file
```

## 📚 Examples

### Testing Commands

```python
from claudecontrol import interactive_command

output = interactive_command("mysql", [
    {"expect": "password:", "send": "secret"},
    {"expect": "mysql>", "send": "show databases;"},
    {"expect": "mysql>", "send": "exit"}
])
```

### Black-Box Testing

```python
from claudecontrol.testing import black_box_test

# Comprehensive testing with automatic report
results = black_box_test("unknown_program", timeout=10)
print(results["report"])
```

### Real-time Output Streaming

```python
# Enable streaming for monitoring
session = control("npm run dev", stream=True)
print(f"Monitor output: tail -f {session.pipe_path}")
```

### SSH Operations

```python
from claudecontrol.claude_helpers import ssh_command

output = ssh_command(
    host="server.example.com",
    command="uptime",
    username="admin"
)
```

### Process Monitoring

```python
from claudecontrol.claude_helpers import watch_process

def on_error(session, pattern):
    print(f"Error detected: {pattern}")

matches = watch_process(
    "npm run dev",
    ["Error:", "Warning:"],
    callback=on_error,
    timeout=300
)
```

## 🔧 Configuration

Configuration file: `~/.claude-control/config.json`

```json
{
    "session_timeout": 300,
    "max_sessions": 20,
    "auto_cleanup": true,
    "log_level": "INFO",
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

Session data stored in: `~/.claude-control/sessions/`
Investigation reports saved to: `~/.claude-control/investigations/`
Replay tapes default to: `./tapes/` (override per session or via `--tapes`).

## 📖 Documentation

- **[OVERVIEW.md](OVERVIEW.md)** - Detailed explanation of the three core capabilities
- **[CLAUDE.md](CLAUDE.md)** - Comprehensive guide for Claude Code usage
- **docs/** - Additional documentation and guides
- **backup/examples/** - Runnable example scripts
- Run `ccontrol` for interactive tutorials
- **requirements.md / architecture.md / implementation.md / plan.md** - Talkback-style record & replay specs and rollout plan

## 🌟 Real-World Scenarios

### When to Use ClaudeControl

**Scenario 1: You encounter an undocumented CLI tool**
```python
# Problem: New database CLI with no docs
# Solution: Let ClaudeControl figure it out
report = investigate_program("mystery_db_cli")
# Now you know all commands, how to login, query syntax, etc.
```

**Scenario 2: You need to test a CLI app before deployment**
```python
# Problem: Need to ensure CLI app is production-ready
# Solution: Run comprehensive black-box tests
results = black_box_test("production_cli", timeout=30)
# Get report on stability, error handling, resource usage
```

**Scenario 3: You need to automate a complex CLI workflow**
```python
# Problem: Daily task requires 20+ manual CLI commands
# Solution: Create robust automation
chain = CommandChain()
chain.add("ssh prod-server", expect="$")
chain.add("cd /app", expect="$")
chain.add("git pull", expect="$")
chain.add("npm test", expect="passing", on_success=True)
chain.add("npm run deploy", on_success=True)
results = chain.run()
```

### Specific Use Cases by Industry

**DevOps & SRE**
- Automate deployment pipelines
- Test CLI tools before production
- Monitor and interact with server processes

**Security Testing**
- Black-box testing of CLI applications
- Fuzz testing for vulnerability discovery
- Automated security scanning workflows

**Release Engineering & CI**
- Lock deterministic CLI interactions behind Talkback-style tapes
- Inject latency and failures to harden pipelines before release
- Enforce tape coverage via exit summaries and validation commands

**Data Engineering**
- Automate database CLI interactions
- Test ETL pipeline tools
- Discover features in data processing CLIs

**Legacy System Migration**
- Map old CLI interfaces before replacement
- Create automation bridges during transition
- Document undocumented tools

**QA & Testing**
- Comprehensive CLI application testing
- Regression test automation
- Performance and stress testing

## ⚠️ Known Limits & Best Practices

- **Full-screen TTY apps (e.g., `vim`, `top`)** are captured as raw streams; matching works best for line-oriented CLIs.
- **Filesystem side effects** are out of scope—run recordings in disposable working directories when command output depends on disk state.
- **Windows PTY support** lags behind POSIX. Use WSL or plan for `wexpect`-style adapters in future releases.
- **Tape edits** are loaded at session start. Restart tooling after modifying JSON5 tapes to rebuild the index.

## 🐛 Troubleshooting

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check System Status

```python
from claudecontrol import status
info = status()
print(f"Active sessions: {info['active_sessions']}")
```

### Clean Up Sessions

```python
from claudecontrol import cleanup_sessions
cleaned = cleanup_sessions(max_age_minutes=60)
```

### Manage Tape Corpora

```bash
# Record with live execution (Talkback NEW mode)
ccontrol rec --tapes ./tapes sqlite3 -batch

# Replay only – fail fast on tape misses (Talkback DISABLED + NOT_FOUND)
ccontrol play --tapes ./tapes sqlite3 -batch

# Replay with proxy fallback to the real program
ccontrol proxy --tapes ./tapes sqlite3 -batch

# Inspect and curate tapes
ccontrol tapes list --unused
ccontrol tapes validate --strict
ccontrol tapes redact --inplace
```

All tape commands honor `--record`, `--fallback`, `--latency`, `--error-rate`, `--summary`, `--silent`, and `--debug` flags so
you can enforce deterministic replay in CI while still authoring new exchanges locally.

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## 📮 Support

- GitHub Issues: [Report bugs or request features](https://github.com/anthropics/claude-code/issues)
- Documentation: See CLAUDE.md for detailed API reference

---

**ClaudeControl** - Making CLI automation, investigation, testing, and replay systematic 🚀