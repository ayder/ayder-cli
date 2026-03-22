"""Tests for loops package exports and ChatLoopConfig."""

from ayder_cli.loops import ChatLoop, ChatLoopConfig, ChatCallbacks


class TestLoopsPackageExports:
    def test_chatloop_exported(self):
        assert ChatLoop is not None

    def test_chatloopconfig_exported(self):
        assert ChatLoopConfig is not None

    def test_chatcallbacks_exported(self):
        assert ChatCallbacks is not None

    def test_chatloop_is_not_subclass_of_anything_unexpected(self):
        # ChatLoop no longer inherits AgentLoopBase — verify the hierarchy is flat
        bases = [b.__name__ for b in ChatLoop.__mro__[1:]]
        assert "AgentLoopBase" not in bases


class TestChatLoopConfig:
    def test_defaults(self):
        cfg = ChatLoopConfig()
        assert cfg.model == "qwen3-coder:latest"
        assert cfg.num_ctx == 65536
        assert cfg.permissions == {"r"}
        assert cfg.verbose is False

    def test_custom_values(self):
        cfg = ChatLoopConfig(model="gpt-4", permissions={"r", "w"})
        assert cfg.model == "gpt-4"
        assert cfg.permissions == {"r", "w"}
