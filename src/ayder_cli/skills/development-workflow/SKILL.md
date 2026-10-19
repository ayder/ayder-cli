---
name: development-workflow
description: Multi-step software work - a new feature, a refactor, a bug whose cause is unknown, a change across several files. Not for small, obvious edits, quick fixes or questions.
---

# Development workflow

Use this workflow for software work in the current project. Act as an experienced engineer.

## Workflow

1. Orient: read `AGENTS.md` and `README.md` if they exist, then the code the task touches.
2. Align: restate the goal and surface ambiguities. Ask before planning when the goal is
   unclear.
3. Plan first: write the plan with `note(action="create", note_id="plan-<slug>")`: the
   steps, the files each step touches, and how each step is verified. Then create one
   task per step with `task(action="create", title=..., body=...)`. Change no project
   files before the plan is approved.
4. Present the plan: show the steps and their verification to the user, and name the
   plan note.
5. Get approval: wait until the plan is approved. The user approves it, or a reviewer
   agent does when the user asked for one: find it with `agent(action="list")`, dispatch
   it with `agent(action="call", name=..., task=...)` giving the plan and asking for
   "approve" or the changes needed, and collect the verdict with
   `agent(action="read_result", run_id=..., wait=true)`. On requested changes, update the
   plan note and the tasks, then present and ask for approval again.
6. Execute and validate: work through the tasks in order. Set each one with
   `task(action="update_status", identifier=..., status="in_progress")` when you start it and
   `status="done"` only when its verification passes. Run the project's tests and checks
   and inspect the results. Delegate a large, parallelizable or specialized task to an
   agent with `agent(action="call", task_id=...)`.
7. Iterate: learn from errors and retry until the checks pass. Stop and ask when stuck;
   mark the task `blocked` and say why.
8. Report at milestones: plan created, starting a task, task done, final delivery. A
   short line each is enough; the final delivery summarizes what changed and how it was
   verified.

## Coding standards

- Match the existing style, architecture, tooling and dependencies of the codebase.
- Use established patterns; avoid overengineering.
- Keep changes targeted. No unrelated refactors unless asked.
- Ask before committing, unless the user already gave commit instructions.
