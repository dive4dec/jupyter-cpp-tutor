"""Tests for jupyter_cpp_tutor.renderer."""
import json
import pytest

from jupyter_cpp_tutor.renderer import render_trace, _generate_inner_html


class TestRenderTrace:
    def test_empty_steps(self):
        html = render_trace([], source_code="int x = 1;")
        assert "No trace steps" in html

    def test_basic_render(self):
        steps = [
            {
                "line": 1,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {
                        "func": "main()",
                        "line": 1,
                        "simple_vars": {"x": {"kind": "simple", "type": "int", "value": "1"}},
                        "pointer_vars": {},
                        "struct_vars": {},
                    }
                ],
            }
        ]
        html = render_trace(steps, source_code="int x = 1;")
        assert "iframe" in html
        assert "srcdoc" in html
        assert "jpt-iframe" in html

    def test_slider_present(self):
        steps = [{"line": 1, "event": "line", "stdout": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        # The type="range" is inside srcdoc attribute where quotes are escaped
        assert "jpt-slider" in html
        assert "range" in html

    def test_step_navigation_buttons(self):
        steps = [{"line": 1, "event": "line", "stdout": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        assert "⏮" in html  # first
        assert "◀" in html  # prev
        assert "▶" in html  # next
        assert "⏭" in html  # last

    def test_code_display(self):
        steps = [{"line": 2, "event": "line", "stdout": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;\nint y = 2;")
        assert "jpt-code-section" in html
        assert "jpt-code-line" in html
        assert "current" in html  # current line highlighting

    def test_frame_display(self):
        steps = [
            {
                "line": 1,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {
                        "func": "main()",
                        "line": 1,
                        "simple_vars": {"x": {"kind": "simple", "type": "int", "value": "42"}},
                        "pointer_vars": {},
                        "struct_vars": {},
                    }
                ],
            }
        ]
        html = render_trace(steps, source_code="int x = 42;")
        assert "jpt-frame" in html
        assert "jpt-frame-header" in html
        assert "main()" in html

    def test_pointer_rendering(self):
        steps = [
            {
                "line": 2,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {
                        "func": "main()",
                        "line": 2,
                        "simple_vars": {},
                        "pointer_vars": {
                            "p": {
                                "kind": "pointer",
                                "addr": "0x7fff1234",
                                "deref_type": "int",
                                "deref_value": {"kind": "simple", "type": "int", "value": "42"},
                            }
                        },
                        "struct_vars": {},
                    }
                ],
            }
        ]
        html = render_trace(steps, source_code="int x = 42;\nint *p = &x;")
        assert "jpt-pointer" in html
        assert "0x7fff1234" in html
        assert "42" in html

    def test_array_rendering(self):
        steps = [
            {
                "line": 1,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {
                        "func": "main()",
                        "line": 1,
                        "simple_vars": {},
                        "pointer_vars": {},
                        "struct_vars": {
                            "arr": {
                                "kind": "array",
                                "type": "int [3]",
                                "size": 3,
                                "elements": [
                                    {"kind": "simple", "type": "int", "value": "10"},
                                    {"kind": "simple", "type": "int", "value": "20"},
                                    {"kind": "simple", "type": "int", "value": "30"},
                                ],
                            }
                        },
                    }
                ],
            }
        ]
        html = render_trace(steps, source_code="int arr[3] = {10, 20, 30};")
        assert "jpt-array" in html
        assert "10" in html
        assert "20" in html
        assert "30" in html

    def test_struct_rendering(self):
        steps = [
            {
                "line": 4,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {
                        "func": "main()",
                        "line": 4,
                        "simple_vars": {},
                        "pointer_vars": {},
                        "struct_vars": {
                            "p": {
                                "kind": "struct",
                                "type": "Point",
                                "fields": [
                                    {"name": "x", "value": {"kind": "simple", "type": "int", "value": "3"}},
                                    {"name": "y", "value": {"kind": "simple", "type": "int", "value": "4"}},
                                ],
                            }
                        },
                    }
                ],
            }
        ]
        html = render_trace(steps, source_code="struct Point { int x; int y; };\nPoint p;\np.x = 3;\np.y = 4;")
        assert "jpt-struct" in html
        assert "Point" in html
        assert "3" in html
        assert "4" in html

    def test_dividers_present(self):
        steps = [{"line": 1, "event": "line", "stdout": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        assert "jpt-divider" in html
        assert "divider1" in html
        assert "divider2" in html

    def test_auto_resize_script(self):
        steps = [{"line": 1, "event": "line", "stdout": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        assert "setInterval" in html
        assert "autoResize" in html or "auto-resize" in html.lower()

    def test_output_display(self):
        steps = [
            {
                "line": 1,
                "event": "line",
                "stdout": "Hello World\n",
                "call_stack": [],
            }
        ]
        html = render_trace(steps, source_code='std::cout << "Hello World";')
        assert "jpt-output" in html
        assert "Hello World" in html

    def test_multiple_frames_in_call_stack(self):
        steps = [
            {
                "line": 2,
                "event": "line",
                "stdout": "",
                "call_stack": [
                    {"func": "add(int, int)", "line": 2, "simple_vars": {"a": {"kind": "simple", "type": "int", "value": "3"}, "b": {"kind": "simple", "type": "int", "value": "4"}}, "pointer_vars": {}, "struct_vars": {}},
                    {"func": "main()", "line": 5, "simple_vars": {}, "pointer_vars": {}, "struct_vars": {}},
                ],
            }
        ]
        html = render_trace(steps, source_code="int add(int a, int b) {\n    return a + b;\n}\nint x = add(3, 4);")
        assert "add(int, int)" in html
        assert "main()" in html

    def test_step_count_in_html(self):
        steps = [
            {"line": i, "event": "line", "stdout": "", "call_stack": []}
            for i in range(1, 6)
        ]
        html = render_trace(steps, source_code="int x = 1;")
        assert "Step 1 of 5" in html

    def test_error_step(self):
        steps = [{"line": 0, "event": "error", "stdout": "Compilation failed", "call_stack": []}]
        html = render_trace(steps, source_code="int x = ;")
        # Should still render, showing the error
        assert "iframe" in html
