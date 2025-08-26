"""
Custom exceptions for claude-pexpect
"""


class ClaudeControlError(Exception):
    """Base exception for all claudecontrol errors"""
    pass


class SessionError(ClaudeControlError):
    """Error related to session management"""
    pass


class TimeoutError(ClaudeControlError):
    """Timeout waiting for expected output"""
    pass


class ProcessError(ClaudeControlError):
    """Error with the spawned process"""
    pass


class CommandError(ClaudeControlError):
    """Error processing a command"""
    pass


class ConfigNotFoundError(ClaudeControlError):
    """Configuration file not found"""
    pass