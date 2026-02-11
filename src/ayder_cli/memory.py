"""
Cross-session memory storage and LLM-based checkpoint operations for ayder-cli.

This module provides:
1. Persistent memory storage (JSON Lines in .ayder/memory/memories.jsonl)
2. LLM-based checkpoint/restore operations for long-running sessions

Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.checkpoint_manager import CHECKPOINT_FILE_NAME
from ayder_cli.prompts import (
    MEMORY_CHECKPOINT_PROMPT_TEMPLATE,
    MEMORY_RESTORE_PROMPT_TEMPLATE,
    MEMORY_QUICK_RESTORE_MESSAGE_TEMPLATE,
    MEMORY_NO_MEMORY_MESSAGE,
)


def _get_memory_dir(project_ctx: ProjectContext) -> Path:
    """Return the memory directory path for the current project context."""
    return project_ctx.root / ".ayder" / "memory"


def _get_memory_file(project_ctx: ProjectContext) -> Path:
    """Return the memories JSONL file path."""
    return _get_memory_dir(project_ctx) / "memories.jsonl"


def save_memory(project_ctx: ProjectContext, content: str, category: str = None, tags: str = None) -> str:
    """Save a piece of context to persistent cross-session memory.

    Args:
        project_ctx: Project context for path resolution.
        content: The content to remember.
        category: Optional category for organization.
        tags: Optional comma-separated tags string.

    Returns:
        ToolSuccess or ToolError.
    """
    try:
        memory_dir = _get_memory_dir(project_ctx)
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = _get_memory_file(project_ctx)

        # Parse tags
        tag_list = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "category": category,
            "tags": tag_list,
            "timestamp": datetime.now().isoformat(),
        }

        with open(memory_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

        return ToolSuccess(f"Memory saved (id: {entry['id'][:8]}...)")

    except Exception as e:
        return ToolError(f"Error saving memory: {str(e)}", "execution")


def load_memory(project_ctx: ProjectContext, category: str = None, query: str = None, limit: int = 10) -> str:
    """Load saved memories from persistent cross-session storage.

    Args:
        project_ctx: Project context for path resolution.
        category: Optional category filter.
        query: Optional search query to filter by content.
        limit: Maximum number of memories to return (default: 10).

    Returns:
        ToolSuccess with JSON array of memories, or ToolError.
    """
    try:
        memory_file = _get_memory_file(project_ctx)

        if not memory_file.exists():
            return ToolSuccess("[]")

        memories = []
        with open(memory_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Apply filters
                if category and entry.get("category") != category:
                    continue
                if query and query.lower() not in entry.get("content", "").lower():
                    continue

                memories.append(entry)

        # Return most recent first, limited
        memories.reverse()
        memories = memories[:limit]

        return ToolSuccess(json.dumps(memories, indent=2))

    except Exception as e:
        return ToolError(f"Error loading memories: {str(e)}", "execution")


class MemoryManager:
    """Manages LLM-based checkpoint/restore operations for long-running agent sessions.
    
    This class handles all LLM interactions related to memory operations, including:
    - Creating checkpoints by asking the LLM to summarize progress
    - Restoring context from saved checkpoints
    - Building prompts for checkpoint and restore operations
    
    File I/O for checkpoints is delegated to CheckpointManager.
    """
    
    def __init__(
        self,
        project_ctx: ProjectContext,
        llm_provider=None,
        tool_executor=None,
        checkpoint_manager=None
    ):
        """Initialize MemoryManager.
        
        Args:
            project_ctx: Project context for path resolution
            llm_provider: LLM provider for making checkpoint calls
            tool_executor: Tool executor for executing save operations
            checkpoint_manager: CheckpointManager for file I/O operations
        """
        self.project_ctx = project_ctx
        self.llm = llm_provider
        self.tool_executor = tool_executor
        self.cm = checkpoint_manager
        self._checkpoint_dir = project_ctx.root / ".ayder" / "memory"
        self._checkpoint_file = self._checkpoint_dir / CHECKPOINT_FILE_NAME
        self._cycle_count = 0
    
    def _ensure_checkpoint_dir(self) -> None:
        """Ensure the checkpoint directory exists."""
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def _read_checkpoint(self) -> Optional[str]:
        """Read the current checkpoint content if it exists.
        
        Returns:
            Checkpoint content as string, or None if no checkpoint exists
        """
        if not self._checkpoint_file.exists():
            return None
        try:
            return self._checkpoint_file.read_text(encoding="utf-8")
        except Exception:
            return None
    
    def build_checkpoint_prompt(self, conversation_summary: str) -> str:
        """Build the prompt asking LLM to create a checkpoint.
        
        Args:
            conversation_summary: Summary of the current conversation/state
            
        Returns:
            Prompt string for the LLM
        """
        return MEMORY_CHECKPOINT_PROMPT_TEMPLATE.format(
            conversation_summary=conversation_summary,
            memory_file_name=CHECKPOINT_FILE_NAME
        )
    
    def build_restore_prompt(self, checkpoint_content: Optional[str] = None) -> str:
        """Build the prompt for restoring context from checkpoint.
        
        Args:
            checkpoint_content: Optional pre-loaded checkpoint content
            
        Returns:
            Prompt string for restoring context
        """
        if checkpoint_content is None:
            checkpoint_content = self._read_checkpoint() or "No previous checkpoint found."
        
        return MEMORY_RESTORE_PROMPT_TEMPLATE.format(
            memory_file_name=CHECKPOINT_FILE_NAME,
            memory_content=checkpoint_content
        )
    
    def build_quick_restore_message(self) -> str:
        """Build a quick restore message for after a checkpoint cycle.
        
        Returns:
            User message content for restoring context
        """
        checkpoint_content = self._read_checkpoint()
        if not checkpoint_content:
            return MEMORY_NO_MEMORY_MESSAGE
        
        return MEMORY_QUICK_RESTORE_MESSAGE_TEMPLATE.format(
            memory_content=checkpoint_content
        )
    
    def create_checkpoint(
        self,
        session,
        model: str,
        num_ctx: int,
        permissions: set,
        verbose: bool
    ) -> bool:
        """Create a memory checkpoint by asking LLM to write a summary.
        
        This method orchestrates the LLM interaction to create a checkpoint:
        1. Builds a conversation summary
        2. Asks LLM to create a checkpoint via prompt
        3. Executes any tool calls from LLM response
        4. Resets the conversation
        5. Loads back the memory as a user message
        
        Args:
            session: Chat session for message management
            model: Model name
            num_ctx: Context window size
            permissions: Granted permission categories
            verbose: Whether to show verbose output
            
        Returns:
            True if checkpoint was created successfully, False otherwise
        """
        if not self.llm or not self.tool_executor:
            return False
        
        # Build a summary of the conversation so far
        conversation_summary = self._build_conversation_summary(session)
        
        # Step 1: Ask LLM to write memory checkpoint
        checkpoint_prompt = self.build_checkpoint_prompt(conversation_summary)
        session.add_message("user", checkpoint_prompt)
        
        # Get schemas for tools (we need write_file tool)
        schemas = self.tool_executor.tool_registry.get_schemas()
        
        response = self.llm.chat(
            model=model,
            messages=session.get_messages(),
            tools=schemas,
            options={"num_ctx": num_ctx},
            verbose=verbose
        )
        
        msg = response.choices[0].message
        content = msg.content or ""
        tool_calls = msg.tool_calls
        
        # If LLM made tool calls to save memory, execute them
        if tool_calls:
            session.append_raw(msg)
            self.tool_executor.execute_tool_calls(tool_calls, session, permissions, verbose)
        elif content:
            # LLM responded with text, maybe it already saved or we need to retry
            session.add_message("assistant", content)
        
        # Step 2: Reset the conversation (keep only system message)
        session.clear_messages(keep_system=True)
        
        # Step 3: Load back the memory as a user message
        restore_msg = self.build_quick_restore_message()
        session.add_message("user", restore_msg)
        
        self._cycle_count += 1
        
        return True
    
    def restore_from_checkpoint(self, session) -> None:
        """Restore session from saved checkpoint.
        
        Args:
            session: Chat session to restore
        """
        session.clear_messages(keep_system=True)
        restore_msg = self.build_quick_restore_message()
        session.add_message("user", restore_msg)
    
    def _build_conversation_summary(self, session) -> str:
        """Build a summary of recent conversation.
        
        Args:
            session: Chat session with messages
            
        Returns:
            String summary of last 10 messages
        """
        summary = ""
        for msg in session.get_messages()[-10:]:  # Last 10 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate long content
            if content:
                summary += f"[{role}] {content[:100]}...\n"
        return summary


def create_memory_manager(
    project_root: str = ".",
    llm_provider=None,
    tool_executor=None,
    checkpoint_manager=None
) -> MemoryManager:
    """Factory function to create a MemoryManager instance.
    
    Args:
        project_root: Project root directory path
        llm_provider: LLM provider for making checkpoint calls
        tool_executor: Tool executor for executing save operations
        checkpoint_manager: CheckpointManager for file I/O operations
        
    Returns:
        Configured MemoryManager instance
    """
    from ayder_cli.core.context import ProjectContext
    project_ctx = ProjectContext(project_root)
    return MemoryManager(project_ctx, llm_provider, tool_executor, checkpoint_manager)
