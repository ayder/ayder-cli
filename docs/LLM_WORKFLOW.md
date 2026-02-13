# TUI LLM Response Handling Workflow

This document describes how LLM responses are processed in the Ayder CLI TUI.

## Overview

The TUI uses a layered architecture to handle LLM responses:

1. **API Layer** (`client.py`) - Makes the LLM API call
2. **Processing Layer** (`tui/chat_loop.py`) - Processes the response, handles tool calls
3. **Parsing Layer** (`parser.py`, `tui/parser.py`) - Parses tool calls and strips markup
4. **Execution Layer** (`tools/registry.py`, `tools/impl.py`) - Executes tools
5. **UI Layer** (`tui/app.py`) - Displays content via callbacks

## Files in the Workflow

### Core Response Handling

| File | Purpose |
|------|---------|
| `src/ayder_cli/tui/chat_loop.py` | **Main response handler** - `TuiChatLoop.run()` processes LLM responses, extracts content/think blocks, routes to tool handlers |
| `src/ayder_cli/tui/app.py` | **UI implementation** - Implements `TuiCallbacks` protocol to receive `on_assistant_content`, `on_thinking_content`, displays in widgets |
| `src/ayder_cli/client.py` | **LLM API client** - `call_llm_async()` makes the actual API call |

### Parsing & Content Processing

| File | Purpose |
|------|---------|
| `src/ayder_cli/tui/parser.py` | **TUI content processor** - `strip_for_display()`, `extract_think_blocks()`, `has_custom_tool_calls()` |
| `src/ayder_cli/parser.py` | **Tool call parser** - `parse_custom_tool_calls()` converts XML → structured data, handles Minimax/DeepSeek formats |

### Tool Execution

| File | Purpose |
|------|---------|
| `src/ayder_cli/tools/registry.py` | **Tool registry** - `ToolRegistry.execute()` runs tools with middleware, callbacks, validation |
| `src/ayder_cli/tools/impl.py` | **Tool implementations** - `read_file`, `write_file`, `list_files`, etc. |
| `src/ayder_cli/tools/definition.py` | **Tool definitions** - `TOOL_DEFINITIONS` with schemas, permissions, aliases |
| `src/ayder_cli/tools/schemas.py` | **Tool schemas** - OpenAI-compatible function schemas |

## Response Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TuiChatLoop.run()                               │
│                    (src/ayder_cli/tui/chat_loop.py)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1: Call LLM                                                        │
│                                                                         │
│   response = await call_llm_async(                                      │
│       self.llm,                                                         │
│       self.messages,                                                    │
│       self.config.model,                                                │
│       tools=tool_schemas,                                               │
│       num_ctx=self.config.num_ctx,                                      │
│   )                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 2: Process Response Metadata                                       │
│                                                                         │
│   usage = getattr(response, "usage", None)                              │
│   tokens = getattr(usage, "total_tokens", 0)                            │
│   self.cb.on_token_usage(self._total_tokens)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 3: Extract Message Content                                         │
│                                                                         │
│   message = response.choices[0].message                                 │
│   content = message.content or ""                                       │
│   tool_calls = message.tool_calls  # OpenAI native format               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 4: Build & Append Assistant Message                                │
│                                                                         │
│   msg_dict = {"role": "assistant", "content": content}                  │
│   if tool_calls:                                                        │
│       msg_dict["tool_calls"] = [...]                                    │
│   self.messages.append(msg_dict)                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 5: Extract & Display Think Blocks                                  │
│   (src/ayder_cli/tui/parser.py)                                         │
│                                                                         │
│   think_blocks = content_processor.extract_think_blocks(content)        │
│   for text in think_blocks:                                             │
│       self.cb.on_thinking_content(text)  # → UI widget                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 6: Strip Tool Markup & Display Content                             │
│   (src/ayder_cli/tui/parser.py)                                         │
│                                                                         │
│   display = content_processor.strip_for_display(content)                │
│   if display:                                                           │
│       self.cb.on_assistant_content(display)  # → UI widget              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 7: Route to Tool Handlers (priority order)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
            ▼                       ▼                       ▼
┌──────────────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│ 7a: OpenAI tool_calls│  │ 7b: Custom XML   │  │ 7c: JSON Fallback   │
│                      │  │                  │  │                     │
│ if tool_calls:       │  │ if has_custom_   │  │ json_calls =        │
│     _execute_openai_ │  │    tool_calls(): │  │     parse_json_     │
│     tool_calls()     │  │     parse_custom_│  │     tool_calls()    │
│                      │  │     tool_calls() │  │                     │
│ Uses:                │  │     _execute_    │  │ Uses:               │
│ - tool_calls from    │  │     custom_tool_ │  │ - tui/parser.py     │
│   response object    │  │     calls()      │  │ Uses:               │
│                      │  │                  │  │ - tui/parser.py     │
└──────────────────────┘  └──────────────────┘  └─────────────────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 8: Execute Tools                                                   │
│   (src/ayder_cli/tools/registry.py)                                     │
│                                                                         │
│   result = await asyncio.to_thread(                                     │
│       self.registry.execute, name, args                                 │
│   )                                                                     │
│                                                                         │
│   - Validates arguments against schema                                  │
│   - Normalizes parameters (aliases, paths, types)                       │
│   - Runs middleware (safe mode, etc.)                                   │
│   - Executes tool function from impl.py                                 │
│   - Runs callbacks for UI updates                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 9: Append Tool Results & Loop                                      │
│                                                                         │
│   self.messages.append({                                                │
│       "role": "tool",                                                   │
│       "tool_call_id": tid,                                              │
│       "name": name,                                                     │
│       "content": str(result)                                            │
│   })                                                                    │
│                                                                         │
│   Loop continues to Step 1 (next LLM call with tool results)            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Supported Tool Call Formats

The TUI supports multiple LLM tool call output formats:

### 1. OpenAI Native Format
```json
{
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "read_file",
        "arguments": "{\"file_path\": \"test.txt\"}"
      }
    }
  ]
}
```

### 2. Standard XML Format
```xml
<function=read_file><parameter=file_path>test.txt</parameter></function>
```

### 3. Wrapped Format (Minimax, etc.)
```xml
<tool_call>
<function=read_file><parameter=file_path>test.txt</parameter></function>
</tool_call>
```

### 4. Namespaced Format
```xml
<minimax:tool_call>
<function=read_file><parameter=file_path>test.txt</parameter></function>
</minimax:tool_call>
```

### 5. DeepSeek Format
```xml
<function_calls>
<invoke name="read_file">
<parameter name="file_path" string="true">test.txt</parameter>
</invoke>
</function_calls>
```

### 6. JSON Array Fallback
```json
[{"function": {"name": "read_file", "arguments": {"file_path": "test.txt"}}}]
```

## Callback Protocol

The `TuiCallbacks` protocol decouples `chat_loop.py` from Textual widgets:

```python
@runtime_checkable
class TuiCallbacks(Protocol):
    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_thinking_content(self, text: str) -> None: ...
    def on_token_usage(self, total_tokens: int) -> None: ...
    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    def on_tools_cleanup(self) -> None: ...
    def on_system_message(self, text: str) -> None: ...
    async def request_confirmation(self, name: str, arguments: dict) -> object | None: ...
    def is_cancelled(self) -> bool: ...
```

Implemented in `app.py` by the main App class.

## Key Design Patterns

1. **Protocol-based callbacks** - `chat_loop.py` never touches Textual widgets directly
2. **Compiled regex** - All patterns pre-compiled in `ContentProcessor` for performance
3. **Async tool execution** - Tools run in thread pool via `asyncio.to_thread()`
4. **Middleware support** - Registry supports middleware for safe mode, logging, etc.
5. **Format normalization** - Multiple input formats normalized to standard internal representation
