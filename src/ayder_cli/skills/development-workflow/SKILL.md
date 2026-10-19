---
name: development-workflow
description: Multi-step software work - a new feature, a refactor, a bug whose cause is unknown, a change across several files. Not for small, obvious edits, quick fixes or questions that need no change.
---

# Development workflow

1. Orient: read `AGENTS.md` and `README.md` if they exist, then the code the task touches.
2. Plan: write the plan with `note(action="create", note_id="plan-<slug>")`: the steps,
   the files each step touches, and how each step is verified. Create one task per step,
   in dependency order, with `task(action="create", title=..., body=..., dependencies=...)`.
   Change no project files before the plan is approved.
3. Approve: show the user the steps and their verification, name the plan note, and end
   your turn until the user approves. When the user asks for a reviewer agent, it
   approves instead: find it with `agent(action="list")`, send it the plan with
   `agent(action="call", name=..., task=...)`, and collect the verdict with
   `agent(action="read_result", run_id=..., wait=true)`. On requested changes, update
   the note and the tasks and ask again.
4. Execute: work through the tasks in order. Set each one `in_progress` with
   `task(action="update_status", identifier=..., status="in_progress")` when you start
   it, `done` when its verification passes, or `blocked` when you need the user, and
   tell the user why. A large, parallelizable or specialized task can go to an agent with
   `agent(action="call", task_id=...)`.
5. Report: one short line at plan created, task started, task done and final delivery.
   The final delivery says what changed and how it was verified.
6. Finish: ask before committing, unless the user gave commit instructions. Then unload
   this skill with `skill(action="unload", name="development-workflow")`.
