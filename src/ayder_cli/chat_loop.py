"""
Chat Loop Module - Manages the agentic conversation loop.

This module separates the concerns of:
- Iteration management and checkpoint triggers
- Tool call handling
- Memory checkpoint/restore cycles (delegated to MemoryManager)
"""

from dataclasses import dataclass, field
from typing import Optional, Callable

from ayder_cli.application.checkpoint_orchestrator import (
    CheckpointOrchestrator,
    CheckpointTrigger,
    EngineState,
)
from ayder_cli.checkpoint_manager import CheckpointManager
from ayder_cli.memory import MemoryManager
from ayder_cli.parser import parse_custom_tool_calls


@dataclass
class LoopState:
    """Mutable state for the chat loop."""

    iteration: int = 0
    should_continue: bool = True
    result: Optional[str] = None


@dataclass
class LoopConfig:
    """Configuration for the chat loop."""

    max_iterations: int = 50
    model: str = "qwen3-coder:latest"
    num_ctx: int = 65536
    verbose: bool = False
    permissions: set = field(default_factory=set)


class IterationController:
    """Manages iteration counting and checkpoint triggers."""

    def __init__(
        self,
        max_iterations: int,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        self.max_iterations = max_iterations
        self.cm = checkpoint_manager
        self._iteration = 0

    @property
    def iteration(self) -> int:
        return self._iteration

    def increment(self) -> int:
        """Increment iteration counter and return new value."""
        self._iteration += 1
        return self._iteration

    def reset(self) -> None:
        """Reset iteration counter to 0."""
        self._iteration = 0

    def should_trigger_checkpoint(self) -> bool:
        """Check if we've exceeded the iteration limit via shared CheckpointTrigger."""
        trigger = CheckpointTrigger(max_iterations=self.max_iterations)
        return trigger.should_trigger(self._iteration)

    def handle_checkpoint(self, clear_and_restore_fn: Callable[[], None]) -> bool:
        """Handle memory checkpoint if available.

        Args:
            clear_and_restore_fn: Function to clear messages and restore from memory

        Returns:
            True if checkpoint was handled and loop should continue, False otherwise
        """
        if self.cm and self.cm.has_saved_checkpoint():
            clear_and_restore_fn()
            self.reset()
            return True
        return False


class ToolCallHandler:
    """Handles parsing and execution of tool calls."""

    def __init__(self, tool_executor, session, permissions: set, verbose: bool):
        self.tool_executor = tool_executor
        self.session = session
        self.permissions = permissions
        self.verbose = verbose

    def parse_tool_calls(self, msg, content: str):
        """Parse tool calls from LLM response.

        Args:
            msg: The LLM response message object
            content: The text content from the message

        Returns:
            Tuple of (tool_calls, custom_calls)
        """
        tool_calls = msg.tool_calls
        custom_calls = []

        if not tool_calls:
            custom_calls = parse_custom_tool_calls(content)

            # Check for parser errors
            for call in custom_calls:
                if "error" in call:
                    self.session.add_message(
                        "user", f"Tool parsing error: {call['error']}"
                    )
                    custom_calls = []
                    break

        return tool_calls, custom_calls

    def execute(self, msg, tool_calls, custom_calls) -> bool:
        """Execute tool calls.

        Args:
            msg: The raw LLM response message (for tool_calls preservation)
            tool_calls: List of tool calls from LLM
            custom_calls: List of custom parsed tool calls

        Returns:
            True if a terminal tool was executed, False otherwise
        """
        # If tools were called: add the message with tool_calls
        if tool_calls or custom_calls:
            self.session.append_raw(msg)

        # Execute tool calls
        if tool_calls:
            return self.tool_executor.execute_tool_calls(
                tool_calls, self.session, self.permissions, self.verbose
            )
        elif custom_calls:
            return self.tool_executor.execute_custom_calls(
                custom_calls, self.session, self.permissions, self.verbose
            )

        return False


class ChatLoop:
    """Orchestrates the agentic chat loop."""

    def __init__(
        self,
        llm_provider,
        tool_executor,
        session,
        config: LoopConfig,
        checkpoint_manager: Optional[CheckpointManager] = None,
        memory_manager: Optional[MemoryManager] = None,
    ):
        self.llm = llm_provider
        self.tools = tool_executor
        self.session = session
        self.config = config
        self.cm = checkpoint_manager
        self.mm = memory_manager

        # Initialize sub-components
        self.iteration_ctrl = IterationController(
            config.max_iterations, checkpoint_manager
        )
        self.tool_handler = ToolCallHandler(
            tool_executor, session, config.permissions, config.verbose
        )

    def run(self, user_input: str) -> Optional[str]:
        """Run the chat loop for a single user input.

        Args:
            user_input: The user's input message

        Returns:
            The assistant's text response, or None if only tools ran
        """
        self.session.add_message("user", user_input)

        while True:
            self.iteration_ctrl.increment()

            # Check if we need a memory checkpoint
            if self.iteration_ctrl.should_trigger_checkpoint():
                if self._handle_checkpoint():
                    continue
                else:
                    # Max iterations reached, no checkpoint possible
                    return None

            # Get tool schemas
            schemas = self._get_tool_schemas()

            # Call LLM
            response = self.llm.chat(
                model=self.config.model,
                messages=self.session.get_messages(),
                tools=schemas,
                options={"num_ctx": self.config.num_ctx},
                verbose=self.config.verbose,
            )

            # Process response
            result, should_exit = self._process_response(response)

            if should_exit:
                return result
            # Otherwise, continue loop (non-terminal tools were executed)

    def _handle_checkpoint(self) -> bool:
        """Handle iteration limit checkpoint via shared CheckpointOrchestrator.

        Returns:
            True if checkpoint handled and loop should continue, False otherwise
        """
        orchestrator = CheckpointOrchestrator()

        # Try to restore from existing memory first
        if self.mm:
            if self.cm and self.cm.has_saved_checkpoint():
                self.mm.restore_from_checkpoint(self.session)
                state = EngineState(
                    iteration=self.iteration_ctrl.iteration,
                    messages=list(self.session.get_messages()),
                )
                orchestrator.reset_state(state)
                orchestrator.restore_from_checkpoint(state, {"cycle": 0, "summary": ""})
                self.iteration_ctrl.reset()
                return True

            # No existing memory — create a checkpoint then reset via orchestrator
            if self.mm.create_checkpoint(
                self.session,
                self.config.model,
                self.config.num_ctx,
                self.config.permissions,
                self.config.verbose,
            ):
                state = EngineState(
                    iteration=self.iteration_ctrl.iteration,
                    messages=list(self.session.get_messages()),
                )
                orchestrator.reset_state(state)
                orchestrator.restore_from_checkpoint(state, {"cycle": 0, "summary": ""})
                self.iteration_ctrl.reset()
                return True

        return False

    def _get_tool_schemas(self) -> list:
        """Get tool schemas, respecting no_tools flag."""
        if self.session.state.pop("no_tools", False):
            return []
        return self.tools.tool_registry.get_schemas()

    def _process_response(self, response) -> tuple[Optional[str], bool]:
        """Process LLM response.

        Args:
            response: LLM response object

        Returns:
            Tuple of (text_response, should_exit)
            - text_response: Text content if no tools, None otherwise
            - should_exit: True if loop should exit (terminal tool or text response)
        """
        msg = response.choices[0].message
        content = msg.content or ""

        # Parse tool calls
        tool_calls, custom_calls = self.tool_handler.parse_tool_calls(msg, content)

        # Check if no tools were called - return text response
        if not tool_calls and not custom_calls:
            if content:
                self.session.add_message("assistant", content)
                return content, True  # Exit with text response
            return None, True  # Empty response, exit

        # Execute tool calls
        is_terminal = self.tool_handler.execute(msg, tool_calls, custom_calls)

        if is_terminal:
            return None, True  # Terminal tool hit, exit loop

        # Tools executed successfully, continue loop
        return None, False
