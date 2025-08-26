"""
Common patterns and pattern helpers for claudecontrol
"""

import re
from typing import Union, List, Optional, Tuple, Dict, Any

# Forward reference for type checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .core import Session

# Common prompt patterns
COMMON_PROMPTS = {
    "bash": [r"\$ ", r"# ", r"\$\s*$", r"#\s*$"],
    "python": [r">>> ", r"\.\.\. "],
    "node": [r"> "],
    "mysql": [r"mysql> "],
    "postgres": [r"=# ", r"=> "],
    "ssh": [r"password:", r"Password:", r"passphrase:", r"yes/no"],
    "sudo": [r"\[sudo\] password", r"Password:"],
    "git": [r"Username:", r"Password:", r"\(yes/no\)"],
}

# Common error patterns
COMMON_ERRORS = {
    "command_not_found": [
        r"command not found",
        r"No such file or directory",
        r"not recognized as",
        r"is not recognized",
    ],
    "permission_denied": [
        r"Permission denied",
        r"Access denied",
        r"Operation not permitted",
    ],
    "connection_failed": [
        r"Connection refused",
        r"Connection timed out",
        r"Could not resolve",
        r"Name or service not known",
    ],
    "authentication_failed": [
        r"Authentication failed",
        r"Invalid credentials",
        r"Access denied",
        r"Login incorrect",
    ],
}

# Combine all prompts for generic waiting
ALL_PROMPTS = []
for prompts in COMMON_PROMPTS.values():
    ALL_PROMPTS.extend(prompts)


def wait_for_prompt(
    session: 'Session',
    prompts: Optional[List[str]] = None,
    timeout: int = 30,
) -> int:
    """
    Wait for a command prompt
    
    Args:
        session: Active session
        prompts: List of prompt patterns (uses common prompts if not provided)
        timeout: Maximum wait time
        
    Returns:
        Index of matched prompt
    """
    if prompts is None:
        prompts = ALL_PROMPTS
        
    return session.expect(prompts, timeout=timeout)


def wait_for_login(
    session: 'Session',
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 30,
) -> bool:
    """
    Handle common login sequences
    
    Args:
        session: Active session
        username: Username to send if prompted
        password: Password to send if prompted
        timeout: Maximum wait time
        
    Returns:
        True if login appears successful
    """
    login_patterns = [
        r"[Uu]sername:",
        r"[Ll]ogin:",
        r"[Pp]assword:",
        r"[Pp]assphrase:",
    ]
    
    # Add common prompts that indicate successful login
    success_patterns = COMMON_PROMPTS.get("bash", []) + [r"Last login:"]
    
    # Add error patterns
    error_patterns = COMMON_ERRORS["authentication_failed"]
    
    all_patterns = login_patterns + success_patterns + error_patterns
    
    while True:
        try:
            index = session.expect(all_patterns, timeout=timeout)
            matched_pattern = all_patterns[index]
            
            # Check what we matched
            if index < len(login_patterns):
                # Login prompt
                if "sername" in matched_pattern.lower() or "ogin" in matched_pattern.lower():
                    if username:
                        session.sendline(username)
                    else:
                        return False  # No username provided
                elif "assword" in matched_pattern.lower() or "assphrase" in matched_pattern.lower():
                    if password:
                        session.sendline(password)
                    else:
                        return False  # No password provided
                        
            elif index < len(login_patterns) + len(success_patterns):
                # Success pattern
                return True
                
            else:
                # Error pattern
                return False
                
        except Exception:
            return False


def extract_between(
    output: str,
    start_pattern: str,
    end_pattern: str,
    include_markers: bool = False,
) -> Optional[str]:
    """
    Extract text between two patterns
    
    Args:
        output: Text to search
        start_pattern: Starting pattern (regex)
        end_pattern: Ending pattern (regex)
        include_markers: Include the patterns in result
        
    Returns:
        Extracted text or None if not found
    """
    try:
        if include_markers:
            pattern = f"({start_pattern}.*?{end_pattern})"
        else:
            pattern = f"{start_pattern}(.*?){end_pattern}"
            
        match = re.search(pattern, output, re.DOTALL)
        if match:
            return match.group(1)
            
    except Exception:
        pass
        
    return None


def extract_json(output: str) -> Optional[Union[dict, list]]:
    """
    Extract and parse JSON from output
    
    Args:
        output: Text containing JSON
        
    Returns:
        Parsed JSON or None if not found
    """
    import json
    
    # Try to find JSON blocks
    json_patterns = [
        (r"\{", r"\}"),  # Object
        (r"\[", r"\]"),  # Array
    ]
    
    for start, end in json_patterns:
        # Find all potential JSON blocks
        matches = re.finditer(f"{start}[^{start}{end}]*{end}", output)
        
        for match in matches:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
                
    # Try the whole output
    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        return None


def wait_for_regex(
    session: 'Session',
    pattern: str,
    timeout: int = 30,
    flags: int = 0,
) -> re.Match:
    """
    Wait for a regex pattern and return the match object
    
    Args:
        session: Active session
        pattern: Regular expression pattern
        timeout: Maximum wait time
        flags: Regex flags (e.g., re.IGNORECASE)
        
    Returns:
        Match object
    """
    compiled = re.compile(pattern, flags)
    session.expect(compiled, timeout=timeout)
    return session.process.match


def find_all_patterns(
    output: str,
    pattern: str,
    flags: int = 0,
) -> List[str]:
    """
    Find all occurrences of a pattern
    
    Args:
        output: Text to search
        pattern: Regular expression pattern
        flags: Regex flags
        
    Returns:
        List of all matches
    """
    return re.findall(pattern, output, flags)


# Investigation-specific patterns
INVESTIGATION_PATTERNS = {
    "help_indicators": [
        r"usage:\s*",
        r"Usage:\s*",
        r"USAGE:\s*",
        r"commands?:\s*",
        r"Commands?:\s*",
        r"COMMANDS?:\s*",
        r"options?:\s*",
        r"Options?:\s*",
        r"OPTIONS?:\s*",
        r"available\s+commands?",
        r"Available\s+commands?",
        r"help\s+menu",
        r"Help\s+menu",
        r"syntax:\s*",
        r"Syntax:\s*",
        r"examples?:\s*",
        r"Examples?:\s*",
        r"arguments?:\s*",
        r"Arguments?:\s*",
        r"flags?:\s*",
        r"Flags?:\s*",
        r"Type\s+.*\s+for\s+help",
        r"--help\s+for\s+more",
    ],
    "command_patterns": [
        r"^\s*(\w+)\s+[-–—]\s+(.+)$",  # command - description
        r"^\s*(\w+)\s+:\s+(.+)$",  # command : description
        r"^\s*\[(\w+)\]\s+(.+)$",  # [command] description
        r"^\s*•\s*(\w+)\s*[-:]?\s*(.*)$",  # • command: description
        r"^\s*\*\s*(\w+)\s*[-:]?\s*(.*)$",  # * command: description
        r"^\s*-\s*(\w+)\s*[-:]?\s*(.*)$",  # - command: description
        r"^\s+(\w+)\s{2,}(.+)$",  # command    description (spaces)
    ],
    "prompt_endings": [
        r">\s*$", r">\s*$", r"#\s*$", r"\$\s*$",
        r":\s*$", r"\]\s*$", r"\)\s*$", r"»\s*$",
        r"→\s*$", r"➜\s*$", r"▶\s*$", r"❯\s*$",
    ],
    "state_transitions": [
        r"entering\s+(\w+)",
        r"Entering\s+(\w+)",
        r"switched\s+to\s+(\w+)",
        r"Switched\s+to\s+(\w+)",
        r"mode:\s*(\w+)",
        r"Mode:\s*(\w+)",
        r"state:\s*(\w+)",
        r"State:\s*(\w+)",
        r"\[(\w+)\]",  # [state] indicators
        r"<(\w+)>",  # <state> indicators
    ],
    "data_formats": {
        "json": [r"\{[^}]*\}", r"\[[^\]]*\]"],
        "xml": [r"<[^>]+>[^<]*</[^>]+>", r"<[^>]+/>"],
        "yaml": [r"^\s*\w+:\s*\w+", r"^\s*-\s+\w+"],
        "ini": [r"^\s*\[[\w\s]+\]", r"^\s*\w+\s*=\s*\w+"],
        "csv": [r"^\s*[\w,]+(?:,[\w,]+)+\s*$"],
        "table": [r"\|.*\|.*\|", r"^\s*\+[-+]+\+\s*$"],
        "key_value": [r"^\s*\w+\s*[:=]\s*\w+"],
    },
    "error_indicators": [
        r"error:?\s*",
        r"Error:?\s*",
        r"ERROR:?\s*",
        r"failed:?\s*",
        r"Failed:?\s*",
        r"FAILED:?\s*",
        r"invalid\s+",
        r"Invalid\s+",
        r"unknown\s+",
        r"Unknown\s+",
        r"not\s+found",
        r"Not\s+found",
        r"denied",
        r"Denied",
        r"refused",
        r"Refused",
        r"abort",
        r"Abort",
        r"fatal",
        r"Fatal",
        r"warning:?\s*",
        r"Warning:?\s*",
        r"WARNING:?\s*",
    ],
}


def detect_prompt_pattern(output: str) -> Optional[str]:
    """
    Detect prompt pattern from program output
    
    Args:
        output: Program output text
        
    Returns:
        Detected prompt pattern or None
    """
    if not output:
        return None
    
    lines = output.strip().split('\n')
    if not lines:
        return None
    
    last_line = lines[-1]
    
    # Check known prompt patterns
    for patterns in COMMON_PROMPTS.values():
        for pattern in patterns:
            if re.search(pattern, last_line):
                return pattern
    
    # Check prompt endings
    for pattern in INVESTIGATION_PATTERNS["prompt_endings"]:
        if re.search(pattern, last_line):
            # Return the actual prompt, not just the pattern
            return last_line.strip()
    
    # Check if last line is short and ends with special char
    if len(last_line) <= 20:
        if re.search(r"[>$#:\])]$", last_line):
            return last_line.strip()
    
    return None


def extract_commands_from_help(help_text: str) -> List[Tuple[str, str]]:
    """
    Extract commands and descriptions from help text
    
    Args:
        help_text: Help output text
        
    Returns:
        List of (command, description) tuples
    """
    commands = []
    
    for line in help_text.split('\n'):
        for pattern in INVESTIGATION_PATTERNS["command_patterns"]:
            match = re.match(pattern, line)
            if match:
                cmd = match.group(1).strip()
                desc = match.group(2).strip() if match.lastindex > 1 else ""
                
                # Validate command (reasonable length, no spaces)
                if cmd and len(cmd) <= 30 and ' ' not in cmd:
                    commands.append((cmd, desc))
                break
    
    return commands


def detect_data_format(output: str) -> List[str]:
    """
    Detect data formats in output
    
    Args:
        output: Program output
        
    Returns:
        List of detected format names
    """
    formats = []
    
    for format_name, patterns in INVESTIGATION_PATTERNS["data_formats"].items():
        for pattern in patterns:
            if re.search(pattern, output, re.MULTILINE):
                formats.append(format_name)
                break
    
    return formats


def is_error_output(output: str) -> bool:
    """
    Check if output contains error indicators
    
    Args:
        output: Program output
        
    Returns:
        True if error indicators found
    """
    for pattern in INVESTIGATION_PATTERNS["error_indicators"]:
        if re.search(pattern, output, re.IGNORECASE):
            return True
    
    # Also check common error patterns
    for patterns in COMMON_ERRORS.values():
        for pattern in patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True
    
    return False


def detect_state_transition(output: str) -> Optional[str]:
    """
    Detect state transition indicators
    
    Args:
        output: Program output
        
    Returns:
        New state name if transition detected
    """
    for pattern in INVESTIGATION_PATTERNS["state_transitions"]:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def classify_output(output: str) -> Dict[str, Any]:
    """
    Classify output into categories
    
    Args:
        output: Program output
        
    Returns:
        Classification dict with detected features
    """
    return {
        "is_error": is_error_output(output),
        "data_formats": detect_data_format(output),
        "has_prompt": detect_prompt_pattern(output) is not None,
        "state_transition": detect_state_transition(output),
        "line_count": len(output.split('\n')),
        "has_table": bool(re.search(r"\|.*\|.*\|", output)),
        "has_json": bool(re.search(r"[\{\[].*[\}\]]", output)),
    }