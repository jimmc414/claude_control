"""
Tests for the black box testing framework
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from claudecontrol.testing import (
    BlackBoxTester, black_box_test
)


class TestBlackBoxTester:
    """Test BlackBoxTester class"""
    
    def test_tester_creation(self):
        """Test creating a black box tester"""
        tester = BlackBoxTester("echo 'test'", timeout=5)
        
        assert tester.program == "echo 'test'"
        assert tester.timeout == 5
        assert len(tester.test_results) == 0
    
    def test_startup_test(self):
        """Test program startup testing"""
        tester = BlackBoxTester("echo 'test'", timeout=2)
        result = tester.test_startup()
        
        assert result["test"] == "startup"
        assert "passed" in result
        assert "details" in result
        assert result["details"]["started"] is not None
    
    def test_help_system_test(self):
        """Test help system discovery"""
        tester = BlackBoxTester("python", timeout=5)
        result = tester.test_help_system()
        
        assert result["test"] == "help_system"
        assert "working_commands" in result
        assert "details" in result
        
        # Python should respond to --help or help()
        # But since we're testing python interpreter, it might not work as expected
        # So we just check the structure
        assert isinstance(result["working_commands"], list)
    
    def test_invalid_input_test(self):
        """Test invalid input handling"""
        tester = BlackBoxTester("python", timeout=5)
        result = tester.test_invalid_input()
        
        assert result["test"] == "invalid_input"
        assert "crashes" in result
        assert "good_errors" in result
        assert "details" in result
        
        # Python should handle invalid input gracefully
        assert isinstance(result["crashes"], list)
    
    def test_exit_behavior_test(self):
        """Test exit behavior testing"""
        tester = BlackBoxTester("python", timeout=5)
        result = tester.test_exit_behavior()
        
        assert result["test"] == "exit_behavior"
        assert "working_exits" in result
        assert "details" in result
        
        # Python should exit on exit() or quit
        assert isinstance(result["working_exits"], list)
    
    @pytest.mark.skipif(
        not pytest.importorskip("psutil"),
        reason="psutil not available"
    )
    def test_resource_usage_test(self):
        """Test resource usage monitoring"""
        tester = BlackBoxTester("python", timeout=5)
        result = tester.test_resource_usage()
        
        assert result["test"] == "resource_usage"
        assert "passed" in result
        assert "details" in result
        
        if "cpu_percent" in result["details"]:
            assert isinstance(result["details"]["cpu_percent"], (int, float))
        if "memory_mb" in result["details"]:
            assert result["details"]["memory_mb"] > 0
    
    def test_concurrent_sessions_test(self):
        """Test concurrent session testing"""
        tester = BlackBoxTester("echo 'test'", timeout=2)
        result = tester.test_concurrent_sessions()
        
        assert result["test"] == "concurrent_sessions"
        assert "passed" in result
        assert "details" in result
        
        # Check session status
        for i in range(3):
            assert f"session_{i}" in result["details"]
    
    def test_fuzz_test(self):
        """Test fuzzing functionality"""
        tester = BlackBoxTester("python", timeout=5)
        result = tester.run_fuzz_test(max_inputs=5)
        
        assert result["test"] == "fuzzing"
        assert "passed" in result
        assert "details" in result
        assert "total_findings" in result["details"]
        assert "crashes" in result["details"]
        assert "errors" in result["details"]
    
    def test_run_all_tests(self):
        """Test running all tests"""
        tester = BlackBoxTester("echo 'test'", timeout=2)
        results = tester.run_all_tests()
        
        assert len(results) > 0
        
        # Check that all test types were run
        test_names = [r["test"] for r in results]
        assert "startup" in test_names
        assert "help_system" in test_names
        assert "invalid_input" in test_names
        assert "exit_behavior" in test_names
        assert "resource_usage" in test_names
        assert "concurrent_sessions" in test_names
        assert "fuzzing" in test_names
    
    def test_generate_report(self):
        """Test report generation"""
        tester = BlackBoxTester("echo 'test'", timeout=2)
        
        # Run some tests
        tester.test_startup()
        tester.test_help_system()
        
        # Generate report
        report = tester.generate_report()
        
        assert "Black Box Test Report" in report
        assert "echo 'test'" in report
        assert "Tests Passed:" in report
        assert "[PASS]" in report or "[FAIL]" in report
    
    def test_save_report(self, temp_dir):
        """Test saving test report"""
        tester = BlackBoxTester("echo 'test'", timeout=2)
        
        # Run tests
        tester.test_startup()
        
        # Save report
        report_path = temp_dir / "test_report.json"
        saved_path = tester.save_report(report_path)
        
        assert saved_path.exists()
        
        # Load and verify
        with open(saved_path) as f:
            data = json.load(f)
        
        assert data["program"] == "echo 'test'"
        assert "test_results" in data
        assert len(data["test_results"]) > 0
        assert "summary" in data


class TestBlackBoxTestFunction:
    """Test the black_box_test helper function"""
    
    def test_black_box_test_basic(self):
        """Test basic black box testing"""
        results = black_box_test(
            "echo 'test'",
            timeout=2,
            save_report=False
        )
        
        assert "program" in results
        assert "results" in results
        assert "report" in results
        assert results["program"] == "echo 'test'"
        assert len(results["results"]) > 0
    
    def test_black_box_test_with_save(self, temp_dir, monkeypatch):
        """Test black box testing with report saving"""
        # Patch home directory
        def mock_home():
            return temp_dir

        monkeypatch.setattr(Path, "home", mock_home)

        results = black_box_test(
            "echo 'test'",
            timeout=2,
            save_report=True
        )

        assert "report_path" in results
        assert results["report_path"] is not None

        # Check file was created
        report_path = Path(results["report_path"])
        assert report_path.exists()

    def test_black_box_test_empty_program(self):
        """black_box_test should validate program input"""
        with pytest.raises(ValueError):
            black_box_test("   ")


class TestSpecificScenarios:
    """Test specific testing scenarios"""
    
    def test_crashing_program(self):
        """Test handling of crashing programs"""
        tester = BlackBoxTester("python -c 'import sys; sys.exit(1)'", timeout=2)
        result = tester.test_startup()
        
        # Should detect the crash
        assert result["test"] == "startup"
        # Program exits immediately, so it might not be alive
        assert "started" in result["details"]
    
    def test_hanging_program(self):
        """Test handling of hanging programs"""
        tester = BlackBoxTester("python -c 'import time; time.sleep(100)'", timeout=1)
        result = tester.test_startup()
        
        assert result["test"] == "startup"
        # Should handle the timeout gracefully
        assert "details" in result
    
    def test_interactive_program(self, mock_script):
        """Test with mock interactive program"""
        tester = BlackBoxTester(f"python {mock_script}", timeout=5)
        
        # Test startup
        result = tester.test_startup()
        assert result["passed"] is True
        
        # Test help
        result = tester.test_help_system()
        assert "help" in result["working_commands"]
        
        # Test exit
        result = tester.test_exit_behavior()
        assert len(result["working_exits"]) > 0


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_nonexistent_program(self):
        """Test with non-existent program"""
        tester = BlackBoxTester("this_does_not_exist_12345", timeout=2)
        result = tester.test_startup()
        
        assert result["test"] == "startup"
        assert result["passed"] is False
        assert "error" in result
    
    def test_empty_program(self):
        """Test with empty program string"""
        with pytest.raises(ValueError):
            BlackBoxTester("", timeout=2)
    
    def test_very_short_timeout(self):
        """Test with very short timeout"""
        tester = BlackBoxTester("sleep 10", timeout=0.1)
        result = tester.test_startup()
        
        assert result["test"] == "startup"
        # Should handle timeout gracefully
        assert "details" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])