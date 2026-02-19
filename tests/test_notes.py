"""Tests for notes management."""

import pytest
from ayder_cli.notes import create_note, _title_to_slug
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestTitleToSlug:
    """Test _title_to_slug helper."""

    def test_simple_title(self):
        assert _title_to_slug("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _title_to_slug("Bug Fix: Auth & Login!") == "bug-fix-auth-login"

    def test_empty_title(self):
        assert _title_to_slug("") == "untitled"

    def test_long_title_truncated(self):
        slug = _title_to_slug("a" * 100)
        assert len(slug) <= 50


class TestCreateNote:
    """Test create_note() function."""

    def test_create_basic_note(self, tmp_path, project_context):
        """Test creating a basic note."""
        result = create_note(project_context, "Test Note", "Some content")

        assert isinstance(result, ToolSuccess)
        assert "Note created" in result

        notes_dir = tmp_path / ".ayder" / "notes"
        assert notes_dir.exists()

        notes = list(notes_dir.glob("*.md"))
        assert len(notes) == 1

        content = notes[0].read_text()
        assert "title: \"Test Note\"" in content
        assert "Some content" in content

    def test_create_note_with_tags(self, tmp_path, project_context):
        """Test creating a note with tags."""
        result = create_note(project_context, "Tagged Note", "Content", tags="bug,security")

        assert isinstance(result, ToolSuccess)

        notes_dir = tmp_path / ".ayder" / "notes"
        content = list(notes_dir.glob("*.md"))[0].read_text()
        assert "tags:" in content
        assert "bug" in content
        assert "security" in content

    def test_create_note_frontmatter(self, tmp_path, project_context):
        """Test that YAML frontmatter is properly formatted."""
        result = create_note(project_context, "Frontmatter Test", "Body text")
        assert isinstance(result, ToolSuccess)

        notes_dir = tmp_path / ".ayder" / "notes"
        content = list(notes_dir.glob("*.md"))[0].read_text()
        assert content.startswith("---\n")
        assert "date:" in content
        assert content.count("---") == 2

    def test_create_note_empty_tags_ignored(self, tmp_path, project_context):
        """Test that empty tags string is handled."""
        result = create_note(project_context, "No Tags", "Content", tags="")
        assert isinstance(result, ToolSuccess)

        notes_dir = tmp_path / ".ayder" / "notes"
        content = list(notes_dir.glob("*.md"))[0].read_text()
        assert "tags:" not in content

    def test_create_note_slug_filename(self, tmp_path, project_context):
        """Test that filename is properly slugified."""
        create_note(project_context, "Investigation Findings!", "Content")

        notes_dir = tmp_path / ".ayder" / "notes"
        notes = list(notes_dir.glob("*.md"))
        assert len(notes) == 1
        assert "investigation-findings" in notes[0].name
