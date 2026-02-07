from abc import ABC, abstractmethod
from typing import Dict, Any, List
from ayder_cli.core.context import SessionContext

class BaseCommand(ABC):
    """Abstract base class for all commands."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The command name (e.g., '/help')."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Short description for help text."""
        pass
        
    @abstractmethod
    def execute(self, args: str, session: SessionContext) -> bool:
        """Execute the command.
        
        Args:
            args: The arguments passed to the command (string after the command name).
            session: The session context containing configuration, messages, state, etc.
            
        Returns:
            True if execution was successful/handled, False otherwise.
        """
        pass
