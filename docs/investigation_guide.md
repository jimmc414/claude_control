# ClaudeControl Investigation Guide

## Overview

ClaudeControl's investigation capabilities allow you to systematically explore and understand unknown CLI programs. This guide covers all investigation features and best practices.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Investigation Methods](#investigation-methods)
3. [Safety Features](#safety-features)
4. [Investigation Reports](#investigation-reports)
5. [Use Cases](#use-cases)
6. [API Reference](#api-reference)
7. [Best Practices](#best-practices)

## Quick Start

### Interactive Menu

The easiest way to investigate a program is through the interactive menu:

```bash
ccontrol
# Select option 2: Investigate Unknown Program
```

### Command Line

```bash
# Full investigation
ccontrol investigate mystery_program

# Quick probe
ccontrol probe unknown_tool --json

# Interactive learning
ccontrol learn complex_app --save

# Fuzz testing
ccontrol fuzz target_app --max-inputs 50
```

### Python API

```python
from claudecontrol import investigate_program

# Simple investigation
report = investigate_program("unknown_app")
print(report.summary())
```

## Investigation Methods

### 1. Automatic Investigation

Fully automated exploration that discovers:
- Command interface and syntax
- Help system
- Prompt patterns
- State transitions
- Exit commands
- Data output formats

```python
from claudecontrol.investigate import ProgramInvestigator

investigator = ProgramInvestigator("mystery_app")
report = investigator.investigate()

# Access findings
print(f"Commands found: {report.commands}")
print(f"Prompts: {report.prompts}")
print(f"Help commands: {report.help_commands}")
```

### 2. Interactive Learning

Learn from user demonstrations:

```python
investigator = ProgramInvestigator("complex_app")
report = investigator.learn_from_interaction()
# User takes control, demonstrates features
# System observes and learns patterns
```

### 3. Quick Probing

Fast check to determine if a program is interactive:

```python
from claudecontrol import probe_interface

result = probe_interface("some_tool")
if result["interactive"]:
    print(f"Prompt detected: {result['prompt']}")
    print(f"Responsive: {result['responsive']}")
```

### 4. State Mapping

Map program states and transitions:

```python
from claudecontrol import map_program_states

states = map_program_states("database_cli", 
    starting_commands=["help", "status", "config"],
    max_depth=3
)

# Visualize state graph
for state, info in states["states"].items():
    print(f"{state}: {info}")
```

### 5. Fuzz Testing

Test program boundaries and find edge cases:

```python
from claudecontrol import fuzz_program

findings = fuzz_program("target_app", 
    max_inputs=100,
    timeout=5
)

# Analyze findings
errors = [f for f in findings if f["type"] == "error"]
crashes = [f for f in findings if f["type"] == "exception"]
```

## Safety Features

### Safe Mode (Default)

ClaudeControl runs in safe mode by default, which:
- Blocks dangerous commands (rm -rf, format, etc.)
- Limits exploration depth
- Enforces timeouts
- Prevents resource exhaustion

```python
# Explicitly control safe mode
report = investigate_program("risky_app", safe_mode=True)
```

### Dangerous Command Detection

The system blocks patterns like:
- `rm -rf /`
- `format C:`
- `dd if=/dev/zero`
- Fork bombs
- System modification commands

### Resource Limits

- **Timeout protection**: Default 10s per operation
- **Memory limits**: Monitors and limits memory usage
- **Output limits**: Caps output buffer size
- **Session limits**: Maximum concurrent sessions

## Investigation Reports

### Report Structure

```python
report = investigate_program("app")

# Report contains:
report.program          # Program name
report.commands         # Dict of discovered commands
report.prompts          # List of prompt patterns
report.help_commands    # Commands that show help
report.exit_commands    # Commands that exit program
report.data_formats     # Detected output formats
report.states           # Program state map
report.interaction_log  # Full interaction history
report.safety_notes     # Security warnings
```

### Saving Reports

```python
# Auto-save to ~/.claude-control/investigations/
report = investigate_program("app", save_report=True)

# Manual save
path = report.save()
print(f"Report saved to {path}")

# Load existing report
from claudecontrol.investigate import load_investigation
report = load_investigation(Path("investigation.json"))
```

### Report Output

```python
# Human-readable summary
print(report.summary())

# JSON export
report_dict = report.to_dict()
json.dumps(report_dict, indent=2)
```

## Use Cases

### 1. Reverse Engineering Proprietary CLIs

```python
# Investigate unknown enterprise tool
report = investigate_program("proprietary_tool")

# Extract command structure
for cmd, info in report.commands.items():
    print(f"{cmd}: {info['description']}")
    
# Build automation based on findings
from claudecontrol import control
session = control("proprietary_tool")
for cmd in report.help_commands:
    session.sendline(cmd)
```

### 2. Security Testing

```python
from examples.black_box_testing import BlackBoxTester

tester = BlackBoxTester("target_app")
tester.test_startup()
tester.test_help_system()
tester.test_invalid_input()
tester.test_exit_behavior()
tester.test_resource_usage()
tester.run_fuzz_test()

print(tester.generate_report())
```

### 3. Documentation Generation

```python
# Generate docs for undocumented tool
report = investigate_program("legacy_app")

# Create markdown documentation
docs = f"""
# {report.program} Documentation

## Commands
{chr(10).join(f'- `{cmd}`: {info.get("description", "Unknown")}' 
              for cmd, info in report.commands.items())}

## Usage Examples
Start the program and use prompt: {report.prompts[0] if report.prompts else 'Unknown'}

## Exit
Use one of: {', '.join(report.exit_commands)}
"""

Path("legacy_app_docs.md").write_text(docs)
```

### 4. CI/CD Integration

```python
# Validate CLI tool behavior in CI
def test_cli_interface():
    report = investigate_program("our_cli_tool")
    
    # Assertions
    assert len(report.commands) >= 10, "Missing commands"
    assert "help" in report.help_commands, "No help command"
    assert report.exit_commands, "No exit command found"
    assert not report.safety_notes, "Safety issues detected"
```

## API Reference

### Main Functions

```python
# High-level investigation
investigate_program(program, timeout=10, safe_mode=True, save_report=True)

# Quick probe
probe_interface(program, commands_to_try=None, timeout=5)

# State mapping
map_program_states(program, starting_commands=None, max_depth=3)

# Fuzz testing
fuzz_program(program, input_patterns=None, max_inputs=50, timeout=5)
```

### ProgramInvestigator Class

```python
class ProgramInvestigator:
    def __init__(self, program, timeout=10, max_depth=5, safe_mode=True)
    def investigate() -> InvestigationReport
    def learn_from_interaction() -> InvestigationReport
    @classmethod
    def quick_probe(program, timeout) -> dict
```

### InvestigationReport Class

```python
class InvestigationReport:
    def to_dict() -> dict
    def save(path=None) -> Path
    def summary() -> str
```

## Best Practices

### 1. Start with Quick Probe

Always probe first to check if a program is interactive:

```python
if probe_interface("app")["interactive"]:
    # Proceed with full investigation
    report = investigate_program("app")
```

### 2. Use Interactive Learning for Complex Programs

For programs with complex interactions, let the system learn from you:

```python
investigator = ProgramInvestigator("complex_db")
report = investigator.learn_from_interaction()
# Demonstrate the workflow manually
```

### 3. Save and Reuse Reports

```python
# First time: investigate and save
report = investigate_program("app", save_report=True)

# Later: load and use
report = load_investigation(Path("~/.claude-control/investigations/app_*.json"))
```

### 4. Combine Methods

```python
# 1. Quick probe
if probe_interface("app")["interactive"]:
    # 2. Automatic investigation
    report = investigate_program("app")
    
    # 3. Fuzz test based on findings
    if report.commands:
        findings = fuzz_program("app")
```

### 5. Handle Failures Gracefully

```python
try:
    report = investigate_program("unstable_app", timeout=5)
except SessionError as e:
    # Try with different approach
    report = ProgramInvestigator("unstable_app", safe_mode=True)
    report = investigator.learn_from_interaction()
```

## Troubleshooting

### Program Not Responding

```python
# Increase timeout
report = investigate_program("slow_app", timeout=30)

# Or use quick probe first
probe = probe_interface("slow_app", timeout=2)
```

### Investigation Incomplete

```python
# Increase exploration depth
investigator = ProgramInvestigator("deep_app", max_depth=10)

# Or use interactive learning
report = investigator.learn_from_interaction()
```

### Safety Blocks

```python
# If safe mode is too restrictive (use with caution!)
report = investigate_program("admin_tool", safe_mode=False)
```

## Advanced Topics

### Custom Investigation Patterns

```python
from claudecontrol.patterns import INVESTIGATION_PATTERNS

# Add custom patterns
INVESTIGATION_PATTERNS["help_indicators"].append(r"HELP MENU")
INVESTIGATION_PATTERNS["command_patterns"].append(r"^CMD: (\w+)")
```

### Parallel Investigation

```python
from claudecontrol import parallel_commands

# Investigate multiple programs
programs = ["app1", "app2", "app3"]
results = {}

for prog in programs:
    results[prog] = investigate_program(prog)
```

### Investigation Automation

```python
# Automated investigation pipeline
def investigate_suite(programs):
    reports = {}
    
    for prog in programs:
        # Probe first
        if probe_interface(prog)["interactive"]:
            # Full investigation
            reports[prog] = investigate_program(prog)
            
            # Test if needed
            if reports[prog].safety_notes:
                findings = fuzz_program(prog, max_inputs=20)
                reports[prog].fuzz_findings = findings
    
    return reports
```

---

This guide covers the full investigation capabilities of ClaudeControl. For more examples, see the `examples/investigation_demo.py` and `examples/black_box_testing.py` files.