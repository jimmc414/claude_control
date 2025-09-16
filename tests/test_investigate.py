"""
Tests for program investigation functionality
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from claudecontrol import investigation_summary
from claudecontrol.investigate import (
    ProgramInvestigator, InvestigationReport,
    ProgramState, investigate_program, load_investigation
)


class TestProgramState:
    """Test ProgramState dataclass"""
    
    def test_state_creation(self):
        """Test creating a program state"""
        state = ProgramState(
            name="test_state",
            prompt="test> "
        )
        
        assert state.name == "test_state"
        assert state.prompt == "test> "
        assert len(state.commands) == 0
        assert len(state.transitions) == 0
    
    def test_state_to_dict(self):
        """Test converting state to dictionary"""
        state = ProgramState(
            name="test_state",
            prompt="test> "
        )
        state.commands.add("help")
        state.commands.add("exit")
        state.transitions["config"] = "config_state"
        
        state_dict = state.to_dict()
        
        assert state_dict["name"] == "test_state"
        assert state_dict["prompt"] == "test> "
        assert "help" in state_dict["commands"]
        assert "exit" in state_dict["commands"]
        assert state_dict["transitions"]["config"] == "config_state"


class TestInvestigationReport:
    """Test InvestigationReport dataclass"""
    
    def test_report_creation(self):
        """Test creating an investigation report"""
        report = InvestigationReport(program="test_program")
        
        assert report.program == "test_program"
        assert report.started_at is not None
        assert report.completed_at is None
        assert len(report.states) == 0
        assert len(report.commands) == 0
    
    def test_report_to_dict(self):
        """Test converting report to dictionary"""
        report = InvestigationReport(program="test_program")
        
        # Add some data
        state = ProgramState("initial", "test> ")
        report.entry_state = state
        report.states["initial"] = state
        report.commands["help"] = {"description": "Show help"}
        report.prompts.append("test> ")
        
        report_dict = report.to_dict()
        
        assert report_dict["program"] == "test_program"
        assert report_dict["entry_state"] is not None
        assert "initial" in report_dict["states"]
        assert "help" in report_dict["commands"]
        assert "test> " in report_dict["prompts"]
    
    def test_report_summary(self):
        """Test generating report summary"""
        report = InvestigationReport(program="test_program")
        report.states["state1"] = ProgramState("state1", "> ")
        report.commands["cmd1"] = {"description": "Test command"}
        report.help_commands.append("help")
        
        summary = report.summary()
        
        assert "test_program" in summary
        assert "States discovered: 1" in summary
        assert "Commands found: 1" in summary
        assert "help" in summary
    
    def test_report_save_and_load(self, temp_dir):
        """Test saving and loading report"""
        # Create report
        report = InvestigationReport(program="test_program")
        report.commands["test"] = {"description": "Test"}
        report.prompts.append("test> ")
        
        # Save report
        save_path = temp_dir / "test_report.json"
        saved_path = report.save(save_path)
        
        assert saved_path.exists()
        
        # Load report
        loaded = load_investigation(saved_path)
        
        assert loaded.program == "test_program"
        assert "test" in loaded.commands
        assert "test> " in loaded.prompts


class TestProgramInvestigator:
    """Test ProgramInvestigator class"""
    
    def test_investigator_creation(self):
        """Test creating an investigator"""
        investigator = ProgramInvestigator(
            program="echo 'test'",
            timeout=5,
            max_depth=3,
            safe_mode=True
        )
        
        assert investigator.program == "echo 'test'"
        assert investigator.timeout == 5
        assert investigator.max_depth == 3
        assert investigator.safe_mode is True
        assert investigator.report is not None
    
    def test_detect_prompt(self):
        """Test prompt detection"""
        investigator = ProgramInvestigator("test")
        
        # Test various prompts
        assert investigator._detect_prompt("test> ") == "test>"
        assert investigator._detect_prompt(">>> ") == ">>>"
        assert investigator._detect_prompt("mysql> ") == "mysql>"
        assert investigator._detect_prompt("user@host:~$ ") is not None
        assert investigator._detect_prompt("no prompt here") is None
    
    def test_is_help_output(self):
        """Test help output detection"""
        investigator = ProgramInvestigator("test")
        
        help_text = """
        Usage: program [options]
        
        Commands:
          help - Show help
          exit - Exit program
        
        Options:
          -v  Verbose mode
        """
        
        assert investigator._is_help_output(help_text) is True
        assert investigator._is_help_output("short") is False
        assert investigator._is_help_output("no help here") is False
    
    def test_parse_help_output(self):
        """Test parsing help output"""
        investigator = ProgramInvestigator("test")
        investigator.current_state = ProgramState("test", "> ")
        
        help_text = """
        Commands:
          help     - Show this help
          list     - List items
          create   - Create item
          delete   - Delete item
        """
        
        investigator._parse_help_output(help_text)
        
        assert "help" in investigator.report.commands
        assert "list" in investigator.report.commands
        assert "create" in investigator.report.commands
        assert "delete" in investigator.report.commands
        
        # Check descriptions were captured
        assert "Show this help" in investigator.report.commands["help"]["description"]
    
    def test_safe_mode_blocks_dangerous(self):
        """Test safe mode blocks dangerous commands"""
        investigator = ProgramInvestigator("test", safe_mode=True)
        investigator.session = MagicMock()
        
        # Should raise error for dangerous commands
        with pytest.raises(Exception):
            investigator._send_command("rm -rf /")
        
        with pytest.raises(Exception):
            investigator._send_command("format c:")
        
        with pytest.raises(Exception):
            investigator._send_command("dd if=/dev/zero of=/dev/sda")
    
    def test_quick_probe(self):
        """Test quick probe functionality"""
        result = ProgramInvestigator.quick_probe("echo 'test'", timeout=2)
        
        assert "interactive" in result
        assert "prompt" in result
        assert "alive" in result
        assert isinstance(result["interactive"], bool)
    
    def test_investigate_echo(self):
        """Test investigating a simple echo command"""
        report = investigate_program(
            "echo 'test'",
            timeout=2,
            safe_mode=True,
            save_report=False
        )
        
        assert report.program == "echo 'test'"
        assert report.started_at is not None
        assert report.completed_at is not None


class TestInvestigationHelpers:
    """Test investigation helper functions"""

    def test_investigate_program_function(self):
        """Test the investigate_program function"""
        report = investigate_program(
            "python --version",
            timeout=2,
            safe_mode=True,
            save_report=False
        )
        
        assert report is not None
        assert report.program == "python --version"
        assert report.completed_at is not None
    
    def test_investigate_with_save(self, temp_dir, monkeypatch):
        """Test investigation with report saving"""
        # Patch home directory to temp
        def mock_home():
            return temp_dir
        
        monkeypatch.setattr(Path, "home", mock_home)
        
        report = investigate_program(
            "echo 'test'",
            timeout=2,
            safe_mode=True,
            save_report=True
        )
        
        # Check report was saved
        reports_dir = temp_dir / ".claude-control" / "investigations"
        assert reports_dir.exists()
        assert len(list(reports_dir.glob("*.json"))) > 0

    def test_investigation_summary_helper(self):
        """Test the investigation_summary convenience helper"""
        summary = investigation_summary(
            "echo 'summary'",
            timeout=2,
            safe_mode=True,
        )

        assert summary["program"] == "echo 'summary'"
        assert "commands" in summary
        assert "summary" in summary


class TestInteractiveLearning:
    """Test interactive learning mode"""
    
    @patch('builtins.input')
    @patch('builtins.print')
    def test_parse_interaction_transcript(self, mock_print, mock_input):
        """Test parsing user interaction transcript"""
        investigator = ProgramInvestigator("test")
        
        transcript = """
        test> help
        Available commands: help, exit, list
        test> list
        No items
        test> exit
        Goodbye!
        """
        
        investigator._parse_interaction_transcript(transcript)
        
        # Should detect prompts
        assert "test>" in investigator.report.prompts
        
        # Should detect commands
        assert "help" in investigator.report.commands
        assert "list" in investigator.report.commands
        assert "exit" in investigator.report.commands


class TestStateExploration:
    """Test state exploration functionality"""
    
    def test_state_creation(self):
        """Test creating and managing states"""
        investigator = ProgramInvestigator("test")
        
        # Create initial state
        investigator.current_state = ProgramState("initial", "main> ")
        investigator.report.states["initial"] = investigator.current_state
        
        # Add commands and transitions
        investigator.current_state.commands.add("config")
        investigator.current_state.commands.add("data")
        investigator.current_state.transitions["config"] = "config_state"
        
        assert len(investigator.report.states) == 1
        assert "config" in investigator.current_state.commands
        assert investigator.current_state.transitions["config"] == "config_state"
    
    def test_visited_states_tracking(self):
        """Test tracking visited states"""
        investigator = ProgramInvestigator("test")
        
        state1 = ProgramState("state1", "> ")
        state2 = ProgramState("state2", ">> ")
        
        investigator.current_state = state1
        state_id = f"{state1.name}_{state1.prompt}"
        
        # Mark as visited
        investigator.visited_states.add(state_id)
        
        assert state_id in investigator.visited_states
        assert f"{state2.name}_{state2.prompt}" not in investigator.visited_states


if __name__ == "__main__":
    pytest.main([__file__, "-v"])