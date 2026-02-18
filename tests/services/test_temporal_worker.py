"""Tests for temporal worker runtime service."""

from ayder_cli.services.temporal_worker import TemporalWorker, TemporalWorkerConfig


class _FakeAdapterOK:
    def __init__(self) -> None:
        self.calls = 0

    def get_client(self):
        self.calls += 1
        return object()


class _FakeAdapterFail:
    def get_client(self):
        from ayder_cli.services.temporal_client import TemporalClientUnavailableError

        raise TemporalClientUnavailableError("disabled")


def test_worker_returns_error_when_client_unavailable():
    config = TemporalWorkerConfig(
        queue_name="dev-team",
        prompt_path=None,
        permissions={"r"},
        iterations=50,
        max_loops=1,
    )
    worker = TemporalWorker(config, client_adapter=_FakeAdapterFail())

    result = worker.run()

    assert result == 1


def test_worker_runs_and_stops_after_max_loops():
    adapter = _FakeAdapterOK()
    config = TemporalWorkerConfig(
        queue_name="qa-team",
        prompt_path="prompts/qa.md",
        permissions={"r", "x"},
        iterations=25,
        max_loops=1,
    )
    worker = TemporalWorker(config, client_adapter=adapter)

    result = worker.run()

    assert result == 0
    assert adapter.calls == 1


def test_worker_stop_request_exits_loop():
    adapter = _FakeAdapterOK()
    config = TemporalWorkerConfig(
        queue_name="arch-team",
        prompt_path=None,
        permissions={"r"},
        iterations=10,
        max_loops=5,
    )
    worker = TemporalWorker(config, client_adapter=adapter)
    worker.stop()

    result = worker.run()

    assert result == 0
