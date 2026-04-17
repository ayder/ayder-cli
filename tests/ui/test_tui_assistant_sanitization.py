"""Defense-in-depth: assistant content rendered in the TUI must not contain
bare tool-call XML tags. If a provider leaks them (e.g. a new model family
not yet in Ollama's XML-fallback matcher), the render path is the last
chance to strip them before the user sees the mess."""
from ayder_cli.tui.widgets import _sanitize_for_assistant_render


def test_sanitize_passes_clean_prose_unchanged():
    text = "Here is a short summary of the task.\n\nHello!"
    assert _sanitize_for_assistant_render(text) == text


def test_sanitize_strips_deepseek_function_calls_block():
    raw = (
        "Creating the file now.\n"
        "<function_calls>\n"
        "<invoke name=\"write_file\">\n"
        "<parameter name=\"path\">foo.txt</parameter>\n"
        "<parameter name=\"content\">hi</parameter>\n"
        "</invoke>\n"
        "</function_calls>\n"
    )
    out = _sanitize_for_assistant_render(raw)
    assert "<function_calls>" not in out
    assert "<invoke" not in out
    assert "<parameter" not in out
    assert "Creating the file now." in out  # prose preserved


def test_sanitize_strips_ayder_style_tool_call_block():
    raw = (
        "Reading the config next.\n"
        "<tool_call><function=read_file>"
        "<parameter=path>config.toml</parameter>"
        "</function></tool_call>"
    )
    out = _sanitize_for_assistant_render(raw)
    assert "<tool_call>" not in out
    assert "<function=" not in out
    assert "Reading the config next." in out


def test_sanitize_strips_orphaned_closing_tags():
    raw = "Sometimes the model leaks </function_calls> mid-prose."
    out = _sanitize_for_assistant_render(raw)
    assert "</function_calls>" not in out


def test_sanitize_preserves_normal_markdown_code_fences():
    raw = "Here is code:\n```python\nprint('hi')\n```"
    out = _sanitize_for_assistant_render(raw)
    assert "```python" in out
    assert "print('hi')" in out


def test_sanitize_empty_string_returns_empty():
    assert _sanitize_for_assistant_render("") == ""
