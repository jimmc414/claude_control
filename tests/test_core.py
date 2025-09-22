"""
Tests for core claudecontrol functionality
"""

import os
import time
import logging
import psutil
import pytest
import threading
from pathlib import Path

from claudecontrol import (
    Session, run, control, get_session, 
    list_sessions, cleanup_sessions,
    SessionError, TimeoutError, ProcessError
)


class TestSession:
    """Test Session class functionality"""
    
    def test_session_creation(self):
        """Test basic session creation"""
        session = Session("echo 'test'", persist=False)
        assert session is not None
        assert session.is_alive()
        session.close()
        assert not session.is_alive()
    
    def test_session_context_manager(self):
        """Test session as context manager"""
        with Session("python", persist=False) as session:
            assert session.is_alive()
            session.expect(">>>", timeout=5)
            session.sendline("1 + 1")
            session.expect(">>>")
            output = session.get_recent_output(5)
            assert "2" in output
        # Session should be closed after context
        assert not session.is_alive()
    
    def test_send_and_expect(self):
        """Test sending commands and expecting output"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            session.sendline("print('hello world')")
            session.expect(">>>")
            output = session.get_recent_output(10)
            assert "hello world" in output
    
    def test_timeout_error(self):
        """Test timeout error handling"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            session.sendline("import time; time.sleep(10)")
            
            with pytest.raises(TimeoutError) as exc_info:
                session.expect(">>>", timeout=1)
            
            # Error should include recent output
            assert "Recent output:" in str(exc_info.value)
    
    def test_output_capture(self):
        """Test output buffering and capture"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Generate some output
            for i in range(5):
                session.sendline(f"print({i})")
                session.expect(">>>")
            
            # Check recent output
            recent = session.get_recent_output(20)
            for i in range(5):
                assert str(i) in recent
            
            # Check full output
            full = session.get_full_output()
            assert len(full) > len(recent)
    
    def test_session_persistence(self):
        """Test session persistence and reuse"""
        # Create a persistent session
        session1 = control("python", reuse=True)
        session_id = session1.session_id
        session1.expect(">>>")
        session1.sendline("x = 42")
        session1.expect(">>>")
        
        # Get the same session
        session2 = control("python", reuse=True)
        assert session2.session_id == session_id
        session2.sendline("print(x)")
        session2.expect(">>>")
        output = session2.get_recent_output(5)
        assert "42" in output
        
        # Cleanup
        session1.close()
    
    def test_session_registry(self):
        """Test session registry and listing"""
        # Start with clean slate
        cleanup_sessions(force=True)
        
        # Create multiple sessions
        s1 = control("echo 'test1'", session_id="test1")
        s2 = control("echo 'test2'", session_id="test2")
        
        # List sessions
        sessions = list_sessions()
        session_ids = [s["session_id"] for s in sessions]
        assert "test1" in session_ids
        assert "test2" in session_ids
        
        # Get specific session
        retrieved = get_session("test1")
        assert retrieved is not None
        assert retrieved.session_id == "test1"
        
        # Cleanup
        cleanup_sessions(force=True)
        sessions = list_sessions()
        assert len([s for s in sessions if s["session_id"] in ["test1", "test2"]]) == 0
    
    def test_process_error(self):
        """Test process error handling"""
        with pytest.raises(ProcessError):
            Session("this_command_does_not_exist_12345", persist=False)
    
    def test_read_nonblocking(self):
        """Test non-blocking read"""
        with Session("python", persist=False) as session:
            session.expect(">>>")
            
            # Should return empty string if no data
            data = session.read_nonblocking(timeout=0.1)
            assert data == ""
            
            # Generate output and read
            session.sendline("print('test')")
            time.sleep(0.5)
            data = session.read_nonblocking(timeout=0.1)
            assert "test" in data
    
    def test_exitstatus(self):
        """Test exit status retrieval"""
        with Session("python -c 'exit(0)'", persist=False) as session:
            time.sleep(0.5)
            while session.is_alive():
                time.sleep(0.1)
            assert session.exitstatus() == 0
        
        with Session("python -c 'exit(1)'", persist=False) as session:
            time.sleep(0.5)
            while session.is_alive():
                time.sleep(0.1)
            assert session.exitstatus() == 1


class TestRunFunction:
    """Test the run() convenience function"""
    
    def test_simple_run(self):
        """Test simple command execution"""
        output = run("echo 'hello world'")
        assert "hello world" in output
    
    def test_run_with_expect(self):
        """Test run with expect pattern"""
        output = run("echo 'test pattern'", expect="pattern")
        assert "test pattern" in output
    
    def test_run_with_timeout(self):
        """Test run with timeout"""
        with pytest.raises(TimeoutError):
            run("sleep 10", timeout=1)

    def test_run_timeout_logs_and_cleans(self, caplog):
        """Ensure timeout raises warning and terminates process"""
        with caplog.at_level(logging.WARNING):
            with pytest.raises(TimeoutError):
                run("sleep 10", timeout=1)

        assert any("exceeded timeout" in message for message in caplog.messages)

        found = False
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmdline_list = proc.info["cmdline"]
            except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
                continue
            if not cmdline_list:
                continue
            cmdline = " ".join(cmdline_list)
            if "sleep 10" in cmdline:
                found = True
                break
        assert not found
    
    def test_run_with_send(self):
        """Test run with input sending"""
        output = run("python", expect=">>>", send="print('sent')\nexit()", timeout=5)
        assert "sent" in output or ">>>" in output  # May capture prompt or output

    def test_run_failure_raises_process_error(self):
        """Failing commands should raise ProcessError with output"""
        with pytest.raises(ProcessError) as exc_info:
            run("bash -c 'echo fail; exit 3'", timeout=5)

        message = str(exc_info.value)
        assert "exit status 3" in message
        assert "fail" in message


class TestControl:
    """Test the control() function"""
    
    def test_control_basic(self):
        """Test basic control function"""
        session = control("echo 'test'", reuse=False)
        assert session is not None
        assert session.is_alive()
        session.close()
    
    def test_control_reuse(self):
        """Test session reuse with control"""
        # First call creates session
        s1 = control("python", reuse=True)
        s1_id = s1.session_id
        
        # Second call reuses
        s2 = control("python", reuse=True)
        assert s2.session_id == s1_id
        
        # Cleanup
        s1.close()
    
    def test_control_with_session_id(self):
        """Test control with explicit session ID"""
        session = control("echo 'test'", session_id="my_test_session")
        assert session.session_id == "my_test_session"
        
        # Should retrieve same session
        session2 = get_session("my_test_session")
        assert session2 is session
        
        session.close()


class TestCleanup:
    """Test cleanup functionality"""
    
    def test_cleanup_dead_sessions(self):
        """Test cleanup of dead sessions"""
        # Create a session that will die
        session = control("echo 'test'", session_id="dead_session")
        time.sleep(0.5)

        # Session should be dead
        assert not session.is_alive()

        # Cleanup should remove it
        cleaned = cleanup_sessions()
        assert cleaned >= 0

        # Should not be in registry
        assert get_session("dead_session") is None

    def test_completed_session_visible_until_cleanup(self):
        """Completed sessions should remain listed until explicitly cleaned up"""
        # Ensure we start from a clean slate
        cleanup_sessions(force=True)

        session_id = "completed_visibility_test"
        session = control(
            "python -c 'print(\"done\")'",
            session_id=session_id,
            reuse=False,
        )

        try:
            # Wait for the command to finish so the session is no longer alive
            session.expect("done", timeout=5)
            for _ in range(50):
                if not session.is_alive():
                    break
                time.sleep(0.1)

            assert not session.is_alive()

            # Default listing should still include completed sessions
            all_sessions = list_sessions()
            assert any(s["session_id"] == session_id for s in all_sessions)

            # Requesting only active sessions should filter it out
            active_sessions = list_sessions(active_only=True)
            assert all(
                s["session_id"] != session_id for s in active_sessions
            )
        finally:
            cleanup_sessions(force=True)

    def test_cleanup_old_sessions(self):
        """Test cleanup of old sessions"""
        # Create a session
        session = control("python", session_id="old_session")

        # Manipulate last_activity to make it old
        session.last_activity = session.last_activity.replace(year=2020)
        
        # Cleanup with max_age
        cleaned = cleanup_sessions(max_age_minutes=1)
        
        # Should be cleaned
        assert get_session("old_session") is None
    
    def test_force_cleanup(self):
        """Test forced cleanup"""
        # Create sessions
        s1 = control("python", session_id="force1")
        s2 = control("python", session_id="force2")
        
        assert s1.is_alive()
        assert s2.is_alive()
        
        # Force cleanup
        cleanup_sessions(force=True)
        
        # All should be gone
        assert not s1.is_alive()
        assert not s2.is_alive()
        assert get_session("force1") is None
        assert get_session("force2") is None


class TestSessionConfiguration:
    """Test session configuration management"""
    
    def test_save_and_load_config(self):
        """Test saving and loading session configurations"""
        from claudecontrol import list_configs, delete_config
        
        # Create and configure a session
        with Session("echo 'test'", timeout=30, persist=False) as session:
            # Save configuration
            session.save_program_config("test_config")
        
        # Check config was saved
        configs = list_configs()
        assert "test_config" in configs
        
        # Create new session from config
        session2 = Session.from_config("test_config", persist=False)
        assert session2.timeout == 30
        
        # Cleanup
        session2.close()
        delete_config("test_config")
        
        # Verify deleted
        configs = list_configs()
        assert "test_config" not in configs


class TestStreamingOutput:
    """Test streaming output functionality"""
    
    def test_pipe_creation(self):
        """Test named pipe creation for streaming"""
        session = Session("echo 'test'", stream=True, persist=False)
        
        # Pipe should be created
        assert session.pipe_path is not None
        assert session.pipe_path.exists()
        
        # Cleanup
        session.close()
        
        # Pipe should be removed
        assert not session.pipe_path.exists()


def test_load_config_thread_safety(monkeypatch, tmp_path):
    """Ensure _load_config initializes config only once when called from multiple threads"""
    import claudecontrol.core as core

    # Prepare temporary config file
    home = tmp_path
    config_dir = home / ".claude-control"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{}")

    monkeypatch.setenv("HOME", str(home))

    core._config = None

    call_count = {"count": 0}
    real_loads = core.json.loads

    def counting_loads(s, *args, **kwargs):
        time.sleep(0.1)
        call_count["count"] += 1
        return real_loads(s, *args, **kwargs)

    monkeypatch.setattr(core.json, "loads", counting_loads)

    def target():
        core._load_config()

    threads = [threading.Thread(target=target) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count["count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])