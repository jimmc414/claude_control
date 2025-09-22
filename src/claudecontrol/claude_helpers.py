"""
Helper functions specifically designed for Claude Code usage
Makes common tasks extremely simple
"""

import json
import time
import shlex
import pexpect
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple

from .core import control, run, get_session, list_sessions, Session
from .patterns import wait_for_prompt, extract_json, COMMON_PROMPTS
from .exceptions import SessionError, TimeoutError, ProcessError


def test_command(
    command: str,
    expected_output: Union[str, List[str]],
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Test if a command produces expected output

    Args:
        command: Command to run
        expected_output: String or list of strings to look for
        timeout: Maximum wait time
        cwd: Working directory

    Returns:
        Tuple of (success, error message). ``error`` will be ``None`` when the
        command executed and all expected outputs were found.

    Example:
        success, error = test_command("npm test", ["✓", "passing"])
        if success:
            print("Tests passed!")
        else:
            print(f"Tests failed: {error}")
    """
    try:
        output = run(command, timeout=timeout, cwd=cwd)

        if isinstance(expected_output, str):
            expected_output = [expected_output]

        for expected in expected_output:
            if expected not in output:
                return False, f"Expected output '{expected}' not found"

        return True, None

    except Exception as e:
        return False, str(e)


# Prevent pytest from collecting this helper as a test
test_command.__test__ = False


def interactive_command(
    command: str,
    interactions: List[Dict[str, str]],
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> str:
    """
    Run a command with multiple interactions
    
    Args:
        command: Command to run
        interactions: List of {"expect": pattern, "send": response} dicts
        timeout: Maximum wait time for each interaction
        cwd: Working directory
        
    Returns:
        Full output from the session
        
    Example:
        output = interactive_command(
            "python app.py",
            [
                {"expect": "Username:", "send": "admin"},
                {"expect": "Password:", "send": "secret"},
                {"expect": "> ", "send": "status"},
                {"expect": "> ", "send": "exit"},
            ]
        )
    """
    with Session(command, timeout=timeout, cwd=cwd, persist=False) as session:
        for interaction in interactions:
            if "expect" in interaction:
                session.expect(interaction["expect"], timeout=timeout)
                
            if "send" in interaction:
                if interaction.get("sendline", True):
                    session.sendline(interaction["send"])
                else:
                    session.send(interaction["send"])
                    
            # Optional delay between interactions
            if "delay" in interaction:
                time.sleep(interaction["delay"])
                
        return session.get_full_output()


def run_script(
    interpreter: str,
    script: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a script with an interpreter and capture results
    
    Args:
        interpreter: Interpreter command (python, node, bash, etc.)
        script: Script content to run
        timeout: Maximum execution time
        cwd: Working directory
        
    Returns:
        Dict with output, exitstatus, and success flag
        
    Example:
        result = run_script("python", "print('Hello')")
        if result["success"]:
            print(result["output"])
    """
    import tempfile
    script_path = None
    
    try:
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".tmp") as f:
            f.write(script)
            script_path = f.name
            
        # Run the script
        start_time = time.time()
        timed_out = False

        with Session(
            f"{interpreter} {script_path}",
            timeout=timeout,
            cwd=cwd,
            persist=False,
        ) as session:
            try:
                elapsed = time.time() - start_time
                remaining = timeout - elapsed if timeout is not None else None

                if remaining is not None:
                    if remaining <= 0:
                        raise TimeoutError("Script execution timed out")
                    session.expect(pexpect.EOF, timeout=remaining)
                else:
                    session.expect(pexpect.EOF)

                if session.exitstatus() is None and getattr(session, "process", None):
                    try:
                        session.process.wait()
                    except (pexpect.exceptions.ExceptionPexpect, OSError):
                        pass

            except TimeoutError:
                timed_out = True
                session.close(force=True)

            if not timed_out and session.is_alive():
                session.close(force=True)

        output = session.get_full_output()
        exitstatus = session.exitstatus()

        if timed_out or exitstatus is None:
            exitstatus = -1

        return {
            "output": output,
            "exitstatus": exitstatus,
            "success": exitstatus == 0,
            "duration": time.time() - start_time,
        }
        
    finally:
        # Ensure cleanup even if exception occurs
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except Exception:
                pass  # Best effort cleanup


def ssh_command(
    host: str,
    command: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30,
) -> str:
    """
    Run a command over SSH
    
    Args:
        host: SSH host
        command: Command to run on remote host
        username: SSH username
        password: SSH password (use keys when possible!)
        port: SSH port
        timeout: Connection timeout
        
    Returns:
        Command output
        
    Example:
        output = ssh_command("server.example.com", "uptime", username="admin")
    """
    ssh_cmd = f"ssh -p {port}"
    
    if username:
        ssh_cmd += f" {username}@{host}"
    else:
        ssh_cmd += f" {host}"
        
    ssh_cmd += f" {shlex.quote(command)}"
    
    with Session(ssh_cmd, timeout=timeout, persist=False) as session:
        # Handle SSH prompts
        patterns = [
            r"Are you sure you want to continue connecting",
            r"[Pp]assword:",
            r"[Pp]assphrase:",
        ]
        patterns.extend(COMMON_PROMPTS["bash"])
        patterns.extend([pexpect.EOF])
        
        while True:
            index = session.expect(patterns, timeout=timeout)
            
            if index == 0:  # SSH fingerprint
                session.sendline("yes")
            elif index in [1, 2]:  # Password/passphrase
                if password:
                    session.sendline(password)
                else:
                    raise SessionError("Password required but not provided")
            else:
                # Either got a prompt or EOF
                break
                
        return session.get_full_output()


def watch_process(
    command: str,
    watch_for: Union[str, List[str]],
    callback: Optional[callable] = None,
    timeout: int = 300,
    cwd: Optional[str] = None,
) -> List[str]:
    """
    Watch a process for specific output patterns
    
    Args:
        command: Command to run
        watch_for: Pattern(s) to watch for
        callback: Function to call when pattern is found
        timeout: Maximum watch time
        cwd: Working directory
        
    Returns:
        List of matched patterns
        
    Example:
        def on_error(session, pattern):
            print(f"Error detected: {pattern}")
            print(session.get_recent_output(20))
            
        matches = watch_process(
            "npm run dev",
            ["Error:", "Warning:"],
            callback=on_error
        )
    """
    if isinstance(watch_for, str):
        watch_for = [watch_for]
        
    matches = []
    
    with Session(command, timeout=timeout, cwd=cwd, persist=False) as session:
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                index = session.expect(watch_for, timeout=5)
                matched = watch_for[index]
                matches.append(matched)

                if callback:
                    callback(session, matched)

            except ProcessError:
                break
            except TimeoutError:
                # No match in this interval, keep watching
                if not session.is_alive():
                    break
                    
    return matches


def parallel_commands(
    commands: List[str],
    timeout: int = 30,
    max_concurrent: int = 10,
) -> Dict[str, Dict[str, Any]]:
    """
    Run multiple commands in parallel
    
    Args:
        commands: List of commands to run
        timeout: Timeout for each command
        max_concurrent: Maximum concurrent sessions
        
    Returns:
        Dict mapping command to result
        
    Example:
        results = parallel_commands([
            "npm test",
            "python -m pytest",
            "cargo test",
        ])
        
        for cmd, result in results.items():
            if result["success"]:
                print(f"✓ {cmd}")
            else:
                print(f"✗ {cmd}: {result['error']}")
    """
    import concurrent.futures
    
    def run_single(cmd):
        try:
            output = run(cmd, timeout=timeout)
            return {
                "success": True,
                "output": output,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
            }
    
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_cmd = {executor.submit(run_single, cmd): cmd for cmd in commands}
        
        for future in concurrent.futures.as_completed(future_to_cmd):
            cmd = future_to_cmd[future]
            results[cmd] = future.result()
            
    return results


class CommandChain:
    """
    Chain multiple commands together with conditional execution
    
    Example:
        chain = CommandChain()
        chain.add("git pull")
        chain.add("npm install", condition=lambda r: "package.json" in r[-1])
        chain.add("npm test")
        chain.add("npm run build", on_success=True)
        
        results = chain.run()
    """
    
    def __init__(self, cwd: Optional[str] = None, timeout: int = 30):
        self.cwd = cwd
        self.timeout = timeout
        self.commands = []
        
    def add(
        self,
        command: str,
        expect: Optional[str] = None,
        send: Optional[str] = None,
        condition: Optional[callable] = None,
        on_success: bool = False,
        on_failure: bool = False,
    ):
        """Add a command to the chain"""
        self.commands.append({
            "command": command,
            "expect": expect,
            "send": send,
            "condition": condition,
            "on_success": on_success,
            "on_failure": on_failure,
        })
        return self
        
    def run(self) -> List[Dict[str, Any]]:
        """Execute the command chain"""
        results = []
        last_success = True
        had_failure = False
        
        for cmd_info in self.commands:
            # Check conditions
            if cmd_info["condition"] and not cmd_info["condition"](results):
                continue
                
            if cmd_info["on_success"] and (not last_success or had_failure):
                continue

            if cmd_info["on_failure"] and last_success:
                continue
                
            # Run command
            try:
                output = run(
                    cmd_info["command"],
                    expect=cmd_info["expect"],
                    send=cmd_info["send"],
                    timeout=self.timeout,
                    cwd=self.cwd,
                )
                
                result = {
                    "command": cmd_info["command"],
                    "output": output,
                    "success": True,
                    "error": None,
                }
                last_success = True
                
            except Exception as e:
                result = {
                    "command": cmd_info["command"],
                    "output": None,
                    "success": False,
                    "error": str(e),
                }
                last_success = False
                had_failure = True

            results.append(result)

            if not result["success"]:
                had_failure = True

        return results


# Investigation helpers
def investigation_summary(
    program: str,
    timeout: int = 10,
    safe_mode: bool = True,
    interactive: bool = False,
) -> Dict[str, Any]:
    """
    Generate a summarized view of an unknown program

    Args:
        program: Program to investigate
        timeout: Operation timeout
        safe_mode: Enable safety checks
        interactive: Use interactive learning mode

    Returns:
        Investigation results dict
    """
    from .investigate import ProgramInvestigator

    investigator = ProgramInvestigator(
        program=program,
        timeout=timeout,
        safe_mode=safe_mode,
    )

    if interactive:
        report = investigator.learn_from_interaction()
    else:
        report = investigator.investigate()

    return {
        "program": report.program,
        "prompts": report.prompts,
        "commands": list(report.commands.keys()),
        "help_commands": report.help_commands,
        "exit_commands": report.exit_commands,
        "data_formats": report.data_formats,
        "states": len(report.states),
        "summary": report.summary(),
    }


def probe_interface(
    program: str,
    commands_to_try: Optional[List[str]] = None,
    timeout: int = 5,
) -> Dict[str, Any]:
    """
    Quick probe of program interface
    
    Args:
        program: Program to probe
        commands_to_try: Commands to test (uses defaults if None)
        timeout: Operation timeout
        
    Returns:
        Probe results
    """
    from .investigate import ProgramInvestigator
    
    if commands_to_try is None:
        commands_to_try = ["help", "?", "--help", "commands", "quit"]
    
    results = {
        "responsive": False,
        "interactive": False,
        "commands_found": [],
        "prompt": None,
    }
    
    try:
        # Quick probe
        probe_result = ProgramInvestigator.quick_probe(program, timeout)
        results["interactive"] = probe_result["interactive"]
        results["prompt"] = probe_result["prompt"]
        results["responsive"] = probe_result["alive"]
        
        if results["interactive"]:
            # Try commands
            with Session(program, timeout=timeout, persist=False) as session:
                for cmd in commands_to_try:
                    try:
                        session.sendline(cmd)
                        output = session.read_nonblocking(timeout=1)
                        if output and len(output) > 10:
                            results["commands_found"].append(cmd)
                    except:
                        continue
                        
    except Exception as e:
        results["error"] = str(e)
    
    return results


def map_program_states(
    program: str,
    starting_commands: Optional[List[str]] = None,
    max_depth: int = 3,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Map program states and transitions
    
    Args:
        program: Program to map
        starting_commands: Initial commands to explore
        max_depth: Maximum exploration depth
        timeout: Operation timeout
        
    Returns:
        State map dict
    """
    from .investigate import ProgramInvestigator
    from .patterns import detect_state_transition
    
    if starting_commands is None:
        starting_commands = ["help", "status", "config", "settings"]
    
    investigator = ProgramInvestigator(
        program=program,
        timeout=timeout,
        max_depth=max_depth,
        safe_mode=True,
    )
    
    states = {}
    transitions = []
    
    try:
        investigator._start_session()
        investigator._detect_initial_state()
        
        # Explore from starting commands
        for cmd in starting_commands:
            try:
                investigator._send_command(cmd)
                output = investigator._wait_for_output()
                
                # Check for state transition
                new_state = detect_state_transition(output)
                if new_state:
                    states[new_state] = {
                        "entered_from": cmd,
                        "prompt": investigator._detect_prompt(output),
                    }
                    transitions.append({
                        "from": "initial",
                        "to": new_state,
                        "command": cmd,
                    })
                    
            except:
                continue
                
    finally:
        if investigator.session:
            investigator.session.close()
    
    return {
        "states": states,
        "transitions": transitions,
        "initial_prompt": investigator.report.entry_state.prompt if investigator.report.entry_state else None,
    }


def fuzz_program(
    program: str,
    input_patterns: Optional[List[str]] = None,
    max_inputs: int = 50,
    timeout: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fuzz test a program with various inputs
    
    Args:
        program: Program to fuzz
        input_patterns: Input patterns to test
        max_inputs: Maximum number of inputs
        timeout: Operation timeout
        
    Returns:
        List of interesting findings
    """
    import random
    import string
    from .patterns import is_error_output, classify_output
    
    if input_patterns is None:
        # Default fuzzing patterns
        input_patterns = [
            "",  # Empty input
            " " * 100,  # Spaces
            "A" * 1000,  # Long input
            "\\x00",  # Null byte
            "../../../etc/passwd",  # Path traversal
            "; ls",  # Command injection
            "' OR '1'='1",  # SQL injection
            "<script>alert(1)</script>",  # XSS
            "%s" * 10,  # Format string
            "-" * 50,  # Special chars
            "\n" * 10,  # Newlines
        ]
        
        # Add random inputs
        for _ in range(20):
            input_patterns.append(
                ''.join(random.choices(string.printable, k=random.randint(1, 50)))
            )
    
    findings = []
    
    with Session(program, timeout=timeout, persist=False) as session:
        # Wait for initial prompt
        time.sleep(1)
        
        for i, test_input in enumerate(input_patterns[:max_inputs]):
            try:
                session.sendline(test_input)
                output = session.read_nonblocking(timeout=1)
                
                # Classify output
                classification = classify_output(output)
                
                # Record interesting findings
                if classification["is_error"]:
                    findings.append({
                        "input": test_input,
                        "type": "error",
                        "output": output[:500],
                        "classification": classification,
                    })
                elif not output:
                    findings.append({
                        "input": test_input,
                        "type": "no_response",
                        "output": "",
                    })
                elif len(output) > 1000:
                    findings.append({
                        "input": test_input,
                        "type": "large_output",
                        "output_size": len(output),
                        "classification": classification,
                    })
                    
            except Exception as e:
                findings.append({
                    "input": test_input,
                    "type": "exception",
                    "error": str(e),
                })
                
                # Restart session if it crashed
                if not session.is_alive():
                    break
    
    return findings


# Quick status check for Claude Code
def status() -> Dict[str, Any]:
    """
    Get current status of all sessions and system
    
    Returns:
        Dict with sessions, stats, and health info
    """
    sessions = list_sessions(active_only=False)
    active = [s for s in sessions if s["is_alive"]]
    
    # Check disk usage for logs
    log_dir = Path.home() / ".claude-control"
    if log_dir.exists():
        total_size = sum(f.stat().st_size for f in log_dir.rglob("*") if f.is_file())
        log_size_mb = total_size / (1024 * 1024)
    else:
        log_size_mb = 0
        
    return {
        "total_sessions": len(sessions),
        "active_sessions": len(active),
        "sessions": sessions,
        "log_size_mb": round(log_size_mb, 2),
        "config_path": str(Path.home() / ".claude-control" / "config.json"),
    }