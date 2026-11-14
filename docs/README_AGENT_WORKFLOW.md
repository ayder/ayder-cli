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
- `agent(action="call", name="<name>", task=…, task_id=…, branch_name=…, base_branch=…)`
  → returns a **run id** immediately. It does not block. `action` and `name` are
  required; `task` may be left out only when `task_id` is given. Use
  `agent(action="list")` to discover the exact names.
- Dispatch independent tasks together (several `agent(action="call")` calls), then
  check `agent(action="status")` to see what is `working` vs `done`.
- Collect a finished one with `agent(action="read_result", run_id=<run_id>)`, or wait
  for a slow one with `agent(action="read_result", run_id=<run_id>, wait=true, timeout_s=…)`
  instead of polling in a loop.
- Each agent only sees the prompt you give it. **For task-file work, pass
  `task_id="TASK-NNN"` and `branch_name="agent/<slug>"`** — the harness resolves the
  id, **fails fast** if it doesn't exist, and embeds the task file itself in the
  agent's prompt. Do **not** read the task file and paste its body into `task`; use
  `task` only for extra steering (or as the whole instruction when there's no file).
- **Don't write notes or summaries yourself.** Every agent auto-saves its full
  deliverable to `.ayder/notes/`; collect it with `agent(action="read_result")` (or
  `read_file` its `note_path`). Re-summarizing an agent's output into your own note is wasted work.
- **Give pointers, not pasted content.** Agents share the working tree and have
  shell/read/search tools — they run their own `git diff` and read their own files.
  Hand a reviewer/QA/gate agent the branch, the base ref, the task id(s), and the
  paths; do **not** read source or diffs and paste them into `task`. Pasting wastes
  your context and is exactly what makes a review/QA dispatch stall.
- **Never dispatch an empty task.** Every `agent(action="call")` must carry a concrete
  instruction — a non-empty `task` and/or a `task_id` that resolves to a task file.
  If neither carries real content, you are not ready to dispatch — fix that first.

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
   one file per task, exactly like `/plan`: one call per task,
   `task(action="create", title=…, body=…, branch="agent/<slug>", dependencies="TASK-NNN,…")`.
   - `body` is the task in PRD form: `## Goal`, `## Files`, `## Acceptance Criteria`
     (as a checklist) and `## Notes`.
   - The tool allocates the next `TASK-<NNN>` id, names the file, writes the
     `## Signature` header (status `pending`) itself and returns the id. Do not
     hand-format a header or compute the next number; use `task(action="list")` to
     review the queue.
5. **Task review.** `architect_review` checks the **whole task set against the
   approved plan**: full coverage (every plan item maps to a task), no scope
   creep, correct sizing/sequencing, consistent interfaces across tasks. Loop
   split↔review until `VERDICT: APPROVED`. The user can now follow the queue with
   `/tasks` (○ pending · ◐ in_progress · ✓ done).
6. **Delegate (isolated — see git rules below).** Work the queue task by task:
   - Flip the task's `**Status:**` to `in_progress`, then dispatch it with
     `agent(action="call", name="senior_coder", task_id="TASK-NNN", branch_name="agent/<slug>", base_branch="feat/<slug>")`
     (small, low-risk tasks → the single `junior_coder`, one at a time). The harness
     hands the agent the task file and the branch directive — you don't paste the
     task body. Each agent commits only to its own branch.
   - When you collect and accept the result, flip the task's `**Status:**` to `done`.
   Update a status with `task(action="update_status", identifier="TASK-NNN",
   status="in_progress")` (or `status="done"`). This keeps `/tasks` accurate so
   the user always sees what is queued, in flight, and finished.
7. **QA.** `qa_engineer` writes and runs the test suite, reports real pass/fail output.
   Give it the branch + task ids; it reads the code and runs the tests itself.
8. **Review.** Tell `code_reviewer` WHERE, not the diff — the branch, the base ref, and
   the task ids (e.g. "review `feat/x` vs `main` for TASK-003..007; run `git diff` yourself").
   It gathers the diff and reads the files from the working tree. Send `CHANGES REQUIRED`
   findings back to the coder, then re-review.
9. **Gate + merge.** `acceptance_gate` collects the approved branches, merges them
   into `feat/<slug>`, resolves conflicts, runs the full suite, and checks every
   acceptance criterion. `GATE: PASS` → merge `feat/<slug>` into `main`.
   `GATE: FAIL` → send the failing criteria back to the relevant stage.

### Git rules — so agents don't step on each other

Agents without a branch share the main working directory, so two of them editing
at once will collide. Give every builder a branch and the harness isolates it:

- **One branch per task.** Name them `agent/<task-slug>` and pass
  `branch_name="agent/<task-slug>"` with `base_branch="feat/<slug>"` to
  `agent(action="call")`.
- **The harness makes the worktree.** A run with a `branch_name` works in its own
  worktree at `.ayder/worktrees/<task-slug>`, forked from `base_branch` (default: the
  repo's default branch; an existing branch is reused), and the worktree is removed
  when the run ends. Parallel builders never touch each other's files. The project
  must be a git repository, or the run fails.
- **Builders commit only to their own branch.** They never touch `main`, `feat/<slug>`,
  or another agent's branch. Uncommitted work is lost with the worktree: a branch run
  that makes no commit ends with status `error` ("no commit on branch"); re-dispatch it.
- **Only the gate merges.** It integrates branches in dependency order:
  ```bash
  git switch feat/<slug>
  git merge --no-ff agent/<task-slug>     # repeat per approved branch; resolve conflicts
  # run the full suite + acceptance checks, then:
  git switch main && git merge --no-ff feat/<slug>
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
