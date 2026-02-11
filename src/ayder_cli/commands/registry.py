from typing import Dict, Type
from .base import BaseCommand

class CommandRegistry:
    """Registry for CLI commands."""
    
    def __init__(self):
        self._commands: Dict[str, BaseCommand] = {}
        
    def register(self, command: BaseCommand) -> None:
        """Register a command instance."""
        self._commands[command.name] = command
        
    def get_command(self, name: str) -> BaseCommand | None:
        """Get a command by name."""
        return self._commands.get(name)
        
    def list_commands(self) -> list[BaseCommand]:
        """List all registered commands."""
        return list(self._commands.values())
    
    def get_command_names(self) -> list[str]:
        """Get all registered command names."""
        return sorted(self._commands.keys())

# Global registry instance
_registry = CommandRegistry()

def register_command(command_cls: Type[BaseCommand]):
    """Decorator to register a command class."""
    _registry.register(command_cls())
    return command_cls

def get_registry() -> CommandRegistry:
    """Get the global registry instance."""
    return _registry
