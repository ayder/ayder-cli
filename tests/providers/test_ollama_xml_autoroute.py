"""Routing assertions for the ChatDriver-based Ollama path."""

import pytest

from ayder_cli.providers.impl.ollama_drivers.matrix import RESOLUTION_MATRIX
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


@pytest.mark.parametrize(
    ("model_info", "expected_driver"),
    [
        (ModelInfo(name="deepseek-r1:32b", family="deepseek2"), "generic_native"),
        (ModelInfo(name="deepseek-v3.2", family="deepseek3"), "generic_native"),
        (ModelInfo(name="qwen3.6:latest", family="qwen3"), "generic_native"),
        (ModelInfo(name="qwen2.5:7b", family="qwen2"), "generic_native"),
        (ModelInfo(name="minimax-m1", family="minimax"), "minimax"),
        (ModelInfo(name="llama3.1:8b", family="llama"), "generic_native"),
    ],
)
def test_legacy_autoroute_models_now_route_via_matrix(model_info, expected_driver):
    rule = next((r for r in RESOLUTION_MATRIX if r.matches(model_info)), None)
    assert rule is not None
    assert rule.driver == expected_driver
