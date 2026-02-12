from typing import Dict, Any
from ayder_cli.ui import draw_box
from ayder_cli.core.context import SessionContext
from ayder_cli.prompts import (
    SYSTEM_PROMPT,
    PLANNING_PROMPT_TEMPLATE,
    COMPACT_COMMAND_PROMPT_TEMPLATE,
)
from .base import BaseCommand
from .registry import register_command, get_registry


@register_command
class HelpCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/help"
        
    @property
    def description(self) -> str:
        return "Show this help message"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        commands = get_registry().list_commands()
        # Sort by name
        commands.sort(key=lambda c: c.name)
        
        help_text = "Available Commands:\n"
        for cmd in commands:
            help_text += f"  {cmd.name:<15} - {cmd.description}\n"
            
        draw_box(help_text, title="Help", width=80, color_code="33")
        return True


@register_command
class VerboseCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/verbose"

    @property
    def description(self) -> str:
        return "Toggle verbose mode"

    def execute(self, args: str, session: SessionContext) -> bool:
        current = session.state.get("verbose", False)
        session.state["verbose"] = not current
        status = "ON" if session.state["verbose"] else "OFF"
        draw_box(f"Verbose mode: {status}", title="System", width=80, color_code="34")
        return True


@register_command
class CompactCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/compact"

    @property
    def description(self) -> str:
        return "Summarize conversation, save to memory, clear, and reload context"

    def execute(self, args: str, session: SessionContext) -> bool:
        messages = session.messages
        
        # Build conversation history (excluding system prompts)
        conversation = []
        for msg in messages:
            if msg.get("role") in ("user", "assistant"):
                conversation.append(msg)
        
        if not conversation:
            draw_box("No conversation to compact.", title="Compact", width=80, color_code="33")
            return True
        
        # Build conversation text
        conversation_text = ""
        for msg in conversation:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_text += f"[{role}] {content}\n\n"
        
        # Clear messages but keep system prompt
        system_msg = None
        if messages and messages[0].get("role") == "system":
            system_msg = messages[0]
        messages.clear()
        if system_msg:
            messages.append(system_msg)
        
        # Create compact prompt using the template
        compact_prompt = COMPACT_COMMAND_PROMPT_TEMPLATE.format(
            conversation_text=conversation_text
        )
        
        messages.append({"role": "user", "content": compact_prompt})
        
        draw_box(
            "Compacting: summarize → save → clear → load",
            title="Compact",
            width=80,
            color_code="36"
        )
        return True


@register_command
class PlanCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/plan"

    @property
    def description(self) -> str:
        return "Analyze request and create implementation tasks"

    def execute(self, args: str, session: SessionContext) -> bool:
        if not args.strip():
            draw_box(
                "Usage: /plan <task description>\n\n"
                "Example: /plan Implement user authentication with JWT tokens",
                title="Error",
                width=80,
                color_code="31"
            )
            return True

        # Inject the planning prompt with the user's task
        planning_prompt = PLANNING_PROMPT_TEMPLATE.format(task_description=args.strip())

        # Add the planning prompt as a user message
        session.messages.append({"role": "user", "content": planning_prompt})

        draw_box(
            f"Planning request submitted: {args.strip()[:50]}...",
            title="Plan",
            width=80,
            color_code="36"
        )
        return True


@register_command
class ModelCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/model"

    @property
    def description(self) -> str:
        return "List available models or switch to a different model"

    def execute(self, args: str, session: SessionContext) -> bool:
        if not args.strip():
            # List models
            try:
                models = session.llm.list_models()
                if not models:
                    draw_box("No models found or error fetching models from LLM provider.", title="Model", width=80, color_code="33")
                    # Still show the current model
                    current_model = session.state.get("model", session.config.model)
                    draw_box(f"Current active model: {current_model}", title="Current Model", width=80, color_code="36")
                    return True
                
                current_model = session.state.get("model", session.config.model)
                model_list = "Available Models:\n"
                # Sort models and highlight current
                for m in sorted(models):
                    prefix = " * " if m == current_model else "   "
                    model_list += f"{prefix}{m}\n"
                
                draw_box(model_list, title="Available Models", width=80, color_code="36")
            except Exception as e:
                draw_box(f"Error listing models: {str(e)}", title="Error", width=80, color_code="31")
            return True
        
        # Switch model
        new_model = args.strip()
        session.state["model"] = new_model
        draw_box(f"Switched to model: {new_model}", title="Model", width=80, color_code="32")
        return True


@register_command
class AskCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/ask"

    @property
    def description(self) -> str:
        return "Ask a general question (no tools used)"

    def execute(self, args: str, session: SessionContext) -> bool:
        if not args.strip():
            draw_box(
                "Usage: /ask <question>\n\n"
                "Example: /ask What is the difference between REST and GraphQL?",
                title="Error", width=80, color_code="31"
            )
            return True

        # Set flag to suppress tool schemas in the next LLM call
        session.state["no_tools"] = True

        # Inject the question as a user message
        session.messages.append({"role": "user", "content": args.strip()})

        draw_box(
            f"Question: {args.strip()[:60]}...",
            title="Ask", width=80, color_code="36"
        )
        return True
