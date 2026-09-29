# Gate

The procedure an agent follows to gate a candidate commit. Follow the steps in order and do
not interpret the results. Never edit a file, fix a failure, skip a step or create a worktree.
Test definitions live in [AGENTS.md](../AGENTS.md#test-definitions).

Input: the candidate SHA.

1. `git rev-parse HEAD` → expected: exactly the candidate SHA.
2. `git status --porcelain` → expected: empty output.
3. `uv run poe check-all` → expected: exit code 0. This runs lint, typecheck, the logging
   gates and the test suite, and stops at the first failing task.
4. Copy the final pytest summary line (`=== N passed, M skipped in …s ===`) verbatim.

Last measured: `2492 passed, 2 skipped` at `bdf44f5` (2026-09-29).

## Report format

```text
SHA: <candidate SHA>
1 git rev-parse HEAD: <output> (match|MISMATCH)
2 git status --porcelain: <empty|output>
3 uv run poe check-all: exit <code>
4 summary: <pytest summary line verbatim>
GATE COMPLETE | GATE FAILED at step <n>
```

`GATE COMPLETE` only when steps 1–3 meet their expected results.
