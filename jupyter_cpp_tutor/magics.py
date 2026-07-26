"""%%cpptutor cell magic and %cpptutor_config line magic for Jupyter notebooks.

Usage in a Jupyter cell (Python kernel):

    %%cpptutor
    int x = 1;
    int y = x + 2;
    std::cout << "y = " << y << std::endl;

Or with options:

    %%cpptutor --height 600
    int arr[5] = {1, 2, 3, 4, 5};

Configure compiler flags for the entire notebook:

    %cpptutor_config --std c++20 --flags "-O2 -Wall"

    %cpptutor_config --std c++17   # just the standard
    %cpptutor_config --reset       # back to defaults
    %cpptutor_config               # show current settings
"""
from __future__ import annotations

import argparse
import html as html_mod
import shlex

from IPython.core.magic import Magics, magics_class, cell_magic, line_magic
from IPython.display import HTML, display

from .tracer import trace_cpp
from .renderer import render_trace

# Defaults
_DEFAULT_STD = "c++23"
_DEFAULT_FLAGS: list[str] = []
_DEFAULT_HEIGHT = 500


@magics_class
class CppTutorMagics(Magics):
    """Register the %%cpptutor cell magic and %cpptutor_config line magic."""

    def __init__(self, shell):
        super().__init__(shell)
        # Per-notebook config stored on the magics instance
        self._cpp_std = _DEFAULT_STD
        self._extra_flags: list[str] = list(_DEFAULT_FLAGS)
        self._height = _DEFAULT_HEIGHT

    # ── %cpptutor_config ──────────────────────────────────────────────

    @line_magic("cpptutor_config")
    def cpptutor_config(self, line: str):
        """Configure C++ compiler settings for the notebook.

        Examples::

            %cpptutor_config --std c++20
            %cpptutor_config --std c++17 --flags "-O2 -Wall -Wextra"
            %cpptutor_config --height 600
            %cpptutor_config --reset
            %cpptutor_config            # show current settings
        """
        parser = argparse.ArgumentParser(prog="%cpptutor_config", add_help=False)
        parser.add_argument("--std", dest="cpp_std", default=None,
                            help="C++ standard (e.g. c++14, c++17, c++20, c++23)")
        parser.add_argument("--flags", default=None,
                            help='Extra compiler flags, quoted (e.g. "-O2 -Wall")')
        parser.add_argument("--height", type=int, default=None,
                            help="Default visualization height in pixels")
        parser.add_argument("--reset", action="store_true",
                            help="Reset all settings to defaults")
        try:
            args = parser.parse_known_args(shlex.split(line))[0]
        except SystemExit:
            return

        if args.reset:
            self._cpp_std = _DEFAULT_STD
            self._extra_flags = list(_DEFAULT_FLAGS)
            self._height = _DEFAULT_HEIGHT
            display(HTML("<p>cpptutor config reset to defaults.</p>"))
            return

        if args.cpp_std is not None:
            self._cpp_std = args.cpp_std

        if args.flags is not None:
            # Split flags like a shell would: "-O2 -Wall" → ["-O2", "-Wall"]
            self._extra_flags = shlex.split(args.flags)

        if args.height is not None:
            self._height = args.height

        # Show current settings
        flags_str = " ".join(self._extra_flags) if self._extra_flags else "(none)"
        display(HTML(
            f"<table style='font-family:monospace;font-size:13px;'>"
            f"<tr><td><b>C++ standard</b></td><td>{self._cpp_std}</td></tr>"
            f"<tr><td><b>Extra flags</b></td><td>{html_mod.escape(flags_str)}</td></tr>"
            f"<tr><td><b>Default height</b></td><td>{self._height}px</td></tr>"
            f"</table>"
        ))

    # ── %%cpptutor ────────────────────────────────────────────────────

    @cell_magic("cpptutor")
    def cpptutor(self, line: str, cell: str):
        """Trace C++ code and display step-by-step visualization."""
        parser = argparse.ArgumentParser(prog="%%cpptutor", add_help=False)
        parser.add_argument("--height", type=int, default=None,
                            help="Height of visualization in pixels")
        parser.add_argument("--std", dest="cpp_std", default=None,
                            help="C++ standard for this cell only (overrides config)")
        parser.add_argument("--flags", default=None,
                            help='Extra compiler flags for this cell only')
        parser.add_argument("--input", action="append", default=[], metavar="VALUE",
                            help="Pre-collected stdin input for cin/getline. "
                                 "Repeat --input for multiple lines: "
                                 "--input Alice --input 25")
        try:
            args, _ = parser.parse_known_args(shlex.split(line))
        except SystemExit:
            return

        source_code = cell.strip()
        if not source_code:
            display(HTML("<p style='color:red;'>No C++ code provided.</p>"))
            return

        # Resolve effective settings (cell overrides > notebook config > defaults)
        cpp_std = args.cpp_std or self._cpp_std
        extra_flags = list(self._extra_flags)
        if args.flags is not None:
            extra_flags = shlex.split(args.flags)
        height = args.height if args.height is not None else self._height

        # Build compiler flags.  -std is always included so the user's
        # choice takes effect even with the auto-added #include headers.
        compiler_flags = [f"-std={cpp_std}"] + extra_flags

        # Trace the code
        inputs = args.input if args.input else None
        steps = trace_cpp(source_code, extra_flags=compiler_flags, inputs=inputs)

        # Check for errors
        if len(steps) == 1 and steps[0].get("event") in ("error", "compile_error"):
            error_msg = steps[0].get("stdout", "Unknown error")
            display(HTML(f"<pre style='color:red;'>{html_mod.escape(error_msg)}</pre>"))
            return

        # Render the visualization
        html_output = render_trace(steps, source_code, height=height)
        display(HTML(html_output))


def load_ipython_extension(ipython):
    """Load the extension in IPython/Jupyter."""
    ipython.register_magics(CppTutorMagics)
