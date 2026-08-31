"""A tool call carrying an argument the tool does not accept is rejected, not crashed.

Models improvise parameter names. Observed live against the `task` tool:

    TypeError: task() got an unexpected keyword argument 'tags'   (2026-08-15)
    TypeError: task() got an unexpected keyword argument 'name'   (2026-08-28)

Those reached ``tool_func(**call_args)`` and raised inside execution. The model
did get a ToolError back — the dispatch boundary converts any exception — but
categorised as an execution failure and worded as a Python TypeError, rather
than a validation error naming the arguments the tool actually takes.
"""

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess
from ayder_cli.tools.registry import ToolRegistry


def _registry(tmp_path, name, func):
    registry = ToolRegistry(ProjectContext(tmp_path))
    registry.register(name, func)
    return registry


def test_unexpected_argument_is_a_validation_error_not_a_crash(tmp_path):
    def spy(project_ctx, action: str):
        return ToolSuccess("ran")

    result = _registry(tmp_path, "spy", spy).execute(
        "spy", {"action": "list", "name": "X"}
    )

    assert result.is_error
    assert result.category == "validation", f"got {result.category}"
    assert "name" in str(result)
    # The raw Python failure must not be what the model sees.
    assert "unexpected keyword argument" not in str(result)


def test_the_error_names_the_arguments_the_tool_accepts(tmp_path):
    def spy(project_ctx, action: str, title: str = ""):
        return ToolSuccess("ran")

    result = _registry(tmp_path, "spy", spy).execute(
        "spy", {"action": "list", "name": "X"}
    )

    assert "action" in str(result) and "title" in str(result)
    # The injected dependency is not part of the tool's public surface.
    assert "project_ctx" not in str(result)


def test_every_unexpected_argument_is_listed(tmp_path):
    def spy(project_ctx, action: str):
        return ToolSuccess("ran")

    result = _registry(tmp_path, "spy", spy).execute(
        "spy", {"action": "x", "name": "a", "tags": "b"}
    )

    assert "name" in str(result) and "tags" in str(result)


def test_a_valid_call_is_unaffected(tmp_path):
    def spy(project_ctx, action: str):
        return ToolSuccess(f"ran={action}")

    result = _registry(tmp_path, "spy", spy).execute("spy", {"action": "list"})

    assert not result.is_error
    assert "ran=list" in str(result)


def test_a_tool_taking_kwargs_still_receives_extras(tmp_path):
    """A **kwargs signature accepts anything — it must be exempt from the check."""

    def flexible(project_ctx, action: str, **kwargs):
        return ToolSuccess(f"action={action} extra={sorted(kwargs)}")

    result = _registry(tmp_path, "flexible", flexible).execute(
        "flexible", {"action": "x", "name": "a"}
    )

    assert not result.is_error
    assert "extra=['name']" in str(result)


def test_the_real_task_tool_rejects_the_observed_arguments(tmp_path):
    """Regression for the two live TypeErrors."""
    from ayder_cli.tools.builtins.task_tool import task

    registry = _registry(tmp_path, "task", task)

    for bad in ("name", "tags"):
        result = registry.execute("task", {"action": "list", bad: "X"})
        assert result.is_error, bad
        assert result.category == "validation", bad
        assert bad in str(result), bad
        assert "unexpected keyword argument" not in str(result), bad
