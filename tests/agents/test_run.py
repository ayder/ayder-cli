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
