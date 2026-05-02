"""Tests for the resolution matrix and ResolutionRule."""

import pytest

from ayder_cli.providers.impl.ollama_drivers.matrix import (
    RESOLUTION_MATRIX,
    ResolutionRule,
)
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_rule_requires_at_least_one_matcher():
    with pytest.raises(ValueError, match="at least one matcher"):
        ResolutionRule(driver="generic_native")


def test_rule_family_substring_case_insensitive():
    rule = ResolutionRule(family_substring="qwen3", driver="qwen3")
    assert rule.matches(ModelInfo(family="QWEN3"))
    assert rule.matches(ModelInfo(family="qwen3"))
    assert not rule.matches(ModelInfo(family="qwen2"))


def test_rule_name_substring_case_insensitive():
    rule = ResolutionRule(name_substring="acme/qwen", driver="acme")
    assert rule.matches(ModelInfo(name="ACME/Qwen3:7b"))
    assert not rule.matches(ModelInfo(name="other/qwen3"))


def test_rule_capability_exact_match():
    rule = ResolutionRule(requires_capability="tools", driver="generic_native")
    assert rule.matches(ModelInfo(capabilities=["tools", "vision"]))
    assert not rule.matches(ModelInfo(capabilities=["vision"]))


def test_rule_all_dimensions_anded():
    rule = ResolutionRule(
        family_substring="qwen3",
        requires_capability="tools",
        driver="qwen3",
    )
    assert rule.matches(ModelInfo(family="qwen3", capabilities=["tools"]))
    assert not rule.matches(ModelInfo(family="qwen3", capabilities=[]))
    assert not rule.matches(ModelInfo(family="llama", capabilities=["tools"]))


@pytest.mark.parametrize(
    ("model_info", "expected_driver"),
    [
        (ModelInfo(name="qwen3.6:latest", family="qwen3"), "qwen3"),
        (ModelInfo(name="qwen2.5:7b", family="qwen2"), "qwen3"),
        (ModelInfo(name="deepseek-r1:32b", family="deepseek2"), "deepseek"),
        (ModelInfo(name="minimax-m1", family="minimax"), "minimax"),
        (ModelInfo(name="llama3.1:8b", family="llama"), "generic_native"),
        (ModelInfo(name="mistral-nemo", family="mistral"), "generic_native"),
        (ModelInfo(name="gemma2:27b", family="gemma"), "generic_native"),
        (ModelInfo(name="phi4", family="phi3"), "generic_native"),
        (ModelInfo(name="granite-code", family="granite"), "generic_native"),
        (
            ModelInfo(name="rare-model", family="unknown", capabilities=["tools"]),
            "generic_native",
        ),
    ],
)
def test_matrix_routes_known_combinations(model_info, expected_driver):
    """Walk the matrix in order: first match wins."""
    matched = next((r for r in RESOLUTION_MATRIX if r.matches(model_info)), None)
    assert matched is not None, f"No matrix entry matched {model_info}"
    assert matched.driver == expected_driver


def test_matrix_returns_no_match_for_truly_unknown_model():
    info = ModelInfo(name="totally-unknown", family="", capabilities=[])
    matched = next((r for r in RESOLUTION_MATRIX if r.matches(info)), None)
    assert matched is None


def test_matrix_rows_are_frozen_dataclasses():
    for rule in RESOLUTION_MATRIX:
        with pytest.raises(Exception):
            rule.driver = "mutated"
