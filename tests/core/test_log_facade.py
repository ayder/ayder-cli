import pytest

from ayder_cli.log import (
    CHANNELS,
    LOG_LEVELS,
    RESERVED_CHANNELS,
    SELECTABLE_CHANNELS,
    get_logger,
)


def test_trace_is_a_valid_level():
    assert "TRACE" in LOG_LEVELS
    assert LOG_LEVELS[0] == "NONE"


def test_get_logger_returns_a_distinct_bound_logger():
    """`bind()` returns a new logger; it must not mutate the global one."""
    from loguru import logger

    assert get_logger("llm") is not logger
    assert get_logger("llm") is not get_logger("tool")


def test_bound_channel_appears_on_the_record():
    from loguru import logger

    seen = []
    sink_id = logger.add(lambda m: seen.append(m.record["extra"]), level=0)
    try:
        get_logger("tool").warning("hello")
    finally:
        logger.remove(sink_id)
    assert seen and seen[0].get("channel") == "tool"


def test_unknown_channel_is_rejected():
    with pytest.raises(ValueError, match="Unknown log channel"):
        get_logger("nope")


def test_reserved_channel_is_not_bindable():
    # `external` is selectable in config but only the bridge may bind it.
    with pytest.raises(ValueError):
        get_logger("external")


def test_selectable_is_channels_plus_reserved():
    assert set(SELECTABLE_CHANNELS) == set(CHANNELS) | set(RESERVED_CHANNELS)
    assert "external" in SELECTABLE_CHANNELS
    assert "external" not in CHANNELS


def test_level_no_orders_correctly():
    from ayder_cli.log import level_no

    assert level_no("TRACE") < level_no("DEBUG") < level_no("WARNING")


def test_flush_is_callable():
    from ayder_cli.log import flush

    flush()   # must not raise even with no sinks configured
