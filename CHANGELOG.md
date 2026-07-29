# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] - 2026-07-30

### Fixed
- stdout output not visible until `std::endl` or `std::flush`: `std::cout` buffers internally and only writes to the C `stdout` FILE* on flush. Added `setvbuf(stdout, 0, _IONBF, 0)` after `freopen` to set stdout to unbuffered mode, so `std::cout` output (synced with C stdio by default) appears in the capture file immediately — even without `std::endl`.

### Changed
- C++ syntax highlighting colors switched from One Dark theme (too light against `#fafafa` background) to One Light theme: keywords `#a626a4`, strings `#50a14f`, numbers `#986801`, comments `#a0a1a7`, functions `#4078f2`, types `#c18401`, preprocessor `#a626a4`.

## [0.2.2] - 2026-07-26

### Fixed
- stdout/stdin capture broken on GDB 17+ (Ubuntu 25.04, Python 3.14): `freopen` calls now cast `stdout`/`stdin` to `(FILE*)` — GDB 17 can't resolve the type of `stdout` without an explicit cast. Falls back to uncast version for GDB 15 and older.

## [0.2.1] - 2026-07-26

### Added
- C++ syntax highlighting in code panel: keywords (purple), types (yellow), strings (green), comments (gray italic), numbers (orange), function calls (blue), preprocessor directives (purple)

### Changed
- Current line color changed from yellow (`#fef3c7` / `#f59e0b`) to pink (`#fce7f3` / `#e10c65`) for consistency with jupyter-python-tutor

## [0.2.0] - 2026-07-26

### Added
- `--input` option for pre-collected stdin values: `%%cpptutor --input Alice --input 25`
- `cin` / `getline` stdin support: pre-collected inputs written to a temp file, `freopen` redirects the inferior's `stdin` to that file after `run`
- `inputs` parameter on `trace_cpp()`: `inputs: list[str] | None`
- `setup_stdin_capture()` function in GDB script: redirects inferior stdin via `freopen(path, "r", stdin)`

### Changed
- GDB script accepts `__STDIN_PATH_PLACEHOLDER__` injection for stdin file path
- `trace_cpp()` signature updated with `inputs` parameter

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
