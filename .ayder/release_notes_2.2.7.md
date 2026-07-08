# ayder-cli 2.2.7 - Internal Release Notes

## Summary

This release folds in the shared skill-loading backend, system prompt tuning,
input quality-of-life work, and a stale-test cleanup pass.

## Changes

- Added a model-facing `skill(action=...)` tool for listing, loading, and
  unloading project skills from `.ayder/skills/`.
- Rewired `/skill` to use the same skill backend as model tool calls.
- Skill loading now bundles `SKILL.md` with directly referenced local resources
  before injecting the active skill system message.
- Added active-skill unload/replacement behavior that preserves the shared chat
  message list.
- Tuned the standard system prompt role guidance.
- Added TUI support for leading `!` shell shortcuts and async turn preparation.
- Added `@file` picker support in the input box.
- Fixed `ayder --resume` so resumed TUI sessions keep the model saved with the
  session instead of silently falling back to the current config model.
- Fixed dynamic/project plugin path normalization so declared path parameters
  are sandboxed through `ProjectContext` like built-in tools.
- Removed a stale `/skill` private-helper absence test; behavior-level tests now
  cover delegation.

## Validation

- `uv run poe lint`
- `uv run poe typecheck`
- `uv run poe test`

## Notes

`.ayder/` is gitignored and used as scratch/internal documentation, so this file
is intentionally local-only unless force-added for release packaging.
