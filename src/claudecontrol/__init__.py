"""
ClaudeControl: Give Claude control of your terminal
"""

from .core import (
    Session,
    run,
    control,
    get_session,
    list_sessions,
    cleanup_sessions,
    list_configs,
    delete_config,
    get_config,
)

from .patterns import (
    COMMON_PROMPTS,
    COMMON_ERRORS,
    wait_for_prompt,
    wait_for_login,
)

from .exceptions import (
    SessionError,
    TimeoutError,
    ProcessError,
    ConfigNotFoundError,
)

from .claude_helpers import (
    test_command,
    interactive_command,
    run_script,
    status,
    investigate_program,
    probe_interface,
    map_program_states,
    fuzz_program,
)

from .investigate import (
    ProgramInvestigator,
    InvestigationReport,
)

from .testing import (
    BlackBoxTester,
    black_box_test,
)

__version__ = "0.1.0"
__all__ = [
    "Session",
    "run",
    "control", 
    "get_session",
    "list_sessions",
    "cleanup_sessions",
    "list_configs",
    "delete_config",
    "get_config",
    "COMMON_PROMPTS",
    "COMMON_ERRORS",
    "wait_for_prompt",
    "wait_for_login",
    "SessionError",
    "TimeoutError", 
    "ProcessError",
    "ConfigNotFoundError",
    "test_command",
    "interactive_command",
    "run_script",
    "status",
    "investigate_program",
    "probe_interface",
    "map_program_states",
    "fuzz_program",
    "ProgramInvestigator",
    "InvestigationReport",
    "BlackBoxTester",
    "black_box_test",
]