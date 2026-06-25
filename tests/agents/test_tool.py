"""The agent tool is one consolidated definition; behavior lives in test_agent_consolidated.py."""

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION


def test_only_consolidated_agent_def_exported():
    import ayder_cli.agents.tool as mod

    assert AGENT_TOOL_DEFINITION.name == "agent"
    for removed in (
        "LIST_AGENTS_TOOL_DEFINITION",
        "AGENT_STATUS_TOOL_DEFINITION",
        "READ_AGENT_RESULT_TOOL_DEFINITION",
        "create_call_agent_handler",
        "create_list_agents_handler",
        "create_agent_status_handler",
        "create_read_agent_result_handler",
    ):
        assert not hasattr(mod, removed), f"{removed} should be removed"
