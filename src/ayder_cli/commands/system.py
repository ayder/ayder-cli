from typing import Dict, Any
from ayder_cli.ui import draw_box
from ayder_cli.core.context import SessionContext
from ayder_cli.prompts import SYSTEM_PROMPT, PLANNING_PROMPT_TEMPLATE
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
class ClearCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/clear"

    @property
    def description(self) -> str:
        return "Clear conversation history and reset context"

    def execute(self, args: str, session: SessionContext) -> bool:
        # Clear messages but keep system prompt if present
        messages = session.messages
        if messages:
            # We assume the first message is system prompt if it exists
            if messages[0].get("role") == "system":
                system_msg = messages[0]
                messages.clear()
                messages.append(system_msg)
            else:
                messages.clear()
        
        # Add a prompt asking AI to acknowledge the reset
        reset_prompt = (
            "The conversation has been cleared. "
            "Please acknowledge this reset and confirm you're ready to start fresh."
        )
        session.messages.append({"role": "user", "content": reset_prompt})
        
        draw_box("Conversation history cleared.", title="System", width=80, color_code="32")
        return True


@register_command
class SummaryCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/summary"

    @property
    def description(self) -> str:
        return "Prompt AI to summarize conversation and save to .ayder/current_memory.md"

    def execute(self, args: str, session: SessionContext) -> bool:
        # Build conversation history text
        messages = session.messages
        if len(messages) <= 1:
            draw_box("No conversation to summarize.", title="System", width=80, color_code="33")
            return True
        
        # Get conversation (excluding system prompts)
        conversation = []
        for msg in messages:
            if msg.get("role") in ("user", "assistant"):
                conversation.append(msg)
        
        if not conversation:
            draw_box("No conversation to summarize.", title="System", width=80, color_code="33")
            return True
        
        # Build conversation text
        conversation_text = ""
        for msg in conversation:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_text += f"[{role}] {content}\n\n"
        
        # Create the summarization prompt
        summary_prompt = (
            "Please summarize the following conversation and save it to `.ayder/current_memory.md`.\n\n"
            "The summary should:\n"
            "- Capture key decisions, context, and progress\n"
            "- Be concise but comprehensive\n"
            "- Help future me understand what we've done so far\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            "Use the write_file tool to save the summary to `.ayder/current_memory.md`."
        )
        
        # Add the prompt as a user message for the agent to process
        session.messages.append({"role": "user", "content": summary_prompt})
        
        draw_box(
            "Summary request submitted. The AI will summarize and save to .ayder/current_memory.md",
            title="Summary",
            width=80,
            color_code="36"
        )
        return True


@register_command
class LoadCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/load"

    @property
    def description(self) -> str:
        return "Prompt AI to load memory from .ayder/current_memory.md"

    def execute(self, args: str, session: SessionContext) -> bool:
        memory_file = session.project.root / ".ayder" / "current_memory.md"
        
        if not memory_file.exists():
            draw_box(
                f"Memory file not found: {memory_file}\nRun /summary first to create it.",
                title="Load",
                width=80,
                color_code="33"
            )
            return True
        
        try:
            content = memory_file.read_text(encoding="utf-8")
            
            # Create a prompt for the AI to acknowledge the loaded memory
            load_prompt = (
                "I've loaded the previous conversation memory from `.ayder/current_memory.md`. "
                "Please acknowledge this context and continue from where we left off.\n\n"
                "[Memory from previous conversation]:\n"
                f"{content}"
            )
            
            # Add as a user message for the agent to process
            session.messages.append({"role": "user", "content": load_prompt})
            
            draw_box(
                f"Memory loaded from: {memory_file}\n"
                "The AI will acknowledge this context.",
                title="Load",
                width=80,
                color_code="32"
            )
            
        except Exception as e:
            draw_box(
                f"Error loading memory: {str(e)}",
                title="Error",
                width=80,
                color_code="31"
            )
        
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
        
        # Combined prompt: summarize, save, and acknowledge
        compact_prompt = (
            "I am compacting our conversation. Please do the following:\n\n"
            "1. SUMMARIZE this conversation:\n"
            f"{conversation_text}\n"
            "2. SAVE the summary to `.ayder/current_memory.md` using write_file\n"
            "3. CONFIRM the conversation has been reset\n"
            "4. ACKNOWLEDGE the saved context so we can continue\n\n"
            "Provide a brief summary, save it, confirm reset, and acknowledge the context."
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


