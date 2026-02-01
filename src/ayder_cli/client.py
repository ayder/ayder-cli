import json
from pathlib import Path
from openai import OpenAI
from ayder_cli import fs_tools
from ayder_cli.config import load_config
from ayder_cli.ui import draw_box, print_running, print_assistant_message, print_tool_result, confirm_tool_call, describe_tool_action, print_file_content, confirm_with_diff, print_tool_skipped
from ayder_cli.banner import print_welcome_banner
from ayder_cli.parser import parse_custom_tool_calls
from ayder_cli.commands import handle_command
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI

SYSTEM_PROMPT = """You are an expert Autonomous Software Engineer. You work with surgical precision and extreme efficiency.

### OPERATIONAL PRINCIPLES:
1. **STRICT NECESSITY**: Call a tool ONLY if it is the direct and primary requirement of the user's request. 
   - If asked to read a file, ONLY use `read_file`. 
   - Prohibited: Do not follow up with `ls`, `list_files`, or exploratory shell commands unless specifically requested.
2. **ONE TASK AT A TIME**: When using `create_task`, your turn ends immediately after the tool result. Do not plan, implement, or explore further.
3. **PRECISION OVER VOLUME**: Prefer `search_codebase` to find definitions over `list_files`. Use "line mode" in `read_file` for files over 100 lines.

### TOOL PROTOCOL:
You MUST use the specialized XML format for all tool calls. Failure to use this format will result in a parsing error.
Format:
<tool_call>
<function=tool_name>
<parameter=key1>value1</parameter>
</function>
</tool_call>

### CAPABILITIES:
- **File System**: `read_file`, `write_file`, `replace_string`. (Note: use `file_path` parameter for file paths).
- **Search**: `search_codebase` (regex supported). Use this to locate code before reading.
- **Shell**: `run_shell_command`. Use for tests and status checks.
- **Tasks**: `create_task`, `show_task`, `implement_task`.

### EXECUTION FLOW:
1. Receive request.
2. Determine the MINIMUM required tool call.
3. Execute and wait for result.
4. Stop immediately if the task (like creating a task) is complete.
"""

# Tools that end the agentic loop after execution
TERMINAL_TOOLS = {"create_task", "list_tasks", "show_task", "implement_task", "implement_all_tasks"}


def prepare_new_content(fname, args):
    """
    Prepare the content that will be written to a file.
    For write_file: return the content directly.
    For replace_string: read the file and apply the replacement in memory.
    Args can be either a dict or a JSON string.
    """
    try:
        # Handle JSON string arguments
        if isinstance(args, str):
            args = json.loads(args)

        if fname == "write_file":
            return args.get("content", "")

        elif fname == "replace_string":
            file_path = args.get("file_path", "")
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")

            if not file_path:
                return ""

            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                return content.replace(old_string, new_string)
            except Exception:
                return ""
        else:
            return ""

    except Exception:
        return ""


def run_chat():
    cfg = load_config()
    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
    MODEL = cfg.model

    # Generate project structure for macro-context
    try:
        project_structure = fs_tools.get_project_structure(max_depth=3)
        macro_context = f"""

### PROJECT STRUCTURE:
```
{project_structure}
```

This is the current project structure. Use `search_codebase` to locate specific code before reading files.
"""
    except Exception:
        macro_context = ""

    # Inject into system prompt
    enhanced_system_prompt = SYSTEM_PROMPT + macro_context

    messages = [
        {"role": "system", "content": enhanced_system_prompt}
    ]

    # Create history file in home directory
    history_file = str(Path("~/.ayder_chat_history").expanduser())

    # Create prompt session with emacs keybindings and history
    session = PromptSession(
        history=FileHistory(history_file),
        enable_history_search=True,
        multiline=False,
        vi_mode=False  # Emacs mode is default
    )

    # Runtime state (mutable dict so commands can toggle flags)
    state = {"verbose": cfg.verbose}

    # Print welcome banner
    print_welcome_banner(MODEL, str(Path.cwd()))

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
                    extra_body={"options": {"num_ctx": cfg.num_ctx}}
                )

                msg = response.choices[0].message
                content = msg.content or ""

                tool_calls = msg.tool_calls
                custom_calls = []
                if not tool_calls:
                    custom_calls = parse_custom_tool_calls(content)

                    # Check for parser errors
                    for call in custom_calls:
                        if "error" in call:
                            messages.append({
                                "role": "user",
                                "content": f"Tool parsing error: {call['error']}"
                            })
                            custom_calls = []
                            break

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

                        # Parse and normalize arguments
                        parsed = json.loads(fargs) if isinstance(fargs, str) else fargs
                        normalized = fs_tools.normalize_tool_arguments(fname, parsed)

                        # Validate before confirmation
                        is_valid, error_msg = fs_tools.validate_tool_call(fname, normalized)
                        if not is_valid:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": fname,
                                "content": f"Validation Error: {error_msg}"
                            })
                            declined = True
                            break

                        description = describe_tool_action(fname, normalized)

                        # Use diff preview for file-modifying tools
                        if fname in ("write_file", "replace_string"):
                            file_path = normalized.get("file_path", "")
                            new_content = prepare_new_content(fname, normalized)
                            confirmed = confirm_with_diff(file_path, new_content, description)
                        else:
                            confirmed = confirm_tool_call(description)

                        if not confirmed:
                            print_tool_skipped()
                            declined = True
                            break

                        result = fs_tools.execute_tool_call(fname, normalized)
                        print_tool_result(result)

                        if state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
                            print_file_content(normalized.get("file_path", ""))

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

                        # Normalize and validate custom calls
                        normalized = fs_tools.normalize_tool_arguments(fname, fargs)
                        is_valid, error_msg = fs_tools.validate_tool_call(fname, normalized)
                        if not is_valid:
                            messages.append({
                                "role": "user",
                                "content": f"Validation Error for tool '{fname}': {error_msg}"
                            })
                            declined = True
                            break

                        description = describe_tool_action(fname, normalized)

                        # Use diff preview for file-modifying tools
                        if fname in ("write_file", "replace_string"):
                            file_path = normalized.get("file_path", "")
                            new_content = prepare_new_content(fname, normalized)
                            confirmed = confirm_with_diff(file_path, new_content, description)
                        else:
                            confirmed = confirm_tool_call(description)

                        if not confirmed:
                            print_tool_skipped()
                            declined = True
                            break

                        result = fs_tools.execute_tool_call(fname, normalized)
                        print_tool_result(result)

                        if state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
                            print_file_content(normalized.get("file_path", ""))

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
