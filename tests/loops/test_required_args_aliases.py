"""The required-argument gate must honour each tool's declared parameter aliases.

Aliases are resolved by normalize_arguments during execution. The chat loop's
pre-flight check runs BEFORE that, so a gate that reads `required` straight off
the schema rejects a call the tool would have handled — observed live, with
glm-5.3:cloud sending read_file {"path": "."}.
"""

from ayder_cli.loops.chat_loop import _check_required_args
from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME


def test_declared_alias_satisfies_a_required_argument():
    """read_file declares ("path", "file_path"); {"path": "."} must pass."""
    assert _check_required_args("read_file", {"path": "."}) == []


def test_every_file_path_alias_is_accepted():
    aliases = dict(TOOL_DEFINITIONS_BY_NAME["read_file"].parameter_aliases)
    assert aliases, "read_file is expected to declare aliases"
    for alias, canonical in aliases.items():
        if canonical != "file_path":
            continue
        assert _check_required_args("read_file", {alias: "x"}) == [], alias


def test_canonical_name_still_satisfies_the_gate():
    assert _check_required_args("read_file", {"file_path": "x"}) == []


def test_a_genuinely_absent_argument_is_still_reported():
    assert _check_required_args("read_file", {}) == ["file_path"]


def test_an_unrelated_key_does_not_satisfy_the_gate():
    """{"action": "list"} was a real payload — the wrong tool's schema."""
    assert _check_required_args("read_file", {"action": "list"}) == ["file_path"]


def test_an_empty_alias_value_is_treated_as_missing():
    """An alias carrying blank text is no better than no argument at all."""
    assert _check_required_args("read_file", {"path": "   "}) == ["file_path"]
    assert _check_required_args("read_file", {"path": None}) == ["file_path"]


def test_alias_does_not_mask_a_different_missing_argument():
    """file_editor's `operation` has no alias; it must still be reported."""
    missing = _check_required_args(
        "file_editor",
        {"file_path": "daily.html", "old_string": "a", "new_string": "b"},
    )
    assert "operation" in missing


def test_canonical_wins_over_an_alias_exactly_as_normalization_does():
    """normalize_arguments keeps the canonical key when both are present.

    So a blank canonical is still missing even alongside a valid alias — the
    gate must not pass a call the tool would then receive empty.
    """
    assert _check_required_args(
        "read_file", {"file_path": "", "path": "real.txt"}
    ) == ["file_path"]


def test_gate_agrees_with_normalization_on_the_observed_payload():
    """End-to-end: what the gate accepts is what the tool can actually run."""
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.normalization import normalize_arguments

    payload = {"path": "."}
    assert _check_required_args("read_file", payload) == []
    normalized = normalize_arguments("read_file", payload, ProjectContext("."))
    assert normalized.get("file_path")
    assert "path" not in normalized
