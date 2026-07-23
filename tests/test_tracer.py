"""Tests for jupyter_cpp_tutor.tracer.

Tests use the Python Tutor-compatible stepping model:
  - Step 0 is the function-entry step (e.g. ``int main() {``) with all
    local variables shown as ``"?"`` (uninitialized).
  - GDB stops BEFORE a line executes, so a variable assigned on line N
    shows its value starting from step N+1 (the step that points at the
    next line).
  - The closing brace ``}`` of ``main()`` is NOT shown as a step.
  - The closing brace ``}`` of other functions IS shown.
  - Heap objects are removed after ``delete`` executes.
"""
import json
import os
import pytest

from jupyter_cpp_tutor.tracer import trace_cpp, _prepare_source


def has_gdb():
    """Check if GDB is available."""
    import shutil
    return shutil.which("gdb") is not None and shutil.which("g++") is not None


skip_if_no_gdb = pytest.mark.skipif(not has_gdb(), reason="GDB or g++ not installed")


# ── _prepare_source tests ──

class TestPrepareSource:
    def test_includes_added(self):
        code = "int main() { return 0; }"
        prepared = _prepare_source(code)
        for inc in ["iostream", "string", "vector", "map", "list", "set", "memory"]:
            assert f"#include <{inc}>" in prepared

    def test_line_directive_present(self):
        code = "int main() { return 0; }"
        prepared = _prepare_source(code)
        assert '#line 1 "user.cpp"' in prepared

    def test_user_code_preserved(self):
        code = "int main() {\n    int x = 1;\n    return 0;\n}"
        prepared = _prepare_source(code)
        assert "int main() {" in prepared
        assert "int x = 1;" in prepared

    def test_no_double_include(self):
        code = "#include <iostream>\nint main() { return 0; }"
        prepared = _prepare_source(code)
        # iostream should appear only once
        assert prepared.count("#include <iostream>") == 1

    def test_using_namespace_preserved(self):
        code = "using namespace std;\nint main() { return 0; }"
        prepared = _prepare_source(code)
        assert "using namespace std;" in prepared


# ── trace_cpp tests (require GDB) ──

@skip_if_no_gdb
class TestTraceCpp:
    def test_simple_variables(self):
        """Variables show '?' before their assignment line, then the value."""
        code = "int main() {\n    int x = 1;\n    int y = x + 2;\n    int z = x * y;\n    return 0;\n}"
        steps = trace_cpp(code)
        src = code.split('\n')
        assert len(steps) >= 5  # func-entry + 3 statements + return
        # Step 0: function entry — all vars uninitialized
        assert steps[0]["line"] == 1  # int main() {
        sv0 = steps[0]["call_stack"][0]["simple_vars"]
        assert sv0["x"]["value"] == "?"
        # Step 1: about to execute "int x = 1;" — x still ?
        assert steps[1]["line"] == 2
        assert steps[1]["call_stack"][0]["simple_vars"]["x"]["value"] == "?"
        # Step 2: x=1 now, about to execute "int y = x + 2;"
        assert steps[2]["line"] == 3
        assert steps[2]["call_stack"][0]["simple_vars"]["x"]["value"] == "1"
        # Step 3: y=3 now, about to execute "int z = x * y;"
        assert steps[3]["line"] == 4
        sv3 = steps[3]["call_stack"][0]["simple_vars"]
        assert sv3["x"]["value"] == "1"
        assert sv3["y"]["value"] == "3"
        # Step 4: z=3 now, about to execute "return 0;"
        assert steps[4]["line"] == 5
        sv4 = steps[4]["call_stack"][0]["simple_vars"]
        assert sv4["x"]["value"] == "1"
        assert sv4["y"]["value"] == "3"
        assert sv4["z"]["value"] == "3"

    def test_line_numbers_match_source(self):
        """Verify GDB line numbers map 1:1 to user source lines."""
        code = "int main() {\n    int x = 1;\n    int y = x + 2;\n    return 0;\n}"
        steps = trace_cpp(code)
        # Step 0: line 1 = "int main() {" (function entry)
        assert steps[0]["line"] == 1
        # Step 1: line 2 = "int x = 1;"
        assert steps[1]["line"] == 2
        # Step 2: line 3 = "int y = x + 2;"
        assert steps[2]["line"] == 3
        # Step 3: line 4 = "return 0;"
        assert steps[3]["line"] == 4
        # No step for "}" (closing brace of main)

    def test_no_closing_brace_for_main(self):
        """The closing brace '}' of main() should NOT be a step."""
        code = "int main() {\n    int x = 1;\n    return 0;\n}"
        steps = trace_cpp(code)
        src = code.split('\n')
        for s in steps:
            assert src[s["line"] - 1].strip() != "}", \
                f"Step at line {s['line']} is a closing brace '}}'"

    def test_for_loop(self):
        code = "int main() {\n    int sum = 0;\n    for (int i = 1; i <= 3; i++) {\n        sum += i;\n    }\n    return 0;\n}"
        steps = trace_cpp(code)
        assert len(steps) >= 8  # at least 8 steps for 3 iterations + entry
        # Final state should have sum=6
        last_step = steps[-1]
        assert last_step["call_stack"][0]["simple_vars"]["sum"]["value"] == "6"

    def test_function_call(self):
        """Function calls produce entry steps and 2-frame call stacks."""
        code = "int add(int a, int b) {\n    return a + b;\n}\nint main() {\n    int x = add(3, 4);\n    return 0;\n}"
        steps = trace_cpp(code)
        src = code.split('\n')
        # Should have function-entry steps for both main and add
        lines = [s["line"] for s in steps]
        assert 4 in lines, "Should have main() entry step at line 4"
        assert 1 in lines, "Should have add() entry step at line 1"
        # Should have at least one step with 2 frames (add + main)
        has_two_frames = any(len(s["call_stack"]) >= 2 for s in steps)
        assert has_two_frames, "Function call should produce 2 frames in call stack"
        # Find the step inside add() where a=3, b=4 (after entry, at return a+b)
        add_step = None
        for s in steps:
            for f in s["call_stack"]:
                if "add" in f["func"] and f.get("simple_vars", {}).get("a", {}).get("value") == "3":
                    add_step = f
                    break
            if add_step:
                break
        assert add_step is not None, "Should have a step inside add() with a=3"
        assert add_step["simple_vars"]["a"]["value"] == "3"
        assert add_step["simple_vars"]["b"]["value"] == "4"
        # Final step should have x=7
        last = steps[-1]
        assert last["call_stack"][0]["simple_vars"]["x"]["value"] == "7"

    def test_function_entry_uninitialized(self):
        """Function-entry steps show all locals as '?' (uninitialized)."""
        code = "int add(int a, int b) {\n    return a + b;\n}\nint main() {\n    int x = add(3, 4);\n    return 0;\n}"
        steps = trace_cpp(code)
        # Find the add() entry step
        add_entry = None
        for s in steps:
            if s.get("event") == "call" and s["line"] == 1:
                add_entry = s
                break
        assert add_entry is not None, "Should have add() entry step at line 1"
        # Arguments should be '?' at entry
        sv = add_entry["call_stack"][0]["simple_vars"]
        assert sv["a"]["value"] == "?"
        assert sv["b"]["value"] == "?"

    def test_closing_brace_shown_for_non_main(self):
        """The closing brace '}' of add() SHOULD be shown as a step."""
        code = "int add(int a, int b) {\n    return a + b;\n}\nint main() {\n    int x = add(3, 4);\n    return 0;\n}"
        steps = trace_cpp(code)
        src = code.split('\n')
        has_add_close = any(s["line"] == 3 for s in steps)
        assert has_add_close, "Should have a step at line 3 (closing brace of add)"

    def test_pointer(self):
        code = "int main() {\n    int x = 42;\n    int *p = &x;\n    return 0;\n}"
        steps = trace_cpp(code)
        # Find step with p as a pointer (after p is assigned, i.e. at return 0)
        ptr_step = None
        for s in steps:
            if "p" in s["call_stack"][0].get("pointer_vars", {}):
                pv = s["call_stack"][0]["pointer_vars"]
                if pv["p"].get("addr", "0x0") != "0x0":
                    ptr_step = s
                    break
        assert ptr_step is not None, "Should have a step with initialized pointer p"
        ptr_vars = ptr_step["call_stack"][0]["pointer_vars"]
        assert ptr_vars["p"]["kind"] == "pointer"
        assert ptr_vars["p"]["deref_value"]["value"] == "42"

    def test_pointer_uninitialized(self):
        """Pointer shows '?' before its assignment line executes."""
        code = "int main() {\n    int x = 42;\n    int *p = &x;\n    return 0;\n}"
        steps = trace_cpp(code)
        # At function entry and at line 2 (int x = 42), p should be '?'
        for s in steps[:2]:
            pv = s["call_stack"][0].get("pointer_vars", {})
            if "p" in pv:
                assert pv["p"]["value"] == "?", \
                    f"Pointer p should be '?' at step with line {s['line']}"

    def test_array(self):
        code = "int main() {\n    int arr[3] = {10, 20, 30};\n    return 0;\n}"
        steps = trace_cpp(code)
        # Find step with arr (after it's assigned)
        arr_step = None
        for s in steps:
            if "arr" in s["call_stack"][0].get("struct_vars", {}):
                arr_step = s
                break
        assert arr_step is not None, "Should have a step with array arr"
        struct_vars = arr_step["call_stack"][0]["struct_vars"]
        assert struct_vars["arr"]["kind"] == "array"
        assert struct_vars["arr"]["size"] == 3
        assert struct_vars["arr"]["elements"][0]["value"] == "10"
        assert struct_vars["arr"]["elements"][1]["value"] == "20"
        assert struct_vars["arr"]["elements"][2]["value"] == "30"

    def test_struct(self):
        code = "struct Point {\n    int x;\n    int y;\n};\nint main() {\n    Point p;\n    p.x = 3;\n    p.y = 4;\n    return 0;\n}"
        steps = trace_cpp(code)
        # Find step with p having both x and y assigned
        for s in steps:
            sv = s["call_stack"][0].get("struct_vars", {})
            if "p" in sv:
                fields = {f["name"]: f["value"]["value"] for f in sv["p"]["fields"]}
                if fields.get("x") == "3" and fields.get("y") == "4":
                    return  # pass
        pytest.fail("Should have a step with Point p having x=3, y=4")

    def test_compile_error(self):
        code = "int main() {\n    int x = ;\n    return 0;\n}"  # syntax error
        steps = trace_cpp(code)
        assert len(steps) == 1
        assert steps[0]["event"] == "compile_error"

    def test_missing_main_error(self):
        """Code without main() should give a clear error message."""
        code = "int x = 1;"
        steps = trace_cpp(code)
        assert len(steps) == 1
        assert steps[0]["event"] == "compile_error"
        assert "main()" in steps[0]["stdout"]

    def test_step_structure(self):
        code = "int main() {\n    int x = 1;\n    return 0;\n}"
        steps = trace_cpp(code)
        for step in steps:
            assert "line" in step
            assert "event" in step
            assert "call_stack" in step
            assert "stdout" in step
            for frame in step["call_stack"]:
                assert "func" in frame
                assert "line" in frame
                assert "simple_vars" in frame
                assert "pointer_vars" in frame
                assert "struct_vars" in frame

    def test_stdout_capture(self):
        code = "#include <iostream>\nint main() {\n    std::cout << \"Hello\" << std::endl;\n    return 0;\n}"
        steps = trace_cpp(code)
        assert len(steps) > 0

    def test_heap_objects(self):
        """Verify heap objects are captured for new-allocated memory."""
        code = "int main() {\n    int *p = new int(42);\n    delete p;\n    return 0;\n}"
        steps = trace_cpp(code)
        # After 'new int(42)' executes, there should be a heap object with value 42
        has_heap_42 = False
        for s in steps:
            for h in s.get("heap_objects", []):
                if h.get("value", {}).get("value") == "42":
                    has_heap_42 = True
                    break
        assert has_heap_42, "Should have a heap object with value 42"

    def test_heap_cleared_after_delete(self):
        """After delete executes, the heap object should be gone."""
        code = "int main() {\n    int *p = new int(42);\n    delete p;\n    return 0;\n}"
        steps = trace_cpp(code)
        src = code.split('\n')
        # The step at "return 0;" is AFTER delete has executed — heap should be empty
        for s in steps:
            if s["line"] == 4:  # return 0; — delete already executed
                assert len(s.get("heap_objects", [])) == 0, \
                    "Heap should be empty after delete"

    def test_recursion_gcd(self):
        """Euclidean GCD algorithm — recursive function calls."""
        code = """int gcd(int a, int b) {
    if (b == 0) return a;
    return gcd(b, a % b);
}
int main() {
    int result = gcd(48, 18);
    return 0;
}"""
        steps = trace_cpp(code)
        src = code.split('\n')
        # Should have multiple gcd() entry steps (recursion)
        gcd_entries = [s for s in steps if s.get("event") == "call" and "gcd" in str(s["call_stack"][0]["func"])]
        assert len(gcd_entries) >= 3, \
            f"GCD(48,18) should recurse at least 3 times, got {len(gcd_entries)} entries"
        # Final result should be 6 (gcd of 48 and 18)
        last = steps[-1]
        assert last["call_stack"][0]["simple_vars"]["result"]["value"] == "6"
        # Should have multiple frames at deepest recursion level
        max_depth = max(len(s["call_stack"]) for s in steps)
        assert max_depth >= 3, f"Should have at least 3 frames at deepest point, got {max_depth}"
