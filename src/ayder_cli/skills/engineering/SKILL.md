---
name: engineering
description: Build, change, debug or review code in a codebase; research a technical problem; plan multi-step technical work.
---

# Engineering

Use this workflow for software work in the current project. Act as an experienced engineer.

## Scale the process to the task

- Small and obvious (a typo, a one-line fix, a config value): make the change, verify it,
  report.
- Multi-step or risky (a feature, a refactor, a bug with an unknown cause, anything that
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

## Development lifecycle (all projects)

The order of work. The project's own AGENTS.md, test documentation and roadmaps own the rules
for each step; this list only orders them. Skip a step the project has no mechanism for.

**Every project has a gitignored `.ayder/` directory, and all internal development
documentation goes there:** specs, plans, reviews, roadmaps, version and release notes. Code,
tests and published user documentation stay in the repository as usual. Nothing under `.ayder/` is ever
committed. If a project lacks the directory or its `.gitignore` entry, add both before writing
the first artifact.

Each body of work gets its own dated directory, `.ayder/superpowers_<YYYYMMDD>/`, where
`<YYYYMMDD>` is the day the work started:

```
.ayder/superpowers_<YYYYMMDD>/
|-- plans/       # implementation plans; reference/ holds code that plans link to
|-- specs/       # designs and specifications
|-- decisions/   # decision records: why an approach was chosen or rejected
`-- pr/          # PR bodies and their evidence
```

Roadmaps, where a project has them, live in `.ayder/roadmaps/`.

1. Place the work on a release line from the project's roadmap, if it has one, then write its
   spec and plan under `.ayder/superpowers_<YYYYMMDD>/`. When code blocks would make a plan
   long, put them in `plans/reference/` and link each step to the exact file and block. That
   meets the writing-plans rule that code steps show their code. Say whether the linked code
   was run.
2. Each fix lands as a `test` commit, then a `fix` commit. Behavior changes update their
   owning document in the same PR.
3. If the project has a gate procedure, follow it: gate the PR's final SHA, and when tests are
   added or removed, re-measure its recorded baselines. A green CI is not a green gate. A
   project without a gate procedure skips this step.
4. A release folds the version bump into its last PR, and its release note goes under
   `.ayder/`. The operator tags; agents never do.

**Every PR requires the operator's confirmed verdict before it is opened.** A green gate, a
green CI or an agent's review is evidence for that verdict, not the verdict itself. Agents do
not open a PR without it.
