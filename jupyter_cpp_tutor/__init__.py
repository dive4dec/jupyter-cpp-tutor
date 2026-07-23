"""jupyter-cpp-tutor: C++ step-by-step code visualization for JupyterLab 4.x and Notebook 7.

Uses GDB to trace C++ code execution and renders an interactive
step-by-step visualization (like Python Tutor / OPT_Mentor) inside
a Jupyter notebook cell.

Usage in a Jupyter cell (Python kernel):

    %%cpptutor
    int x = 1;
    int y = x + 2;
    std::cout << "y = " << y << std::endl;

Requirements:
  - g++ (with -g debug support)
  - gdb (with Python scripting support)
  - A Python kernel (not a C++ kernel — the tracing is done via GDB)
"""
from .tracer import trace_cpp
from .renderer import render_trace

__version__ = "0.1.0"

__all__ = ["trace_cpp", "render_trace", "__version__"]


def _load_jupyter_extension(ipython):
    """Load the %%cpptutor magic when used as a Jupyter extension."""
    from .magics import CppTutorMagics
    ipython.register_magics(CppTutorMagics)


def load_ipython_extension(ipython):
    """Load the %%cpptutor magic (standard IPython entry point)."""
    _load_jupyter_extension(ipython)
