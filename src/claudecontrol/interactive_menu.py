"""
Interactive menu system for ClaudeControl
Provides guided walkthrough of all features
"""

import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from .core import control, list_sessions, get_session, cleanup_sessions
from .claude_helpers import (
    test_command,
    investigation_summary,
    probe_interface,
    fuzz_program,
    status,
)
from .investigate import ProgramInvestigator


class InteractiveMenu:
    """Interactive menu system for ClaudeControl"""
    
    def __init__(self):
        self.menu_options = {
            "1": ("Quick Start - Run a Simple Command", self.quick_start),
            "2": ("Investigate Unknown Program", self.investigate_menu),
            "3": ("Manage Sessions", self.session_menu),
            "4": ("Test Commands", self.test_menu),
            "5": ("Black Box Testing", self.blackbox_menu),
            "6": ("Interactive Learning", self.learning_menu),
            "7": ("System Status", self.status_menu),
            "8": ("Examples & Tutorials", self.examples_menu),
            "9": ("Help & Documentation", self.help_menu),
            "0": ("Exit", self.exit_menu),
        }
        
    def run(self):
        """Run the interactive menu"""
        self.show_welcome()
        
        while True:
            self.show_main_menu()
            choice = self.get_input("\nSelect an option (0-9): ")
            
            if choice in self.menu_options:
                _, handler = self.menu_options[choice]
                if handler() == "exit":
                    break
            else:
                print("Invalid option. Please try again.")
                
    def show_welcome(self):
        """Show welcome message"""
        print("\n" + "=" * 60)
        print("     Welcome to ClaudeControl Interactive Menu")
        print("=" * 60)
        print("\nClaudeControl gives you elegant control over CLI programs.")
        print("Perfect for investigating unknown tools and automation.")
        print("\nLet's explore what you can do!")
        
    def show_main_menu(self):
        """Display main menu"""
        print("\n" + "-" * 40)
        print("MAIN MENU")
        print("-" * 40)
        
        for key in sorted(self.menu_options.keys()):
            label, _ = self.menu_options[key]
            print(f"  {key}. {label}")
            
    def get_input(self, prompt: str) -> str:
        """Get user input with prompt"""
        try:
            return input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting...")
            sys.exit(0)
            
    def get_yes_no(self, prompt: str, default: bool = True) -> bool:
        """Get yes/no answer from user"""
        default_str = "Y/n" if default else "y/N"
        response = self.get_input(f"{prompt} [{default_str}]: ").lower()
        
        if not response:
            return default
        return response in ['y', 'yes']
        
    def quick_start(self):
        """Quick start walkthrough"""
        print("\n" + "=" * 50)
        print("QUICK START - Run a Simple Command")
        print("=" * 50)
        
        print("\nThis will help you run a command and capture its output.")
        print("\nExamples of commands you can run:")
        print("  - echo 'Hello World'")
        print("  - ls -la")
        print("  - python --version")
        print("  - npm list")
        
        command = self.get_input("\nEnter command to run (or 'back' to return): ")
        
        if command.lower() == 'back':
            return
            
        print(f"\nRunning: {command}")
        print("-" * 30)
        
        try:
            from .core import run
            output = run(command, timeout=10)
            print("Output:")
            print(output)
            
            if self.get_yes_no("\nWould you like to save this output to a file?", False):
                filename = self.get_input("Enter filename (default: output.txt): ") or "output.txt"
                Path(filename).write_text(output)
                print(f"Output saved to {filename}")
                
        except Exception as e:
            print(f"Error: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def investigate_menu(self):
        """Investigation walkthrough"""
        print("\n" + "=" * 50)
        print("INVESTIGATE UNKNOWN PROGRAM")
        print("=" * 50)
        
        print("\nProgram investigation helps you understand unknown CLI tools.")
        print("ClaudeControl will automatically:")
        print("  ✓ Detect prompts and commands")
        print("  ✓ Find help information")
        print("  ✓ Map program states")
        print("  ✓ Test exit commands")
        print("  ✓ Identify data formats")
        
        print("\nInvestigation options:")
        print("  1. Full automatic investigation")
        print("  2. Quick probe (fast check)")
        print("  3. Interactive learning (you demonstrate)")
        print("  4. Fuzz testing (find edge cases)")
        print("  5. Back to main menu")
        
        choice = self.get_input("\nSelect option (1-5): ")
        
        if choice == "1":
            self.run_investigation()
        elif choice == "2":
            self.run_probe()
        elif choice == "3":
            self.run_learning()
        elif choice == "4":
            self.run_fuzzing()
            
    def run_investigation(self):
        """Run full investigation"""
        print("\n" + "-" * 40)
        print("Full Investigation")
        print("-" * 40)
        
        program = self.get_input("\nEnter program name to investigate: ")
        
        if not program:
            return
            
        safe_mode = self.get_yes_no("Use safe mode? (blocks dangerous commands)", True)
        
        print(f"\nInvestigating {program}...")
        print("This may take a moment...\n")
        
        try:
            result = investigation_summary(
                program=program,
                timeout=10,
                safe_mode=safe_mode,
            )
            
            print("\n" + "=" * 40)
            print("Investigation Results:")
            print("=" * 40)
            print(f"Program: {result['program']}")
            print(f"Commands found: {len(result['commands'])}")
            print(f"Prompts detected: {result['prompts']}")
            print(f"Help commands: {result['help_commands']}")
            print(f"Exit commands: {result['exit_commands']}")
            print(f"Data formats: {result['data_formats']}")
            
            if result['commands']:
                print("\nDiscovered commands:")
                for cmd in result['commands'][:10]:
                    print(f"  • {cmd}")
                    
            if self.get_yes_no("\nView full summary?", False):
                print("\n" + result['summary'])
                
        except Exception as e:
            print(f"Investigation failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def run_probe(self):
        """Run quick probe"""
        print("\n" + "-" * 40)
        print("Quick Probe")
        print("-" * 40)
        
        program = self.get_input("\nEnter program name to probe: ")
        
        if not program:
            return
            
        print(f"\nProbing {program}...")
        
        try:
            result = probe_interface(program, timeout=5)
            
            print("\nProbe Results:")
            print(f"  Interactive: {'Yes' if result['interactive'] else 'No'}")
            print(f"  Responsive: {'Yes' if result['responsive'] else 'No'}")
            print(f"  Prompt: {result.get('prompt', 'None detected')}")
            
            if result.get('commands_found'):
                print(f"  Working commands: {', '.join(result['commands_found'])}")
                
        except Exception as e:
            print(f"Probe failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def run_learning(self):
        """Run interactive learning"""
        print("\n" + "-" * 40)
        print("Interactive Learning")
        print("-" * 40)
        
        print("\nIn learning mode, YOU control the program while ClaudeControl observes.")
        print("This is perfect for complex programs that need human demonstration.")
        
        program = self.get_input("\nEnter program to learn: ")
        
        if not program:
            return
            
        print(f"\nStarting interactive session with {program}")
        print("You will take control. Demonstrate the program's features.")
        print("Press Ctrl+] when done to return control.\n")
        
        if not self.get_yes_no("Ready to start?"):
            return
            
        try:
            investigator = ProgramInvestigator(program, timeout=10)
            report = investigator.learn_from_interaction()
            
            print("\n" + "=" * 40)
            print("Learning Complete!")
            print(f"Discovered {len(report.commands)} commands")
            print(f"Detected {len(report.prompts)} prompt patterns")
            
            if self.get_yes_no("Save learning results?", True):
                path = report.save()
                print(f"Saved to: {path}")
                
        except Exception as e:
            print(f"Learning failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def run_fuzzing(self):
        """Run fuzz testing"""
        print("\n" + "-" * 40)
        print("Fuzz Testing")
        print("-" * 40)
        
        print("\nFuzz testing sends random/edge-case inputs to find bugs.")
        print("WARNING: This may crash or stress the target program!")
        
        program = self.get_input("\nEnter program to fuzz: ")
        
        if not program:
            return
            
        max_inputs = int(self.get_input("Number of test inputs (default 30): ") or "30")
        
        if not self.get_yes_no(f"Start fuzzing {program} with {max_inputs} inputs?"):
            return
            
        print(f"\nFuzzing {program}...")
        
        try:
            findings = fuzz_program(program, max_inputs=max_inputs, timeout=5)
            
            print(f"\nFound {len(findings)} interesting results")
            
            # Group by type
            by_type = {}
            for finding in findings:
                ftype = finding["type"]
                by_type.setdefault(ftype, []).append(finding)
                
            for ftype, items in by_type.items():
                print(f"\n{ftype.upper()} ({len(items)} findings):")
                for item in items[:3]:
                    if ftype == "error":
                        print(f"  Input: {repr(item['input'][:30])}")
                        
        except Exception as e:
            print(f"Fuzzing failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def session_menu(self):
        """Session management menu"""
        print("\n" + "=" * 50)
        print("SESSION MANAGEMENT")
        print("=" * 50)
        
        sessions = list_sessions(active_only=False)
        active = [s for s in sessions if s["is_alive"]]
        
        print(f"\nActive sessions: {len(active)}")
        print(f"Total sessions: {len(sessions)}")
        
        if active:
            print("\nActive Sessions:")
            for s in active:
                print(f"  • {s['session_id']}: {s['command']}")
                
        print("\nOptions:")
        print("  1. List all sessions")
        print("  2. Attach to session")
        print("  3. Close a session")
        print("  4. Clean up dead sessions")
        print("  5. Back to main menu")
        
        choice = self.get_input("\nSelect option (1-5): ")
        
        if choice == "1":
            self.list_all_sessions()
        elif choice == "2":
            self.attach_to_session()
        elif choice == "3":
            self.close_session()
        elif choice == "4":
            self.cleanup_sessions()
            
    def list_all_sessions(self):
        """List all sessions with details"""
        sessions = list_sessions(active_only=False)
        
        if not sessions:
            print("\nNo sessions found")
        else:
            print("\nAll Sessions:")
            print("-" * 60)
            for s in sessions:
                status = "ALIVE" if s["is_alive"] else "DEAD"
                print(f"ID: {s['session_id']}")
                print(f"  Command: {s['command']}")
                print(f"  Status: {status}")
                print(f"  PID: {s.get('pid', 'N/A')}")
                print(f"  Created: {s['created_at']}")
                print()
                
        self.get_input("Press Enter to continue...")
        
    def attach_to_session(self):
        """Attach to existing session"""
        sessions = list_sessions(active_only=True)
        
        if not sessions:
            print("\nNo active sessions to attach to")
            self.get_input("Press Enter to continue...")
            return
            
        print("\nActive sessions:")
        for i, s in enumerate(sessions, 1):
            print(f"  {i}. {s['session_id']}: {s['command']}")
            
        choice = self.get_input("\nSelect session number (or 'back'): ")
        
        if choice.lower() == 'back':
            return
            
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                session_id = sessions[idx]['session_id']
                session = get_session(session_id)
                
                if session:
                    print(f"\nAttaching to {session_id}")
                    print("Press Ctrl+] to detach\n")
                    session.interact()
                    print("\nDetached from session")
                    
        except (ValueError, IndexError):
            print("Invalid selection")
        except Exception as e:
            print(f"Error: {e}")
            
        self.get_input("Press Enter to continue...")
        
    def close_session(self):
        """Close a session"""
        sessions = list_sessions(active_only=True)
        
        if not sessions:
            print("\nNo active sessions to close")
            self.get_input("Press Enter to continue...")
            return
            
        print("\nActive sessions:")
        for i, s in enumerate(sessions, 1):
            print(f"  {i}. {s['session_id']}: {s['command']}")
            
        choice = self.get_input("\nSelect session to close (or 'back'): ")
        
        if choice.lower() == 'back':
            return
            
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                session_id = sessions[idx]['session_id']
                session = get_session(session_id)
                
                if session:
                    session.close()
                    print(f"Closed session {session_id}")
                    
        except (ValueError, IndexError):
            print("Invalid selection")
        except Exception as e:
            print(f"Error: {e}")
            
        self.get_input("Press Enter to continue...")
        
    def cleanup_sessions(self):
        """Clean up dead sessions"""
        print("\nCleaning up dead sessions...")
        
        cleaned = cleanup_sessions()
        print(f"Cleaned up {cleaned} sessions")
        
        self.get_input("Press Enter to continue...")
        
    def test_menu(self):
        """Test commands menu"""
        print("\n" + "=" * 50)
        print("TEST COMMANDS")
        print("=" * 50)
        
        print("\nTest if commands produce expected output.")
        print("\nExamples:")
        print("  • Test if 'npm test' contains 'passing'")
        print("  • Test if 'python --version' contains 'Python'")
        print("  • Test if 'git status' runs without error")
        
        command = self.get_input("\nEnter command to test: ")
        
        if not command:
            return
            
        expected = self.get_input("Expected output (substring to find): ")
        
        if not expected:
            print("\nRunning command without expectation check...")
            expected = ""
            
        print(f"\nTesting: {command}")
        print(f"Expecting: {expected}")
        
        try:
            if expected:
                success, error = test_command(command, expected, timeout=10)
                if success:
                    print("✓ TEST PASSED - Found expected output")
                else:
                    message = error or "Expected output not found"
                    print(f"✗ TEST FAILED - {message}")
            else:
                from .core import run
                output = run(command, timeout=10)
                print("Command executed successfully")
                print(f"Output length: {len(output)} characters")
                
                if self.get_yes_no("Show output?", True):
                    print("\nOutput:")
                    print("-" * 40)
                    print(output[:1000])  # First 1000 chars
                    if len(output) > 1000:
                        print("... (truncated)")
                        
        except Exception as e:
            print(f"Test failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def blackbox_menu(self):
        """Black box testing menu"""
        print("\n" + "=" * 50)
        print("BLACK BOX TESTING")
        print("=" * 50)
        
        print("\nBlack box testing systematically tests programs without source code.")
        print("\nTests include:")
        print("  • Startup behavior")
        print("  • Help system")
        print("  • Invalid input handling")
        print("  • Exit commands")
        print("  • Resource usage")
        print("  • Concurrent sessions")
        
        program = self.get_input("\nEnter program to test: ")
        
        if not program:
            return
            
        print(f"\nRunning black box tests on {program}...")
        print("This will take a moment...\n")
        
        from .testing import BlackBoxTester
        
        try:
            tester = BlackBoxTester(program, timeout=5)
            
            # Run tests
            print("Running tests:")
            tester.test_startup()
            tester.test_help_system()
            tester.test_invalid_input()
            tester.test_exit_behavior()
            
            # Show report
            print(tester.generate_report())
            
        except Exception as e:
            print(f"Testing failed: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def learning_menu(self):
        """Interactive learning menu"""
        print("\n" + "=" * 50)
        print("INTERACTIVE LEARNING")
        print("=" * 50)
        
        print("\nLearn how to use ClaudeControl with guided examples.")
        
        print("\nTutorials:")
        print("  1. Basic session control")
        print("  2. Pattern matching and expects")
        print("  3. Session reuse and persistence")
        print("  4. Parallel command execution")
        print("  5. Back to main menu")
        
        choice = self.get_input("\nSelect tutorial (1-5): ")
        
        if choice == "1":
            self.tutorial_basic()
        elif choice == "2":
            self.tutorial_patterns()
        elif choice == "3":
            self.tutorial_reuse()
        elif choice == "4":
            self.tutorial_parallel()
            
    def tutorial_basic(self):
        """Basic tutorial"""
        print("\n" + "-" * 40)
        print("Tutorial: Basic Session Control")
        print("-" * 40)
        
        print("""
Sessions are the core of ClaudeControl. A session represents
a controlled process that you can interact with.

Example code:
    from claudecontrol import Session
    
    # Create a session
    with Session("python") as s:
        s.expect(">>>")  # Wait for prompt
        s.sendline("2 + 2")  # Send input
        s.expect(">>>")  # Wait for next prompt
        print(s.process.before)  # Get output

Try it yourself!
""")
        
        if self.get_yes_no("Run this example?"):
            try:
                from .core import Session
                
                with Session("python", persist=False) as s:
                    s.expect(">>>")
                    s.sendline("2 + 2")
                    s.expect(">>>")
                    output = s.process.before.strip()
                    print(f"\nResult: {output}")
                    
            except Exception as e:
                print(f"Example failed: {e}")
                
        self.get_input("\nPress Enter to continue...")
        
    def tutorial_patterns(self):
        """Pattern matching tutorial"""
        print("\n" + "-" * 40)
        print("Tutorial: Pattern Matching")
        print("-" * 40)
        
        print("""
Pattern matching lets you wait for specific output.

Example code:
    from claudecontrol import Session
    
    with Session("bc") as calc:
        # Wait for any of these patterns
        calc.expect(["warranty", ">", "ready"])
        
        calc.sendline("2 + 2")
        calc.expect("\\n")  # Wait for newline
        result = calc.process.before.strip()

Patterns can be:
  • Exact strings: ">>>"
  • Regular expressions: r"\\d+"
  • Lists of patterns: ["error", "success"]
""")
        
        self.get_input("\nPress Enter to continue...")
        
    def tutorial_reuse(self):
        """Session reuse tutorial"""
        print("\n" + "-" * 40)
        print("Tutorial: Session Reuse")
        print("-" * 40)
        
        print("""
Sessions can persist across script runs for efficiency.

Example code:
    from claudecontrol import control
    
    # First call creates session
    server = control("npm run dev", reuse=True)
    
    # Later calls get the same session
    server = control("npm run dev", reuse=True)
    
    # Session persists even after script ends!

This is perfect for:
  • Development servers
  • Database connections
  • Long-running processes
""")
        
        self.get_input("\nPress Enter to continue...")
        
    def tutorial_parallel(self):
        """Parallel execution tutorial"""
        print("\n" + "-" * 40)
        print("Tutorial: Parallel Execution")
        print("-" * 40)
        
        print("""
Run multiple commands simultaneously for speed.

Example code:
    from claudecontrol.claude_helpers import parallel_commands
    
    results = parallel_commands([
        "npm test",
        "pytest",
        "cargo test"
    ])
    
    for cmd, result in results.items():
        if result["success"]:
            print(f"✓ {cmd}")
        else:
            print(f"✗ {cmd}: {result['error']}")

Perfect for running test suites across multiple projects!
""")
        
        self.get_input("\nPress Enter to continue...")
        
    def status_menu(self):
        """Show system status"""
        print("\n" + "=" * 50)
        print("SYSTEM STATUS")
        print("=" * 50)
        
        try:
            info = status()
            
            print(f"\nTotal sessions: {info['total_sessions']}")
            print(f"Active sessions: {info['active_sessions']}")
            print(f"Log size: {info['log_size_mb']} MB")
            print(f"Config path: {info['config_path']}")
            
            if info['sessions']:
                print("\nSession Details:")
                for s in info['sessions']:
                    status_str = "ALIVE" if s['is_alive'] else "DEAD"
                    print(f"  • {s['session_id']}: {s['command']} [{status_str}]")
                    
        except Exception as e:
            print(f"Error getting status: {e}")
            
        self.get_input("\nPress Enter to continue...")
        
    def examples_menu(self):
        """Show examples"""
        print("\n" + "=" * 50)
        print("EXAMPLES & TUTORIALS")
        print("=" * 50)
        
        print("\nAvailable example scripts:")
        print("  • simple_usage.py - Basic usage patterns")
        print("  • investigation_demo.py - Program investigation")
        print("  • black_box_testing.py - Security testing")
        print("  • claude_code_examples.py - Claude Code integration")
        
        examples_dir = Path(__file__).parent.parent.parent / "examples"
        
        if examples_dir.exists():
            print(f"\nExamples location: {examples_dir}")
            
            if self.get_yes_no("List example files?"):
                for example in examples_dir.glob("*.py"):
                    print(f"  • {example.name}")
                    
        print("\nRun examples with:")
        print("  python examples/simple_usage.py")
        
        self.get_input("\nPress Enter to continue...")
        
    def help_menu(self):
        """Show help"""
        print("\n" + "=" * 50)
        print("HELP & DOCUMENTATION")
        print("=" * 50)
        
        print("""
ClaudeControl Help
-----------------

Basic Commands:
  ccontrol run COMMAND        - Run a command
  ccontrol investigate PROG   - Investigate unknown program
  ccontrol probe PROG        - Quick interface check
  ccontrol list              - List sessions
  ccontrol status            - Show system status

Python API:
  from claudecontrol import run, control, Session
  
  # One-liner
  output = run("npm test", expect="passing")
  
  # Session control
  session = control("python", reuse=True)
  
  # Context manager
  with Session("bc") as calc:
      calc.sendline("2+2")

Investigation API:
  from claudecontrol import investigate_program
  
  report = investigate_program("unknown_tool")
  print(report.summary())

Documentation:
  • README.md - Getting started
  • CLAUDE.md - Detailed guide
  • examples/ - Example scripts

Support:
  • GitHub: https://github.com/anthropics/claude-code/issues
""")
        
        self.get_input("\nPress Enter to continue...")
        
    def exit_menu(self):
        """Exit confirmation"""
        print("\n" + "-" * 40)
        
        # Check for active sessions
        sessions = list_sessions(active_only=True)
        
        if sessions:
            print(f"You have {len(sessions)} active sessions.")
            if self.get_yes_no("Clean up sessions before exit?", True):
                cleanup_sessions()
                print("Sessions cleaned up.")
                
        print("\nThank you for using ClaudeControl!")
        print("Happy automating! 🚀")
        return "exit"


def interactive_menu():
    """Entry point for interactive menu"""
    menu = InteractiveMenu()
    menu.run()