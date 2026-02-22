"""Tests for parser.py module.

This module tests the parser functionality including:
- Line 13: Empty content check returns []
- Standard format parsing
- Lazy format parsing
- Error handling
"""


from ayder_cli.parser import parse_custom_tool_calls, _infer_parameter_name, _normalize_tool_call_markup, _normalize_dsml_markup


class TestParseCustomToolCallsEmpty:
    """Tests for empty content handling - Line 13."""

    def test_empty_string_returns_empty_list(self):
        """Test that empty string returns empty list."""
        result = parse_custom_tool_calls("")
        assert result == []

    def test_none_returns_empty_list(self):
        """Test that None returns empty list."""
        result = parse_custom_tool_calls(None)
        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        """Test that whitespace-only string returns empty list."""
        result = parse_custom_tool_calls("   \n\t  ")
        assert result == []


class TestParseCustomToolCallsStandardFormat:
    """Tests for standard format parsing with parameter tags."""

    def test_single_parameter(self):
        """Test parsing with single parameter."""
        content = '<function=write_file><parameter=file_path>/tmp/test.txt</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["arguments"] == {"file_path": "/tmp/test.txt"}

    def test_multiple_parameters(self):
        """Test parsing with multiple parameters."""
        content = '<function=replace_string><parameter=file_path>/tmp/test.txt</parameter><parameter=old_string>old</parameter><parameter=new_string>new</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "replace_string"
        assert result[0]["arguments"] == {
            "file_path": "/tmp/test.txt",
            "old_string": "old",
            "new_string": "new"
        }

    def test_multiple_function_calls(self):
        """Test parsing multiple function calls in one content."""
        content = (
            '<function=read_file><parameter=file_path>/file1.txt</parameter></function>'
            '<function=read_file><parameter=file_path>/file2.txt</parameter></function>'
        )
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 2
        assert result[0]["arguments"]["file_path"] == "/file1.txt"
        assert result[1]["arguments"]["file_path"] == "/file2.txt"

    def test_multiline_parameter_value(self):
        """Test parsing with multiline parameter value."""
        content = '<function=write_file><parameter=content>Line 1\nLine 2\nLine 3</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert result[0]["arguments"]["content"] == "Line 1\nLine 2\nLine 3"


class TestParseCustomToolCallsLazyFormat:
    """Tests for lazy format parsing (single parameter without tags)."""

    def test_run_shell_command_lazy(self):
        """Test lazy parsing for run_shell_command."""
        content = '<function=run_shell_command>ls -la</function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"
        assert result[0]["arguments"] == {"command": "ls -la"}

    def test_unknown_tool_lazy_no_infer(self):
        """Test lazy parsing for unknown tool without parameter inference."""
        content = '<function=unknown_tool>some value</function>'
        result = parse_custom_tool_calls(content)
        
        assert result[0]["name"] == "unknown_tool"
        assert "error" in result[0]
        assert "Missing <parameter> tags" in result[0]["error"]


class TestParseCustomToolCallsErrorHandling:
    """Tests for error handling in parsing."""

    def test_empty_function_name(self):
        """Test handling of empty function name."""
        content = '<function= ><parameter=key>value</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "unknown"
        assert "error" in result[0]
        assert "function name is empty" in result[0]["error"]

    def test_no_parameters_valid(self):
        """Test that tools with no parameters are parsed as valid calls."""
        content = '<function=get_project_structure></function>'
        result = parse_custom_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "get_project_structure"
        assert result[0]["arguments"] == {}
        assert "error" not in result[0]

    def test_no_parameters_whitespace_body(self):
        """Test that tools with whitespace-only body are parsed as valid calls."""
        content = '<function=list_background_processes>   </function>'
        result = parse_custom_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "list_background_processes"
        assert result[0]["arguments"] == {}
        assert "error" not in result[0]

    def test_empty_parameter_name(self):
        """Test handling of empty parameter name."""
        content = '<function=read_file><parameter=>value</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        # Empty parameter names should be ignored
        assert result[0]["arguments"] == {}


class TestToolCallWrapperFormat:
    """Tests for <tool_call> wrapper format used by some models (e.g. Ministral)."""

    def test_tool_call_wrapper_with_function_close(self):
        """Test <tool_call> wrapper where </function> is present."""
        content = '<tool_call> <function=read_file><parameter=file_path>test.py</parameter></function> </tool_call>'
        result = parse_custom_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert result[0]["arguments"] == {"file_path": "test.py"}

    def test_tool_call_wrapper_without_function_close(self):
        """Test <tool_call> wrapper where </function> is missing (closed by </tool_call>)."""
        content = '<tool_call> <function=run_shell_command> <parameter=command>echo "hello"  </tool_call>'
        result = parse_custom_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"
        assert result[0]["arguments"]["command"] == 'echo "hello"'

    def test_tool_call_wrapper_lazy_format(self):
        """Test <tool_call> wrapper with lazy format (no parameter tags)."""
        content = '<tool_call> <function=run_shell_command>ls -la </tool_call>'
        result = parse_custom_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"
        assert result[0]["arguments"] == {"command": "ls -la"}

    def test_multiple_tool_call_wrappers(self):
        """Test multiple <tool_call> blocks."""
        content = (
            '<tool_call> <function=read_file><parameter=file_path>a.py</parameter> </tool_call>'
            '<tool_call> <function=read_file><parameter=file_path>b.py</parameter> </tool_call>'
        )
        result = parse_custom_tool_calls(content)

        assert len(result) == 2
        assert result[0]["arguments"]["file_path"] == "a.py"
        assert result[1]["arguments"]["file_path"] == "b.py"

    def test_normalize_strips_wrapper_keeps_function_close(self):
        """Test normalizer preserves </function> when present."""
        content = '<tool_call><function=test><parameter=x>1</parameter></function></tool_call>'
        normalized = _normalize_tool_call_markup(content)
        assert "</function>" in normalized
        assert "<tool_call>" not in normalized

    def test_normalize_adds_function_close_when_missing(self):
        """Test normalizer adds </function> when missing."""
        content = '<tool_call><function=test><parameter=x>1</parameter></tool_call>'
        normalized = _normalize_tool_call_markup(content)
        assert "</function>" in normalized
        assert "<tool_call>" not in normalized


class TestInferParameterName:
    """Tests for _infer_parameter_name() function."""

    def test_run_shell_command(self):
        """Test inference for run_shell_command."""
        assert _infer_parameter_name("run_shell_command") == "command"

    def test_unknown_tool(self):
        """Test inference for unknown tool returns empty string."""
        assert _infer_parameter_name("unknown_tool") == ""

    def test_empty_string(self):
        """Test inference for empty string returns empty string."""
        assert _infer_parameter_name("") == ""


class TestDSMLFormat:
    """Tests for DeepSeek DSML-prefixed tag format."""

    DSML_SAMPLE = (
        '<\uff5c\uff24\uff33\uff2d\uff2c\uff5cfunction_calls>\n'
        '  <\uff5c\uff24\uff33\uff2d\uff2c\uff5cinvoke name="write_file">\n'
        '  <\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter name="file_path" string="true">'
        '.ayder/memory/current_memory.md</\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter>\n'
        '  <\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter name="content" string="true">'
        '# Memory Checkpoint\n\nSome content here.\n'
        '</\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter>\n'
        '  </\uff5c\uff24\uff33\uff2d\uff2c\uff5cinvoke>\n'
        '  </\uff5c\uff24\uff33\uff2d\uff2c\uff5cfunction_calls>'
    )

    def test_dsml_normalize_strips_markers(self):
        """Test that DSML markers are stripped to standard DeepSeek format."""
        result = _normalize_dsml_markup(self.DSML_SAMPLE)
        assert "<function_calls>" in result
        assert '<invoke name="write_file">' in result
        assert "</invoke>" in result
        assert "</function_calls>" in result
        assert "\uff5c\uff24\uff33\uff2d\uff2c\uff5c" not in result

    def test_dsml_full_parse(self):
        """Test end-to-end parsing of DSML-formatted tool calls."""
        result = parse_custom_tool_calls(self.DSML_SAMPLE)

        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["arguments"]["file_path"] == ".ayder/memory/current_memory.md"
        assert "Memory Checkpoint" in result[0]["arguments"]["content"]

    def test_dsml_no_markers_passthrough(self):
        """Test that content without DSML markers is unchanged."""
        plain = "<function=read_file><parameter=file_path>test.py</parameter></function>"
        assert _normalize_dsml_markup(plain) == plain

    def test_dsml_has_custom_tool_calls_detected(self):
        """Test that has_custom_tool_calls detects DSML format."""
        from ayder_cli.tui.parser import has_custom_tool_calls

        assert has_custom_tool_calls(self.DSML_SAMPLE) is True


class TestContentProcessorUnified:
    """Acceptance criteria tests for the unified ContentProcessor (Phase 1).

    Verifies that ContentProcessor in parser.py handles all formats through
    a single API, and that backward-compat shims work correctly.
    """

    # -------------------------------------------------------------------------
    # parse_tool_calls — unified extraction
    # -------------------------------------------------------------------------

    def test_parse_tool_calls_xml_standard(self):
        """XML standard format is extracted via parse_tool_calls."""
        from ayder_cli.parser import content_processor

        content = "<function=read_file><parameter=file_path>/tmp/x.py</parameter></function>"
        result = content_processor.parse_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert result[0]["arguments"] == {"file_path": "/tmp/x.py"}

    def test_parse_tool_calls_wrapped_tool_call(self):
        """<tool_call> wrapper format is handled by parse_tool_calls."""
        from ayder_cli.parser import content_processor

        content = "<tool_call><function=run_shell_command><parameter=command>ls</parameter></function></tool_call>"
        result = content_processor.parse_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"
        assert result[0]["arguments"]["command"] == "ls"

    def test_parse_tool_calls_deepseek(self):
        """DeepSeek <invoke> format is converted and extracted."""
        from ayder_cli.parser import content_processor

        content = (
            "<function_calls>\n"
            '<invoke name="write_file">\n'
            '<parameter name="file_path" type="string">/tmp/out.txt</parameter>\n'
            '<parameter name="content" type="string">hello world</parameter>\n'
            "</invoke>\n"
            "</function_calls>"
        )
        result = content_processor.parse_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["arguments"]["file_path"] == "/tmp/out.txt"
        assert result[0]["arguments"]["content"] == "hello world"

    def test_parse_tool_calls_dsml(self):
        """DSML-prefixed format is normalized and extracted."""
        from ayder_cli.parser import content_processor

        dsml = (
            "<\uff5c\uff24\uff33\uff2d\uff2c\uff5cfunction_calls>\n"
            "  <\uff5c\uff24\uff33\uff2d\uff2c\uff5cinvoke name=\"read_file\">\n"
            "  <\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter name=\"file_path\" string=\"true\">"
            "README.md"
            "</\uff5c\uff24\uff33\uff2d\uff2c\uff5cparameter>\n"
            "  </\uff5c\uff24\uff33\uff2d\uff2c\uff5cinvoke>\n"
            "  </\uff5c\uff24\uff33\uff2d\uff2c\uff5cfunction_calls>"
        )
        result = content_processor.parse_tool_calls(dsml)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert result[0]["arguments"]["file_path"] == "README.md"

    def test_parse_tool_calls_json_fallback(self):
        """JSON array format falls back correctly when no XML found."""
        from ayder_cli.parser import content_processor

        content = '[{"function": {"name": "search_codebase", "arguments": "{\\"query\\": \\"parser\\"}"}}]'
        result = content_processor.parse_tool_calls(content)

        assert len(result) == 1
        assert result[0]["name"] == "search_codebase"
        assert result[0]["arguments"]["query"] == "parser"

    def test_parse_tool_calls_returns_empty_on_empty(self):
        """Empty or None content returns []."""
        from ayder_cli.parser import content_processor

        assert content_processor.parse_tool_calls("") == []
        assert content_processor.parse_tool_calls(None) == []

    def test_parse_tool_calls_lazy_single_param(self):
        """Lazy format (no parameter tags) inferred for single-param tools."""
        from ayder_cli.parser import content_processor

        content = "<function=run_shell_command>echo hello</function>"
        result = content_processor.parse_tool_calls(content)

        assert len(result) == 1
        assert result[0]["arguments"] == {"command": "echo hello"}

    # -------------------------------------------------------------------------
    # has_tool_calls
    # -------------------------------------------------------------------------

    def test_has_tool_calls_detects_xml(self):
        """Detects standard XML format."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("<function=read_file>") is True

    def test_has_tool_calls_detects_tool_call_wrapper(self):
        """Detects <tool_call> wrapper."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("<tool_call>...</tool_call>") is True

    def test_has_tool_calls_detects_deepseek(self):
        """Detects DeepSeek <function_calls> format."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("<function_calls><invoke") is True

    def test_has_tool_calls_detects_dsml(self):
        """Detects DSML fullwidth prefix."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("\uff5c\uff24\uff33\uff2d\uff2c\uff5c") is True

    def test_has_tool_calls_false_on_plain_text(self):
        """Plain text returns False."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("Hello, world!") is False

    def test_has_tool_calls_false_on_empty(self):
        """Empty content returns False."""
        from ayder_cli.parser import content_processor

        assert content_processor.has_tool_calls("") is False

    # -------------------------------------------------------------------------
    # strip_for_display
    # -------------------------------------------------------------------------

    def test_strip_for_display_removes_xml_tool_calls(self):
        """XML tool calls are stripped, leaving surrounding text."""
        from ayder_cli.parser import content_processor

        content = "Let me read it.<function=read_file><parameter=file_path>x.py</parameter></function>Done."
        result = content_processor.strip_for_display(content)

        assert "<function=" not in result
        assert "<parameter=" not in result
        assert "Let me read it." in result
        assert "Done." in result

    def test_strip_for_display_removes_think_blocks(self):
        """Think blocks are stripped entirely."""
        from ayder_cli.parser import content_processor

        content = "<think>internal reasoning</think>The answer is 42."
        result = content_processor.strip_for_display(content)

        assert "<think>" not in result
        assert "internal reasoning" not in result
        assert "The answer is 42." in result

    def test_strip_for_display_removes_deepseek_blocks(self):
        """DeepSeek function_calls blocks are stripped."""
        from ayder_cli.parser import content_processor

        content = 'Thinking...<function_calls><invoke name="x"><parameter name="p">v</parameter></invoke></function_calls>Done.'
        result = content_processor.strip_for_display(content)

        assert "<function_calls>" not in result
        assert "<invoke" not in result
        assert "Done." in result

    # -------------------------------------------------------------------------
    # extract_think_blocks
    # -------------------------------------------------------------------------

    def test_extract_think_blocks_closed(self):
        """Closed think blocks are extracted."""
        from ayder_cli.parser import content_processor

        content = "<think>step 1\nstep 2</think>Result."
        blocks = content_processor.extract_think_blocks(content)

        assert len(blocks) == 1
        assert "step 1" in blocks[0]

    def test_extract_think_blocks_unclosed(self):
        """Unclosed think blocks (streaming) are extracted."""
        from ayder_cli.parser import content_processor

        content = "<think>thinking in progress..."
        blocks = content_processor.extract_think_blocks(content)

        assert len(blocks) == 1
        assert "thinking in progress" in blocks[0]

    def test_extract_think_blocks_empty_returns_empty_list(self):
        """Content with no think blocks returns []."""
        from ayder_cli.parser import content_processor

        assert content_processor.extract_think_blocks("No think blocks here.") == []

    # -------------------------------------------------------------------------
    # Backward-compat shim verification
    # -------------------------------------------------------------------------

    def test_shim_parse_custom_tool_calls(self):
        """parse_custom_tool_calls() module-level shim works unchanged."""
        from ayder_cli.parser import parse_custom_tool_calls

        result = parse_custom_tool_calls(
            "<function=read_file><parameter=file_path>a.py</parameter></function>"
        )
        assert result[0]["name"] == "read_file"

    def test_shim_tui_parser_content_processor(self):
        """tui/parser.py content_processor re-export points to unified instance."""
        from ayder_cli.tui.parser import content_processor as tui_cp
        from ayder_cli.parser import content_processor as main_cp

        assert tui_cp is main_cp

    def test_shim_tui_parser_has_custom_tool_calls(self):
        """tui/parser.py has_custom_tool_calls() shim works correctly."""
        from ayder_cli.tui.parser import has_custom_tool_calls

        assert has_custom_tool_calls("<function=x>") is True
        assert has_custom_tool_calls("plain text") is False

    def test_shim_tui_parser_extract_think_blocks(self):
        """tui/parser.py extract_think_blocks() shim works correctly."""
        from ayder_cli.tui.parser import extract_think_blocks

        blocks = extract_think_blocks("<think>hello</think>")
        assert blocks == ["hello"]

    def test_shim_tui_parser_strip_for_display(self):
        """tui/parser.py strip_for_display() shim works correctly."""
        from ayder_cli.tui.parser import strip_for_display

        result = strip_for_display("<think>x</think>Hello")
        assert "Hello" in result
        assert "<think>" not in result

    def test_shim_tui_parser_parse_json_tool_calls(self):
        """tui/parser.py parse_json_tool_calls() shim works correctly."""
        from ayder_cli.tui.parser import parse_json_tool_calls

        result = parse_json_tool_calls('[{"function": {"name": "x", "arguments": "{}"}}]')
        assert result[0]["name"] == "x"

    def test_shim_infer_parameter_name(self):
        """Module-level _infer_parameter_name() shim works correctly."""
        from ayder_cli.parser import _infer_parameter_name

        assert _infer_parameter_name("run_shell_command") == "command"
        assert _infer_parameter_name("nonexistent") == ""

    def test_shim_normalize_dsml_markup(self):
        """Module-level _normalize_dsml_markup() shim works correctly."""
        from ayder_cli.parser import _normalize_dsml_markup

        dsml = "<\uff5c\uff24\uff33\uff2d\uff2c\uff5cfunction_calls>"
        result = _normalize_dsml_markup(dsml)
        assert "<function_calls>" in result

    def test_shim_normalize_tool_call_markup(self):
        """Module-level _normalize_tool_call_markup() shim works correctly."""
        from ayder_cli.parser import _normalize_tool_call_markup

        content = "<tool_call><function=read_file><parameter=file_path>x.py</parameter></function></tool_call>"
        result = _normalize_tool_call_markup(content)
        assert "<tool_call>" not in result
        assert "<function=read_file>" in result
