from ayder_cli.agents.run import AgentRun


def test_working_time_uses_now_until_finished():
    r = AgentRun(run_id=1, generation=1, agent_name="x", started_at=100.0)
    assert r.working_time(now=142.0) == 42
    r.finished_at = 130.0
    assert r.working_time(now=999.0) == 30  # frozen at finish


def test_to_status_dict_hides_result_body():
    r = AgentRun(run_id=2, generation=1, agent_name="rev", started_at=0.0,
                 status="done", result="SECRET", note_path=".ayder/notes/n.md")
    d = r.to_status_dict(now=5.0)
    assert d == {"run_id": 2, "name": "rev", "status": "done", "working_time_s": 5,
                 "has_unread_result": True, "note_path": ".ayder/notes/n.md"}
    assert "SECRET" not in str(d)


def test_has_unread_result_false_when_working_or_drained():
    r = AgentRun(run_id=1, generation=1, agent_name="x", started_at=0.0, status="working")
    assert r.to_status_dict(now=0.0)["has_unread_result"] is False
    r.status, r.drained = "done", True
    assert r.to_status_dict(now=0.0)["has_unread_result"] is False


def test_panel_label_combines_preview_and_task_id():
    assert AgentRun(run_id=1, generation=1, agent_name="c", started_at=0.0,
                    task_preview="refactor auth", task_id="TASK-003").panel_label() \
        == "refactor auth · TASK-003"
    # Either alone:
    assert AgentRun(run_id=1, generation=1, agent_name="c", started_at=0.0,
                    task_id="TASK-007").panel_label() == "TASK-007"
    assert AgentRun(run_id=1, generation=1, agent_name="c", started_at=0.0,
                    task_preview="do the thing").panel_label() == "do the thing"
    # Neither -> None (panel falls back to just the agent name).
    assert AgentRun(run_id=1, generation=1, agent_name="c", started_at=0.0).panel_label() is None


def test_to_status_dict_includes_assignment_metadata_only_when_set():
    r = AgentRun(run_id=3, generation=1, agent_name="coder", started_at=0.0,
                 task_id="TASK-007", branch_name="agent/collect-cli")
    d = r.to_status_dict(now=0.0)
    assert d["task_id"] == "TASK-007"
    assert d["branch_name"] == "agent/collect-cli"
    # Absent (not None-valued) when the dispatch carried no assignment metadata.
    bare = AgentRun(run_id=4, generation=1, agent_name="coder", started_at=0.0)
    assert "task_id" not in bare.to_status_dict(now=0.0)
    assert "branch_name" not in bare.to_status_dict(now=0.0)
