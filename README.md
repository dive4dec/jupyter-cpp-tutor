# jupyter-cpp-tutor

C++ step-by-step code visualization for JupyterLab 4.x and Notebook 7.

Uses GDB to trace C++ code execution and renders an interactive
step-by-step visualization (like [Python Tutor](https://pythontutor.com/) /
[OPT_Mentor](https://github.com/dive4dec/OPT_Mentor)) inside a Jupyter notebook cell.

## Features

- **%%cpptutor cell magic** — write C++ code in a Python kernel cell, get instant visualization
- **GDB-based tracing** — compiles with `g++ -g`, traces with GDB's Python API
- **Step-by-step navigation** — slider + first/prev/next/last buttons
- **Variable visualization** — int, char, bool, float, pointers, arrays, structs
- **Call stack** — see function frames with parameters and locals
- **Pointer arrows** — SVG arrows from pointers to their targets
- **Resizable panels** — draggable dividers between code/frames/heap columns
- **Iframe srcdoc** — works in trusted JupyterLab 4 / Notebook 7 notebooks

## Requirements

- `g++` (with `-g` debug support)
- `gdb` (with Python scripting support — standard on Linux)
- A Python kernel (not a C++ kernel — tracing is done via GDB)
- JupyterLab 4.x or Notebook 7.x

## Installation

```bash
pip install jupyter-cpp-tutor
```

Then load the extension in a notebook:

```python
%load_ext jupyter_cpp_tutor
```

Or add to your `~/.ipython/profile_default/ipython_config.py`:

```python
c.InteractiveShellApp.extensions = ['jupyter_cpp_tutor']
```

## Usage

### Basic

```python
%%cpptutor
int main() {
    int x = 1;
    int y = x + 2;
    int z = x * y;
    return 0;
}
```

### Functions

```python
%%cpptutor
int add(int a, int b) {
    return a + b;
}
int main() {
    int x = add(3, 4);
    return 0;
}
```

### Pointers

```python
%%cpptutor
int main() {
    int x = 42;
    int *p = &x;
    return 0;
}
```

### Arrays

```python
%%cpptutor
int main() {
    int arr[3] = {10, 20, 30};
    return 0;
}
```

### Structs

```python
%%cpptutor
struct Point {
    int x;
    int y;
};
int main() {
    Point p;
    p.x = 3;
    p.y = 4;
    return 0;
}
```

### Loops

```python
%%cpptutor
int main() {
    int sum = 0;
    for (int i = 1; i <= 3; i++) {
        sum += i;
    }
    return 0;
}
```

### With cout output

```python
%%cpptutor
#include <iostream>
int main() {
    std::cout << "Hello, C++!" << std::endl;
    int x = 42;
    std::cout << "x = " << x << std::endl;
    return 0;
}
```

### Configuring the compiler

Set the C++ standard and extra compiler flags for the entire notebook:

```python
%cpptutor_config --std c++20 --flags "-Wall -Wextra"
```

Or per-cell:

```python
%%cpptutor --std c++20
consteval int sq(int n) { return n * n; }
int main() {
    constexpr int x = sq(5);
    return 0;
}
```

Show current settings or reset:

```python
%cpptutor_config            # show current settings
%cpptutor_config --reset    # back to defaults (c++23, no extra flags)
```

Default: **C++23**, no extra flags. `-g -O0` are always added for GDB debugging.

### Writing code

You **must** write your own `main()` function. The magic does **not** auto-wrap
your code — this ensures GDB line numbers map 1:1 to your source for accurate
step highlighting.

Common `#include` headers (`<iostream>`, `<string>`, `<vector>`, `<map>`,
`<list>`, `<set>`, `<memory>`) are added automatically if not already present.
A `#line 1` directive is injected so GDB reports line numbers matching your
original source exactly.

If you forget `main()`, you'll get a clear error message reminding you.

## How It Works

1. Standard `#include` headers are prepended (if not already present)
2. A `#line 1 "user.cpp"` directive ensures GDB line numbers match your source 1:1
3. The code is compiled with `g++ -g -O0 -std=c++23`
4. GDB runs in batch mode with a Python script that:
   - Sets breakpoints on `main()` and all user-defined functions
   - Steps through execution with `next`
   - At each step, captures variables (via GDB's block/symbol API)
   - Captures the call stack and heap objects (from `new`/`malloc` pointers)
5. The trace is rendered as an HTML iframe with srcdoc

## License

MIT
