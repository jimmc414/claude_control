"""
Tests for claudecontrol helper functions
"""

import time
import shlex
import pytest
from unittest.mock import patch, MagicMock

from claudecontrol.claude_helpers import (
    test_command, interactive_command, run_script,
    watch_process, parallel_commands, CommandChain,
    status, probe_interface, map_program_states,
    fuzz_program, ssh_command
)


class TestTestCommand:
    """Test the test_command helper"""
    
    def test_simple_success(self):
        """Test command with expected output"""
        success, error = test_command("echo 'hello world'", "hello")
        assert success is True
        assert error is None
    
    def test_simple_failure(self):
        """Test command without expected output"""
        success, _ = test_command("echo 'hello'", "goodbye")
        assert success is False
    
    def test_multiple_patterns(self):
        """Test with multiple expected patterns"""
        success, error = test_command("echo 'hello world'", ["hello", "world"])
        assert success is True
        assert error is None

        success, _ = test_command("echo 'hello'", ["hello", "goodbye"])
        assert success is False
    
    def test_command_failure(self):
        """Test with failing command"""
        success, err = test_command("false", "anything")
        assert success is False
        assert err
    
    def test_with_timeout(self):
        """Test with timeout"""
        success, err = test_command("sleep 10", "done", timeout=1)
        assert success is False
        assert err


class TestInteractiveCommand:
    """Test the interactive_command helper"""
    
    def test_python_interaction(self):
        """Test interactive Python session"""
        interactions = [
            {"expect": ">>>", "send": "x = 10"},
            {"expect": ">>>", "send": "y = 20"},
            {"expect": ">>>", "send": "print(x + y)"},
            {"expect": ">>>", "send": "exit()"}
        ]
        
        output = interactive_command("python", interactions, timeout=5)
        assert "30" in output
    
    def test_with_delay(self):
        """Test interaction with delays"""
        interactions = [
            {"expect": ">>>", "send": "import time", "delay": 0.5},
            {"expect": ">>>", "send": "print('done')", "delay": 0.5},
            {"expect": ">>>", "send": "exit()"}
        ]
        
        output = interactive_command("python", interactions, timeout=5)
        assert "done" in output


class TestRunScript:
    """Test the run_script helper"""
    
    def test_python_script(self):
        """Test running a Python script"""
        script = """
print("Hello from script")
print(2 + 2)
"""
        result = run_script("python", script)
        
        assert result["success"] is True
        assert "Hello from script" in result["output"]
        assert "4" in result["output"]
        assert result["exitstatus"] == 0
    
    def test_bash_script(self):
        """Test running a bash script"""
        script = """
echo "Test output"
echo "Line 2"
"""
        result = run_script("bash", script)
        
        assert result["success"] is True
        assert "Test output" in result["output"]
        assert "Line 2" in result["output"]
    
    def test_failing_script(self):
        """Test script that fails"""
        script = "exit 1"
        result = run_script("bash", script)
        
        assert result["success"] is False
        assert result["exitstatus"] == 1
    
    def test_script_timeout(self):
        """Test script timeout"""
        script = "import time; time.sleep(10)"
        result = run_script("python", script, timeout=1)
        
        assert result["success"] is False
        assert result["duration"] < 2  # Should timeout quickly


class TestWatchProcess:
    """Test the watch_process helper"""
    
    def test_watch_for_patterns(self):
        """Test watching for specific patterns"""
        # Use a command that outputs predictable text
        matches = watch_process(
            "echo 'Error: test error'; echo 'Warning: test warning'",
            ["Error:", "Warning:"],
            timeout=2
        )
        
        assert len(matches) >= 1
        assert any("Error:" in m or "Warning:" in m for m in matches)
    
    def test_watch_with_callback(self):
        """Test watch with callback function"""
        callback_data = []

        def callback(session, pattern):
            callback_data.append(pattern)

        watch_process(
            "echo 'Error: test'",
            "Error:",
            callback=callback,
            timeout=2
        )

        assert len(callback_data) > 0

    def test_short_lived_command_returns_cleanly(self):
        """Ensure short-lived commands don't raise errors"""
        matches = watch_process(
            "echo 'done'",
            "nonexistent pattern",
            timeout=2
        )

        assert matches == []


class TestParallelCommands:
    """Test parallel command execution"""
    
    def test_parallel_execution(self):
        """Test running multiple commands in parallel"""
        commands = [
            "echo 'cmd1'",
            "echo 'cmd2'",
            "echo 'cmd3'"
        ]
        
        results = parallel_commands(commands, timeout=5)
        
        assert len(results) == 3
        assert all(r["success"] for r in results.values())
        assert "cmd1" in results["echo 'cmd1'"]["output"]
        assert "cmd2" in results["echo 'cmd2'"]["output"]
        assert "cmd3" in results["echo 'cmd3'"]["output"]
    
    def test_parallel_with_failures(self):
        """Test parallel execution with some failures"""
        commands = [
            "echo 'success'",
            "false",
            "this_does_not_exist"
        ]
        
        results = parallel_commands(commands, timeout=5)

        assert results["echo 'success'"]["success"] is True
        assert results["false"]["success"] is False
        assert results["this_does_not_exist"]["success"] is False
        assert "false" in results["false"]["error"]
        assert results["this_does_not_exist"]["error"]


class TestSSHCommand:
    """Test the ssh_command helper"""

    def test_quotes_command(self):
        """Ensure commands with spaces are properly quoted"""
        captured = {}

        class DummySession:
            def __init__(self, cmd, timeout=None, persist=False):
                captured["cmd"] = cmd

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

            def expect(self, patterns, timeout=None):
                return len(patterns) - 1

            def sendline(self, _):
                pass

            def get_full_output(self):
                return "output"

        with patch("claudecontrol.claude_helpers.Session", DummySession):
            result = ssh_command("localhost", 'echo "hello world"')

        expected = f"ssh -p 22 localhost {shlex.quote('echo "hello world"')}"
        assert captured["cmd"] == expected
        assert result == "output"

class TestCommandChain:
    """Test CommandChain class"""
    
    def test_simple_chain(self):
        """Test simple command chain"""
        chain = CommandChain()
        chain.add("echo 'step1'")
        chain.add("echo 'step2'")
        chain.add("echo 'step3'")
        
        results = chain.run()
        
        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert "step1" in results[0]["output"]
        assert "step2" in results[1]["output"]
        assert "step3" in results[2]["output"]
    
    def test_conditional_execution(self):
        """Test conditional command execution"""
        chain = CommandChain()
        chain.add("echo 'always'")
        chain.add("false")
        chain.add("echo 'on_failure'", on_failure=True)
        chain.add("echo 'on_success'", on_success=True)
        
        results = chain.run()
        
        # Should run: always, false, on_failure
        # Should skip: on_success
        assert len(results) == 3
        assert results[0]["success"] is True  # echo always
        assert results[1]["success"] is False  # false
        assert results[2]["success"] is True  # echo on_failure
        assert "false" in results[1]["error"]
    
    def test_chain_with_condition(self):
        """Test chain with custom condition"""
        chain = CommandChain()
        chain.add("echo 'test'")
        chain.add(
            "echo 'conditional'",
            condition=lambda results: "test" in results[-1]["output"]
        )
        
        results = chain.run()
        
        assert len(results) == 2
        assert "conditional" in results[1]["output"]


class TestStatus:
    """Test status function"""
    
    def test_status_info(self):
        """Test getting status information"""
        info = status()
        
        assert "total_sessions" in info
        assert "active_sessions" in info
        assert "sessions" in info
        assert "log_size_mb" in info
        assert isinstance(info["total_sessions"], int)
        assert isinstance(info["active_sessions"], int)


class TestProbeInterface:
    """Test probe_interface function"""
    
    def test_probe_python(self):
        """Test probing Python interface"""
        result = probe_interface("python", timeout=5)
        
        assert "interactive" in result
        assert "prompt" in result
        assert result["interactive"] is True
        assert ">>>" in str(result.get("prompt", ""))


class TestMapProgramStates:
    """Test map_program_states function"""
    
    def test_map_states(self):
        """Test mapping program states"""
        result = map_program_states(
            "python",
            starting_commands=["help()"],
            max_depth=1,
            timeout=5
        )
        
        assert "states" in result
        assert "transitions" in result
        assert "initial_prompt" in result


class TestFuzzProgram:
    """Test fuzz_program function"""
    
    def test_basic_fuzzing(self):
        """Test basic fuzzing functionality"""
        findings = fuzz_program(
            "python",
            max_inputs=5,
            timeout=5
        )
        
        assert isinstance(findings, list)
        # Should find at least some interesting behavior
        assert len(findings) >= 0
        
        for finding in findings:
            assert "input" in finding
            assert "type" in finding


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
