"""file_editor advertises a 10MB content limit, so it must enforce one.

The description previously said 'write' was "for new/small files", which is a
policy, not a capability. Models read it as a reason to split one file across
many sequential edits — each extra call another chance to drop a required
argument. The stated limit is now the real one read_file already enforces.
"""

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.filesystem import MAX_FILE_SIZE, file_editor
from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME


def test_a_large_file_is_written_in_one_call(tmp_path):
    """The size the model was previously nudged away from must just work."""
    ctx = ProjectContext(tmp_path)
    content = "<div>x</div>\n" * 2000          # ~26 KB, the planner's ballpark

    result = file_editor(ctx, "planner.html", "write", content=content)

    assert not result.is_error, str(result)
    assert (tmp_path / "planner.html").read_text() == content


def test_content_over_the_limit_is_refused(tmp_path):
    ctx = ProjectContext(tmp_path)
    oversized = "x" * (MAX_FILE_SIZE + 1)

    result = file_editor(ctx, "big.txt", "write", content=oversized)

    assert result.is_error
    assert result.category == "validation"
    assert "10MB" in str(result)
    assert not (tmp_path / "big.txt").exists(), "nothing may be written"


def test_content_at_the_limit_is_accepted(tmp_path):
    """The boundary is inclusive — exactly the limit is not 'too large'."""
    ctx = ProjectContext(tmp_path)
    at_limit = "x" * MAX_FILE_SIZE

    result = file_editor(ctx, "edge.txt", "write", content=at_limit)

    assert not result.is_error, str(result)


def test_the_limit_is_measured_in_bytes_not_characters(tmp_path):
    """Multi-byte text must not slip past a character-based check."""
    ctx = ProjectContext(tmp_path)
    # 3 bytes per char in UTF-8, so this is over the limit despite fewer chars.
    multibyte = "€" * (MAX_FILE_SIZE // 2)

    result = file_editor(ctx, "euro.txt", "write", content=multibyte)

    assert result.is_error
    assert "10MB" in str(result)


def test_the_description_states_the_capability_not_a_policy():
    description = TOOL_DEFINITIONS_BY_NAME["file_editor"].description
    assert "small files" not in description, "policy hint reintroduced"
    assert "10MB" in description, "the real limit must be advertised"
