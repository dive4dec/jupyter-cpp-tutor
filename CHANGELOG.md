# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-09-27

### Fixed
- **Stepping no longer skips into function templates.** C++20 `auto` parameter
  functions (e.g. `void increment(auto &x)`) and explicit templates are
  *function templates* — GDB lists them with a template-argument suffix
  (`increment<int>`, `Square::twice<int>`). The breakpoint-discovery regex did
  not match that suffix, so no breakpoint was set on the callee and stepping
  went straight over the call instead of entering it. The name parser now
  accepts the optional `<...>` suffix, strips it (and any `Class::` qualifier)
  to the base name, and sets one breakpoint per base name so every
  instantiation is entered. Verified for plain functions, member functions,
  member function templates, and multi-argument templates.
- Added regression tests: `test_template_function_step_into`,
  `test_member_template_step_into`.

## [0.3.0] - 2026-09-27

### Fixed
- **C++23 references to arrays of unknown bound** (e.g. `double (&u)[0]` initialized from a `double[3]`) now display with their actual type (`double (&)[0]`) instead of `unknown ?`. Root cause: GDB reports references as `TYPE_CODE_REF`, which had no handling in the value formatter — it fell through to the simple-value path where the float conversion failed and the value was force-blanked to `?`. Added `is_reference()` / `format_reference()` (uses GDB's `referenced_value()`), and made `format_array` tolerate arrays whose `range()` is unavailable.
- **References in general** (`std::string &`, etc.) now render with their reference type and a `(&)` alias marker so students can distinguish an alias from a copy.
- **Warnings were silently dropped**: a successful compile's stderr was discarded, so compiler warnings (e.g. clang's `[-Wdangling]`, GCC's `[-Wunused-variable]` with `-Wall`) never appeared. They are now attached to every trace step's stderr and displayed in the stderr panel.

### Added
- **stderr panel (terminal-style)**: the inferior's `stderr` (e.g. `std::cerr`) is captured per step via `freopen` + unbuffered `setvbuf` (mirroring the existing stdout capture) and shown in a red panel below the green stdout panel — hidden when empty, just like a terminal.

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
