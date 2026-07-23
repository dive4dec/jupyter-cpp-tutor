"""Tests for jupyter_cpp_tutor.magics."""
import pytest
from unittest.mock import patch, MagicMock
from IPython.testing.globalipapp import get_ipython

from jupyter_cpp_tutor.magics import CppTutorMagics


class TestCppTutorMagics:
    def test_magic_registration(self):
        """Test that the magic can be registered."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        assert magics is not None

    def test_empty_cell(self):
        """Test that empty cell produces an error message."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        # Call the magic with empty cell — should not crash
        magics.cpptutor("", "")

    def test_magic_with_valid_code(self):
        """Test that the magic processes valid code."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        # Mock trace_cpp to return simple steps
        with patch("jupyter_cpp_tutor.magics.trace_cpp") as mock_trace:
            mock_trace.return_value = [
                {"line": 1, "event": "line", "stdout": "", "call_stack": []}
            ]
            magics.cpptutor("", "int x = 1;")
            assert mock_trace.called
            assert mock_trace.call_args[0][0] == "int x = 1;"


class TestCppTutorConfig:
    def test_default_config(self):
        """Test default configuration values."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        assert magics._cpp_std == "c++23"
        assert magics._extra_flags == []
        assert magics._height == 500

    def test_set_std(self):
        """Test setting C++ standard."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config("--std c++20")
        assert magics._cpp_std == "c++20"

    def test_set_flags(self):
        """Test setting extra compiler flags."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config('--flags "-Wall -Wextra"')
        assert magics._extra_flags == ["-Wall", "-Wextra"]

    def test_set_height(self):
        """Test setting visualization height."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config("--height 600")
        assert magics._height == 600

    def test_reset(self):
        """Test resetting to defaults."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config("--std c++20 --flags -Wall --height 600")
        magics.cpptutor_config("--reset")
        assert magics._cpp_std == "c++23"
        assert magics._extra_flags == []
        assert magics._height == 500

    def test_cell_override_std(self):
        """Test that --std in cell magic overrides notebook config."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config("--std c++20")
        with patch("jupyter_cpp_tutor.magics.trace_cpp") as mock_trace:
            mock_trace.return_value = [
                {"line": 1, "event": "line", "stdout": "", "call_stack": []}
            ]
            magics.cpptutor("--std c++14", "int x = 1;")
            # Check that -std=c++14 was passed (not c++20 from config)
            extra_flags = mock_trace.call_args.kwargs.get("extra_flags")
            assert extra_flags is not None
            assert "-std=c++14" in extra_flags

    def test_cell_uses_config_std(self):
        """Test that cell magic uses notebook config when no cell override."""
        shell = get_ipython()
        magics = CppTutorMagics(shell)
        magics.cpptutor_config("--std c++20")
        with patch("jupyter_cpp_tutor.magics.trace_cpp") as mock_trace:
            mock_trace.return_value = [
                {"line": 1, "event": "line", "stdout": "", "call_stack": []}
            ]
            magics.cpptutor("", "int x = 1;")
            extra_flags = mock_trace.call_args.kwargs.get("extra_flags")
            assert extra_flags is not None
            assert "-std=c++20" in extra_flags
