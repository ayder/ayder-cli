# Changelog

## 2.0.0

### Breaking
- `anthropic` and `google-genai` are no longer installed by default. Install the
  corresponding extra: `pip install ayder-cli[anthropic]` / `[google]`.
- Default install now ships OpenAI + Ollama (+ DeepSeek, which reuses the OpenAI SDK).

### Added
- Optional extras: `[anthropic]`, `[google]`, `[qwen]`, `[glm]`, `[all]`.
- Driver names `deepseek`, `qwen`/`dashscope`, `glm`/`zhipu` are now selectable.
- Selecting an uninstalled driver fails fast with the exact `pip install` command
  and a list of available drivers.
