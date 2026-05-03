# Ollama Models — Verifying Tool-Call Compatibility

This guide explains how to determine whether a given Ollama model handles
tool calling cleanly via Ollama's native protocol, or whether it needs an
IN_CONTENT chat-driver. Use it whenever you add a new model family to the
[resolution matrix](../src/ayder_cli/providers/impl/ollama_drivers/matrix.py)
or investigate a regression.

## TL;DR — what counts as "working natively"

A model works natively when, given a request with `tools=[...]`, Ollama
returns:

1. `msg.tool_calls` populated with one or more `{id, function: {name, arguments}}` entries.
2. `msg.content` empty (or containing only natural-language commentary, never tool markup).

If `msg.content` contains any of these markers, the model is leaking and
needs an IN_CONTENT driver:

| Marker | Source |
|---|---|
| `<tool_call>...</tool_call>` | qwen-trained format |
| `<function_calls><invoke>...</invoke></function_calls>` | deepseek-r1/v3 |
| `<tool_calls>...</tool_calls>` (plural) | deepseek-v4 family |
| `<｜DSML｜tool_calls>` / `<｜DSML｜function_calls>` | deepseek with DSML wrappers |
| `<minimax:tool_call>...` | MiniMax-M1 |
| `<function=name>` / `<parameter=key>` | generic XML protocol output |

## Method 1 — `OllamaInspector.probe_native_tool_calling()` (preferred)

The probe lives at
[`src/ayder_cli/providers/impl/ollama_inspector.py`](../src/ayder_cli/providers/impl/ollama_inspector.py).
It sends a single non-streaming `/api/chat` request with a known tool
definition and inspects the response. This is the canonical answer to
"how can we be sure?" — code beats interpretation.

### Quick check from a Python REPL

```python
import asyncio
from ayder_cli.providers.impl.ollama_inspector import OllamaInspector

probe = asyncio.run(
    OllamaInspector(host="http://localhost:11434").probe_native_tool_calling(
        "qwen3.6:latest"
    )
)
print(probe.verdict)
print(probe.reason)
print("tool_calls returned:", probe.tool_call_count)
print("markup leaked:", probe.content_markup_found)
print("content preview:", probe.content_preview)
```

### Verdicts

| `probe.verdict` | Meaning | What to do |
|---|---|---|
| `native_works` | `msg.tool_calls` populated, content has no markup. | Matrix entry: `driver="generic_native"`. |
| `leaks_in_content` | Markup tokens present in `msg.content`. `probe.content_markup_found` shows which. | Use an existing IN_CONTENT driver (`deepseek`, `qwen3`, `minimax`, or `generic_xml`), or write a family-specific one. |
| `no_tool_call` | Neither `tool_calls` nor markup. Model ignored the tool list. | Inconclusive. Try a stronger prompt or different model state. |
| `stream_failed` | Ollama raised. `probe.raw_error` carries the message. | Check whether the message matches a `_BUG_SIGNATURES` entry in [`_errors.py`](../src/ayder_cli/providers/impl/ollama_drivers/_errors.py); the reactive fallback may engage in production. |

### Custom probe prompt

If the default `"Read the file at /tmp/probe.txt"` doesn't trigger a tool
call for your model, pass a domain-relevant prompt:

```python
probe = await inspector.probe_native_tool_calling(
    "deepseek-v4-pro:cloud",
    prompt="List the contents of /etc/hosts using the read_file tool",
)
```

### What the probe sends

Always the same minimal `read_file` tool, so verdicts are comparable across
models:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from disk",
    "parameters": {
      "type": "object",
      "properties": {"path": {"type": "string"}},
      "required": ["path"]
    }
  }
}
```

### What the probe checks for

Markup-detection patterns (in order, first match wins on the verdict; the
full set is reported in `probe.content_markup_found`):

```
<tool_call>           — singular qwen3 / wrapped formats
<function_calls>      — deepseek-r1/v3 wrapper
<tool_calls>          — deepseek-v4 plural wrapper
<function=...>        — generic XML function tag
<invoke              — deepseek invoke block
｜DSML｜              — fullwidth DSML markers (deepseek)
|DSML|                — ASCII DSML fallback
```

## Method 2 — direct `curl` (for shell debugging)

Two single-shot tests reproduce what the probe does. Useful for ad-hoc
investigation when you don't have a Python REPL handy or want to inspect
the raw streaming behavior.

### A. Native path with `tools=[...]` (the canonical test)

```bash
curl -fsS -N -o /tmp/probe.json -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  --data-raw '{
    "model": "qwen3.6:latest",
    "messages": [{"role": "user", "content": "Read the file at /tmp/foo.txt"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {
          "type": "object",
          "properties": {"path": {"type": "string"}},
          "required": ["path"]
        }
      }
    }],
    "stream": false,
    "think": false,
    "options": {"num_predict": 300}
  }'

cat /tmp/probe.json | python3 -m json.tool
```

**Healthy native output** (qwen3.6, deepseek-v4-pro:cloud, llama3.1, etc.):

```json
{
  "model": "qwen3.6",
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [{
      "id": "call_kqprwpsg",
      "function": {"name": "read_file", "arguments": {"path": "/tmp/foo.txt"}}
    }]
  },
  "done": true,
  "done_reason": "stop"
}
```

**Unhealthy output** (anything in `msg.content`):

```json
{
  "message": {
    "role": "assistant",
    "content": "<｜DSML｜tool_calls><｜DSML｜invoke name=\"read_file\">...",
    "tool_calls": []
  }
}
```

### B. Streaming path (catches mid-stream EOFs)

Some Ollama bugs only surface in streaming mode (e.g. issue #14834 truncated
tool-call XML, bare `EOF (status code: -1)`). Use this when the non-streaming
test passes but production hits errors:

```bash
curl -fsS -N -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  --data-raw '{
    "model": "qwen3.6:latest",
    "messages": [{"role": "user", "content": "Read /tmp/foo.txt"}],
    "tools": [{"type":"function","function":{"name":"read_file","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}],
    "stream": true,
    "think": false,
    "options": {"num_predict": 300}
  }' \
  | grep -E '"done":true|"error"|"tool_calls"|content":"[^"]'
```

Expected lines for a healthy stream — one chunk with `tool_calls`, one with
`done:true done_reason:"stop"`. Any line containing `"error":"..."` is a
classified failure; cross-reference the message against `_BUG_SIGNATURES`
in [`_errors.py`](../src/ayder_cli/providers/impl/ollama_drivers/_errors.py).

### C. IN_CONTENT bypass (only as a last resort)

Use this only to verify that an IN_CONTENT driver's prompt template would
work for a model. Sends `tools=null` plus an injected protocol instruction:

```bash
curl -fsS -N -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  --data-raw '{
    "model": "qwen3.6:latest",
    "messages": [
      {"role": "system", "content": "# Tools\n\n<tools>\n{\"type\":\"function\",\"function\":{\"name\":\"read_file\",\"parameters\":{\"type\":\"object\",\"properties\":{\"path\":{\"type\":\"string\"}}}}}\n</tools>\n\nFor each function call, return:\n<tool_call>\n{\"name\": <function-name>, \"arguments\": <args>}\n</tool_call>"},
      {"role": "user", "content": "Read /tmp/foo.txt"}
    ],
    "stream": true,
    "think": false,
    "options": {"num_predict": 500}
  }' \
  | grep -E '"done":true|"error"|content":"[^"]'
```

A common failure here is `{"error":"EOF"}` mid-stream — Ollama's chat
template is scanning the system prompt for `<tool_call>` tokens and
choking. **This is not a sign the model is broken; it's a sign the
IN_CONTENT path is wrong for this model.** Check method A; if that works,
prefer it.

## Decision flow for adding a new model family

```
Run probe (method 1) or curl test A (method 2).
│
├── verdict == native_works
│   → Add matrix row: ResolutionRule(family_substring="<family>", driver="generic_native")
│   → Done.
│
├── verdict == leaks_in_content
│   → Inspect probe.content_markup_found.
│   ├── Existing driver matches the markup style
│   │   (DSML or <function_calls> → deepseek; <tool_call>{json} → qwen3;
│   │    <minimax:tool_call> → minimax; otherwise → generic_xml)
│   │   → Re-route via matrix to that driver.
│   └── New markup style not covered by any existing driver
│       → Author a new driver under
│         src/ayder_cli/providers/impl/ollama_drivers/<family>.py
│         + paired test under
│         tests/providers/ollama_drivers/test_<family>.py
│       → Add matrix row pointing at it.
│
├── verdict == no_tool_call
│   → Try a stronger prompt; if still inconclusive, add the model to a
│     wishlist comment in matrix.py rather than guessing.
│
└── verdict == stream_failed
    → Match probe.raw_error against _BUG_SIGNATURES.
    → If matched: route to generic_native and trust reactive fallback.
    → If unmatched: propagate (the retry layer will decide).
```

## Currently-verified routing

| Model / family | Verdict | Driver | Notes |
|---|---|---|---|
| `qwen3.6:latest` | `native_works` | `generic_native` | Confirmed 2026-05. Earlier Ollama versions hit issue #14834. |
| `qwen2.x`, `qwen3.x` (general) | inferred `native_works` | `generic_native` | Same family routing as `qwen3.6`. |
| `deepseek-v4-pro:cloud` | `native_works` | `generic_native` | Confirmed 2026-05. Empty content + populated tool_calls. |
| `deepseek-r1`, `deepseek-v3` | not yet re-verified | `generic_native` | Inherited from family-substring rule. If you observe leaks, drop a matrix row routing the specific name to `deepseek` (the dormant IN_CONTENT driver). |
| `llama`, `mistral`, `gemma`, `phi`, `granite` | family routing only | `generic_native` | Trusted by convention; probe before any new entry. |
| `minimax-m1` | not yet re-probed | `minimax` | Default IN_CONTENT routing. Re-probe and consider switching to `generic_native` if the verdict comes back clean. |

## When to update this document

- A new model family is added to the matrix → add a row to the
  "Currently-verified routing" table with the date and verdict.
- A previously-routed model regresses → update its row, link the issue,
  and note the new driver routing.
- A new markup style is observed in `leaks_in_content` → add it to the
  TL;DR markup table and the probe's pattern list.

## Related files

- [`src/ayder_cli/providers/impl/ollama_inspector.py`](../src/ayder_cli/providers/impl/ollama_inspector.py) — `OllamaInspector`, `NativeToolProbe`, `probe_native_tool_calling`.
- [`src/ayder_cli/providers/impl/ollama_drivers/matrix.py`](../src/ayder_cli/providers/impl/ollama_drivers/matrix.py) — resolution matrix and rules for adding/removing rows.
- [`src/ayder_cli/providers/impl/ollama_drivers/_errors.py`](../src/ayder_cli/providers/impl/ollama_drivers/_errors.py) — `OllamaServerToolBug` and the curated bug-signature list.
- [`docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md`](superpowers/specs/2026-05-02-ollama-chat-drivers-design.md) — full design rationale.
- [`tests/providers/test_ollama_inspector.py`](../tests/providers/test_ollama_inspector.py) — probe test cases that double as usage examples.
