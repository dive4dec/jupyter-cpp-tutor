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

    def test_stderr_panel_present(self):
        """The stderr panel (label + body) is present in the rendered HTML."""
        steps = [{"line": 1, "event": "line", "stdout": "", "stderr": "", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        assert "jpt-stderr" in html
        # srcdoc escapes quotes: id=&quot;stderr&quot;
        assert "id=&quot;stderr&quot;" in html
        assert "stderr-label" in html

    def test_stderr_content_in_steps_json(self):
        """Non-empty stderr on a step is carried into the embedded steps JSON."""
        steps = [{"line": 1, "event": "line", "stdout": "out",
                  "stderr": "some warning here", "call_stack": []}]
        html = render_trace(steps, source_code="int x = 1;")
        assert "some warning here" in html

    def test_reference_var_rendered(self):
        """A reference variable (ref=True, ref_type) renders its reference
        type and the (&) alias marker."""
        steps = [{
            "line": 2, "event": "line", "stdout": "", "stderr": "",
            "call_stack": [{
                "func": "main()", "line": 2,
                "simple_vars": {"r": {"kind": "string", "type": "string",
                                       "value": '"hi"', "ref": True,
                                       "ref_type": "std::string &"}},
                "pointer_vars": {}, "struct_vars": {},
            }],
        }]
        html = render_trace(steps, source_code="std::string &r = msg;")
        # ref_type is embedded in the steps JSON
        assert "std::string &" in html
        # The (&) alias marker class is defined and used
        assert "jpt-var-ref" in html


class TestScrollMode:
    """The optional scrolling feature: a navbar toggle + a `scroll` render flag
    switch the window between a fixed height (inner column scroll) and a
    fit-all height that grows to show all content (no inner scrollbars)."""

    STEPS = [{"line": 1, "event": "line", "stdout": "", "call_stack": [], "heap_objects": []}]
    SRC = "int x = 1;"

    def _inner(self, scroll=True):
        return _generate_inner_html(self.STEPS, self.SRC, 500, scroll=scroll)

    def test_toggle_button_present(self):
        html = render_trace(self.STEPS, source_code=self.SRC)
        assert "btn-scroll-mode" in html

    def test_scroll_mode_default_widget_class(self):
        h = self._inner(scroll=True)
        assert 'class="jpt-widget"' in h
        assert "jpt-widget no-scroll" not in h
        assert "var scrollMode = true;" in h

    def test_no_scroll_widget_class(self):
        h = self._inner(scroll=False)
        assert 'class="jpt-widget no-scroll"' in h
        assert "var scrollMode = false;" in h

    def test_no_scroll_css_rules_present(self):
        h = self._inner(scroll=False)
        assert ".jpt-widget.no-scroll" in h
        assert "height: auto !important" in h      # overrides the inline fixed height
        # columns stop scrolling internally
        assert ".jpt-widget.no-scroll .jpt-code-section" in h
        assert "overflow: visible" in h

    def test_toggle_js_wired(self):
        h = self._inner(scroll=False)
        # the click handler flips scrollMode and re-applies the class
        assert "scrollBtn.onclick" in h
        assert "applyScrollMode" in h
        # applyScrollMode toggles the class off/on based on scrollMode
        assert "classList.toggle('no-scroll', !scrollMode)" in h

    def test_render_trace_scroll_false_carries_class_into_srcdoc(self):
        html = render_trace(self.STEPS, source_code=self.SRC, scroll=False)
        # inner html is escaped for the srcdoc attribute; the class survives
        assert "jpt-widget no-scroll" in html

    def test_render_trace_default_is_scroll(self):
        html = render_trace(self.STEPS, source_code=self.SRC)
        assert "jpt-widget no-scroll" not in html

    def test_render_trace_height_still_applied_in_scroll_mode(self):
        html = render_trace(self.STEPS, source_code=self.SRC, height=640, scroll=True)
        assert "height:640px" in html.replace(' ', '') or "height: 640px" in html or "640px" in html
