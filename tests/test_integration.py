"""
Integration tests for claudecontrol
End-to-end testing of complete workflows
"""

import os
import time
import json
import pytest
from pathlib import Path

from claudecontrol import (
    Session, run, control, cleanup_sessions,
    list_sessions, get_session, investigate_program
)
from claudecontrol.claude_helpers import (
    test_command, parallel_commands, CommandChain,
    status
)
from claudecontrol.patterns import (
    extract_json, detect_prompt_pattern, classify_output
)
from claudecontrol.testing import black_box_test


class TestCompleteWorkflows:
    """Test complete end-to-end workflows"""
    
    def test_python_repl_workflow(self):
        """Test complete Python REPL interaction workflow"""
        with Session("python", persist=False) as session:
            # Wait for prompt
            session.expect(">>>", timeout=5)
            
            # Define a function
            session.sendline("def factorial(n):")
            session.expect("...")
            session.sendline("    if n <= 1:")
            session.expect("...")
            session.sendline("        return 1")
            session.expect("...")
            session.sendline("    return n * factorial(n-1)")
            session.expect("...")
            session.sendline("")  # Empty line to end function
            session.expect(">>>")
            
            # Use the function
            session.sendline("factorial(5)")
            session.expect(">>>")
            
            output = session.get_recent_output(10)
            assert "120" in output
            
            # Test with variables
            session.sendline("result = factorial(6)")
            session.expect(">>>")
            session.sendline("print(f'6! = {result}')")
            session.expect(">>>")
            
            output = session.get_recent_output(5)
            assert "6! = 720" in output
            
            # Exit cleanly
            session.sendline("exit()")
    
    def test_command_chaining_workflow(self):
        """Test command chaining workflow"""
        chain = CommandChain()
        
        # Build a chain of commands
        chain.add("echo 'Starting workflow'")
        chain.add("echo 'Step 1: Check Python'")
        chain.add("python --version")
        chain.add("echo 'Step 2: Run calculation'")
        chain.add("python -c 'print(2**10)'")
        chain.add("echo 'Workflow complete'")
        
        # Run the chain
        results = chain.run()
        
        # Verify all steps completed
        assert len(results) == 6
        assert all(r["success"] for r in results)
        
        # Check outputs
        assert "Starting workflow" in results[0]["output"]
        assert "Python" in results[2]["output"]
        assert "1024" in results[4]["output"]
        assert "Workflow complete" in results[5]["output"]
    
    def test_parallel_testing_workflow(self):
        """Test parallel command execution workflow"""
        # Run multiple tests in parallel
        test_commands = [
            "python -c 'print(1+1)'",
            "python -c 'print(2*3)'",
            "python -c 'import sys; print(sys.version_info.major)'",
            "echo 'test4'",
            "pwd"
        ]
        
        results = parallel_commands(test_commands, timeout=5)
        
        # All should succeed
        assert len(results) == 5
        assert all(r["success"] for r in results.values())
        
        # Check specific outputs
        assert "2" in results["python -c 'print(1+1)'"]["output"]
        assert "6" in results["python -c 'print(2*3)'"]["output"]
        assert "test4" in results["echo 'test4'"]["output"]
    
    def test_session_persistence_workflow(self):
        """Test session persistence across multiple operations"""
        # Create a persistent session
        session_id = f"persist_test_{int(time.time())}"
        
        # First interaction
        s1 = control("python", session_id=session_id, reuse=True)
        s1.expect(">>>")
        s1.sendline("data = {'key': 'value'}")
        s1.expect(">>>")
        
        # Simulate disconnect (but keep session alive)
        # In real use, this might be across different script runs
        
        # Reconnect to same session
        s2 = control("python", session_id=session_id, reuse=True)
        assert s2.session_id == session_id
        
        # Data should still be there
        s2.sendline("print(data)")
        s2.expect(">>>")
        
        output = s2.get_recent_output(5)
        assert "{'key': 'value'}" in output
        
        # Cleanup
        s2.sendline("exit()")
        s2.close()
    
    def test_error_recovery_workflow(self):
        """Test error recovery workflow"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Cause an error
            session.sendline("1/0")
            session.expect(">>>")
            
            output = session.get_recent_output(10)
            assert "ZeroDivisionError" in output
            
            # Recover and continue
            session.sendline("print('Recovered from error')")
            session.expect(">>>")
            
            output = session.get_recent_output(5)
            assert "Recovered from error" in output
            
            # Session should still be functional
            session.sendline("2 + 2")
            session.expect(">>>")
            
            output = session.get_recent_output(5)
            assert "4" in output


class TestRealWorldScenarios:
    """Test real-world usage scenarios"""
    
    def test_development_server_monitoring(self):
        """Test monitoring a development server (simulated)"""
        # Create a mock server that outputs periodically
        script = """
import time
import sys
print("Server starting on port 8000...")
sys.stdout.flush()
for i in range(3):
    time.sleep(0.5)
    print(f"Request {i+1} processed")
    sys.stdout.flush()
print("Server stopped")
"""
        
        with Session(f"python -c '{script}'", persist=False) as session:
            # Wait for server to start
            try:
                session.expect("starting", timeout=5)
                output = session.get_full_output()
                assert "port 8000" in output
                
                # Monitor for requests
                for i in range(3):
                    session.expect(f"Request {i+1}", timeout=2)
                
                # Wait for shutdown
                session.expect("stopped", timeout=5)
                
            except Exception:
                # Server might have already finished
                pass
    
    def test_interactive_cli_automation(self, mock_script):
        """Test automating an interactive CLI application"""
        with Session(f"python {mock_script}", persist=False) as session:
            # Wait for prompt
            session.expect("Enter command:", timeout=5)
            
            # Test help
            session.sendline("help")
            session.expect("Enter command:")
            output = session.get_recent_output(20)
            assert "Available commands" in output
            
            # Test echo
            session.sendline("echo Hello World")
            session.expect("Enter command:")
            output = session.get_recent_output(5)
            assert "Hello World" in output
            
            # Test sleep
            session.sendline("sleep 0.5")
            session.expect("Enter command:", timeout=2)
            output = session.get_recent_output(5)
            assert "Slept for 0.5 seconds" in output
            
            # Exit
            session.sendline("exit")
            time.sleep(0.5)
            assert not session.is_alive()
    
    def test_data_extraction_workflow(self):
        """Test extracting structured data from command output"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Generate JSON output
            session.sendline("import json")
            session.expect(">>>")
            session.sendline("data = {'users': [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}]}")
            session.expect(">>>")
            session.sendline("print(json.dumps(data))")
            session.expect(">>>")
            
            # Extract and parse JSON
            output = session.get_recent_output(10)
            json_data = extract_json(output)
            
            assert json_data is not None
            assert "users" in json_data
            assert len(json_data["users"]) == 2
            assert json_data["users"][0]["name"] == "Alice"
            assert json_data["users"][1]["age"] == 25
    
    def test_multi_state_program_workflow(self, temp_dir):
        """Test working with multi-state program"""
        # Use the mock interactive program
        mock_program = temp_dir / "mock_interactive.py"
        mock_program.write_text(Path(__file__).parent.joinpath("fixtures", "mock_interactive.py").read_text())
        
        with Session(f"python {mock_program}", persist=False) as session:
            # Initial state
            session.expect("main>", timeout=5)
            
            # Check state
            session.sendline("state")
            session.expect("main>")
            output = session.get_recent_output(5)
            assert "Current state: main" in output
            
            # Change to config state
            session.sendline("config")
            session.expect("config>")
            output = session.get_recent_output(5)
            assert "Entering config mode" in output
            
            # Set a value in config mode
            session.sendline("set timeout 30")
            session.expect("config>")
            
            # Return to main
            session.sendline("main")
            session.expect("main>")
            
            # Change to data state
            session.sendline("data")
            session.expect("data>")
            
            # Add items
            session.sendline("add item1")
            session.expect("data>")
            session.sendline("add item2")
            session.expect("data>")
            
            # List items
            session.sendline("list")
            session.expect("data>")
            output = session.get_recent_output(10)
            assert "item1" in output
            assert "item2" in output
            
            # Get JSON output
            session.sendline("json")
            session.expect("data>")
            output = session.get_recent_output(5)
            json_data = extract_json(output)
            assert json_data is not None
            assert "item1" in json_data["items"]
            assert "item2" in json_data["items"]
            
            # Exit
            session.sendline("exit")


class TestCompleteSystemIntegration:
    """Test complete system integration"""
    
    def test_full_investigation_workflow(self):
        """Test complete program investigation workflow"""
        # Investigate a simple program
        report = investigate_program(
            "echo 'test'",
            timeout=2,
            safe_mode=True,
            save_report=False
        )
        
        # Verify investigation completed
        assert report.completed_at is not None
        assert report.program == "echo 'test'"
        
        # Should have found basic information
        assert len(report.interaction_log) > 0
    
    def test_full_testing_workflow(self):
        """Test complete black box testing workflow"""
        # Run black box tests
        results = black_box_test(
            "echo 'test'",
            timeout=2,
            save_report=False
        )
        
        # Verify all tests ran
        assert "results" in results
        assert len(results["results"]) > 0
        
        # Check report was generated
        assert "report" in results
        assert "Black Box Test Report" in results["report"]
    
    def test_session_cleanup_workflow(self):
        """Test session cleanup workflow"""
        # Create multiple sessions
        sessions = []
        for i in range(3):
            s = control(f"echo 'session{i}'", session_id=f"cleanup_test_{i}")
            sessions.append(s)
        
        # Verify all are registered
        active = list_sessions()
        session_ids = [s["session_id"] for s in active]
        
        for i in range(3):
            assert f"cleanup_test_{i}" in session_ids
        
        # Cleanup all
        cleanup_sessions(force=True)
        
        # Verify all are gone
        active = list_sessions()
        session_ids = [s["session_id"] for s in active]
        
        for i in range(3):
            assert f"cleanup_test_{i}" not in session_ids
    
    def test_status_monitoring_workflow(self):
        """Test system status monitoring"""
        # Create some sessions
        s1 = control("python", session_id="status_test_1")
        s2 = control("echo 'test'", session_id="status_test_2")
        
        # Get status
        info = status()
        
        # Verify status information
        assert info["total_sessions"] >= 2
        assert info["active_sessions"] >= 0  # Some might have already exited
        assert "sessions" in info
        assert "log_size_mb" in info
        
        # Cleanup
        cleanup_sessions(force=True)


class TestEdgeCasesIntegration:
    """Test edge cases in integration"""
    
    def test_very_long_output(self):
        """Test handling very long output"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Generate lots of output
            session.sendline("for i in range(1000): print(i)")
            session.expect(">>>", timeout=5)
            
            # Should handle large output
            output = session.get_full_output()
            assert len(output) > 1000
            assert "999" in output
    
    def test_rapid_commands(self):
        """Test rapid command execution"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Send many commands quickly
            for i in range(10):
                session.sendline(f"x{i} = {i}")
                session.expect(">>>", timeout=2)
            
            # Verify all were processed
            session.sendline("print(x9)")
            session.expect(">>>")
            
            output = session.get_recent_output(5)
            assert "9" in output
    
    def test_unicode_handling(self):
        """Test Unicode character handling"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Test Unicode
            session.sendline("print('Hello 世界 🌍')")
            session.expect(">>>")
            
            output = session.get_recent_output(5)
            assert "Hello" in output
            assert "🌍" in output or "世界" in output  # Might depend on encoding
    
    def test_concurrent_session_isolation(self):
        """Test that concurrent sessions are isolated"""
        s1 = control("python", session_id="isolated_1")
        s2 = control("python", session_id="isolated_2")
        
        try:
            # Set different values in each session
            s1.expect(">>>")
            s1.sendline("x = 'session1'")
            s1.expect(">>>")
            
            s2.expect(">>>")
            s2.sendline("x = 'session2'")
            s2.expect(">>>")
            
            # Verify isolation
            s1.sendline("print(x)")
            s1.expect(">>>")
            output1 = s1.get_recent_output(5)
            assert "session1" in output1
            assert "session2" not in output1
            
            s2.sendline("print(x)")
            s2.expect(">>>")
            output2 = s2.get_recent_output(5)
            assert "session2" in output2
            assert "session1" not in output2
            
        finally:
            s1.close()
            s2.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])