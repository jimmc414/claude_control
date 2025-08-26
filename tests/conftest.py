"""
Shared fixtures and configuration for claudecontrol tests
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from claudecontrol import cleanup_sessions


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatically cleanup sessions after each test"""
    yield
    # Cleanup any sessions created during the test
    cleanup_sessions(force=True)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    # Cleanup
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_script(temp_dir):
    """Create a mock Python script for testing"""
    script_path = temp_dir / "mock_script.py"
    script_content = '''#!/usr/bin/env python3
import sys
import time

def main():
    print("Mock script started")
    print("Enter command: ", end="", flush=True)
    
    while True:
        try:
            cmd = input()
            if cmd == "exit":
                print("Goodbye!")
                break
            elif cmd == "help":
                print("Available commands: help, echo, error, sleep, exit")
            elif cmd.startswith("echo "):
                print(cmd[5:])
            elif cmd == "error":
                print("ERROR: This is a test error", file=sys.stderr)
                sys.exit(1)
            elif cmd.startswith("sleep "):
                try:
                    seconds = float(cmd[6:])
                    time.sleep(seconds)
                    print(f"Slept for {seconds} seconds")
                except ValueError:
                    print("Invalid sleep duration")
            else:
                print(f"Unknown command: {cmd}")
            
            print("Enter command: ", end="", flush=True)
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\\nInterrupted")
            break

if __name__ == "__main__":
    main()
'''
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    return str(script_path)


@pytest.fixture
def sample_outputs():
    """Sample outputs for testing pattern matching"""
    return {
        "json": '{"name": "test", "value": 42, "items": [1, 2, 3]}',
        "xml": '<root><item>test</item><value>42</value></root>',
        "csv": 'name,age,city\nAlice,30,NYC\nBob,25,LA',
        "table": """
+-------+-----+-------+
| Name  | Age | City  |
+-------+-----+-------+
| Alice | 30  | NYC   |
| Bob   | 25  | LA    |
+-------+-----+-------+
""",
        "error": "ERROR: Connection failed\nPermission denied",
        "help": """
Usage: program [options] command

Commands:
  help     - Show this help message
  list     - List all items
  create   - Create a new item
  delete   - Delete an item

Options:
  -v, --verbose  Enable verbose output
  -q, --quiet    Suppress output
""",
        "prompt_bash": "user@host:~/dir$ ",
        "prompt_python": ">>> ",
        "prompt_mysql": "mysql> ",
    }


@pytest.fixture
def test_config():
    """Test configuration settings"""
    return {
        "timeout": 5,  # Short timeout for tests
        "test_mode": True,
        "safe_mode": True,
    }


@pytest.fixture
def safe_commands():
    """List of safe commands for testing"""
    return [
        "echo 'test'",
        "python --version",
        "pwd",
        "date",
        "whoami",
        "true",
        "false",
    ]


# Ensure proper cleanup on test session end
def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all tests complete"""
    cleanup_sessions(force=True)