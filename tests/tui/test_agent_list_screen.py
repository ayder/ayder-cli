"""Tests for AgentListScreen (construction + rendering, no pilot)."""

from unittest.mock import MagicMock

import pytest

from ayder_cli.tui.screens import AgentListScreen


def _make_registry(agents_with_status: dict[str, tuple[str, int]]):
    """Build a fake registry. Maps name -> (status, running_count)."""
    reg = MagicMock()
    reg.agents = {name: MagicMock() for name in agents_with_status}
    reg.list_agents.return_value = [
        {
            "name": name,
            "description": f"{name} description",
            "status": status,
            "running_count": count,
        }
        for name, (status, count) in agents_with_status.items()
    ]
    reg.get_status.side_effect = lambda n: agents_with_status[n][0]
    reg.get_running_count.side_effect = lambda n: agents_with_status[n][1]
    return reg


def test_agent_list_screen_init_with_agents():
    reg = _make_registry({"reviewer": ("idle", 0), "planner": ("running", 2)})
    screen = AgentListScreen(registry=reg)
    assert screen.selected_index == 0
    assert len(screen._snapshot) == 2
    names = [row["name"] for row in screen._snapshot]
    assert names == ["reviewer", "planner"]


def test_agent_list_screen_render_has_status_icons():
    reg = _make_registry(
        {
            "reviewer": ("idle", 0),
            "planner": ("running", 2),
            "fixer": ("error", 0),
        }
    )
    screen = AgentListScreen(registry=reg)
    rendered = screen._render_list().plain
    assert "reviewer" in rendered
    assert "planner" in rendered
    assert "fixer" in rendered
    # Running count is shown when > 1
    assert "x2" in rendered or "(2)" in rendered
    # Status labels surface in the rendered output
    assert "idle" in rendered.lower()
    assert "running" in rendered.lower() or "working" in rendered.lower()


def test_agent_list_screen_empty_registry_renders_placeholder():
    reg = _make_registry({})
    screen = AgentListScreen(registry=reg)
    rendered = screen._render_list().plain
    assert "no agents" in rendered.lower()


def test_agent_list_screen_navigation_clamps():
    reg = _make_registry({"a": ("idle", 0), "b": ("idle", 0)})
    screen = AgentListScreen(registry=reg)
    screen.selected_index = -5
    screen._clamp_index()
    assert screen.selected_index == 0
    screen.selected_index = 99
    screen._clamp_index()
    assert screen.selected_index == 1


def test_agent_list_screen_refresh_picks_up_status_change():
    state = {"reviewer": ("idle", 0)}
    reg = _make_registry(state)
    screen = AgentListScreen(registry=reg)
    # Mutate underlying state and re-snapshot
    state["reviewer"] = ("running", 3)
    reg.list_agents.return_value = [
        {"name": "reviewer", "description": "reviewer description",
         "status": "running", "running_count": 3}
    ]
    screen._refresh_snapshot()
    assert screen._snapshot[0]["status"] == "running"
    assert screen._snapshot[0]["running_count"] == 3
