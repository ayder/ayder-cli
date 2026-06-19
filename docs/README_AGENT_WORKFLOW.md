## Domain
Driving the multi-agent software-delivery harness defined in `config.toml.example`:
a 9-role pipeline (spec → review → plan → review → task-split → task-review →
build → QA → review → gate). After the plan is approved, the **architect** splits
it into task files in `.ayder/tasks/` (the same format `/plan` produces) and
**architect_review** checks the task set, so the user can follow the queue with
`/tasks`; parallel builders are isolated by git branches and the gate agent
collects and merges. This skill tells YOU — the main orchestrator LLM — how to run it.

## Trigger
A non-trivial software task ("build / implement / add feature X") where the
configured agents (`pm_spec`, `pm_review`, `architect`, `architect_review`,
`senior_coder`, `qa_engineer`, `junior_coder`, `code_reviewer`, `acceptance_gate`)
are available. For tiny one-file edits, just do it yourself — don't spin up the harness.

## Guidelines

You are the **orchestrator**. You do not write the feature yourself — you dispatch
specialist agents, pass each one the right context, and move work through the
pipeline. Keep your own messages short; let the agents do the heavy lifting.

### How to talk to an agent
- `call_agent("<name>", "<task>")` → returns a **run id** immediately. It does not block.
- Dispatch independent tasks together (several `call_agent` calls), then poll
  `agent_status()` to see what is `working` vs `done`.
- Collect a finished one with `read_agent_result(<run_id>)`, or wait for a slow one
  with `read_agent_result(<run_id>, wait=true, timeout_s=…)`.
- Each agent only sees the task string you give it. Hand it what it needs: the
  spec, the plan task, the branch to work on, the relevant file paths.
- **Never dispatch an empty task.** Every `call_agent` must carry a concrete,
  non-empty task: what to do, which files, which branch, and the acceptance
  criteria. If the task string would be empty, you are not ready to dispatch —
  fix that first.

### The pipeline (run in order)

1. **Branch off.** Create one integration branch for the feature:
   `git switch -c feat/<slug>`. All harness work happens off this branch; `main`
   is only touched by the final merge.
2. **Spec.** `pm_spec` writes the spec + acceptance criteria → `pm_review` checks it.
   Loop until `pm_review` returns `VERDICT: APPROVED`.
3. **Plan.** `architect` turns the approved spec into a development plan →
   `architect_review` checks it. Loop until `VERDICT: APPROVED`. The plan marks
   which tasks are **parallel** and which are small/low-risk.
4. **Task split (delegate it — don't split the work yourself).** Ask the
   `architect` to break the **approved plan** into task files in `.ayder/tasks/`,
   one file per task, exactly like `/plan`. Hand it this format to `write_file`:
   - Name each file `.ayder/tasks/TASK-<NNN>-<slug>.md` (zero-padded NNN;
     `list_tasks` first, then increment past the highest existing number).
   - Begin every file with this exact header, then the task in PRD form with its
     acceptance criteria, the files it touches, and its `agent/<slug>` branch:
     ```
     ## Signature
     - **ID:** TASK-<NNN>
     - **Status:** pending
     - **Created:** <YYYY-MM-DD HH:MM:SS>
     ```
5. **Task review.** `architect_review` checks the **whole task set against the
   approved plan**: full coverage (every plan item maps to a task), no scope
   creep, correct sizing/sequencing, consistent interfaces across tasks. Loop
   split↔review until `VERDICT: APPROVED`. The user can now follow the queue with
   `/tasks` (○ pending · ◐ in_progress · ✓ done).
6. **Delegate (isolated — see git rules below).** Work the queue task by task:
   - Flip the task's `**Status:**` to `in_progress`, then `call_agent` it to a
     `senior_coder` on its **own branch** (small, low-risk tasks → the single
     `junior_coder`, one at a time). Pass the task body, its branch, and the
     acceptance criteria as the **non-empty** task string. Each agent commits
     only to its own branch.
   - When you collect and accept the result, flip the task's `**Status:**` to `done`.
   Update a status by rewriting the task file's `**Status:**` line (read it with
   `show_task`, write it back with `write_file`). This keeps `/tasks` accurate so
   the user always sees what is queued, in flight, and finished.
7. **QA.** `qa_engineer` writes and runs the test suite, reports real pass/fail output.
8. **Review.** `code_reviewer` reviews each branch's diff. Send `CHANGES REQUIRED`
   findings back to the coder, then re-review.
9. **Gate + merge.** `acceptance_gate` collects the approved branches, merges them
   into `feat/<slug>`, resolves conflicts, runs the full suite, and checks every
   acceptance criterion. `GATE: PASS` → merge `feat/<slug>` into `main`.
   `GATE: FAIL` → send the failing criteria back to the relevant stage.

### Git rules — so agents don't step on each other

The agents share one working directory, so two builders editing at once will
collide. Isolate them with git:

- **One branch per task.** Name them `agent/<task-slug>`, branched off `feat/<slug>`.
- **For true parallel builds, give each builder its own worktree** (a separate
  folder) so their files never touch:
  ```bash
  git worktree add .ayder/worktrees/<task-slug> -b agent/<task-slug> feat/<slug>
  ```
  Tell the builder to work in that folder. If you'd rather keep it simple, skip
  worktrees and run the builders **one at a time** on their branches instead.
- **Builders commit only to their own branch.** They never touch `main`, `feat/<slug>`,
  or another agent's branch.
- **Only the gate merges.** It integrates branches in dependency order:
  ```bash
  git switch feat/<slug>
  git merge --no-ff agent/<task-slug>     # repeat per approved branch; resolve conflicts
  # run the full suite + acceptance checks, then:
  git switch main && git merge --no-ff feat/<slug>
  git worktree remove .ayder/worktrees/<task-slug>   # clean up
  ```

### Simple rules to keep it on the rails
- Don't skip a review gate. `pm_review`, `architect_review`, and `code_reviewer`
  exist to catch problems early — loop until each approves.
- Keep `junior_coder` to **one instance at a time** (local memory limit). Don't fan it out.
- Keep task statuses current: `pending` → `in_progress` (on dispatch) → `done`
  (on accepted result), so `/tasks` always reflects reality for the user.
- Never call an agent with an empty task string — no concrete task, no dispatch.
- A reviewer is always a different model family than the author it checks — trust
  that independent second opinion; don't override it without a reason.
- If an agent fails or times out, handle that task yourself or hand it to a
  `senior_coder` — don't re-dispatch the same failed agent in a loop.
- Tell the user the verdict at each gate; don't merge to `main` until `GATE: PASS`.

See `config.toml.example` for which model backs each role and why.
