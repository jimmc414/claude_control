"""
Program investigation and discovery module for ClaudeControl
Systematically explore and understand unknown CLI programs
"""

import re
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass, field, asdict

from .core import Session, control
from .patterns import COMMON_PROMPTS, COMMON_ERRORS, find_all_patterns
from .exceptions import SessionError, TimeoutError

logger = logging.getLogger(__name__)


@dataclass
class ProgramState:
    """Represents a discovered program state"""
    name: str
    prompt: str
    commands: Set[str] = field(default_factory=set)
    transitions: Dict[str, str] = field(default_factory=dict)
    output_samples: List[str] = field(default_factory=list)
    error_patterns: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "name": self.name,
            "prompt": self.prompt,
            "commands": list(self.commands),
            "transitions": self.transitions,
            "output_samples": self.output_samples[:5],  # Limit samples
            "error_patterns": list(self.error_patterns),
        }


@dataclass
class InvestigationReport:
    """Complete investigation findings"""
    program: str
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    entry_state: Optional[ProgramState] = None
    states: Dict[str, ProgramState] = field(default_factory=dict)
    commands: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompts: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    help_commands: List[str] = field(default_factory=list)
    exit_commands: List[str] = field(default_factory=list)
    data_formats: List[str] = field(default_factory=list)
    interaction_log: List[Dict[str, Any]] = field(default_factory=list)
    safety_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "program": self.program,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "entry_state": self.entry_state.to_dict() if self.entry_state else None,
            "states": {k: v.to_dict() for k, v in self.states.items()},
            "commands": self.commands,
            "prompts": self.prompts,
            "error_messages": self.error_messages,
            "help_commands": self.help_commands,
            "exit_commands": self.exit_commands,
            "data_formats": self.data_formats,
            "interaction_log": self.interaction_log[-100:],  # Last 100 interactions
            "safety_notes": self.safety_notes,
        }
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Save report to file"""
        if path is None:
            reports_dir = Path.home() / ".claude-control" / "investigations"
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = reports_dir / f"{self.program}_{timestamp}.json"
        
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path
    
    def summary(self) -> str:
        """Generate human-readable summary"""
        lines = [
            f"Investigation Report: {self.program}",
            f"=" * 50,
            f"Duration: {(self.completed_at - self.started_at).total_seconds():.1f}s" if self.completed_at else "In progress",
            f"States discovered: {len(self.states)}",
            f"Commands found: {len(self.commands)}",
            f"Prompts detected: {self.prompts}",
            f"Help commands: {self.help_commands}",
            f"Exit commands: {self.exit_commands}",
        ]
        
        if self.safety_notes:
            lines.append(f"\nSafety Notes:")
            for note in self.safety_notes:
                lines.append(f"  ⚠️  {note}")
        
        if self.commands:
            lines.append(f"\nTop Commands:")
            for cmd, info in list(self.commands.items())[:10]:
                lines.append(f"  • {cmd}: {info.get('description', 'Unknown')}")
        
        return "\n".join(lines)


class ProgramInvestigator:
    """
    Systematic investigation of unknown CLI programs
    """
    
    # Common help commands to try
    HELP_COMMANDS = [
        "help", "?", "h", 
        "--help", "-h", "-?",
        "\\h", "\\?",
        "commands", "usage",
        "info", "about",
        "man", "manual",
    ]
    
    # Common exit commands
    EXIT_COMMANDS = [
        "exit", "quit", "q",
        "bye", "logout", "close",
        "\\q", "\\quit", 
        "end", "stop",
        ".exit", ".quit",
        ":q", ":quit", ":q!",
        "ctrl-c", "ctrl-d",
    ]
    
    # Patterns that indicate help/usage information
    HELP_PATTERNS = [
        r"usage:", r"Usage:",
        r"commands:", r"Commands:",
        r"options:", r"Options:",
        r"available", r"Available",
        r"help", r"Help",
        r"syntax:", r"Syntax:",
        r"examples?:", r"Examples?:",
        r"arguments?:", r"Arguments?:",
        r"flags?:", r"Flags?:",
    ]
    
    # Patterns indicating data output
    DATA_PATTERNS = [
        r"\{.*\}",  # JSON object
        r"\[.*\]",  # JSON array  
        r"<.*>.*</.*>",  # XML
        r"\w+:\s+\w+",  # Key-value pairs
        r"\|.*\|",  # Table rows
        r"\w+,\w+",  # CSV
    ]
    
    def __init__(
        self,
        program: str,
        timeout: int = 10,
        max_depth: int = 5,
        safe_mode: bool = True,
        session_id: Optional[str] = None,
    ):
        """
        Initialize investigator
        
        Args:
            program: Program command to investigate
            timeout: Timeout for each operation
            max_depth: Maximum state exploration depth
            safe_mode: Enable safety checks and limits
            session_id: Optional session ID for reuse
        """
        self.program = program
        self.timeout = timeout
        self.max_depth = max_depth
        self.safe_mode = safe_mode
        self.session_id = session_id
        
        self.report = InvestigationReport(
            program=program,
            started_at=datetime.now()
        )
        
        self.session: Optional[Session] = None
        self.current_state: Optional[ProgramState] = None
        self.visited_states: Set[str] = set()
        
    def investigate(self) -> InvestigationReport:
        """
        Perform complete investigation
        
        Returns:
            Investigation report with findings
        """
        try:
            # Start the program
            self._start_session()
            
            # Detect initial state
            self._detect_initial_state()
            
            # Probe for help
            self._probe_help_commands()
            
            # Explore states and commands
            self._explore_states()
            
            # Test exit commands
            self._probe_exit_commands()
            
            # Analyze data formats
            self._analyze_data_formats()
            
        except Exception as e:
            logger.error(f"Investigation error: {e}")
            self.report.safety_notes.append(f"Investigation stopped: {e}")
            
        finally:
            self.report.completed_at = datetime.now()
            if self.session and self.session.is_alive():
                self.session.close()
        
        return self.report
    
    def _start_session(self):
        """Start the program session"""
        try:
            self.session = control(
                self.program,
                timeout=self.timeout,
                session_id=self.session_id,
                reuse=False,
            )
            
            # Give program time to start
            time.sleep(0.5)
            
            # Capture initial output
            initial_output = self.session.read_nonblocking(timeout=1)
            if initial_output:
                self._log_interaction("START", "", initial_output)
                
        except Exception as e:
            raise SessionError(f"Failed to start {self.program}: {e}")
    
    def _detect_initial_state(self):
        """Detect the initial program state and prompt"""
        output = self.session.get_recent_output(50)
        
        # Try to detect prompt
        prompt = self._detect_prompt(output)
        
        # Create initial state
        self.current_state = ProgramState(
            name="initial",
            prompt=prompt or "unknown",
        )
        
        self.report.entry_state = self.current_state
        self.report.states["initial"] = self.current_state
        
        if prompt:
            self.report.prompts.append(prompt)
            logger.info(f"Detected initial prompt: {prompt}")
    
    def _detect_prompt(self, output: str) -> Optional[str]:
        """Detect prompt pattern from output"""
        if not output:
            return None
        
        # Check common prompts first
        for prompt_type, patterns in COMMON_PROMPTS.items():
            for pattern in patterns:
                last_valid_match = None
                for match in re.finditer(pattern, output):
                    start = match.start()
                    if start == 0 or output[start - 1] in "\n\r":
                        last_valid_match = match

                if last_valid_match:
                    matched_text = last_valid_match.group(0)
                    if matched_text:
                        stripped = matched_text.strip()
                        return stripped or matched_text
        
        # Look for patterns at end of output
        lines = output.strip().split('\n')
        if lines:
            last_line = lines[-1]
            
            # Common prompt endings
            prompt_endings = [">", "$", "#", ":", "]", ")", "»", "→"]
            for ending in prompt_endings:
                if last_line.endswith(ending):
                    # Extract the prompt pattern
                    if len(last_line) <= 20:  # Reasonable prompt length
                        return last_line
        
        return None
    
    def _probe_help_commands(self):
        """Try common help commands to understand the interface"""
        for help_cmd in self.HELP_COMMANDS:
            if not self.session.is_alive():
                break
                
            try:
                self._send_command(help_cmd)
                output = self._wait_for_output()
                
                # Check if this looks like help output
                if self._is_help_output(output):
                    self.report.help_commands.append(help_cmd)
                    self._parse_help_output(output)
                    logger.info(f"Help command found: {help_cmd}")
                    
                    # Record the command
                    self.report.commands[help_cmd] = {
                        "type": "help",
                        "description": "Display help information",
                        "output_sample": output[:500],
                    }
                    
            except (TimeoutError, SessionError):
                continue
    
    def _is_help_output(self, output: str) -> bool:
        """Check if output looks like help/usage information"""
        if not output or len(output) < 20:
            return False
        
        matches = 0
        for pattern in self.HELP_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                matches += 1
        
        return matches >= 2  # At least 2 help indicators
    
    def _parse_help_output(self, output: str):
        """Parse help output to extract commands"""
        # Look for command listings
        command_patterns = [
            r"^\s*(\w+)\s+[-–—]\s+(.+)$",  # command - description
            r"^\s*(\w+)\s+:\s+(.+)$",  # command : description
            r"^\s*\[(\w+)\]\s+(.+)$",  # [command] description
            r"^\s*•\s*(\w+)\s*[-:]?\s*(.*)$",  # • command: description
        ]
        
        for line in output.split('\n'):
            for pattern in command_patterns:
                match = re.match(pattern, line)
                if match:
                    cmd = match.group(1)
                    desc = match.group(2).strip() if match.lastindex > 1 else ""
                    
                    if cmd and len(cmd) <= 20:  # Reasonable command length
                        if cmd not in self.report.commands:
                            self.report.commands[cmd] = {
                                "description": desc,
                                "discovered_from": "help",
                            }
                        
                        if self.current_state:
                            self.current_state.commands.add(cmd)
    
    def _explore_states(self, depth: int = 0):
        """Explore program states and transitions"""
        if depth >= self.max_depth:
            return
        
        if not self.current_state:
            return
        
        state_id = f"{self.current_state.name}_{self.current_state.prompt}"
        if state_id in self.visited_states:
            return
        
        self.visited_states.add(state_id)
        
        # Try discovered commands
        commands_to_try = list(self.current_state.commands)[:10]  # Limit exploration
        
        for cmd in commands_to_try:
            if not self.session.is_alive():
                break
            
            try:
                self._send_command(cmd)
                output = self._wait_for_output()
                
                # Detect new state
                new_prompt = self._detect_prompt(output)
                if new_prompt and new_prompt != self.current_state.prompt:
                    # State transition detected
                    new_state = ProgramState(
                        name=f"state_{len(self.report.states)}",
                        prompt=new_prompt,
                    )
                    
                    self.current_state.transitions[cmd] = new_state.name
                    self.report.states[new_state.name] = new_state
                    
                    # Recursive exploration
                    old_state = self.current_state
                    self.current_state = new_state
                    self._explore_states(depth + 1)
                    self.current_state = old_state
                
                # Analyze output
                self._analyze_output(output, cmd)
                
            except (TimeoutError, SessionError):
                continue
    
    def _probe_exit_commands(self):
        """Test exit commands (carefully in safe mode)"""
        if self.safe_mode:
            # Just record potential exit commands without testing
            for exit_cmd in self.EXIT_COMMANDS[:5]:  # Test only first few
                if exit_cmd in self.report.commands:
                    self.report.exit_commands.append(exit_cmd)
        else:
            # Actually test exit commands
            for exit_cmd in self.EXIT_COMMANDS:
                if not self.session.is_alive():
                    break
                
                try:
                    self._send_command(exit_cmd)
                    time.sleep(0.5)
                    
                    if not self.session.is_alive():
                        self.report.exit_commands.append(exit_cmd)
                        logger.info(f"Exit command found: {exit_cmd}")
                        break
                        
                except (TimeoutError, SessionError):
                    continue
    
    def _analyze_data_formats(self):
        """Analyze output data formats"""
        formats_found = set()
        
        # Check all captured output samples
        for state in self.report.states.values():
            for output in state.output_samples:
                # Check for JSON
                if re.search(r"\{.*\}", output) or re.search(r"\[.*\]", output):
                    formats_found.add("JSON")
                
                # Check for XML
                if re.search(r"<\w+>.*</\w+>", output):
                    formats_found.add("XML")
                
                # Check for tables
                if re.search(r"\|.*\|.*\|", output):
                    formats_found.add("Table")
                
                # Check for CSV
                if re.search(r"\w+,\w+,\w+", output):
                    formats_found.add("CSV")
                
                # Check for key-value
                if re.search(r"\w+\s*[:=]\s*\w+", output):
                    formats_found.add("Key-Value")
        
        self.report.data_formats = list(formats_found)
    
    def _analyze_output(self, output: str, command: str):
        """Analyze command output for patterns and information"""
        if not output:
            return
        
        # Store output sample
        if self.current_state:
            self.current_state.output_samples.append(output[:500])
        
        # Check for errors
        for error_type, patterns in COMMON_ERRORS.items():
            for pattern in patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    error_msg = f"{command}: {error_type}"
                    self.report.error_messages.append(error_msg)
                    if self.current_state:
                        self.current_state.error_patterns.add(pattern)
        
        # Update command info
        if command in self.report.commands:
            self.report.commands[command]["tested"] = True
            self.report.commands[command]["output_length"] = len(output)
    
    def _send_command(self, command: str):
        """Send a command and log it"""
        if self.safe_mode:
            # Check for potentially dangerous commands
            dangerous_patterns = [
                r"rm\s+-rf",
                r"del\s+/",
                r"format",
                r"fdisk",
                r"dd\s+if=",
                r"mkfs",
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    self.report.safety_notes.append(f"Skipped dangerous command: {command}")
                    raise SessionError(f"Dangerous command blocked: {command}")
        
        self.session.sendline(command)
        self._log_interaction("SEND", command, "")
    
    def _wait_for_output(self, wait_time: float = 1.0) -> str:
        """Wait for and capture output"""
        time.sleep(wait_time)
        output = self.session.read_nonblocking(timeout=self.timeout - 1)
        
        if output:
            self._log_interaction("RECV", "", output)
        
        return output
    
    def _log_interaction(self, action: str, input_text: str, output_text: str):
        """Log an interaction for the report"""
        self.report.interaction_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "input": input_text,
            "output": output_text[:500],  # Limit output size
        })
    
    def learn_from_interaction(self):
        """
        Learn from manual interaction with the program
        User takes control, investigator observes and learns
        """
        if not self.session or not self.session.is_alive():
            self._start_session()
        
        print("=== Interactive Learning Mode ===")
        print("Take control of the program. I'll observe and learn.")
        print("Press Ctrl+] to return control.\n")
        
        # Record output before interaction
        before_output = self.session.get_full_output()
        
        # Give control to user
        self.session.interact()
        
        # Analyze what happened during interaction
        after_output = self.session.get_full_output()
        new_output = after_output[len(before_output):]
        
        # Parse the interaction
        self._parse_interaction_transcript(new_output)
        
        print("\n=== Learning Complete ===")
        print(f"Discovered {len(self.report.commands)} commands")
        print(f"Found {len(self.report.prompts)} prompt patterns")
        
        return self.report
    
    def _parse_interaction_transcript(self, transcript: str):
        """Parse user interaction to learn commands and patterns"""
        lines = transcript.split('\n')
        
        for i, line in enumerate(lines):
            # Detect prompts
            prompt = self._detect_prompt(line)
            if prompt and prompt not in self.report.prompts:
                self.report.prompts.append(prompt)
            
            # Look for command-response patterns
            if i > 0 and prompt:
                # Previous line might be a command
                potential_cmd = lines[i-1].strip()
                if potential_cmd and len(potential_cmd) <= 50:
                    if potential_cmd not in self.report.commands:
                        self.report.commands[potential_cmd] = {
                            "discovered_from": "interaction",
                            "follows_prompt": prompt,
                        }
    
    @classmethod
    def quick_probe(cls, program: str, timeout: int = 5) -> Dict[str, Any]:
        """
        Quick probe to check if program is interactive
        
        Returns:
            Dict with basic program information
        """
        investigator = cls(program, timeout=timeout, safe_mode=True)
        
        try:
            investigator._start_session()
            investigator._detect_initial_state()
            
            # Quick help probe
            for cmd in ["help", "?", "--help"][:1]:
                try:
                    investigator._send_command(cmd)
                    output = investigator._wait_for_output()
                    if investigator._is_help_output(output):
                        break
                except:
                    pass
            
            return {
                "interactive": investigator.current_state is not None,
                "prompt": investigator.current_state.prompt if investigator.current_state else None,
                "alive": investigator.session.is_alive() if investigator.session else False,
            }
            
        finally:
            if investigator.session:
                investigator.session.close()


def investigate_program(
    program: str,
    timeout: int = 10,
    safe_mode: bool = True,
    save_report: bool = True,
) -> InvestigationReport:
    """
    High-level function to investigate an unknown program
    
    Args:
        program: Program command to investigate
        timeout: Timeout for operations
        safe_mode: Enable safety checks
        save_report: Save report to file
        
    Returns:
        Investigation report
    """
    investigator = ProgramInvestigator(
        program=program,
        timeout=timeout,
        safe_mode=safe_mode,
    )
    
    report = investigator.investigate()
    
    if save_report:
        path = report.save()
        logger.info(f"Investigation report saved to {path}")
    
    return report


def load_investigation(path: Path) -> InvestigationReport:
    """Load a saved investigation report"""
    data = json.loads(path.read_text())
    
    report = InvestigationReport(
        program=data["program"],
        started_at=datetime.fromisoformat(data["started_at"]),
    )
    
    # Restore fields
    if data.get("completed_at"):
        report.completed_at = datetime.fromisoformat(data["completed_at"])
    
    report.commands = data.get("commands", {})
    report.prompts = data.get("prompts", [])
    report.error_messages = data.get("error_messages", [])
    report.help_commands = data.get("help_commands", [])
    report.exit_commands = data.get("exit_commands", [])
    report.data_formats = data.get("data_formats", [])
    report.safety_notes = data.get("safety_notes", [])
    
    return report