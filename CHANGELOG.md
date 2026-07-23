# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-23

### Added
- `%%cpptutor` cell magic for step-by-step C++ code visualization in JupyterLab 4.x / Notebook 7
- GDB-based tracer: compiles with `g++ -g -O0 -std=c++23`, traces with GDB Python API
- `%cpptutor_config` line magic for compiler settings (default: C++23)
- Interactive HTML visualization with:
  - Step-by-step navigation (slider + first/prev/next/last buttons)
  - Code section with dual-line highlighting (executed line green, next line pink)
  - Call stack frames with per-frame variables (each recursive call shows its own vars)
  - Heap objects with SVG pointer arrows from stack to heap
  - Program output (stdout) panel with accumulated cout output
  - Resizable panels (draggable dividers between code/frames/heap columns)
- Variable visualization: int, char, bool, float, double, pointers, arrays, structs, strings
- Function entry steps with `?` for uninitialized variables (aligned with Python Tutor)
- Per-frame variable reading via `frame.older()` chain (correct recursion visualization)
- Member function support: constructor chaining, virtual function dispatch, diamond problem
- `#line 1 "user.cpp"` directive for 1:1 GDB line number mapping to user source
- Automatic `#include` header injection (iostream, string, vector, map, list, set, memory)
- User-provided `main()` required (no auto-wrapping)
- 48 unit tests (tracer, renderer, magics)
- Example notebooks: comprehensive test (10 examples), advanced examples (13), OOP examples (8)
