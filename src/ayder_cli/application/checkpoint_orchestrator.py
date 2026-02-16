"""Shared Checkpoint Orchestration Service — Phase 05.

Single policy path for both CLI and TUI checkpoint behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


@dataclass
class RuntimeContext:
    """Interface context — accepted by orchestrator but does not alter behavior."""

    interface: str  # "cli" | "tui"
    max_iterations: int = 50


@dataclass
class EngineState:
    """Mutable engine state managed by the orchestrator."""

    iteration: int
    messages: list
    checkpoint_cycle: int = 0
    restored_cycle: int = 0


@dataclass
class Summary:
    """Checkpoint summary produced from current engine state."""

    content: str


class CheckpointTransition(Enum):
    TRIGGER_AND_RESET = "trigger_and_reset"


class CheckpointTrigger:
    """Determines when a checkpoint should fire."""

    def __init__(self, max_iterations: int) -> None:
        self.max_iterations = max_iterations

    def should_trigger(self, current_iteration: int) -> bool:
        return current_iteration >= self.max_iterations


def create_checkpoint_trigger(context: RuntimeContext) -> CheckpointTrigger:
    """Create a trigger from a runtime context — same threshold for CLI and TUI."""
    return CheckpointTrigger(max_iterations=context.max_iterations)


class CheckpointOrchestrator:
    """Shared service that orchestrates checkpoint reset/restore for both interfaces."""

    def reset_state(self, state: EngineState, context: Optional[RuntimeContext] = None) -> None:
        """Reset iteration counter and clear non-system messages."""
        state.iteration = 0
        state.messages = [m for m in state.messages if m.get("role") == "system"]

    def restore_from_checkpoint(
        self,
        state: EngineState,
        saved: dict,
        context: Optional[RuntimeContext] = None,
    ) -> None:
        """Load saved checkpoint state and increment cycle count."""
        state.restored_cycle = saved.get("cycle", 0)
        state.checkpoint_cycle += 1
        summary = saved.get("summary", "")
        state.messages.append({"role": "user", "content": summary})

    def generate_summary(
        self,
        state: EngineState,
        context: Optional[RuntimeContext] = None,
    ) -> Summary:
        """Generate a summary from current engine state — interface-agnostic."""
        parts = []
        for msg in state.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                parts.append(content)
        content = " | ".join(parts) if parts else "No content"
        return Summary(content=content)

    def apply_transition(self, state: EngineState, transition: CheckpointTransition) -> None:
        """Apply a state transition — deterministic, no interface branching."""
        if transition is CheckpointTransition.TRIGGER_AND_RESET:
            self.reset_state(state)

    def orchestrate_checkpoint(
        self,
        state: EngineState,
        summary: str,
        checkpoint_manager: Any,
        memory_manager: Any = None,
        save: bool = True,
    ) -> str:
        """Save checkpoint, reset state, restore with real summary data.

        Single shared transition path for both CLI and TUI.

        Args:
            state: Mutable engine state to reset.
            summary: Real checkpoint summary content (not a placeholder).
            checkpoint_manager: Used to persist summary (skipped if save=False).
            memory_manager: Optional — used to build restore message.
            save: Set False when caller has already persisted the summary.

        Returns:
            The restore message to inject into the conversation.
        """
        if save:
            checkpoint_manager.save_checkpoint(summary)
        self.reset_state(state)
        saved_data = {"cycle": state.checkpoint_cycle, "summary": summary}
        self.restore_from_checkpoint(state, saved_data)
        if memory_manager is not None and hasattr(memory_manager, "build_quick_restore_message"):
            return memory_manager.build_quick_restore_message()
        return f"[SYSTEM: Context reset. Previous summary saved.]\n\n{summary}\n\nPlease continue."
