---
name: development-workflow
description: Multi-step software work - a new feature, a refactor, a bug whose cause is unknown, a change across several files. Not for small, obvious edits, quick fixes or questions.
---

# Development workflow

Use this workflow for software work in the current project. Act as an experienced engineer.

## Scale the process to the task

- Small and obvious (a typo, a one-line fix, a config value): make the change, verify it,
  report.
- Multi-step (a feature, a refactor, a bug with an unknown cause, anything that
  touches several files): follow the full workflow below.

## Workflow

1. Orient: read `AGENTS.md` and `README.md` if they exist, then the code the task touches.
2. Align: restate the goal and surface ambiguities before acting.
3. Approve: present the approach and wait for the user's approval before executing.
4. Plan: break the work into steps. Track them with the `task()` tool and refer to them
   while working. Mark a task done only when it succeeds.
5. Execute and validate: follow the plan, run the project's tests and checks, inspect the
   results. Delegate to agents when a subtask is large, parallelizable or specialized.
6. Iterate: learn from errors and retry until the checks pass. Stop and ask when stuck.
7. Report at milestones only: plan created, task done, final delivery. Stay concise
   between them.

## Coding standards

- Match the existing style, architecture, tooling and dependencies of the codebase.
- Use established patterns; avoid overengineering.
- Keep changes targeted. No unrelated refactors unless asked.
- Ask before committing, unless the user already gave commit instructions.
