"""Tests for command registry."""

import pytest
from ayder_cli.commands.base import BaseCommand
from ayder_cli.commands.registry import CommandRegistry, register_command

class MockCommand(BaseCommand):
    @property
    def name(self):
        return "/mock"
    
    @property
    def description(self):
        return "Mock command"
        
    def execute(self, args, session):
        return True

class TestCommandRegistry:
    """Test CommandRegistry class."""

    def test_register_command(self):
        """Test registering and retrieving a command."""
        registry = CommandRegistry()
        cmd = MockCommand()
        registry.register(cmd)
        
        assert registry.get_command("/mock") == cmd
        assert registry.get_command("/unknown") is None

    def test_list_commands(self):
        """Test listing all commands."""
        registry = CommandRegistry()
        cmd1 = MockCommand()
        registry.register(cmd1)
        
        cmds = registry.list_commands()
        assert len(cmds) == 1
        assert cmds[0] == cmd1

    def test_decorator_registration(self):
        """Test decorator registration."""
        # Note: The decorator uses the global registry, so this affects global state.
        # We need to be careful or mock the global registry.
        # Ideally, we verify the side effect.
        
        from ayder_cli.commands.registry import _registry
        
        @register_command
        class DecoratedCommand(BaseCommand):
            @property
            def name(self):
                return "/decorated"
            
            @property
            def description(self):
                return "Decorated"
                
            def execute(self, args, session):
                return True
                
        assert _registry.get_command("/decorated") is not None

    def test_get_command_names(self):
        """Test getting all command names."""
        registry = CommandRegistry()
        
        # Register multiple commands
        cmd1 = MockCommand()
        registry.register(cmd1)
        
        class AnotherMockCommand(BaseCommand):
            @property
            def name(self):
                return "/another"
            
            @property
            def description(self):
                return "Another mock"
                
            def execute(self, args, session):
                return True
        
        cmd2 = AnotherMockCommand()
        registry.register(cmd2)
        
        names = registry.get_command_names()
        assert len(names) == 2
        assert "/another" in names  # Sorted alphabetically
        assert "/mock" in names
