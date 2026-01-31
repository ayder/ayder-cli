import os
import json
from openai import OpenAI
from ayder_cli import fs_tools
from ayder_cli.config import load_config
from ayder_cli.ui import draw_box, print_running, print_assistant_message, print_tool_result, confirm_tool_call, describe_tool_action, print_file_content
from ayder_cli.banner import print_welcome_banner
from ayder_cli.parser import parse_custom_tool_calls
from ayder_cli.commands import handle_command
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI

SYSTEM_PROMPT = """You are an expert Autonomous Software Engineer.
You have access to a set of powerful tools to interact with the file system and shell.

Your Capabilities:
1.  **File System:** You can list, read, and write files.
    -   Use `read_file` with `start_line` and `end_line` ("line mode") to read specific sections of large files to save context.
    -   Use `replace_string` to edit code precisely without overwriting the whole file.
2.  **Command Window:** You can execute shell commands using `run_shell_command`.
    -   Use this to run tests, list directories (`ls -R`), check git status, or install dependencies.

Guidelines:
-   **Explore First:** When asked to work on a project, list files and read relevant code first.
-   **Verify:** After editing code, try to run a syntax check if possible.
-   **Be Precise:** When replacing text, ensure `old_string` matches exactly.
-   **Context:** If a file is huge, don't read the whole thing. Use `list_files` to find it, then `read_file` with line numbers.
-   **Tasks:** When the user asks you to create, add, or plan a task, use the `create_task` tool. This saves the task as a markdown file in .ayder/tasks/ (current working directory) with the naming format TASK-XXX.md. After creating a task, STOP. Do not proceed to implement, write code, or run any commands for that task. Just confirm the task was saved. To show a specific task, use the `show_task` tool with the task ID number.

You MUST use the provided tools to perform actions.
"""

# Tools that end the agentic loop after execution
TERMINAL_TOOLS = {"create_task", "list_tasks", "show_task", "implement_task", "implement_all_tasks"}

def run_chat():
    cfg = load_config()
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    MODEL = cfg["model"]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Create history file in home directory
    history_file = os.path.expanduser("~/.ayder_chat_history")

    # Create prompt session with emacs keybindings and history
    session = PromptSession(
        history=FileHistory(history_file),
        enable_history_search=True,
        multiline=False,
        vi_mode=False  # Emacs mode is default
    )

    # Runtime state (mutable dict so commands can toggle flags)
    state = {"verbose": cfg.get("verbose", False)}

    # Print welcome banner
    print_welcome_banner(MODEL, os.getcwd())

    while True:
        try:
            # Use prompt_toolkit for input with emacs keybindings
            user_input = session.prompt(ANSI("\n\033[1;36m❯\033[0m "), vi_mode=False)

            if not user_input.strip():
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\n\033[33mGoodbye!\033[0m\n")
                break

            # --- Slash Commands ---
            if user_input.startswith('/'):
                handle_command(user_input.strip(), messages, SYSTEM_PROMPT, state)
                continue
            # ----------------------

            print_running()
            messages.append({"role": "user", "content": user_input})

            # Main Loop for Agentic Steps (Allow up to 5 consecutive tool calls)
            for _ in range(5):
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=fs_tools.tools_schema,
                    tool_choice="auto",
                    extra_body={"options": {"num_ctx": cfg["num_ctx"]}}
                )

                msg = response.choices[0].message
                content = msg.content or ""

                tool_calls = msg.tool_calls
                custom_calls = []
                if not tool_calls:
                    custom_calls = parse_custom_tool_calls(content)

                if not tool_calls and not custom_calls:
                    # No tools used, just conversation
                    if content:
                        print_assistant_message(content)
                        messages.append({"role": "assistant", "content": content})
                    break # Wait for user input

                # If tools were called:
                messages.append(msg)

                # Execute Standard Calls
                declined = False
                hit_terminal = False
                if tool_calls:
                    for tc in tool_calls:
                        fname = tc.function.name
                        fargs = tc.function.arguments
                        description = describe_tool_action(fname, fargs)

                        if not confirm_tool_call(description):
                            print(draw_box("Tool call skipped by user.", title="Skipped", width=80, color_code="33"))
                            declined = True
                            break

                        result = fs_tools.execute_tool_call(fname, fargs)
                        print_tool_result(result)

                        if state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
                            parsed = json.loads(fargs) if isinstance(fargs, str) else fargs
                            print_file_content(parsed.get("file_path", ""))

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": fname,
                            "content": str(result)
                        })

                        if fname in TERMINAL_TOOLS:
                            hit_terminal = True
                            break

                # Execute Custom Calls
                if custom_calls and not declined and not hit_terminal:
                    for call in custom_calls:
                        fname = call['name']
                        fargs = call['arguments']
                        description = describe_tool_action(fname, fargs)

                        if not confirm_tool_call(description):
                            print(draw_box("Tool call skipped by user.", title="Skipped", width=80, color_code="33"))
                            declined = True
                            break

                        result = fs_tools.execute_tool_call(fname, fargs)
                        print_tool_result(result)

                        if state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
                            parsed = json.loads(fargs) if isinstance(fargs, str) else fargs
                            print_file_content(parsed.get("file_path", ""))

                        # Feed back as user message since it's a custom parsing loop
                        messages.append({
                            "role": "user",
                            "content": f"Tool '{fname}' execution result: {result}"
                        })

                        if fname in TERMINAL_TOOLS:
                            hit_terminal = True
                            break

                if declined or hit_terminal:
                    break

        except KeyboardInterrupt:
            print("\n\033[33m\nUse 'exit' or Ctrl+D to quit.\033[0m")
            continue
        except EOFError:
            print("\n\033[33mGoodbye!\033[0m\n")
            break
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print("\n" + draw_box(error_msg, title="Error", width=80, color_code="31"))

if __name__ == "__main__":
    run_chat()
