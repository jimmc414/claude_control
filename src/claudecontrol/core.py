"""
Core functionality for ClaudeControl
Give Claude control of your terminal with elegant simplicity
"""

import os
import json
import time
import atexit
import logging
import tempfile
import threading
import signal
import fcntl
import re
import platform
from builtins import TimeoutError as BuiltinTimeoutError
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Union, List, Dict, Any, Callable
from contextlib import contextmanager
from collections import deque

import pexpect
import psutil

from .exceptions import SessionError, TimeoutError, ProcessError, ConfigNotFoundError
from .patterns import COMMON_PROMPTS, COMMON_ERRORS
from .replay.modes import RecordMode, FallbackMode
from .replay.store import TapeStore, KeyBuilder
from .replay.namegen import TapeNameGenerator
from .replay.record import Recorder
from .replay.play import ReplayTransport
from .replay.summary import print_summary
from .replay.exceptions import TapeMissError
from .replay.matchers import MatchingContext, default_command_matcher, default_stdin_matcher
from .replay.decorators import InputDecorator, OutputDecorator, TapeDecorator

# Global session registry for persistence across calls
_sessions: Dict[str, 'Session'] = {}
_lock = threading.Lock()
_config = None
_config_lock = threading.Lock()

logger = logging.getLogger(__name__)

# Compile error patterns for pipe streaming
ERROR_PATTERNS = re.compile('|'.join(
    pattern for patterns in COMMON_ERRORS.values() 
    for pattern in patterns
), re.IGNORECASE)


def _load_config() -> dict:
    """Load configuration with smart defaults"""
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:
                config_path = Path.home() / ".claude-control" / "config.json"
                if config_path.exists():
                    try:
                        _config = json.loads(config_path.read_text())
                    except Exception:
                        _config = {}
                else:
                    _config = {}

                # Apply defaults
                _config.setdefault("session_timeout", 300)
                _config.setdefault("max_sessions", 20)
                _config.setdefault("auto_cleanup", True)
                _config.setdefault("log_level", "INFO")
                _config.setdefault("output_limit", 10000)

    return _config


class Session:
    """
    A smart controlled session with automatic management
    """
    
    def __init__(
        self,
        command: str,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        encoding: str = "utf-8",
        dimensions: tuple = (24, 80),
        session_id: Optional[str] = None,
        persist: bool = True,
        stream: bool = False,
        *,
        replay: bool = False,
        tapes_path: Optional[str] = None,
        record: RecordMode = RecordMode.DISABLED,
        fallback: FallbackMode = FallbackMode.NOT_FOUND,
        summary: bool = False,
        tape_name_generator: Optional[TapeNameGenerator] = None,
        allow_env: Optional[List[str]] = None,
        ignore_env: Optional[List[str]] = None,
        stdin_matcher: Optional[Callable] = None,
        command_matcher: Optional[Callable] = None,
        input_decorator: Optional[InputDecorator] = None,
        output_decorator: Optional[OutputDecorator] = None,
        tape_decorator: Optional[TapeDecorator] = None,
        latency: Union[int, tuple, Callable] = 0,
        error_rate: Union[int, Callable] = 0,
    ):
        self.session_id = session_id or f"session_{int(time.time() * 1000)}"
        self.command = command
        self.timeout = timeout
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.persist = persist
        self.encoding = encoding
        self.cwd = cwd or os.getcwd()
        self.env = dict(env or {})
        self.dimensions = dimensions
        self.latency = latency
        self.error_rate = error_rate
        self.summary = summary
        self._record_mode = record
        self._fallback_mode = fallback
        self._replay_enabled = replay
        self._tapes_path = Path(tapes_path) if tapes_path else Path("./tapes")
        self._tape_store = TapeStore(self._tapes_path)
        self._tape_name_generator = tape_name_generator or TapeNameGenerator(self._tapes_path)
        self._tape_index: Dict = {}
        self._allow_env = allow_env
        self._ignore_env = ignore_env
        self._stdin_matcher = stdin_matcher or default_stdin_matcher
        self._command_matcher = command_matcher or default_command_matcher
        self._key_builder = KeyBuilder(
            self._allow_env,
            self._ignore_env,
            self._stdin_matcher,
            self._command_matcher,
        )
        self._input_decorator = input_decorator
        self._output_decorator = output_decorator
        self._tape_decorator = tape_decorator
        self._recorder: Optional[Recorder] = None
        self._using_replay = False
        self._summary_printed = False
        self._last_prompt: Optional[str] = None
        self.platform = platform.platform()
        self.tool_version = "claude_control"
        self._spawn_command = command
        self._spawn_timeout = timeout
        self._spawn_cwd = cwd
        self._spawn_env = env
        self._spawn_encoding = encoding
        self._spawn_dimensions = dimensions
        self._spawn_stream = stream
        
        # Output management
        config = _load_config()
        self.output_buffer = deque(maxlen=config["output_limit"])
        self.full_output = [
            f"[session {self.session_id} started {self.created_at.isoformat()}]\n"
        ]
        self._last_output_at: Optional[datetime] = None

        # Track expect/response history for configuration generation
        self.expect_history: List[Dict[str, Any]] = []
        
        # Add resource management
        self.start_time = time.time()
        self.max_runtime = config.get("max_session_runtime", 3600)  # 1 hour default
        self.max_output_size = config.get("max_output_size", 100 * 1024 * 1024)  # 100MB
        
        # Check total sessions
        if len(_sessions) >= config.get("max_sessions", 20):
            raise SessionError("Maximum number of sessions reached")
        
        # Set up streaming if requested
        self._pipe_path = None
        self.pipe_fd = None
        if stream:
            self._setup_pipe_stream()

        # Create the initial transport (live or replay)
        try:
            self._initialize_transport()
            if persist:
                with _lock:
                    _sessions[self.session_id] = self
        except Exception as e:
            raise ProcessError(f"Failed to initialize session for '{command}': {e}")
    
    class _OutputCapture:
        """Capture output to both buffer and file"""
        def __init__(self, session):
            self.session = session

        def write(self, data):
            if data:
                self.session._capture_output(data)

        def flush(self):
            pass

    # ------------------------------------------------------------------ replay helpers
    def _initialize_transport(self) -> None:
        if self._replay_enabled and self._record_mode == RecordMode.DISABLED:
            self._setup_replay_transport()
        else:
            self._setup_live_transport()

    def _setup_live_transport(self) -> None:
        self.process = pexpect.spawn(
            self._spawn_command,
            timeout=self._spawn_timeout,
            cwd=self._spawn_cwd,
            env=self._spawn_env,
            encoding=self._spawn_encoding,
            dimensions=self._spawn_dimensions,
            echo=False,
        )
        self.process.logfile_read = self._OutputCapture(self)
        self._using_replay = False
        if self._record_mode != RecordMode.DISABLED:
            self._recorder = Recorder(
                session=self,
                tapes_path=self._tapes_path,
                mode=self._record_mode,
                namegen=self._tape_name_generator,
                input_decorator=self._input_decorator,
                output_decorator=self._output_decorator,
                tape_decorator=self._tape_decorator,
            )
            self._recorder.start()

    def _setup_replay_transport(self) -> None:
        self._tape_store.load_all()
        self._tape_index = self._tape_store.build_index(self._key_builder)
        self.process = ReplayTransport(
            self._tape_store,
            self._tape_index,
            self._key_builder,
            self._matching_context(),
            self.latency,
            self.error_rate,
        )
        self._using_replay = True

    def _switch_to_live(self) -> None:
        self._setup_live_transport()

    def _matching_context(self, prompt: Optional[str] = None) -> MatchingContext:
        return MatchingContext(
            program=self.command,
            args=[],
            env=self.env,
            cwd=self.cwd,
            prompt=prompt if prompt is not None else self._last_prompt,
        )

    def _update_prompt_from_process(self) -> None:
        prompt = getattr(self.process, "after", None)
        if isinstance(prompt, bytes):
            try:
                prompt = prompt.decode(self.encoding)
            except Exception:
                prompt = prompt.decode("utf-8", "ignore")
        if isinstance(prompt, str) and prompt:
            self._last_prompt = prompt
    
    def _capture_output(self, data: str):
        """Capture output with automatic rotation"""
        self.last_activity = datetime.now()
        self._last_output_at = self.last_activity
        
        # Add to buffers
        lines = data.splitlines(keepends=True)
        for line in lines:
            self.output_buffer.append(line)
            self.full_output.append(line)
            
            # Write to pipe if streaming
            if self.pipe_fd is not None:
                # Check if line matches error patterns
                event_type = "ERR" if ERROR_PATTERNS.search(line.rstrip()) else "OUT"
                self._write_pipe_event(event_type, line.rstrip())
            
        # Write to session log
        log_dir = Path.home() / ".claude-control" / "sessions" / self.session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "output.log"
        with open(log_file, "a", encoding=self.encoding) as f:
            f.write(data)
            
        # Rotate if needed (> 10MB)
        if log_file.stat().st_size > 10 * 1024 * 1024:
            rotated = log_dir / f"output_{int(time.time())}.log"
            log_file.rename(rotated)

    def _drain_output(self) -> None:
        """Best-effort drain of any pending child output."""
        if not self.process or self._using_replay:
            return
        if not hasattr(self.process, "read_nonblocking"):
            return
        while True:
            try:
                chunk = self.process.read_nonblocking(size=1024, timeout=0)
            except (pexpect.TIMEOUT, BuiltinTimeoutError, pexpect.EOF):
                break
            except Exception:
                break
            else:
                if not chunk:
                    break

    
    def send(self, text: str, delay: float = 0, _record: bool = True) -> None:
        """Send input to the process"""
        if self._using_replay:
            payload = text.encode(self.encoding)
            self.process.ctx = self._matching_context()
            try:
                self.process.send(payload)
            except TapeMissError:
                if self._fallback_mode == FallbackMode.PROXY:
                    self._switch_to_live()
                    self._using_replay = False
                    return self.send(text, delay)
                raise
            self.last_activity = datetime.now()
            return

        if not self.is_alive():
            raise SessionError(f"Session {self.session_id} is not active")

        # Write to pipe if streaming
        if self.pipe_fd is not None:
            self._write_pipe_event("IN ", text)

        if self._recorder and _record:
            self._recorder.on_send(text.encode(self.encoding), "raw", self._matching_context())

        if delay:
            for char in text:
                self.process.send(char)
                time.sleep(delay)
        else:
            self.process.send(text)

        self.last_activity = datetime.now()
    
    def sendline(self, line: str = "") -> None:
        """Send a line to the process"""
        if self._recorder and not self._using_replay:
            self._recorder.on_send((line + "\n").encode(self.encoding), "line", self._matching_context())
        self.send(line + "\n", _record=False)
    
    def expect(
        self,
        patterns: Union[str, List[str]],
        timeout: Optional[int] = None,
        searchwindowsize: Optional[int] = None,
    ) -> int:
        """
        Wait for patterns with better error handling
        Returns index of matched pattern
        """
        if isinstance(patterns, str):
            patterns = [patterns]
            
        timeout = timeout or self.timeout
        output_marker = len(self.full_output)

        try:
            if self._using_replay:
                target = patterns if len(patterns) > 1 else patterns[0]
                index = self.process.expect(target, timeout=timeout)
            else:
                index = self.process.expect(
                    patterns,
                    timeout=timeout,
                    searchwindowsize=searchwindowsize,
                )
            self.last_activity = datetime.now()
            self._record_expectation("expect", patterns, index)
            self._update_prompt_from_process()
            if self._recorder and not self._using_replay:
                exit_info = None
                if not self.process.isalive():
                    exit_info = {
                        "code": getattr(self.process, "exitstatus", None),
                        "signal": getattr(self.process, "signalstatus", None),
                    }
                self._recorder.on_exchange_end(self._matching_context(), exit_info)
            return index

        except (pexpect.TIMEOUT, BuiltinTimeoutError):
            output_growth = len(self.full_output) - output_marker
            recent_output = (
                self._last_output_at is not None
                and datetime.now() - self._last_output_at < timedelta(seconds=1)
            )
            retried = False
            if (
                timeout is not None
                and timeout < self.timeout
                and self.process.isalive()
                and (output_growth > 0 or recent_output)
            ):
                before = getattr(self.process, "before", "")
                if before:
                    if isinstance(before, bytes):
                        try:
                            before_text = before.decode(self.encoding, errors="ignore")
                        except Exception:
                            before_text = before.decode("utf-8", errors="ignore")
                    else:
                        before_text = str(before)
                    if before_text.rstrip().endswith("..."):
                        try:
                            self.process.sendline("")
                        except Exception:
                            pass
                try:
                    index = self.process.expect(
                        patterns,
                        timeout=self.timeout,
                        searchwindowsize=searchwindowsize,
                    )
                    retried = True
                    self.last_activity = datetime.now()
                    self._record_expectation("expect", patterns, index)
                    self._update_prompt_from_process()
                    if self._recorder and not self._using_replay:
                        exit_info = None
                        if not self.process.isalive():
                            exit_info = {
                                "code": getattr(self.process, "exitstatus", None),
                                "signal": getattr(self.process, "signalstatus", None),
                            }
                        self._recorder.on_exchange_end(self._matching_context(), exit_info)
                    return index
                except (pexpect.TIMEOUT, BuiltinTimeoutError):
                    retried = True
            # Include recent output in error for debugging
            recent = self.get_recent_output(50)
            raise TimeoutError(
                f"Timeout waiting for patterns {patterns}\n"
                f"Recent output:\n{recent}"
            )
        except pexpect.EOF:
            raise ProcessError(f"Process ended unexpectedly")

    def expect_exact(
        self,
        patterns: Union[str, List[str]],
        timeout: Optional[int] = None,
    ) -> int:
        """Expect exact strings (no regex)"""
        if isinstance(patterns, str):
            patterns = [patterns]
            
        timeout = timeout or self.timeout

        try:
            if self._using_replay:
                target = patterns if len(patterns) > 1 else patterns[0]
                index = self.process.expect_exact(target, timeout=timeout)
            else:
                index = self.process.expect_exact(patterns, timeout=timeout)
            self.last_activity = datetime.now()
            self._record_expectation("expect_exact", patterns, index)
            self._update_prompt_from_process()
            if self._recorder and not self._using_replay:
                exit_info = None
                if not self.process.isalive():
                    exit_info = {
                        "code": getattr(self.process, "exitstatus", None),
                        "signal": getattr(self.process, "signalstatus", None),
                    }
                self._recorder.on_exchange_end(self._matching_context(), exit_info)
            return index
        except (pexpect.TIMEOUT, BuiltinTimeoutError):
            recent = self.get_recent_output(50)
            raise TimeoutError(
                f"Timeout waiting for exact patterns {patterns}\n"
                f"Recent output:\n{recent}"
            )

    def _record_expectation(self, expect_type: str, patterns: List[Any], matched_index: int) -> None:
        """Store successful expect calls for later analysis"""
        pattern_list = list(patterns) if isinstance(patterns, (list, tuple)) else [patterns]
        normalized_patterns = [self._pattern_to_str(pattern) for pattern in pattern_list]

        matched_pattern = None
        if 0 <= matched_index < len(normalized_patterns):
            matched_pattern = normalized_patterns[matched_index]

        history_entry: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "type": expect_type,
            "patterns": normalized_patterns,
            "matched_index": matched_index,
            "matched_pattern": matched_pattern,
        }

        if hasattr(self.process, "before"):
            history_entry["before"] = self.process.before
        if hasattr(self.process, "after"):
            history_entry["after"] = self.process.after

        self.expect_history.append(history_entry)

    @staticmethod
    def _pattern_to_str(pattern: Any) -> str:
        """Convert pattern or regex to a readable string"""
        if pattern is None:
            return ""

        if isinstance(pattern, str):
            return pattern

        if hasattr(pattern, "pattern"):
            return pattern.pattern

        return str(pattern)

    def read_until(
        self,
        pattern: str,
        timeout: Optional[int] = None,
        include_pattern: bool = True,
    ) -> str:
        """Read until pattern is found, return everything before it"""
        self.expect(pattern, timeout)
        result = self.process.before
        
        if include_pattern and self.process.after:
            result += self.process.after
            
        return result
    
    def read_nonblocking(self, size: int = 1024, timeout: float = 0) -> str:
        """Read available data without blocking"""
        try:
            return self.process.read_nonblocking(size, timeout)
        except pexpect.TIMEOUT:
            return ""
    
    def get_recent_output(self, lines: int = 100) -> str:
        """Get recent output lines"""
        self._drain_output()
        return "".join(list(self.output_buffer)[-lines:])

    def get_full_output(self) -> str:
        """Get all captured output"""
        self._drain_output()
        return "".join(self.full_output)

    def is_alive(self) -> bool:
        """Check if process is still running"""
        if not self.process:
            return False
        try:
            return self.process.isalive()
        except (pexpect.exceptions.ExceptionPexpect, OSError):
            return False
    
    def exitstatus(self) -> Optional[int]:
        """Get exit status if process has ended"""
        if self.process:
            return self.process.exitstatus
        return None
    
    def close(self, force: bool = False) -> Optional[int]:
        """Close the session gracefully"""
        if not self.process:
            return None

        try:
            if self._using_replay:
                self.process.close()
                exitstatus = getattr(self.process, "exitstatus", 0)
            else:
                if self.is_alive():
                    if force:
                        self.process.terminate(force=True)
                    else:
                        self.process.terminate()
                        time.sleep(0.5)
                        if self.is_alive():
                            self.process.terminate(force=True)

                exitstatus = self.process.exitstatus

        except Exception as e:
            logger.error(f"Error closing session: {e}")
            exitstatus = -1

        finally:
            # Clean up pipe if streaming
            if self.pipe_fd is not None:
                self._write_pipe_event("MTX", "session_closed=true")
                try:
                    os.close(self.pipe_fd)
                except OSError:
                    pass
                self.pipe_fd = None
            
            if self._pipe_path and self._pipe_path.exists():
                try:
                    self._pipe_path.unlink()
                except OSError:
                    pass
            
            # Remove from registry
            if self.persist:
                with _lock:
                    _sessions.pop(self.session_id, None)

            if self._recorder and not self._using_replay:
                self._recorder.finalize(self._tape_store)

            if self.summary and not self._summary_printed:
                print_summary(self._tape_store)
                self._summary_printed = True

        return exitstatus
    
    def interact(self) -> None:
        """
        Give control to the user for interactive session
        Useful for debugging
        """
        print(f"\n[Entering interactive mode for session {self.session_id}]")
        print("[Press Ctrl+] to exit]")
        
        try:
            self.process.interact()
        except Exception as e:
            print(f"\n[Exited interactive mode: {e}]")
    
    def save_state(self) -> Dict[str, Any]:
        """Save session state for persistence"""
        state_dir = Path.home() / ".claude-control" / "sessions" / self.session_id
        state_dir.mkdir(parents=True, exist_ok=True)
        
        state = {
            "session_id": self.session_id,
            "command": self.command,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_alive": self.is_alive(),
            "pid": self.process.pid if self.process else None,
            "exitstatus": self.exitstatus(),
            "output_lines": len(self.full_output),
        }
        
        state_file = state_dir / "state.json"
        state_file.write_text(json.dumps(state, indent=2))
        
        return state
    
    def save_program_config(self, name: str, include_output: bool = False) -> None:
        """Save current session as a program configuration

        Args:
            name: Name for the configuration
            include_output: Whether to include captured output (default False)
        """
        # Extract interaction patterns from session
        expect_sequences = []

        # Analyze the process interaction history if available
        if not getattr(self, "expect_history", None):
            logger.warning(
                "No expect history recorded for session %s. "
                "Saved configuration will have an empty expect_sequences list.",
                self.session_id,
            )
        else:
            step = 1
            for entry in self.expect_history:
                matched_pattern = entry.get("matched_pattern")
                if matched_pattern is None:
                    continue

                sequence = {
                    "step": step,
                    "expect": matched_pattern,
                }

                patterns = entry.get("patterns") or []
                matched_index = entry.get("matched_index")
                if len(patterns) > 1 and matched_index is not None:
                    readable_patterns = ", ".join(patterns)
                    sequence["note"] = (
                        f"Matched option {matched_index + 1} from patterns: {readable_patterns}"
                    )

                expect_sequences.append(sequence)
                step += 1
        
        notes = [
            f"Saved from session {self.session_id} on {datetime.now().isoformat()}"
        ]
        if not expect_sequences:
            notes.append("No expect history was recorded during this session.")

        config = {
            "name": name,
            "command_template": self.command,
            "expect_sequences": expect_sequences,
            "success_indicators": [],
            "ready_indicators": [],
            "typical_timeout": self.timeout,
            "notes": " ".join(notes),
        }
        
        if include_output:
            # Add sample output for reference (first 100 lines)
            output_lines = self.full_output[:100]
            config["sample_output"] = output_lines
        
        # Save configuration
        config_dir = Path.home() / ".claude-control" / "programs"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_path = config_dir / f"{name}.json"
        config_path.write_text(json.dumps(config, indent=2))
        
        logger.info(f"Saved program configuration '{name}'")
    
    def apply_config(self, name: str) -> None:
        """Apply a saved configuration to current session
        
        Args:
            name: Name of the configuration to apply
        """
        config = get_config(name)
        
        # Apply timeout if not explicitly set
        if hasattr(self, '_original_timeout') and self.timeout == self._original_timeout:
            self.timeout = config.get("typical_timeout", self.timeout)
        
        # Store configuration for reference
        self._applied_config = config
        
        logger.info(f"Applied configuration '{name}' to session")
    
    @classmethod
    def from_config(cls, name: str, **kwargs) -> 'Session':
        """Create a new session from a saved configuration
        
        Args:
            name: Name of the configuration to use
            **kwargs: Additional parameters to override config
            
        Returns:
            New Session instance
        """
        config = get_config(name)
        
        # Extract session parameters from config
        command = kwargs.get('command', config.get('command_template', ''))
        timeout = kwargs.get('timeout', config.get('typical_timeout', 30))
        
        # Create session
        session = cls(
            command=command,
            timeout=timeout,
            **{k: v for k, v in kwargs.items() if k not in ['command', 'timeout']}
        )
        
        # Store config reference
        session._applied_config = config
        session._config_name = name
        
        return session
    
    @property
    def pipe_path(self) -> Optional[Path]:
        """Get the path to the named pipe if streaming is enabled"""
        return self._pipe_path
    
    def _setup_pipe_stream(self):
        """Set up named pipe for streaming"""
        pipe_dir = Path("/tmp/claudecontrol")
        pipe_dir.mkdir(exist_ok=True, mode=0o700)
        
        self._pipe_path = pipe_dir / f"{self.session_id}.pipe"
        
        # Remove existing pipe if present
        if self._pipe_path.exists():
            try:
                self._pipe_path.unlink()
            except OSError:
                pass
        
        try:
            # Create named pipe
            os.mkfifo(self._pipe_path, mode=0o600)
            
            # Open pipe for writing with non-blocking mode
            # Use O_RDWR to avoid blocking when no reader is present
            self.pipe_fd = os.open(str(self._pipe_path), os.O_RDWR | os.O_NONBLOCK)
            
            # Write initial metadata
            self._write_pipe_event("MTX", f"session_id={self.session_id}")
            self._write_pipe_event("MTX", f"command={self.command}")
            
        except Exception as e:
            # Failed to create pipe - continue without streaming
            logger.debug(f"Failed to create pipe: {e}")
            self._pipe_path = None
            self.pipe_fd = None
    
    def _write_pipe_event(self, event_type: str, data: str):
        """Write an event to the pipe if streaming is enabled"""
        if self.pipe_fd is None:
            return
        
        try:
            timestamp = f"{time.time():.3f}"
            event = f"[{timestamp}][{event_type}] {data}\n"
            os.write(self.pipe_fd, event.encode(self.encoding))
        except (BlockingIOError, OSError):
            # No readers or pipe closed - ignore
            pass
    
    def __enter__(self):
        """Context manager support"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit"""
        if not self.persist:
            self.close()
            
    def __repr__(self):
        return (
            f"Session(id={self.session_id}, "
            f"command={self.command!r}, alive={self.is_alive()})"
        )


# High-level convenience functions

def control(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    session_id: Optional[str] = None,
    reuse: bool = True,
    with_config: Optional[str] = None,
    stream: bool = False,
) -> Session:
    """
    Take control of a process or reuse existing one
    
    Args:
        command: Command to execute
        timeout: Default timeout for operations
        cwd: Working directory
        env: Environment variables
        session_id: Explicit session ID (auto-generated if not provided)
        reuse: If True, reuse existing session with same command
        with_config: Name of configuration to apply
        stream: If True, enable named pipe streaming
        
    Returns:
        Session instance
    """
    # Check for reusable session
    if reuse and not session_id:
        with _lock:
            for sid, session in _sessions.items():
                if session.command == command and session.is_alive():
                    logger.debug(f"Reusing session {sid} for command: {command}")
                    return session
    
    # Check for existing session by ID
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        if session.is_alive():
            return session
        else:
            # Clean up dead session
            session.close()
    
    # Create new session
    if with_config:
        # Use configuration
        session = Session.from_config(
            with_config,
            command=command,
            timeout=timeout,
            cwd=cwd,
            env=env,
            session_id=session_id,
            stream=stream,
        )
    else:
        session = Session(
            command=command,
            timeout=timeout,
            cwd=cwd,
            env=env,
            session_id=session_id,
            stream=stream,
        )
    
    return session


def run(
    command: str,
    expect: Optional[Union[str, List[str]]] = None,
    send: Optional[str] = None,
    timeout: int = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """
    One-liner to run a controlled command.
    If the command does not finish before ``timeout`` when no ``expect`` pattern
    is provided, the process is terminated and a :class:`TimeoutError` is
    raised.
    
    Args:
        command: Command to run
        expect: Pattern(s) to wait for
        send: Input to send after expect
        timeout: Operation timeout. When no ``expect`` pattern is provided and
            the process does not complete before this timeout, a
            :class:`TimeoutError` is raised and the process is terminated.
        cwd: Working directory
        env: Environment variables
        
    Returns:
        Captured output
        
    Example:
        output = run("npm test", expect="All tests passed")
    """
    with Session(command, timeout=timeout, cwd=cwd, env=env, persist=False) as session:

        exit_status = None
        signal_status = None

        if expect:
            session.expect(expect, timeout=timeout)

        if send:
            session.send(send)
            # Wait a bit for response
            time.sleep(0.5)

        # Wait for process to complete if no expect pattern given
        if not expect:
            try:
                session.expect(pexpect.EOF, timeout=timeout)
                exit_status = session.exitstatus()
                if session.process is not None:
                    signal_status = session.process.signalstatus
                    if exit_status is None:
                        try:
                            session.process.wait()
                        except (pexpect.exceptions.ExceptionPexpect, OSError):
                            pass
                        else:
                            exit_status = session.exitstatus()
                            signal_status = session.process.signalstatus
            except TimeoutError:
                logger.warning(
                    f"Command '{command}' exceeded timeout of {timeout}s; terminating"
                )
                session.close()
                raise

        # Get all output
        output = session.get_full_output()

        if exit_status not in (None, 0) or signal_status not in (None, 0):
            status_parts = []
            if exit_status not in (None, 0):
                status_parts.append(f"exit status {exit_status}")
            if signal_status not in (None, 0):
                status_parts.append(f"signal {signal_status}")
            status_desc = " and ".join(status_parts) if status_parts else "an unknown error"
            raise ProcessError(
                f"Command '{command}' failed with {status_desc}.\nOutput:\n{output}"
            )

        # If process is still running, terminate it
        if session.is_alive():
            session.close()

    return output


def get_session(session_id: str) -> Optional[Session]:
    """Get existing session by ID"""
    with _lock:
        return _sessions.get(session_id)


def list_sessions(active_only: bool = False) -> List[Dict[str, Any]]:
    """
    List all sessions

    Args:
        active_only: If True, only return alive sessions. Defaults to False so
            completed sessions remain visible until cleanup.
        
    Returns:
        List of session info dicts
    """
    sessions = []
    
    with _lock:
        for session in _sessions.values():
            if active_only and not session.is_alive():
                continue
                
            sessions.append({
                "session_id": session.session_id,
                "command": session.command,
                "is_alive": session.is_alive(),
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "pid": session.process.pid if session.process else None,
            })
            
    return sessions


def cleanup_zombies():
    """Clean up any zombie processes"""
    try:
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        
        for child in children:
            try:
                if child.status() == psutil.STATUS_ZOMBIE:
                    child.terminate()
                    child.wait(timeout=1)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass
                
    except Exception as e:
        logger.error(f"Error cleaning zombies: {e}")


def cleanup_sessions(force: bool = False, max_age_minutes: int = 60) -> int:
    """
    Clean up dead or old sessions
    
    Args:
        force: Force close all sessions
        max_age_minutes: Close sessions older than this
        
    Returns:
        Number of sessions cleaned up
    """
    cleanup_zombies()  # Clean up zombies first
    
    cleaned = 0
    cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)

    # Collect sessions to clean while holding the lock
    with _lock:
        sessions_to_clean = [
            session
            for session in _sessions.values()
            if (
                force
                or not session.is_alive()
                or session.last_activity < cutoff_time
            )
        ]

    # Close sessions outside of the lock to avoid deadlocks
    for session in sessions_to_clean:
        session.close()
        cleaned += 1
                
    logger.info(f"Cleaned up {cleaned} sessions")
    return cleaned


# Configuration management functions

def list_configs() -> List[str]:
    """List all saved program configurations"""
    config_dir = Path.home() / ".claude-control" / "programs"
    if not config_dir.exists():
        return []
    
    configs = []
    for config_file in config_dir.glob("*.json"):
        configs.append(config_file.stem)
    
    return sorted(configs)


def delete_config(name: str) -> None:
    """Delete a program configuration"""
    config_path = Path.home() / ".claude-control" / "programs" / f"{name}.json"
    if not config_path.exists():
        raise ConfigNotFoundError(f"Configuration '{name}' not found")
    
    config_path.unlink()
    logger.info(f"Deleted configuration '{name}'")


def get_config(name: str) -> dict:
    """Get a program configuration as dict"""
    config_path = Path.home() / ".claude-control" / "programs" / f"{name}.json"
    if not config_path.exists():
        raise ConfigNotFoundError(f"Configuration '{name}' not found")
    
    try:
        return json.loads(config_path.read_text())
    except Exception as e:
        raise ConfigNotFoundError(f"Error reading configuration '{name}': {e}")


# Auto-cleanup on exit
@atexit.register 
def _cleanup_on_exit():
    """Clean up sessions on program exit"""
    config = _load_config()
    if config.get("auto_cleanup", True):
        cleanup_sessions(force=True)


# File-based interface for Claude Code

class FileInterface:
    """
    File-based communication for Claude Code
    This is optional - direct usage is preferred
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.home() / ".claude-control"
        self.commands_dir = self.base_dir / "commands"
        self.responses_dir = self.base_dir / "responses"
        
        # Ensure directories exist
        self.commands_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
    
    def process_commands(self, timeout: float = 0.1):
        """Process any pending command files with file locking"""
        for cmd_file in self.commands_dir.glob("*.json"):
            try:
                # Try to acquire exclusive lock
                with open(cmd_file, 'r') as f:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except IOError:
                        # Another process has the lock, skip this file
                        continue
                    
                    # Read command
                    cmd_data = json.loads(f.read())
                
                # Process it (file is now closed and unlocked)
                response = self._process_command(cmd_data)
                
                # Write response
                resp_file = self.responses_dir / f"resp_{cmd_file.stem}.json"
                resp_file.write_text(json.dumps(response, indent=2))
                
                # Clean up command file
                cmd_file.unlink()
                
            except Exception as e:
                logger.error(f"Error processing command {cmd_file}: {e}")
    
    def _process_command(self, cmd: dict) -> dict:
        """Process a single command"""
        cmd_type = cmd.get("command")
        
        try:
            if cmd_type == "spawn":
                session = control(**cmd.get("parameters", {}))
                return {
                    "status": "success",
                    "session_id": session.session_id,
                    "pid": session.process.pid,
                }
                
            elif cmd_type == "send":
                session = get_session(cmd["session_id"])
                if not session:
                    raise SessionError(f"Session not found: {cmd['session_id']}")
                session.send(cmd["text"])
                return {"status": "success"}
                
            elif cmd_type == "expect":
                session = get_session(cmd["session_id"])
                if not session:
                    raise SessionError(f"Session not found: {cmd['session_id']}")
                index = session.expect(cmd["patterns"], cmd.get("timeout"))
                return {
                    "status": "success",
                    "index": index,
                    "before": session.process.before,
                    "after": session.process.after,
                }
                
            elif cmd_type == "close":
                session = get_session(cmd["session_id"])
                if session:
                    session.close()
                return {"status": "success"}
                
            elif cmd_type == "list":
                return {
                    "status": "success",
                    "sessions": list_sessions(),
                }
                
            else:
                raise ValueError(f"Unknown command: {cmd_type}")
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "type": type(e).__name__,
            }
