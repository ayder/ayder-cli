"""Extracted TUI command handlers from AyderApp.

Each handler is a standalone function taking (app, args, chat_view) instead of
being a method on AyderApp. This cuts AyderApp roughly in half.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ayder_cli.core.context import ProjectContext
from ayder_cli.tui.screens import CLISelectScreen, CLIPermissionScreen, TaskEditScreen
from ayder_cli.tui.widgets import ChatView, StatusBar, CLIInputBar

if TYPE_CHECKING:
    from ayder_cli.tui.app import AyderApp


def handle_help(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Show help message in TUI."""
    help_text = "**Available Commands:**\n\n"
    for cmd_name in sorted(COMMAND_MAP):
        handler = COMMAND_MAP[cmd_name]
        desc = handler.__doc__ or ""
        # Use just the first line of the docstring
        desc = desc.strip().split("\n")[0]
        help_text += f"- `{cmd_name}` — {desc}\n"

    help_text += "\n**Keyboard Shortcuts:**\n"
    help_text += "- `Ctrl+Q` — Quit\n"
    help_text += "- `Ctrl+X` / `Ctrl+C` — Cancel operation\n"
    help_text += "- `Ctrl+L` — Clear chat\n"

    chat_view.add_assistant_message(help_text)


def handle_model(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /model command."""
    if not args.strip():
        try:
            models = app.llm.list_models()
            if not models:
                chat_view.add_system_message(f"Current model: {app.model}")
                return

            # Show interactive select screen
            items = [(m, m) for m in sorted(models)]

            def on_model_selected(selected: str | None) -> None:
                if selected:
                    app.model = selected
                    app.chat_loop.config.model = selected
                    app.update_system_prompt_model()
                    status_bar = app.query_one("#status-bar", StatusBar)
                    status_bar.set_model(selected)
                    chat_view.add_system_message(f"Switched to model: {selected}")

            app.push_screen(
                CLISelectScreen(
                    title="Select model",
                    items=items,
                    current=app.model,
                    description=f"Currently using: {app.model}"
                ),
                on_model_selected
            )
        except Exception as e:
            chat_view.add_system_message(f"Error listing models: {e}")
    else:
        new_model = args.strip()
        app.model = new_model
        app.chat_loop.config.model = new_model
        app.update_system_prompt_model()
        status_bar = app.query_one("#status-bar", StatusBar)
        status_bar.set_model(new_model)
        chat_view.add_system_message(f"Switched to model: {new_model}")


def handle_tasks(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /tasks command."""
    from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _parse_title, _extract_id

    try:
        project_ctx = ProjectContext(".")
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            chat_view.add_system_message("No tasks directory found. Create tasks first with /plan.")
            return

        # Build list of tasks
        items = []
        task_paths = {}  # Map display text to task path

        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue

            title = _parse_title(task_file)
            content = task_file.read_text(encoding="utf-8")

            # Determine status
            status = "pending"
            if "- **status:** done" in content.lower():
                status = "done"
            elif "- **status:** in_progress" in content.lower():
                status = "in_progress"

            # Format display with status indicator
            status_icon = "✓" if status == "done" else "○" if status == "pending" else "◐"
            display = f"TASK-{task_id:03d}: {title} [{status_icon}]"

            items.append((str(task_id), display))
            task_paths[str(task_id)] = task_file

        if not items:
            chat_view.add_system_message("No tasks found. Create tasks first with /plan.")
            return

        def on_task_selected(selected: str | None) -> None:
            if selected:
                task_id = int(selected)
                task_path = task_paths.get(selected)
                if task_path:
                    title = _parse_title(task_path)
                    _run_implement_task(app, task_id, title, chat_view)

        app.push_screen(
            CLISelectScreen(
                title="Select task to implement",
                items=items,
                description=f"{len(items)} task(s) found • Enter to implement • Esc to cancel"
            ),
            on_task_selected
        )

    except Exception as e:
        chat_view.add_system_message(f"Error listing tasks: {e}")


def handle_tools(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /tools command - list all available tools."""
    from ayder_cli.tools.schemas import tools_schema

    try:
        if not tools_schema:
            chat_view.add_system_message("No tools available.")
            return

        tools_text = "**Available Tools:**\n\n"
        for tool in tools_schema:
            func = tool.get('function', {})
            name = func.get('name', 'Unknown')
            desc = func.get('description', 'No description provided.')
            if len(desc) > 100:
                desc = desc[:100] + "..."
            tools_text += f"- `{name}` — {desc}\n"

        chat_view.add_assistant_message(tools_text)
    except Exception as e:
        chat_view.add_system_message(f"Error listing tools: {e}")


def handle_verbose(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /verbose command."""
    current = getattr(app, '_verbose_mode', False)
    app._verbose_mode = not current
    status = "ON" if app._verbose_mode else "OFF"
    chat_view.add_system_message(f"Verbose mode: {status}")


def handle_compact(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /compact command."""
    from ayder_cli.prompts import COMPACT_COMMAND_PROMPT_TEMPLATE

    if len(app.messages) <= 1:
        chat_view.add_system_message("No conversation to compact.")
        return

    conversation_text = ""
    for msg in app.messages:
        if msg.get("role") in ("user", "assistant"):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_text += f"[{role}] {content}\n\n"

    system_msg = None
    if app.messages and app.messages[0].get("role") == "system":
        system_msg = app.messages[0]
    app.messages.clear()
    if system_msg:
        app.messages.append(system_msg)

    compact_prompt = COMPACT_COMMAND_PROMPT_TEMPLATE.format(conversation_text=conversation_text)
    app.messages.append({"role": "user", "content": compact_prompt})
    chat_view.add_system_message("Compacting: summarize → save → clear → load")

    app.chat_loop.reset_iterations()
    app.start_llm_processing()


def handle_plan(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /plan command."""
    from ayder_cli.prompts import PLANNING_PROMPT_TEMPLATE

    if not args.strip():
        chat_view.add_system_message("Usage: /plan <task description>\nExample: /plan Implement user authentication")
        return

    planning_prompt = PLANNING_PROMPT_TEMPLATE.format(task_description=args.strip())
    app.messages.append({"role": "user", "content": planning_prompt})
    chat_view.add_system_message(f"Planning: {args.strip()[:50]}...")

    app.start_llm_processing()


def handle_ask(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /ask command."""
    if not args.strip():
        chat_view.add_system_message("Usage: /ask <question>\nExample: /ask What is Python?")
        return

    app.messages.append({"role": "user", "content": args.strip()})
    chat_view.add_user_message(args.strip())

    app.start_llm_processing(no_tools=True)


def handle_implement(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /implement command."""
    from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _parse_title, _extract_id
    from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

    if not args.strip():
        chat_view.add_system_message("Usage: /implement <task_id|name|pattern>\nExample: /implement 001")
        return

    project_ctx = ProjectContext(".")
    tasks_dir = _get_tasks_dir(project_ctx)
    query = args.strip()

    try:
        task_id = int(query)
        task_path = _get_task_path_by_id(project_ctx, task_id)
        if task_path:
            title = _parse_title(task_path)
            rel_path = project_ctx.to_relative(task_path)
            command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
            app.messages.append({"role": "user", "content": command})
            chat_view.add_system_message(f"Running TASK-{task_id:03d}: {title}")

            app.start_llm_processing()
            return
    except ValueError:
        pass

    matching = []
    query_lower = query.lower()
    for task_file in sorted(tasks_dir.glob("*.md")):
        task_id = _extract_id(task_file.name)
        if task_id is None:
            continue
        title = _parse_title(task_file)
        if query_lower in title.lower():
            matching.append((task_id, task_file, title))

    if not matching:
        chat_view.add_system_message(f"No tasks found matching: {query}")
        return

    for task_id, task_path, title in matching:
        rel_path = project_ctx.to_relative(task_path)
        command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
        app.messages.append({"role": "user", "content": command})

    chat_view.add_system_message(f"Running {len(matching)} matching task(s)...")

    app.start_llm_processing()


def handle_implement_all(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /implement-all command."""
    from ayder_cli.tasks import _get_tasks_dir, _extract_id, _parse_title
    from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

    project_ctx = ProjectContext(".")
    tasks_dir = _get_tasks_dir(project_ctx)

    if not tasks_dir.exists():
        chat_view.add_system_message("No tasks directory found. Create tasks first with /plan.")
        return

    pending = []
    for task_file in sorted(tasks_dir.glob("*.md")):
        task_id = _extract_id(task_file.name)
        if task_id is None:
            continue
        content = task_file.read_text(encoding="utf-8")
        if "- **status:** pending" in content.lower() or "- **status:** todo" in content.lower():
            title = _parse_title(task_file)
            pending.append((task_id, title))

    if not pending:
        chat_view.add_system_message("No pending tasks found. All tasks are complete!")
        return

    task_list = "\n".join([f"  - TASK-{tid:03d}: {title}" for tid, title in pending])
    chat_view.add_system_message(f"Implementing {len(pending)} pending tasks:\n{task_list}")

    app.messages.append({"role": "user", "content": TASK_EXECUTION_ALL_PROMPT_TEMPLATE})

    app.start_llm_processing()


def _open_task_in_editor(app: AyderApp, task_id: int, task_path, chat_view: ChatView) -> None:
    """Open task in an in-app TextArea editor screen."""
    from pathlib import Path

    path = Path(task_path)
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        chat_view.add_system_message(f"Error reading task: {e}")
        return

    def on_edit_result(new_content: str | None) -> None:
        if new_content is None:
            chat_view.add_system_message("Edit cancelled.")
            return
        try:
            path.write_text(new_content, encoding="utf-8")
            chat_view.add_system_message(f"Task TASK-{task_id:03d} saved.")
        except Exception as e:
            chat_view.add_system_message(f"Error saving task: {e}")

    app.push_screen(
        TaskEditScreen(title=f"TASK-{task_id:03d}", content=content),
        on_edit_result
    )


def handle_task_edit(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /task-edit command — show interactive task selector or edit by ID."""
    from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _parse_title, _extract_id

    project_ctx = ProjectContext(".")

    # Direct edit by ID if arg provided
    if args.strip():
        try:
            task_id = int(args.strip())
        except ValueError:
            chat_view.add_system_message(f"Invalid task ID: {args.strip()}")
            return

        task_path = _get_task_path_by_id(project_ctx, task_id)
        if task_path is None:
            chat_view.add_system_message(f"Task TASK-{task_id:03d} not found.")
            return

        _open_task_in_editor(app, task_id, task_path, chat_view)
        return

    # No arg — show interactive select screen
    try:
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            chat_view.add_system_message("No tasks directory found. Create tasks first with /plan.")
            return

        items = []
        task_paths = {}

        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue

            title = _parse_title(task_file)
            content = task_file.read_text(encoding="utf-8")

            status = "pending"
            if "- **status:** done" in content.lower():
                status = "done"
            elif "- **status:** in_progress" in content.lower():
                status = "in_progress"

            status_icon = "✓" if status == "done" else "○" if status == "pending" else "◐"
            display = f"TASK-{task_id:03d}: {title} [{status_icon}]"

            items.append((str(task_id), display))
            task_paths[str(task_id)] = task_file

        if not items:
            chat_view.add_system_message("No tasks found. Create tasks first with /plan.")
            return

        def on_task_selected(selected: str | None) -> None:
            if selected:
                tid = int(selected)
                path = task_paths.get(selected)
                if path:
                    _open_task_in_editor(app, tid, path, chat_view)

        app.push_screen(
            CLISelectScreen(
                title="Select task to edit",
                items=items,
                description=f"{len(items)} task(s) found • ↑↓ navigate • Enter to edit • Esc to cancel"
            ),
            on_task_selected
        )

    except Exception as e:
        chat_view.add_system_message(f"Error listing tasks: {e}")


def handle_archive(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /archive-completed-tasks command."""
    import shutil
    from ayder_cli.tasks import _get_tasks_dir, _extract_id, _parse_title

    project_ctx = ProjectContext(".")
    tasks_dir = _get_tasks_dir(project_ctx)

    if not tasks_dir.exists():
        chat_view.add_system_message("No tasks directory found.")
        return

    archive_dir = tasks_dir.parent / "task_archive"
    archived = []

    for task_file in sorted(tasks_dir.glob("*.md")):
        task_id = _extract_id(task_file.name)
        if task_id is None:
            continue
        content = task_file.read_text(encoding="utf-8")
        if "- **status:** done" in content.lower():
            title = _parse_title(task_file)
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(task_file), str(archive_dir / task_file.name))
            archived.append((task_id, title))

    if not archived:
        chat_view.add_system_message("No completed tasks to archive.")
    else:
        lines = "\n".join(f"  TASK-{tid:03d}: {title}" for tid, title in archived)
        chat_view.add_system_message(f"Archived {len(archived)} completed task(s):\n{lines}")


def handle_permission(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /permission command -- open permission toggle screen."""
    def on_result(new_permissions: set | None):
        if new_permissions is not None:
            app.permissions = new_permissions
            app.chat_loop.config.permissions = new_permissions
            status_bar = app.query_one("#status-bar", StatusBar)
            status_bar.update_permissions(new_permissions)
            mode_str = "".join(sorted(new_permissions))
            chat_view.add_system_message(f"Permissions updated: mode {mode_str}")

    app.push_screen(
        CLIPermissionScreen(app.permissions),
        on_result
    )


def do_clear(app: AyderApp, chat_view: ChatView) -> None:
    """Clear conversation history."""
    if app.messages:
        if app.messages[0].get("role") == "system":
            system_msg = app.messages[0]
            app.messages.clear()
            app.messages.append(system_msg)
        else:
            app.messages.clear()

    app.chat_loop.reset_iterations()
    chat_view.clear_messages()
    chat_view.add_system_message("Conversation history cleared.")


def _run_implement_task(app: AyderApp, task_id: int, title: str, chat_view: ChatView) -> None:
    """Run a single task implementation."""
    from ayder_cli.tasks import _get_task_path_by_id
    from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

    project_ctx = ProjectContext(".")
    task_path = _get_task_path_by_id(project_ctx, task_id)

    if task_path is None:
        chat_view.add_system_message(f"Task TASK-{task_id:03d} not found.")
        return

    rel_path = project_ctx.to_relative(task_path)
    command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
    app.messages.append({"role": "user", "content": command})
    chat_view.add_system_message(f"Running TASK-{task_id:03d}: {title}")

    app.start_llm_processing()


# Command dispatch map: command name -> handler function
# All handlers have signature (app, args, chat_view) -> None
COMMAND_MAP: dict[str, Callable] = {
    "/help": handle_help,
    "/model": handle_model,
    "/tasks": handle_tasks,
    "/tools": handle_tools,
    "/verbose": handle_verbose,
    "/compact": handle_compact,
    "/plan": handle_plan,
    "/ask": handle_ask,
    "/implement": handle_implement,
    "/implement-all": handle_implement_all,
    "/task-edit": handle_task_edit,
    "/archive-completed-tasks": handle_archive,
    "/permission": handle_permission,
}
