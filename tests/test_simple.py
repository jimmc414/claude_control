"""
Simple fast tests to verify basic functionality
These tests avoid long-running Python interpreter sessions
"""

import pytest
import time
from pathlib import Path

from claudecontrol import (
    Session, run, control, cleanup_sessions,
    SessionError, TimeoutError, ProcessError
)
from claudecontrol.patterns import (
    extract_json, detect_prompt_pattern, is_error_output,
    extract_commands_from_help, detect_data_format
)
from claudecontrol.claude_helpers import test_command


class TestBasicFunctionality:
    """Test basic claudecontrol functionality with fast tests"""
    
    def test_run_echo(self):
        """Test simple echo command"""
        output = run("echo 'hello world'")
        assert "hello world" in output
    
    def test_run_with_timeout(self):
        """Test run with timeout"""
        # This should complete quickly
        output = run("echo 'quick'", timeout=2)
        assert "quick" in output
    
    def test_session_echo(self):
        """Test session with echo"""
        with Session("echo 'test'", persist=False) as session:
            time.sleep(0.5)
            output = session.get_full_output()
            assert "test" in output
    
    def test_test_command(self):
        """Test the test_command helper"""
        # Test with true command
        success, error = test_command("echo 'success'", "success")
        assert success is True
        assert error is None
        # Test with false expectation
        success, _ = test_command("echo 'hello'", "goodbye")
        assert success is False
    
    def test_session_lifecycle(self):
        """Test session creation and cleanup"""
        session = Session("echo 'lifecycle'", persist=False)
        assert session is not None
        time.sleep(0.5)
        session.close()
        assert not session.is_alive()
    
    def test_error_handling(self):
        """Test error handling"""
        with pytest.raises(ProcessError):
            Session("command_that_does_not_exist_12345", persist=False)
    
    def test_cleanup_sessions(self):
        """Test session cleanup"""
        # Create a session
        s = control("echo 'cleanup'", session_id="cleanup_test", reuse=False)
        time.sleep(0.5)
        
        # Cleanup
        cleanup_sessions(force=True)
        
        # Should be cleaned
        assert not s.is_alive()


class TestPatternBasics:
    """Test basic pattern functionality"""
    
    def test_json_extraction(self):
        """Test JSON extraction"""
        text = 'Data: {"key": "value", "number": 42}'
        result = extract_json(text)
        assert result is not None
        assert result["key"] == "value"
        assert result["number"] == 42
    
    def test_prompt_detection(self):
        """Test prompt detection"""
        assert detect_prompt_pattern("user@host:~$ ") is not None
        assert detect_prompt_pattern(">>> ") == ">>>"
        assert detect_prompt_pattern("mysql> ") == "mysql>"
        assert detect_prompt_pattern("normal text") is None
    
    def test_error_detection(self):
        """Test error detection"""
        assert is_error_output("ERROR: Something failed") is True
        assert is_error_output("Permission denied") is True
        assert is_error_output("Normal output") is False
    
    def test_command_extraction(self):
        """Test command extraction from help"""
        help_text = """
        Commands:
          help  - Show help
          list  - List items
          exit  - Exit program
        """
        commands = extract_commands_from_help(help_text)
        cmd_names = [cmd[0] for cmd in commands]
        assert "help" in cmd_names
        assert "list" in cmd_names
        assert "exit" in cmd_names
    
    def test_data_format_detection(self):
        """Test data format detection"""
        assert "json" in detect_data_format('{"key": "value"}')
        assert "xml" in detect_data_format('<tag>content</tag>')
        assert "csv" in detect_data_format('name,age\nAlice,30')
        assert "table" in detect_data_format('| col1 | col2 |')


class TestQuickCommands:
    """Test quick command execution"""
    
    def test_pwd_command(self):
        """Test pwd command"""
        output = run("pwd")
        assert "/" in output  # Should have a path
    
    def test_date_command(self):
        """Test date command"""
        output = run("date")
        # Should have some date output
        assert len(output) > 5
    
    def test_true_false_commands(self):
        """Test true and false commands"""
        # true should succeed
        output = run("true")
        # false will exit with non-zero and should raise an error
        with pytest.raises(ProcessError):
            run("false")
    
    def test_echo_multiple(self):
        """Test multiple echo commands"""
        output1 = run("echo 'first'")
        output2 = run("echo 'second'")
        output3 = run("echo 'third'")
        
        assert "first" in output1
        assert "second" in output2
        assert "third" in output3


class TestSessionManagement:
    """Test session management without long-running processes"""
    
    def test_session_id_management(self):
        """Test session ID management"""
        s1 = control("echo 'test1'", session_id="managed_1", reuse=False)
        s2 = control("echo 'test2'", session_id="managed_2", reuse=False)
        
        assert s1.session_id == "managed_1"
        assert s2.session_id == "managed_2"
        
        # Cleanup
        s1.close()
        s2.close()
    
    def test_output_capture(self):
        """Test output capture"""
        with Session("echo 'line1'; echo 'line2'; echo 'line3'", persist=False) as session:
            time.sleep(0.5)
            output = session.get_full_output()
            
            # All lines should be captured
            assert "line1" in output
            assert "line2" in output
            assert "line3" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])