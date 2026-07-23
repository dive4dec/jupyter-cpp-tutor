"""Render a C++ trace as interactive HTML inside an iframe srcdoc.

Adapted from jupyter-python-tutor's renderer, with C++-specific features:
  - C++ types: int, char, bool, float, pointers, arrays, structs
  - SVG arrows from pointer variables to their targets
  - Call stack with C++ function signatures
  - Stack frames + heap objects (for dynamically allocated memory)
  - Draggable dividers between code/frames/heap columns

Layout (OPT_Mentor / Python Tutor style):

  ┌──────────────────────────────────────────────────────────┐
  │  ⏮ ◀  [====slider====] ▶ ⏭   Step 3 of 15             │  ← nav bar
  ├──────────────────────────────────────────────────────────┤
  │  Program Output                                          │
  ├──────────────┬───────────────────────────────────────────┤
  │  Code        │  Frames         │  Objects (heap)          │
  │  (current    │  (call stack)   │  (new/malloc'd objects)  │
  │   line ►)    │                 │                          │
  └──────────────┴───────────────────────────────────────────┘
"""
from __future__ import annotations

import html
import json

__all__ = ["render_trace"]


def _generate_inner_html(steps: list[dict], source_code: str, height: int = 500) -> str:
    """Generate the full HTML page that goes inside the iframe srcdoc."""
    if not steps:
        return '<!DOCTYPE html><html><body><p style="color:red;">No trace steps to display.</p></body></html>'

    # Determine source lines
    if source_code:
        source_lines = source_code.splitlines()
    else:
        max_line = max((s.get("line", 0) for s in steps), default=0)
        source_lines = [""] * max_line

    n_steps = len(steps)

    # Prepare step data as JSON
    clean_steps = []
    for step in steps:
        clean_step = {
            "line": step.get("line", 0),
            "stdout": step.get("stdout", ""),
            "call_stack": [],
            "heap_objects": step.get("heap_objects", []),
            "event": step.get("event", ""),
        }
        for frame_info in step.get("call_stack", []):
            clean_frame = {
                "func": frame_info.get("func", "main"),
                "line": frame_info.get("line", 0),
                "simple_vars": frame_info.get("simple_vars", {}),
                "pointer_vars": frame_info.get("pointer_vars", {}),
                "struct_vars": frame_info.get("struct_vars", {}),
            }
            clean_step["call_stack"].append(clean_frame)
        clean_steps.append(clean_step)

    steps_json = json.dumps(clean_steps, ensure_ascii=False)
    source_json = json.dumps(source_lines, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'DejaVu Sans', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
  color: #1f2937;
  background: #fff;
  overflow: hidden;
}}
.jpt-widget {{
  display: flex;
  flex-direction: column;
  border: 1px solid #d4d4d4;
  border-radius: 6px;
  overflow: hidden;
}}
/* Nav bar */
.jpt-navbar {{
  display: flex;
  align-items: center;
  padding: 4px 10px;
  background: #f9fafb;
  border-bottom: 1px solid #d4d4d4;
  gap: 6px;
  flex-shrink: 0;
}}
.jpt-navbar button {{
  padding: 2px 8px;
  font-size: 12px;
  border: 1px solid #d4d4d4;
  border-radius: 3px;
  background: #fff;
  cursor: pointer;
  line-height: 1.5;
}}
.jpt-navbar button:hover {{ background: #f0f0f0; }}
.jpt-navbar button:disabled {{ opacity: 0.4; cursor: default; }}
.jpt-slider {{
  flex: 1;
  accent-color: #3b82f6;
}}
.jpt-step-label {{
  font-size: 12px;
  color: #6b7280;
  min-width: 100px;
  text-align: right;
}}
/* Output */
.jpt-output-label {{
  padding: 2px 10px;
  background: #dcfce7;
  border-bottom: 1px solid #d4d4d4;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 10px;
  font-weight: bold;
  color: #166534;
  flex-shrink: 0;
}}
.jpt-output {{
  padding: 4px 10px;
  background: #f0fdf4;
  border-bottom: 1px solid #d4d4d4;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  min-height: 24px;
  max-height: 120px;
  overflow-y: auto;
  flex-shrink: 0;
}}
/* Main content area */
.jpt-content {{
  display: flex;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}}
/* Code section */
.jpt-code-section {{
  flex: 0 0 40%;
  min-width: 30px;
  border-right: 1px solid #d4d4d4;
  overflow: auto;
  background: #fafafa;
}}
.jpt-code-line {{
  display: flex;
  padding: 0;
  min-height: 20px;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 12px;
}}
.jpt-line-num {{
  width: 36px;
  text-align: right;
  padding: 0 8px 0 4px;
  color: #9ca3af;
  user-select: none;
  flex-shrink: 0;
}}
.jpt-line-code {{
  padding: 0 8px;
  white-space: pre;
  flex: 1;
}}
.jpt-code-line.executed {{
  background: #dcfce7;
  border-left: 3px solid #22c55e;
}}
.jpt-code-line.current {{
  background: #fef3c7;
  border-left: 3px solid #f59e0b;
}}
.jpt-code-line.current .jpt-line-code {{
  font-weight: bold;
}}
.jpt-code-line.current .jpt-line-num::before {{
  content: "►";
  color: #f59e0b;
  margin-right: 2px;
}}
/* Divider */
.jpt-divider {{
  width: 4px;
  background: #e5e7eb;
  cursor: col-resize;
  flex-shrink: 0;
  transition: background 0.15s;
}}
.jpt-divider:hover {{ background: #3b82f6; }}
.jpt-divider.collapsed {{ background: #9ca3af; cursor: pointer; }}
/* Frames section */
.jpt-frames-section {{
  flex: 1;
  border-right: 1px solid #d4d4d4;
  overflow: auto;
  padding: 6px;
  min-width: 30px;
}}
.jpt-frame {{
  border: 1px solid #d4d4d4;
  border-radius: 4px;
  margin-bottom: 2px;
  background: #fff;
}}
.jpt-frame-header {{
  background: #e0e7ff;
  padding: 3px 8px;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 12px;
  font-weight: bold;
  border-radius: 3px 3px 0 0;
  color: #3730a3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.jpt-frame-line {{
  font-weight: normal;
  font-size: 10px;
  color: #6b7280;
  margin-left: 4px;
}}
.jpt-frame-body {{
  padding: 4px 8px;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 12px;
}}
.jpt-var-row {{
  display: flex;
  align-items: flex-start;
  padding: 1px 0;
  gap: 4px;
}}
.jpt-var-name {{
  color: #1e40af;
  font-weight: bold;
  min-width: 40px;
}}
.jpt-var-type {{
  color: #6b7280;
  font-size: 11px;
}}
.jpt-var-value {{
  color: #166534;
}}
.jpt-var-arrow {{
  color: #dc2626;
  cursor: pointer;
  font-size: 11px;
}}
/* Struct display */
.jpt-struct {{
  border: 1px solid #e5e7eb;
  border-radius: 3px;
  margin: 2px 0;
  padding: 2px 4px;
  background: #f9fafb;
}}
.jpt-struct-header {{
  font-weight: bold;
  color: #7c2d12;
  font-size: 11px;
}}
.jpt-struct-field {{
  display: flex;
  padding: 1px 0;
  padding-left: 12px;
  gap: 4px;
}}
/* Array display */
.jpt-array {{
  display: inline-flex;
  gap: 1px;
  margin: 1px 0;
}}
.jpt-array-elem {{
  border: 1px solid #d4d4d4;
  padding: 1px 6px;
  background: #eff6ff;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 11px;
  text-align: center;
  min-width: 28px;
}}
.jpt-array-elem .jpt-elem-val {{
  color: #166534;
}}
/* Pointer display */
.jpt-pointer {{
  color: #dc2626;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 11px;
}}
.jpt-pointer-addr {{
  color: #6b7280;
}}
/* Heap section */
.jpt-heap-section {{
  flex: 1;
  overflow: auto;
  padding: 6px;
  min-width: 30px;
}}
.jpt-heap-empty {{
  color: #9ca3af;
  font-style: italic;
  padding: 8px;
  text-align: center;
}}
.jpt-heap-obj {{
  border: 2px solid #f59e0b;
  border-radius: 6px;
  margin-bottom: 8px;
  background: #fffbeb;
  padding: 6px 10px;
  font-family: 'DejaVu Sans Mono', 'Consolas', monospace;
  font-size: 12px;
  position: relative;
}}
.jpt-heap-addr {{
  font-size: 10px;
  color: #6b7280;
  margin-bottom: 2px;
}}
.jpt-heap-type {{
  font-size: 11px;
  color: #92400e;
  font-weight: bold;
  margin-bottom: 4px;
  border-bottom: 1px solid #fde68a;
  padding-bottom: 2px;
}}
.jpt-heap-val {{
  font-size: 13px;
}}
/* SVG overlay for arrows */
.jpt-svg-overlay {{
  position: absolute;
  pointer-events: none;
  z-index: 10;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}}
</style>
</head>
<body>
<div class="jpt-widget" style="height:{height}px;position:relative;">
  <div class="jpt-navbar">
    <button id="btn-first" title="First">⏮</button>
    <button id="btn-prev" title="Previous">◀</button>
    <input type="range" class="jpt-slider" id="slider" min="0" max="{n_steps - 1}" value="0">
    <button id="btn-next" title="Next">▶</button>
    <button id="btn-last" title="Last">⏭</button>
    <span class="jpt-step-label" id="step-label">Step 1 of {n_steps}</span>
  </div>
  <div class="jpt-output-label">Program output (stdout)</div>
  <div class="jpt-output" id="output"></div>
  <div class="jpt-content" id="content">
    <div class="jpt-code-section" id="code-section"></div>
    <div class="jpt-divider" id="divider1"></div>
    <div class="jpt-frames-section" id="frames-section"></div>
    <div class="jpt-divider" id="divider2"></div>
    <div class="jpt-heap-section" id="heap-section"></div>
  </div>
  <svg class="jpt-svg-overlay" id="svg-overlay"><defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#ef4444"></polygon></marker></defs></svg>
</div>
<script>
var steps = {steps_json};
var sourceLines = {source_json};
var currentStep = 0;

// ── Navigation ──
var slider = document.getElementById('slider');
var stepLabel = document.getElementById('step-label');
var btnFirst = document.getElementById('btn-first');
var btnPrev = document.getElementById('btn-prev');
var btnNext = document.getElementById('btn-next');
var btnLast = document.getElementById('btn-last');

function gotoStep(idx) {{
  currentStep = Math.max(0, Math.min(idx, steps.length - 1));
  slider.value = currentStep;
  stepLabel.textContent = 'Step ' + (currentStep + 1) + ' of ' + steps.length;
  btnFirst.disabled = currentStep === 0;
  btnPrev.disabled = currentStep === 0;
  btnNext.disabled = currentStep === steps.length - 1;
  btnLast.disabled = currentStep === steps.length - 1;
  renderStep();
}}

slider.oninput = function() {{ gotoStep(parseInt(this.value)); }};
btnFirst.onclick = function() {{ gotoStep(0); }};
btnPrev.onclick = function() {{ gotoStep(currentStep - 1); }};
btnNext.onclick = function() {{ gotoStep(currentStep + 1); }};
btnLast.onclick = function() {{ gotoStep(steps.length - 1); }};

// ── Rendering ──
function escapeHtml(s) {{
  var div = document.createElement('div');
  div.textContent = String(s);
  return div.innerHTML;
}}

function renderVarVal(val) {{
  if (!val || typeof val !== 'object') return '<span class="jpt-var-value">' + escapeHtml(val) + '</span>';
  var kind = val.kind;
  if (kind === 'simple' || kind === 'string') {{
    return '<span class="jpt-var-type">' + escapeHtml(val.type || '') + '</span> ' +
           '<span class="jpt-var-value">' + escapeHtml(val.value) + '</span>';
  }}
  if (kind === 'pointer') {{
    var html = '<span class="jpt-pointer">';
    if (val.value === '?') {{
      // Uninitialized pointer
      html += '<span class="jpt-var-type">' + escapeHtml(val.type || '') + '</span> ';
      html += '<span class="jpt-var-value">?</span>';
      html += '</span>';
      return html;
    }}
    html += '<span class="jpt-pointer-addr">' + escapeHtml(val.addr || '0x0') + '</span>';
    if (val.deref_value) {{
      html += ' <span class="jpt-var-arrow" data-addr="' + escapeHtml(val.addr) + '">➜</span>';
    }}
    html += '</span>';
    return html;
  }}
  if (kind === 'array') {{
    var html = '<span class="jpt-var-type">' + escapeHtml(val.type || '') + '</span> ';
    html += '<div class="jpt-array">';
    for (var i = 0; i < (val.elements || []).length; i++) {{
      var elem = val.elements[i];
      html += '<div class="jpt-array-elem"><span class="jpt-elem-val">' + escapeHtml(elem.value || '') + '</span></div>';
    }}
    html += '</div>';
    return html;
  }}
  if (kind === 'struct') {{
    var html = '<div class="jpt-struct">';
    html += '<div class="jpt-struct-header">' + escapeHtml(val.type || 'struct') + '</div>';
    for (var i = 0; i < (val.fields || []).length; i++) {{
      var field = val.fields[i];
      html += '<div class="jpt-struct-field">';
      html += '<span class="jpt-var-name">' + escapeHtml(field.name) + '</span>';
      html += renderVarVal(field.value);
      html += '</div>';
    }}
    html += '</div>';
    return html;
  }}
  if (kind === 'container') {{
    var html = '<div class="jpt-struct">';
    html += '<div class="jpt-struct-header">' + escapeHtml(val.type || 'container') + ' (size=' + (val.size || 0) + ')</div>';
    for (var i = 0; i < (val.elements || []).length; i++) {{
      var elem = val.elements[i];
      html += '<div class="jpt-struct-field">';
      html += '<span class="jpt-var-name">[' + i + ']</span>';
      html += renderVarVal(elem);
      html += '</div>';
    }}
    html += '</div>';
    return html;
  }}
  return '<span class="jpt-var-value">' + escapeHtml(JSON.stringify(val)) + '</span>';
}}

function renderFrame(frame, idx) {{
  var html = '<div class="jpt-frame-header">';
  html += escapeHtml(frame.func);
  html += ' <span class="jpt-frame-line">line ' + (frame.line || '?') + '</span>';
  html += '</div>';
  html += '<div class="jpt-frame-body">';
  var hasVars = false;
  // Simple vars
  var sv = frame.simple_vars || {{}};
  for (var name in sv) {{
    hasVars = true;
    html += '<div class="jpt-var-row">';
    html += '<span class="jpt-var-name">' + escapeHtml(name) + '</span>';
    html += renderVarVal(sv[name]);
    html += '</div>';
  }}
  // Pointer vars
  var pv = frame.pointer_vars || {{}};
  for (var name in pv) {{
    hasVars = true;
    html += '<div class="jpt-var-row">';
    html += '<span class="jpt-var-name">' + escapeHtml(name) + '</span>';
    html += renderVarVal(pv[name]);
    html += '</div>';
  }}
  // Struct vars (arrays, structs, containers)
  var stv = frame.struct_vars || {{}};
  for (var name in stv) {{
    hasVars = true;
    html += '<div class="jpt-var-row">';
    html += '<span class="jpt-var-name">' + escapeHtml(name) + '</span>';
    html += renderVarVal(stv[name]);
    html += '</div>';
  }}
  if (!hasVars) {{
    html += '<div style="color:#9ca3af;font-style:italic;">(no variables)</div>';
  }}
  html += '</div>';
  return html;
}}

function renderStep() {{
  var step = steps[currentStep];
  // Output
  document.getElementById('output').textContent = step.stdout || '';
  // Code
  var codeHtml = '';
  var curLine = step.line || 0;
  // The line just executed is the *previous* step's line
  var execLine = 0;
  if (currentStep > 0) {{
    execLine = steps[currentStep - 1].line || 0;
  }}
  for (var i = 0; i < sourceLines.length; i++) {{
    var lineNum = i + 1;
    var cls = 'jpt-code-line';
    if (lineNum === execLine) cls += ' executed';
    if (lineNum === curLine) cls += ' current';
    codeHtml += '<div class="' + cls + '">';
    codeHtml += '<span class="jpt-line-num">' + lineNum + '</span>';
    codeHtml += '<span class="jpt-line-code">' + escapeHtml(sourceLines[i] || '') + '</span>';
    codeHtml += '</div>';
  }}
  document.getElementById('code-section').innerHTML = codeHtml;
  // Frames
  var framesHtml = '';
  var frames = step.call_stack || [];
  for (var i = 0; i < frames.length; i++) {{
    framesHtml += '<div class="jpt-frame" id="frame-' + i + '" data-frame-idx="' + i + '">';
    framesHtml += renderFrame(frames[i], i);
    framesHtml += '</div>';
  }}
  if (!framesHtml) {{
    framesHtml = '<div style="color:#9ca3af;font-style:italic;padding:8px;">Program exited.</div>';
  }}
  document.getElementById('frames-section').innerHTML = framesHtml;
  // Heap
  var heapHtml = '';
  var heapObjs = step.heap_objects || [];
  for (var h = 0; h < heapObjs.length; h++) {{
    var obj = heapObjs[h];
    heapHtml += '<div class="jpt-heap-obj" id="heap-' + h + '" data-addr="' + escapeHtml(obj.addr) + '">';
    heapHtml += '<div class="jpt-heap-addr">' + escapeHtml(obj.addr) + '</div>';
    heapHtml += '<div class="jpt-heap-type">' + escapeHtml(obj.type || 'int') + '</div>';
    heapHtml += '<div class="jpt-heap-val">' + renderVarVal(obj.value) + '</div>';
    heapHtml += '</div>';
  }}
  if (!heapHtml) {{
    heapHtml = '<div class="jpt-heap-empty">(no heap objects)</div>';
  }}
  document.getElementById('heap-section').innerHTML = heapHtml;
  // Draw arrows after DOM updates
  requestAnimationFrame(function() {{
    requestAnimationFrame(function() {{
      drawArrows();
      setTimeout(drawArrows, 100);
    }});
  }});
}}

// ── SVG arrows ──
function drawArrows() {{
  var svg = document.getElementById('svg-overlay');
  var widget = svg.parentElement;
  var rect = widget.getBoundingClientRect();
  svg.setAttribute('viewBox', '0 0 ' + rect.width + ' ' + rect.height);
  // Remove only previously drawn paths, keep the <defs> with arrowhead marker
  var oldPaths = svg.querySelectorAll('path');
  oldPaths.forEach(function(p) {{ p.remove(); }});
  // Draw arrows from pointer vars in frames to heap objects
  var step = steps[currentStep];
  var heapObjs = step.heap_objects || [];
  var arrows = document.querySelectorAll('.jpt-var-arrow[data-addr]');
  arrows.forEach(function(arrow) {{
    var addr = arrow.getAttribute('data-addr');
    // Find matching heap object
    var heapEl = null;
    for (var h = 0; h < heapObjs.length; h++) {{
      if (heapObjs[h].addr === addr) {{
        heapEl = document.getElementById('heap-' + h);
        break;
      }}
    }}
    if (heapEl) {{
      var fromRect = arrow.getBoundingClientRect();
      var toRect = heapEl.getBoundingClientRect();
      var x1 = fromRect.left + fromRect.width / 2 - rect.left;
      var y1 = fromRect.top + fromRect.height / 2 - rect.top;
      var x2 = toRect.left - rect.left;
      var y2 = toRect.top + toRect.height / 2 - rect.top;
      // Curved path
      var dx = x2 - x1;
      var cx1 = x1 + dx * 0.3;
      var cx2 = x2 - dx * 0.3;
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', 'M ' + x1 + ' ' + y1 + ' C ' + cx1 + ' ' + y1 + ', ' + cx2 + ' ' + y2 + ', ' + x2 + ' ' + y2);
      path.setAttribute('stroke', '#ef4444');
      path.setAttribute('stroke-width', '1.5');
      path.setAttribute('fill', 'none');
      path.setAttribute('marker-end', 'url(#arrowhead)');
      svg.appendChild(path);
    }}
  }});
}}

// ── Draggable dividers ──
function startDrag(divider, state) {{
  divider._justCollapsed = false;
  var startX, startFlex;
  var content = document.getElementById('content');
  var section = state === 'left' ? document.getElementById('code-section') : document.getElementById('frames-section');
  function onMouseDown(e) {{
    if (divider._justCollapsed) return;
    e.preventDefault();
    startX = e.clientX;
    var cs = window.getComputedStyle(section);
    startFlex = parseFloat(cs.flexBasis) || section.offsetWidth;
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }}
  function onMouseMove(e) {{
    var dx = e.clientX - startX;
    var contentRect = content.getBoundingClientRect();
    var pct = ((startFlex + dx) / contentRect.width * 100);
    pct = Math.max(5, Math.min(90, pct));
    section.style.flex = '0 0 ' + pct + '%';
    drawArrows();
  }}
  function onMouseUp() {{
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
  }}
  divider.addEventListener('mousedown', onMouseDown);
}}

function toggleCollapse(divider, sectionId) {{
  divider.addEventListener('dblclick', function(e) {{
    e.preventDefault();
    e.stopPropagation();
    divider._justCollapsed = true;
    var section = document.getElementById(sectionId);
    if (section.style.display === 'none') {{
      section.style.display = '';
      divider.classList.remove('collapsed');
      section.style.flex = section._savedFlex || '0 0 40%';
    }} else {{
      section._savedFlex = section.style.flex || '0 0 40%';
      section.style.display = 'none';
      divider.classList.add('collapsed');
    }}
    drawArrows();
  }});
}}

startDrag(document.getElementById('divider1'), 'left');
startDrag(document.getElementById('divider2'), 'right');
toggleCollapse(document.getElementById('divider1'), 'code-section');
toggleCollapse(document.getElementById('divider2'), 'frames-section');

// ── Auto-resize iframe height ──
// Parent page polls iframe height via setInterval (see render_trace below)

// ── Initialize ──
gotoStep(0);
</script>
</body>
</html>"""


def render_trace(steps: list[dict], source_code: str | None = None, height: int = 500) -> str:
    """Render a trace as an HTML string with an iframe srcdoc.

    Returns HTML that can be displayed via ``IPython.display.HTML``.
    Works in trusted JupyterLab 4 / Notebook 7 notebooks.
    """
    src = source_code or ""
    inner = _generate_inner_html(steps, src, height)
    # Escape for srcdoc attribute
    escaped = inner.replace("&", "&amp;").replace('"', "&quot;")
    # Parent polling script to auto-resize iframe height
    return f"""<iframe class="jpt-iframe" srcdoc="{escaped}" style="width:100%;border:none;overflow:hidden;" onload="this.style.height=this.contentDocument.body.scrollHeight+20+'px'"></iframe>
<script>
(function() {{
  function autoResize() {{
    document.querySelectorAll('iframe.jpt-iframe').forEach(function(iframe) {{
      try {{
        var h = iframe.contentDocument.body.scrollHeight;
        if (h > 0) iframe.style.height = (h + 20) + 'px';
      }} catch(e) {{}}
    }});
  }}
  if (!window._jptPollStarted) {{
    window._jptPollStarted = true;
    setInterval(autoResize, 200);
  }}
}})();
</script>"""
