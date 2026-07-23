"""C++ code tracer using GDB's Python API.

Compiles C++ code with ``g++ -g``, then runs GDB in batch mode with an
embedded Python script that steps through ``main()`` line by line,
capturing variables, call stack, and pointer targets at each step.

Produces a list of TraceStep dicts compatible with the renderer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import typing

__all__ = ["trace_cpp"]

# GDB Python script that runs inside GDB's interpreter.
# It steps through main() and captures variable state at each line.
_GDB_SCRIPT = r'''import gdb
import json
import re
import os

# Source lines injected by trace_cpp() — used to check if a line is just "}"
_source_lines = __SOURCE_LINES_PLACEHOLDER__

steps = []
step_idx = [0]
stdout_buffer = [""]
_freed_addrs = set()  # heap addresses freed by delete

# ── Stdout capture via output redirection ──
# We redirect the program's stdout to a temp file, then read it after each step.
_stdout_fd = None
_stdout_path = None

def setup_stdout_capture():
    """Redirect the inferior's stdout to a temp file so we can read it.

    Uses ``freopen`` to redirect the C ``stdout`` FILE* to a temp file.
    This must be called AFTER the inferior starts (after ``run``), when
    we're stopped at the first breakpoint.
    """
    global _stdout_path
    _stdout_path = "/tmp/__jpt_stdout_" + str(os.getpid()) + ".txt"
    # Create/truncate the file
    with open(_stdout_path, "w") as f:
        f.write("")
    # Redirect inferior's stdout to the temp file using freopen.
    # This must be called from within GDB when the inferior is running.
    try:
        gdb.execute('call (void) freopen("' + _stdout_path + '", "w", stdout)',
                    to_string=True)
    except Exception:
        # If freopen fails (e.g. no stdout symbol), try setvbuf + write approach
        pass

def read_stdout():
    """Read the current stdout content from the capture file."""
    if not _stdout_path or not os.path.exists(_stdout_path):
        return ""
    try:
        with open(_stdout_path, "r") as f:
            return f.read()
    except:
        return ""

# ── Source file tracking ──
_user_source_file = None

def get_user_source_file():
    """Find the user's source file from 'info source' command.

    With the ``#line 1 "user.cpp"`` directive, GDB reports the source
    as ``user.cpp`` (or the full path containing ``user.cpp``).
    """
    try:
        # Use 'info source' after loading the binary
        output = gdb.execute("info source", to_string=True)
        for line in output.split("\n"):
            # Line like: "Source file is /path/to/user.cpp."
            m = re.search(r"Source file is\s+(\S+\.cpp)", line)
            if m:
                return m.group(1)
    except:
        pass
    return None

# ── Variable declaration line tracking ──
# Maps variable name → declaration line, so we can hide uninitialized vars
_var_decl_lines = {}

def build_var_decl_map():
    """Build a map of variable name → declaration line from DWARF debug info."""
    global _var_decl_lines
    _var_decl_lines = {}
    try:
        # Use GDB's symbol table to find local variable declarations
        frame = gdb.selected_frame()
        if frame is None:
            return
        block = frame.block()
        depth = 0
        # Walk up to function block (limit depth to prevent infinite loops)
        while block is not None and depth < 5:
            for sym in block:
                if sym.is_variable or sym.is_argument:
                    name = sym.name
                    if name and not name.startswith("__"):
                        # Try to get the line where this symbol was declared
                        try:
                            # sym.line gives the declaration line in some GDB versions
                            line = sym.line if hasattr(sym, 'line') and sym.line else 0
                        except:
                            line = 0
                        _var_decl_lines[name] = line
            func = block.function
            if func is not None:
                break
            try:
                parent = block.superblock
                if parent is None or parent == block:
                    break
                block = parent
            except:
                break
            depth += 1
    except:
        pass

def get_source_line(symtab, lineno):
    """Get the source text at a given line."""
    try:
        if symtab and symtab.filename:
            with open(symtab.filename, 'r') as f:
                lines = f.readlines()
            if 0 < lineno <= len(lines):
                return lines[lineno - 1].rstrip()
    except:
        pass
    return ""

def get_source_line_from_file(filename, lineno):
    """Get the source text at a given line from a filename."""
    try:
        if filename:
            with open(filename, 'r') as f:
                lines = f.readlines()
            if 0 < lineno <= len(lines):
                return lines[lineno - 1].rstrip()
    except:
        pass
    return ""

# ── Value formatting ──

def get_type_name(val):
    try:
        return str(val.type)
    except:
        return "unknown"

def is_pointer(val):
    try:
        return val.type.code == gdb.TYPE_CODE_PTR
    except:
        return False

def is_array(val):
    try:
        return val.type.code == gdb.TYPE_CODE_ARRAY
    except:
        return False

def is_struct(val):
    try:
        return val.type.code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION)
    except:
        return False

def format_pointer(val):
    try:
        addr = int(val) if int(val) != 0 else 0
        addr_str = "0x{:x}".format(addr) if addr else "0x0"
        if addr != 0:
            try:
                deref = val.dereference()
                type_name = get_type_name(deref)
                return {"kind": "pointer", "addr": addr_str,
                        "deref_type": type_name, "deref_value": format_value(deref)}
            except:
                pass
        return {"kind": "pointer", "addr": addr_str,
                "deref_type": None, "deref_value": None}
    except:
        return {"kind": "pointer", "addr": "0x0",
                "deref_type": None, "deref_value": None}

def format_array(val):
    try:
        t = val.type
        n = t.range()[1] - t.range()[0] + 1 if hasattr(t, 'range') else 0
        n = min(n, 20)
        elements = []
        for i in range(n):
            try:
                elem = val[i]
                elements.append(format_value(elem))
            except:
                break
        return {"kind": "array", "type": get_type_name(val),
                "size": n, "elements": elements}
    except:
        return {"kind": "array", "type": "unknown", "size": 0, "elements": []}

def format_struct(val):
    try:
        t = val.type
        fields = []
        for field in t.fields():
            try:
                fname = field.name
                if not fname or field.is_base_class:
                    continue
                # Skip vptr
                if fname.startswith("_vptr"):
                    continue
                fval = val[fname]
                fields.append({"name": fname, "value": format_value(fval)})
            except:
                pass
        type_name = str(t).replace("struct ", "").replace("class ", "").replace("union ", "")
        if "<" in type_name:
            type_name = type_name.split("<")[0]
        return {"kind": "struct", "type": type_name, "fields": fields}
    except:
        return {"kind": "struct", "type": "unknown", "fields": []}

def format_simple(val):
    try:
        t = val.type
        type_str = str(t)
        # std::string
        if "std::string" in type_str or "basic_string" in type_str:
            try:
                s = str(val)
                # GDB prints strings as "content"
                return {"kind": "string", "type": "string", "value": s}
            except:
                return {"kind": "string", "type": "string", "value": "<string>"}
        # bool
        if type_str == "bool":
            return {"kind": "simple", "type": "bool",
                    "value": "true" if int(val) else "false"}
        # char
        if type_str == "char":
            c = int(val) & 0xFF
            if 32 <= c < 127:
                return {"kind": "simple", "type": "char", "value": "'{}'".format(chr(c))}
            elif c == 0:
                return {"kind": "simple", "type": "char", "value": "'\\0'"}
            elif c == 10:
                return {"kind": "simple", "type": "char", "value": "'\\n'"}
            else:
                return {"kind": "simple", "type": "char", "value": "'\\x{:02x}'".format(c)}
        # int variants
        if any(x in type_str for x in ["int", "short", "long", "unsigned"]):
            return {"kind": "simple", "type": type_str, "value": str(int(val))}
        # float/double
        if "float" in type_str or "double" in type_str:
            return {"kind": "simple", "type": type_str, "value": str(float(val))}
        # enum
        if t.code == gdb.TYPE_CODE_ENUM:
            return {"kind": "simple", "type": "enum", "value": str(val)}
        # fallback
        return {"kind": "simple", "type": type_str, "value": str(val)}
    except:
        return {"kind": "simple", "type": "unknown", "value": "<error>"}

def format_value(val):
    if val is None:
        return {"kind": "simple", "type": "void", "value": "void"}
    try:
        if is_pointer(val):
            return format_pointer(val)
        elif is_array(val):
            return format_array(val)
        elif is_struct(val):
            type_str = str(val.type)
            if "std::string" in type_str or "basic_string" in type_str:
                return format_simple(val)
            if "std::vector" in type_str:
                return format_stl_container(val, "vector")
            if "std::list" in type_str:
                return format_stl_container(val, "list")
            if "std::map" in type_str:
                return format_stl_container(val, "map")
            if "std::set" in type_str:
                return format_stl_container(val, "set")
            return format_struct(val)
        else:
            return format_simple(val)
    except Exception as e:
        return {"kind": "simple", "type": "unknown", "value": "<error: {}>".format(e)}

def format_stl_container(val, kind):
    try:
        n = 0
        elements = []
        addr = int(val.address) if val.address else 0
        if kind == "vector":
            try:
                size_val = gdb.parse_and_eval("((std::vector*){})->size()".format(addr))
                n = int(size_val)
                n = min(n, 20)
                for i in range(n):
                    try:
                        elem = gdb.parse_and_eval("(*((std::vector*){}))[{}]".format(addr, i))
                        elements.append(format_value(elem))
                    except:
                        break
            except:
                pass
        type_name = "std::{}".format(kind)
        return {"kind": "container", "type": type_name, "size": n, "elements": elements}
    except:
        return {"kind": "container", "type": "std::{}".format(kind),
                "size": 0, "elements": []}

# ── Variable scope tracking ──
# We track which variables are "in scope" at the current line.
# A variable is in scope if its declaration line <= current line.

def get_local_vars(frame, current_line):
    """Get all local variables that are in scope at the current line.

    Variables declared on the current line or future lines are shown as
    uninitialized (value ``"?"``) — matching Python Tutor's behavior.
    Variables that haven't been assigned yet are also shown as ``"?"``
    when GDB reports them as optimized out or unavailable.
    """
    locals_dict = {}
    try:
        # Build var decl map for THIS specific frame
        frame_decl_lines = {}
        try:
            block = frame.block()
            depth = 0
            while block is not None and depth < 5:
                for sym in block:
                    if not (sym.is_variable or sym.is_argument):
                        continue
                    if sym.addr_class == gdb.SYMBOL_LOC_TYPEDEF:
                        continue
                    name = sym.name
                    if not name or name.startswith("__") or name.startswith("_"):
                        continue
                    try:
                        sym_line = sym.line
                    except:
                        sym_line = 0
                    if sym_line > 0:
                        frame_decl_lines[name] = sym_line
                func = block.function
                if func is not None:
                    break
                try:
                    parent = block.superblock
                    if parent is None or parent == block:
                        break
                    block = parent
                except:
                    break
                depth += 1
        except:
            pass

        block = frame.block()
        depth = 0
        while block is not None and depth < 5:  # limit depth to prevent infinite loops
            for sym in block:
                # Include both variables and function arguments
                if not (sym.is_variable or sym.is_argument):
                    continue
                if sym.addr_class == gdb.SYMBOL_LOC_TYPEDEF:
                    continue
                name = sym.name
                if not name or name.startswith("__") or name.startswith("_"):
                    continue
                # Variables in scope: show all variables declared in this
                # function block, even those on future lines (as "?").
                # Python Tutor shows all function-scope variables from the
                # first step, with "?" for not-yet-initialized ones.
                decl_line = frame_decl_lines.get(name, 0)
                if decl_line > 0 and current_line > 0 and decl_line >= current_line:
                    # Variable declared on this line or a future line — show as "?"
                    try:
                        type_str = str(sym.type) if sym.type else "int"
                        if "*" in type_str:
                            locals_dict[name] = {"kind": "pointer", "type": type_str,
                                                  "value": "?", "addr": "0x0"}
                        else:
                            locals_dict[name] = {"kind": "simple", "type": type_str,
                                                  "value": "?"}
                    except:
                        pass
                    continue
                # Variable declared before current line — try to read value
                try:
                    val = frame.read_var(name)
                    formatted = format_value(val)
                    # Check for uninitialized markers
                    if formatted.get("kind") == "simple":
                        raw = formatted.get("value", "")
                        if "optimized" in raw or "<uninitialized>" in raw or raw == "<error>":
                            formatted["value"] = "?"
                    locals_dict[name] = formatted
                except Exception:
                    # Variable exists in scope but can't be read (uninitialized)
                    try:
                        type_str = str(sym.type) if sym.type else "int"
                        if "*" in type_str:
                            locals_dict[name] = {"kind": "pointer", "type": type_str,
                                                  "value": "?", "addr": "0x0"}
                        else:
                            locals_dict[name] = {"kind": "simple", "type": type_str,
                                                  "value": "?"}
                    except:
                        pass
            # Check if this is the function's top-level block
            func = block.function
            if func is not None:
                break
            try:
                parent = block.superblock
                if parent is None or parent == block:
                    break
                block = parent
            except:
                break
            depth += 1
    except:
        pass
    return locals_dict

def get_call_stack():
    """Build the full call stack with variables for EACH frame.

    Unlike the old version that only read vars for frame 0, this reads
    variables for every frame in the call stack.  This is essential for
    recursion — each gcd() frame has its own a, b values.
    """
    frames = []
    try:
        frame = gdb.newest_frame()
        while frame is not None:
            sal = frame.find_sal()
            func_name = "?"
            line = 0
            if frame.function():
                func_name = frame.function().name
            elif sal and sal.symtab:
                func_name = "main"
            if sal:
                line = sal.line

            # Read local variables for THIS frame
            try:
                # Select this frame so frame.read_var works correctly
                frame.select()
                locals_dict = get_local_vars(frame, line)
            except Exception:
                locals_dict = {}

            simple_vars = {k: v for k, v in locals_dict.items()
                          if isinstance(v, dict) and v.get("kind") in ("simple", "string")}
            pointer_vars = {k: v for k, v in locals_dict.items()
                           if isinstance(v, dict) and v.get("kind") == "pointer"}
            struct_vars = {k: v for k, v in locals_dict.items()
                          if isinstance(v, dict) and v.get("kind") in ("struct", "container", "array")}

            frames.append({
                "func": func_name,
                "line": line,
                "simple_vars": simple_vars,
                "pointer_vars": pointer_vars,
                "struct_vars": struct_vars,
            })
            frame = frame.older()
    except:
        pass
    # Restore the innermost frame as selected
    try:
        gdb.newest_frame().select()
    except:
        pass
    return frames

def is_user_function(frame):
    """Check if the current frame is in the user's source file.

    The ``#line 1 "user.cpp"`` directive makes GDB report the source
    filename as ``user.cpp`` (possibly with a path prefix).
    """
    sal = frame.find_sal()
    if sal and sal.symtab:
        fname = sal.symtab.filename
        if fname and "user.cpp" in fname:
            return True
        # Fallback: any .cpp/.cc/.c file
        if fname and (fname.endswith('.cpp') or fname.endswith('.cc') or fname.endswith('.c')):
            return True
    return False

def capture_step():
    """Capture the current execution state as a trace step."""
    try:
        frame = gdb.selected_frame()
        sal = frame.find_sal()
        line = sal.line if sal else 0

        # Rebuild var decl map for this frame
        global _var_decl_lines, _freed_addrs
        _var_decl_lines = {}
        build_var_decl_map()

        locals_dict = get_local_vars(frame, line)
        call_stack = get_call_stack()
        stdout_text = read_stdout()

        # Collect heap objects from all pointer variables in the current frame
        heap_objects = []
        seen_addrs = set()
        # Track freed addresses — once delete executes, the heap object is gone.
        # GDB stops BEFORE the line executes, so at the "delete p" line the
        # object still exists.  At the NEXT line, it's freed.
        # We use _freed_addrs to track addresses that were freed by a
        # previous delete statement.
        if _source_lines and 1 <= line <= len(_source_lines):
            _prev_src = _source_lines[line - 2].strip() if line >= 2 else ""
            if _prev_src.startswith("delete ") or _prev_src.startswith("delete["):
                # Previous line was a delete — mark current pointer addrs as freed
                for name, val in locals_dict.items():
                    if isinstance(val, dict) and val.get("kind") == "pointer":
                        addr = val.get("addr", "0x0")
                        if addr and addr != "0x0":
                            _freed_addrs.add(addr)
        for var_dict in [locals_dict]:
            for name, val in var_dict.items():
                if isinstance(val, dict) and val.get("kind") == "pointer":
                    addr = val.get("addr", "0x0")
                    # Skip pointers with "?" (uninitialized) value
                    if val.get("value") == "?":
                        continue
                    if addr and addr != "0x0" and addr not in seen_addrs:
                        seen_addrs.add(addr)
                        # Skip freed addresses
                        if addr in _freed_addrs:
                            continue
                        deref = val.get("deref_value")
                        if deref is not None:
                            heap_obj = {
                                "addr": addr,
                                "type": val.get("deref_type", "int"),
                                "value": deref,
                                "src_var": name,
                            }
                            heap_objects.append(heap_obj)
        step = {
            "line": line,
            "event": "line",
            "call_stack": call_stack,  # now includes vars for ALL frames
            "heap_objects": heap_objects,
            "stdout": stdout_text,
        }
        steps.append(step)
        step_idx[0] += 1
    except Exception as e:
        steps.append({"line": 0, "event": "error", "call_stack": [],
                      "stdout": "Trace error: {}".format(e)})

# ── Function-entry helpers ──

def _find_func_entry_line(func_name):
    """Find the source line of a function's signature (opening line).

    Scans ``_source_lines`` for a line like ``int main() {`` or
    ``int add(int a, int b) {``.  Returns the 1-indexed line number, or 0.
    """
    if not _source_lines:
        return 0
    # Strip C++ name mangling: "add(int, int)" → "add"
    # For member functions: "Widget::Widget(int)" → "Widget"
    #                        "Square::area()" → "area"
    bare_name = func_name.split("(")[0].strip()
    # Extract the method name part after the last "::"
    if "::" in bare_name:
        parts = bare_name.split("::")
        class_name = parts[0]
        method_name = parts[-1]
        # For constructors, method_name == class_name
        # Search using both class_name and method_name
        search_names = [bare_name, method_name, class_name]
    else:
        search_names = [bare_name]
    
    for idx, line in enumerate(_source_lines):
        stripped = line.strip()
        for sname in search_names:
            if sname in stripped and "(" in stripped:
                # Check if this line has the function name and a '('
                # The opening brace may be on this line or the next
                if "{" in stripped:
                    return idx + 1
                # Check next line for opening brace
                if idx + 1 < len(_source_lines):
                    next_stripped = _source_lines[idx + 1].strip()
                    if next_stripped == "{":
                        return idx + 1
    return 0

def _capture_function_entry(entry_line, func_name):
    """Emit a function-entry step at the signature line.

    All local variables are shown as "?" (uninitialized).  The call stack
    is built from GDB's current frame chain.  Heap objects from outer frames
    are preserved.
    """
    try:
        call_stack = get_call_stack()
        stdout_text = read_stdout()

        # Build locals for the current frame — all as "?"
        # We need to get variable names/types from the block
        entry_locals = {}
        try:
            frame = gdb.selected_frame()
            block = frame.block()
            depth = 0
            while block is not None and depth < 5:
                for sym in block:
                    if not (sym.is_variable or sym.is_argument):
                        continue
                    if sym.addr_class == gdb.SYMBOL_LOC_TYPEDEF:
                        continue
                    name = sym.name
                    if not name or name.startswith("__") or name.startswith("_"):
                        continue
                    try:
                        type_str = str(sym.type) if sym.type else "int"
                        if "*" in type_str:
                            entry_locals[name] = {"kind": "pointer", "type": type_str,
                                                   "value": "?", "addr": "0x0"}
                        else:
                            entry_locals[name] = {"kind": "simple", "type": type_str,
                                                   "value": "?"}
                    except:
                        pass
                func = block.function
                if func is not None:
                    break
                try:
                    parent = block.superblock
                    if parent is None or parent == block:
                        break
                    block = parent
                except:
                    break
                depth += 1
        except:
            pass

        # Collect heap objects from outer frame pointers (if any)
        heap_objects = []
        try:
            # Read heap from the caller frame
            caller = gdb.selected_frame().older()
            if caller:
                caller_locals = get_local_vars(caller, entry_line)
                seen_addrs = set()
                for name, val in caller_locals.items():
                    if isinstance(val, dict) and val.get("kind") == "pointer":
                        addr = val.get("addr", "0x0")
                        if val.get("value") == "?":
                            continue
                        if addr and addr != "0x0" and addr not in seen_addrs:
                            seen_addrs.add(addr)
                            deref = val.get("deref_value")
                            if deref is not None:
                                heap_objects.append({
                                    "addr": addr,
                                    "type": val.get("deref_type", "int"),
                                    "value": deref,
                                    "src_var": name,
                                })
        except:
            pass

        step = {
            "line": entry_line,
            "event": "call",
            "call_stack": [],
            "heap_objects": heap_objects,
            "stdout": stdout_text,
        }
        for i, f in enumerate(call_stack):
            if i == 0:
                # Current frame — all vars as "?"
                step["call_stack"].append({
                    "func": f["func"],
                    "line": entry_line,
                    "simple_vars": {k: v for k, v in entry_locals.items()
                                    if isinstance(v, dict) and v.get("kind") in ("simple", "string")},
                    "pointer_vars": {k: v for k, v in entry_locals.items()
                                     if isinstance(v, dict) and v.get("kind") == "pointer"},
                    "struct_vars": {},
                })
            else:
                # Parent frames — use the variables already captured by get_call_stack
                step["call_stack"].append({
                    "func": f["func"],
                    "line": f["line"],
                    "simple_vars": f.get("simple_vars", {}),
                    "pointer_vars": f.get("pointer_vars", {}),
                    "struct_vars": f.get("struct_vars", {}),
                })
        steps.append(step)
        step_idx[0] += 1
    except Exception as e:
        pass

# ── Main tracing logic ──

# Set breakpoints on ALL user-defined functions so 'next' will stop
# inside them when they're called.  This lets us step into user functions
# without getting stuck in library code.
try:
    # Set breakpoint at main
    gdb.execute("break main", to_string=True)

    # Find and set breakpoints on all other user functions
    try:
        funcs_output = gdb.execute("info functions", to_string=True)
        user_funcs = []
        in_user_file = False
        for line in funcs_output.split("\n"):
            # Track when we're in the user's source file section
            # With #line directive, the file shows as "user.cpp"
            if line.startswith("File ") and ("user.cpp" in line or ".cpp" in line):
                in_user_file = True
                continue
            elif line.startswith("File ") or line.startswith("Non-debugging"):
                in_user_file = False
                continue
            if in_user_file:
                # Lines like: "int add(int, int);" or "8:\tint main();"
                # Also: "void Square::Square(int);" or "int Square::area();"
                m = re.match(r"^\s*(?:\d+:\s*)?(?:[\w\s\*\&:]+)\s+((?:\w+::)*\w+)\s*\(", line)
                if m:
                    fname = m.group(1)
                    if fname != "main":
                        user_funcs.append(fname)

        for fname in user_funcs:
            try:
                gdb.execute("break {}".format(fname), to_string=True)
            except:
                pass
    except:
        pass
except:
    gdb.execute("break main", to_string=True)

# Run the program
gdb.execute("run", to_string=True)

# Redirect inferior stdout to a temp file (must be after run, when inferior is alive)
setup_stdout_capture()

# Find the user source file AFTER run (need a selected frame for info source)
_user_source_file = get_user_source_file()

# Step through the program using 'next' (steps over library calls,
# but stops at breakpoints inside user functions).
max_iters = 5000
i = 0
prev_line = -1
prev_func = ""
_prev_depth = 0  # track call stack depth for function-entry detection
while i < max_iters:
    try:
        frame = gdb.selected_frame()
        if frame is None:
            break

        if not is_user_function(frame):
            # In library code — step out
            try:
                gdb.execute("finish", to_string=True)
            except:
                break
            continue

        # Get current line
        sal = frame.find_sal()
        current_line = sal.line if sal else 0
        current_func = frame.function().name if frame.function() else "?"

        # Skip duplicate lines within the same function
        # (but allow re-entry to the same line in a different function, e.g. recursion)
        if current_line == prev_line and current_func == prev_func:
            gdb.execute("next", to_string=True)
            try:
                gdb.execute("info program", to_string=True)
            except:
                break
            continue

        # Initialize skip flag
        _skip_step = False

        # ── Function entry step ──
        # Python Tutor shows the function's opening line (e.g. "int main() {")
        # as a separate step when entering a function.  GDB's breakpoint skips
        # the prologue and stops at the first executable statement, so we need
        # to manually insert a step at the function signature line.
        # Emit an entry step whenever the call stack depth increases — this
        # covers first entry AND recursive re-entry (same function, deeper).
        _cur_depth = len(get_call_stack())
        if _cur_depth > _prev_depth:
            _entry_line = _find_func_entry_line(current_func)
            if _entry_line > 0 and _entry_line <= current_line:
                _capture_function_entry(_entry_line, current_func)
                # If entry line is the same as current line, skip regular capture
                # to avoid duplicate. If different, regular capture will show the
                # first executable statement (a distinct step from the entry).
                if _entry_line == current_line:
                    _skip_step = True

        prev_line = current_line
        prev_func = current_func
        _prev_depth = _cur_depth

        # Check if this line should be skipped.
        # Python Tutor does NOT show the closing brace '}' of main() as a
        # separate step — it stops at 'return' as the last step.
        # But it DOES show '}' of other functions (e.g. add()).
        if _source_lines and 1 <= current_line <= len(_source_lines):
            _src = _source_lines[current_line - 1].strip()
            if _src == "}" and "main" in current_func:
                _skip_step = True

        # Capture current step (unless skipping — which includes duplicate
        # function-entry lines and closing braces of main)
        if not _skip_step:
            capture_step()

        # Step to next line — 'next' steps over library calls
        gdb.execute("next", to_string=True)

        # Check if program exited
        try:
            gdb.execute("info program", to_string=True)
        except:
            break

        i += 1
    except gdb.error:
        # Program may have exited normally
        break

# Output the trace as JSON
print("===TRACE_JSON_START===")
print(json.dumps(steps))
print("===TRACE_JSON_END===")
'''


def _prepare_source(source: str) -> str:
    """Prepare C++ source for tracing.

    Adds commonly-needed ``#include`` headers (only those not already
    present) and a ``#line 1 "user.cpp"`` directive so GDB reports line
    numbers that map 1:1 to the user's original source.

    The user **must** provide their own ``main()`` — no automatic
    wrapping is done.
    """
    # Standard headers to include if not already present
    std_headers = [
        "<iostream>", "<string>", "<vector>", "<map>",
        "<list>", "<set>", "<memory>",
    ]
    existing = set()
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#include"):
            m = re.search(r"#include\s*(<[^>]+>)", stripped)
            if m:
                existing.add(m.group(1))

    header_lines = [
        f"#include {h}" for h in std_headers if h not in existing
    ]

    # #line 1 "user.cpp" makes GDB report line numbers matching the
    # user's original source (1-indexed from the first line of their code).
    parts = []
    if header_lines:
        parts.append("\n".join(header_lines))
    parts.append('#line 1 "user.cpp"')
    parts.append(source)
    return "\n".join(parts)


def trace_cpp(
    source_code: str,
    max_steps: int = 5000,
    compiler: str = "g++",
    extra_flags: list[str] | None = None,
) -> list[dict]:
    """Trace C++ code execution and return a list of trace step dicts.

    Parameters
    ----------
    source_code : str
        C++ source code **with a ``main()`` function**.  The user is
        responsible for writing ``main()`` — no automatic wrapping is
        performed.  Common ``#include`` headers are added automatically.
    max_steps : int
        Maximum number of trace steps to capture.
    compiler : str
        C++ compiler to use (default: ``g++``).
    extra_flags : list[str] | None
        Additional compiler flags (e.g. ``["-std=c++17"]``).

    Returns
    -------
    list[dict]
        Trace steps compatible with :func:`render_trace`.
    """
    # Prepare source: add includes + #line directive so GDB line numbers
    # match the user's original source 1:1.
    wrapped = _prepare_source(source_code)

    # Validate: user must provide main()
    if not re.search(r'\bint\s+main\s*\(', source_code):
        return [{
            "line": 0,
            "event": "compile_error",
            "call_stack": [],
            "stdout": "Error: Your code must contain an 'int main()' function.\n"
                      "jupyter-cpp-tutor does not auto-wrap code — please write\n"
                      "your own main() function.\n\nExample:\n"
                      "  %%cpptutor\n"
                      "  int main() {\n"
                      "      int x = 1;\n"
                      "      return 0;\n"
                      "  }",
        }]

    with tempfile.TemporaryDirectory(prefix="jpt-cpp-") as tmpdir:
        src_path = os.path.join(tmpdir, "trace.cpp")
        bin_path = os.path.join(tmpdir, "trace.bin")
        script_path = os.path.join(tmpdir, "trace.py")

        # Write source
        with open(src_path, "w") as f:
            f.write(wrapped)

        # Compile with debug info, no optimization
        # Base flags: -g (debug), -O0 (no optimization — needed for GDB stepping)
        flags = ["-g", "-O0", "-o", bin_path, src_path]

        # Build the -std flag.  If extra_flags contains a -std=..., use
        # the user's value; otherwise default to c++23.
        std_flag = "-std=c++23"
        user_flags = list(extra_flags) if extra_flags else []
        for f in user_flags:
            if f.startswith("-std="):
                std_flag = f
                user_flags.remove(f)
                break
        flags = [std_flag] + flags

        # Prepend any remaining user flags (e.g. -Wall, -O2)
        # Note: user-specified -O overrides our -O0 (last wins in g++)
        if user_flags:
            flags = user_flags + flags

        compile_cmd = [compiler] + flags

        try:
            result = subprocess.run(
                compile_cmd, capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            return [{"line": 0, "event": "error", "call_stack": [], "stdout": "Compilation timed out (>30s)"}]

        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Extract just the error lines
            error_lines = [l for l in stderr.split('\n') if 'error:' in l.lower() or 'note:' in l.lower()]
            error_msg = '\n'.join(error_lines) if error_lines else stderr
            return [{"line": 0, "event": "compile_error", "call_stack": [], "stdout": error_msg}]

        # Write GDB script — inject source lines for brace detection
        source_lines_json = json.dumps(source_code.split('\n'))
        script_content = _GDB_SCRIPT.replace("__SOURCE_LINES_PLACEHOLDER__", source_lines_json)
        with open(script_path, "w") as f:
            f.write(script_content)

        # Run GDB in batch mode with the Python script
        gdb_cmd = [
            "gdb", "--batch",
            "-ex", "set pagination off",
            "-ex", "set print elements 0",
            "-ex", "set print object on",
            "-ex", f"file {bin_path}",
            "-ex", f"source -s {script_path}",
        ]

        try:
            result = subprocess.run(
                gdb_cmd, capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            return [{"line": 0, "event": "error", "call_stack": [], "stdout": "GDB execution timed out (>30s)"}]

        # Parse the trace JSON from GDB output
        output = result.stdout
        match = re.search(
            r"===TRACE_JSON_START===\s*(.*?)\s*===TRACE_JSON_END===",
            output,
            re.DOTALL,
        )
        if not match:
            # Check for GDB errors
            gdb_err = result.stderr.strip()
            if gdb_err:
                return [{"line": 0, "event": "error", "call_stack": [], "stdout": f"GDB error: {gdb_err}"}]
            return [{"line": 0, "event": "error", "call_stack": [], "stdout": "No trace output from GDB"}]

        try:
            steps = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            return [{"line": 0, "event": "error", "call_stack": [], "stdout": f"JSON parse error: {e}"}]

        # Cap steps
        if len(steps) > max_steps:
            steps = steps[:max_steps]

        # Add source code to each step for the renderer
        user_source_lines = source_code.split('\n')
        for step in steps:
            step["source_lines"] = user_source_lines

        return steps
