"""AgentSummary — structured result of an agent run."""

from dataclasses import dataclass


@dataclass
class AgentSummary:
    """Result of a single agent dispatch."""

    agent_name: str
    status: str          # "completed" | "timeout" | "error"
    summary: str         # what the agent accomplished (even partial)
    error: str | None    # error details if status != "completed"

    def format_for_injection(self) -> str:
        """Format summary for injection into the main agent's context."""
        lines = [
            f'[Agent "{self.agent_name}" {self.status}]',
            f"STATUS: {self.status}",
            f"SUMMARY: {self.summary}",
        ]
        if self.error:
            lines.append(f"ERROR: {self.error}")
        return "\n".join(lines)
