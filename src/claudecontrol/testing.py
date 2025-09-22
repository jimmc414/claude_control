"""
Black box testing framework for ClaudeControl
Systematic testing of CLI programs without source code
"""

import time
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

from .core import Session, control
from .patterns import classify_output, is_error_output
from .claude_helpers import fuzz_program
from .investigate import ProgramInvestigator


class BlackBoxTester:
    """
    Black box testing framework for CLI programs
    
    Provides systematic testing of unknown programs including:
    - Startup behavior
    - Help system discovery
    - Invalid input handling
    - Exit behavior
    - Resource usage
    - Concurrent sessions
    - Fuzz testing
    """
    
    def __init__(self, program: str, timeout: int = 10):
        """
        Initialize black box tester

        Args:
            program: Program to test
            timeout: Default timeout for operations
        """
        if not program or not str(program).strip():
            raise ValueError("program must be a non-empty string")

        self.program = program
        self.timeout = timeout
        self.test_results = []
        
    def test_startup(self) -> dict:
        """Test program startup behavior"""
        result = {
            "test": "startup",
            "passed": False,
            "details": {}
        }
        
        try:
            session = control(self.program, timeout=self.timeout, reuse=False)
            time.sleep(1)
            
            # Check if process started
            result["details"]["started"] = session.is_alive()
            
            # Get initial output
            initial_output = session.get_recent_output(50)
            result["details"]["has_output"] = len(initial_output) > 0
            result["details"]["output_length"] = len(initial_output)
            
            # Classify output
            classification = classify_output(initial_output)
            result["details"]["classification"] = classification
            
            # Check for errors
            result["details"]["has_errors"] = classification["is_error"]
            
            # Check for prompt
            result["details"]["has_prompt"] = classification["has_prompt"]
            
            result["passed"] = session.is_alive() and not classification["is_error"]
            
            session.close()
            
        except Exception as e:
            result["error"] = str(e)
            result["passed"] = False
            
        self.test_results.append(result)
        return result
    
    def test_help_system(self) -> dict:
        """Test help command variations"""
        help_commands = ["help", "--help", "-h", "?", "\\h", "man"]
        result = {
            "test": "help_system",
            "passed": False,
            "working_commands": [],
            "details": {}
        }
        
        for help_cmd in help_commands:
            try:
                with Session(self.program, timeout=self.timeout, persist=False) as session:
                    time.sleep(0.5)
                    session.sendline(help_cmd)
                    output = session.read_nonblocking(timeout=2)
                    
                    # Check if this looks like help
                    if output and len(output) > 50:
                        help_indicators = ["usage", "help", "command", "option", "syntax"]
                        if any(ind in output.lower() for ind in help_indicators):
                            result["working_commands"].append(help_cmd)
                            result["details"][help_cmd] = "Found help content"
                        else:
                            result["details"][help_cmd] = "No help indicators"
                    else:
                        result["details"][help_cmd] = "No/minimal output"
                        
            except Exception as e:
                result["details"][help_cmd] = f"Error: {e}"
        
        result["passed"] = len(result["working_commands"]) > 0
        
        self.test_results.append(result)
        return result
    
    def test_invalid_input(self) -> dict:
        """Test program's handling of invalid input"""
        invalid_inputs = [
            "this_command_does_not_exist",
            "!!!###$$$",
            "a" * 1000,  # Very long input
            "",  # Empty input
            "\x00\x01\x02",  # Control characters
        ]
        
        result = {
            "test": "invalid_input",
            "passed": True,
            "crashes": [],
            "good_errors": [],
            "details": {}
        }
        
        for test_input in invalid_inputs:
            display_input = repr(test_input[:50]) if len(test_input) > 50 else repr(test_input)
            
            try:
                with Session(self.program, timeout=self.timeout, persist=False) as session:
                    time.sleep(0.5)
                    session.sendline(test_input)
                    output = session.read_nonblocking(timeout=1)
                    
                    # Check if still alive after bad input
                    still_alive = session.is_alive()
                    
                    if not still_alive:
                        result["crashes"].append(display_input)
                        result["passed"] = False
                        result["details"][display_input] = "CRASHED"
                    elif is_error_output(output):
                        result["good_errors"].append(display_input)
                        result["details"][display_input] = "Proper error handling"
                    else:
                        result["details"][display_input] = "Accepted/ignored"
                        
            except Exception as e:
                result["details"][display_input] = f"Exception: {e}"
                result["passed"] = False
        
        self.test_results.append(result)
        return result
    
    def test_exit_behavior(self) -> dict:
        """Test various exit commands"""
        exit_commands = ["exit", "quit", "q", "bye", "\\q", ".exit", ":q"]
        
        result = {
            "test": "exit_behavior",
            "passed": False,
            "working_exits": [],
            "details": {}
        }
        
        for exit_cmd in exit_commands:
            try:
                session = control(self.program, timeout=self.timeout, reuse=False)
                time.sleep(0.5)
                
                # Send exit command
                session.sendline(exit_cmd)
                time.sleep(0.5)
                
                # Check if process exited
                if not session.is_alive():
                    result["working_exits"].append(exit_cmd)
                    result["details"][exit_cmd] = "Clean exit"
                else:
                    result["details"][exit_cmd] = "Still running"
                    
                session.close(force=True)
                    
            except Exception as e:
                result["details"][exit_cmd] = f"Error: {e}"
        
        result["passed"] = len(result["working_exits"]) > 0
        
        self.test_results.append(result)
        return result
    
    def test_resource_usage(self) -> dict:
        """Test resource usage and limits"""
        result = {
            "test": "resource_usage",
            "passed": True,
            "details": {}
        }
        
        session = None
        try:
            import psutil

            # Start process
            session = control(self.program, timeout=self.timeout, reuse=False)
            time.sleep(1)

            if session.process and session.process.pid:
                proc = psutil.Process(session.process.pid)

                # Check initial resource usage
                result["details"]["cpu_percent"] = proc.cpu_percent(interval=1)
                result["details"]["memory_mb"] = proc.memory_info().rss / 1024 / 1024
                result["details"]["num_threads"] = proc.num_threads()

                # Send some activity
                session.sendline("help")
                time.sleep(1)

                # Check again
                result["details"]["cpu_after_activity"] = proc.cpu_percent(interval=1)

                # Check for excessive resource usage
                if result["details"]["memory_mb"] > 500:
                    result["passed"] = False
                    result["details"]["issue"] = "High memory usage"
                elif result["details"]["cpu_percent"] > 80:
                    result["passed"] = False
                    result["details"]["issue"] = "High CPU usage"

        except ImportError:
            result["details"]["note"] = "psutil not available"
        except Exception as e:
            result["error"] = str(e)
            result["passed"] = False
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

        self.test_results.append(result)
        return result
    
    def test_concurrent_sessions(self) -> dict:
        """Test multiple concurrent sessions"""
        result = {
            "test": "concurrent_sessions",
            "passed": True,
            "details": {}
        }
        
        sessions = []
        
        try:
            # Start multiple sessions
            for i in range(3):
                session = control(
                    self.program, 
                    timeout=self.timeout,
                    session_id=f"concurrent_{i}",
                    reuse=False
                )
                sessions.append(session)
                result["details"][f"session_{i}"] = "started"
            
            time.sleep(1)
            
            # Check all are alive
            for i, session in enumerate(sessions):
                if not session.is_alive():
                    result["passed"] = False
                    result["details"][f"session_{i}_alive"] = False
                else:
                    result["details"][f"session_{i}_alive"] = True
                    
                    # Try to use each session
                    try:
                        session.sendline("echo test")
                        output = session.read_nonblocking(timeout=1)
                        result["details"][f"session_{i}_responsive"] = len(output) > 0
                    except:
                        result["details"][f"session_{i}_responsive"] = False
                        
        except Exception as e:
            result["error"] = str(e)
            result["passed"] = False
            
        finally:
            # Clean up
            for session in sessions:
                try:
                    session.close()
                except:
                    pass
                    
        self.test_results.append(result)
        return result
    
    def run_fuzz_test(self, max_inputs: int = 30) -> dict:
        """Run fuzzing test"""
        result = {
            "test": "fuzzing",
            "passed": True,
            "details": {}
        }
        
        findings = fuzz_program(
            self.program,
            max_inputs=max_inputs,
            timeout=self.timeout,
        )
        
        # Analyze findings
        crashes = [f for f in findings if f["type"] == "exception"]
        errors = [f for f in findings if f["type"] == "error"]
        
        result["details"]["total_findings"] = len(findings)
        result["details"]["crashes"] = len(crashes)
        result["details"]["errors"] = len(errors)
        
        if crashes:
            result["passed"] = False
            result["details"]["crash_inputs"] = [c["input"][:50] for c in crashes[:3]]
            
        self.test_results.append(result)
        return result
    
    def run_all_tests(self) -> List[dict]:
        """Run all tests"""
        self.test_startup()
        self.test_help_system()
        self.test_invalid_input()
        self.test_exit_behavior()
        self.test_resource_usage()
        self.test_concurrent_sessions()
        self.run_fuzz_test()
        
        return self.test_results
    
    def generate_report(self) -> str:
        """Generate test report"""
        passed = sum(1 for r in self.test_results if r["passed"])
        total = len(self.test_results)
        
        report = [
            f"\nBlack Box Test Report for: {self.program}",
            "=" * 50,
            f"Tests Passed: {passed}/{total}",
            "",
            "Test Results:",
        ]
        
        for result in self.test_results:
            status = "PASS" if result["passed"] else "FAIL"
            report.append(f"  [{status}] {result['test']}")
            
            if not result["passed"]:
                if "error" in result:
                    report.append(f"        Error: {result['error']}")
                if "crashes" in result.get("details", {}):
                    report.append(f"        Crashes: {result['details']['crashes']}")
                    
        return "\n".join(report)
    
    def save_report(self, path: Optional[Path] = None) -> Path:
        """Save test report to file"""
        if path is None:
            reports_dir = Path.home() / ".claude-control" / "test-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = reports_dir / f"{self.program}_{timestamp}.json"
        
        report_data = {
            "program": self.program,
            "timestamp": time.time(),
            "test_results": self.test_results,
            "summary": {
                "total_tests": len(self.test_results),
                "passed": sum(1 for r in self.test_results if r["passed"]),
                "failed": sum(1 for r in self.test_results if not r["passed"]),
            }
        }
        
        path.write_text(json.dumps(report_data, indent=2))
        return path


def black_box_test(
    program: str,
    timeout: int = 10,
    save_report: bool = True
) -> Dict[str, Any]:
    """
    High-level function to run black box tests on a program
    
    Args:
        program: Program to test
        timeout: Operation timeout
        save_report: Whether to save report to file
        
    Returns:
        Test results dictionary
    """
    if not program or not str(program).strip():
        raise ValueError("program must be a non-empty string")

    tester = BlackBoxTester(program, timeout=timeout)
    tester.run_all_tests()
    
    if save_report:
        report_path = tester.save_report()
    
    return {
        "program": program,
        "results": tester.test_results,
        "report": tester.generate_report(),
        "report_path": str(report_path) if save_report else None,
    }