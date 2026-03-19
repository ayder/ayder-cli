"""Tests for AgentSummary dataclass."""

from ayder_cli.agents.summary import AgentSummary


class TestAgentSummary:
    def test_completed_summary(self):
        s = AgentSummary(
            agent_name="code-reviewer",
            status="completed",
            summary="Found 3 issues.",
            error=None,
        )
        assert s.agent_name == "code-reviewer"
        assert s.status == "completed"
        assert s.summary == "Found 3 issues."
        assert s.error is None

    def test_error_summary(self):
        s = AgentSummary(
            agent_name="test-writer",
            status="error",
            summary="Partial progress: wrote 2 tests.",
            error="API key invalid",
        )
        assert s.status == "error"
        assert s.error == "API key invalid"

    def test_timeout_summary(self):
        s = AgentSummary(
            agent_name="analyzer",
            status="timeout",
            summary="Analyzed 5 of 10 files.",
            error=None,
        )
        assert s.status == "timeout"

    def test_format_for_injection(self):
        """format_for_injection produces a readable multi-line string."""
        s = AgentSummary(
            agent_name="reviewer",
            status="completed",
            summary="All good.",
            error=None,
        )
        text = s.format_for_injection()
        assert "reviewer" in text
        assert "completed" in text
        assert "All good." in text

    def test_format_for_injection_with_error(self):
        s = AgentSummary(
            agent_name="reviewer",
            status="error",
            summary="Partial.",
            error="Connection timeout",
        )
        text = s.format_for_injection()
        assert "Connection timeout" in text
