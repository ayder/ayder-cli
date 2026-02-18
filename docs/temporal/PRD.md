# Product Requirements Document (PRD)
# Temporal-Integrated Async Workflow for ayder-cli

Status: Draft v0.3 (reviewed)
Owner: PM (ayder-cli)
Last Updated: 2026-02-18

---

## 1) Vision

Add an **optional** Temporal runtime to `ayder-cli` so multi-agent software delivery workflows can run durably with retries, timeouts, and queue isolation, while keeping default (non-Temporal) usage lightweight.

This integration must:

- Keep existing CLI/TUI flows working when Temporal is disabled.
- Be activated only by explicit configuration and/or tool usage.
- Enable async, role-based orchestration through Temporal queues.
- Use a unified tool contract (`temporal_workflow`) as the agent interface.
- Support future workflow topologies (e.g., `FrontendDev`, `BackendDev`) without architecture rewrites.

---

## 2) Scope

### 2.1 In Scope (v1)

1. Optional Temporal SDK integration.
2. `config.toml` driven Temporal configuration.
3. Async Temporal workflows and workers for role queues.
4. A shared tool contract named `temporal_workflow` that agents can call.
5. A minimal `/temporal` TUI command to set the local worker queue name.
6. PM-centric routing workflow that decides next phase.
7. Temporal-aware logging aligned with existing ayder verbosity/log-file settings.
8. Metadata persistence in a configurable project directory.

### 2.2 Out of Scope (v1)


1. Telemetry pipelines (Prometheus, OTEL, Grafana, etc.).
2. Mandatory fixed metadata path.
3. Hard-coded workflow graph limited to only Architect/Dev/QA.

---

## 3) Core Requirements

### 3.1 Optional Runtime / No Bloat Requirement

Temporal must not bloat default usage.

- If Temporal is not enabled/called:
  - No Temporal client connection attempts.
  - No worker startup.
  - No extra runtime cost in standard chat/CLI flows beyond minimal import/config checks.
- Temporal code path is lazy-activated by:
  - Config flag (`temporal.enabled = true`) and
  - Agent tool invocation of `temporal_workflow`.

> **REVIEW NOTE**: Lazy activation means `import temporalio` must be deferred behind the config check. Use a provider pattern or conditional import at call site, never at module top level in non-temporal modules.

### 3.2 Configuration Source of Truth

Temporal runtime configuration is defined in `config.toml`.

Example structure:

```toml
[temporal]
enabled = false
host = "localhost:7233"
namespace = "default"
metadata_dir = ".ayder/temporal"

[temporal.timeouts]
workflow_schedule_to_close_seconds = 7200
activity_start_to_close_seconds = 900
activity_heartbeat_seconds = 30

[temporal.retry]
initial_interval_seconds = 5
backoff_coefficient = 2.0
maximum_interval_seconds = 60
maximum_attempts = 3
```

Rules:

1. `temporal.enabled = false` keeps all legacy behavior unchanged.
2. Missing `temporal` section falls back to disabled mode.
3. Invalid Temporal config should fail fast with clear validation messages.
4. Queue names are not sourced from `config.toml` in v1.
5. Queue selection is prompt-driven and/or set by local runtime command state.

### 3.3 Tool-First Interaction Contract

`temporal_workflow` is the integration surface for orchestration actions.

- No full `/temporal ...` command family in v1 (only `/temporal <queue-name>` is required).
- Agents are instructed via prompts to call `temporal_workflow` for workflow lifecycle actions.
- Tool availability can be role-scoped by prompt/policy, but contract is shared.

Initial action set:

1. `start_workflow` — start a new workflow on a named queue.
2. `query_workflow` — query status/state of a running workflow by ID.
3. `signal_workflow` — send a `clarify` signal (request/response) to a running workflow. v1 signal type: `clarify` only.
4. `escalate` — escalate a blocked/failed workflow to the human user. Escalation UX: display a toast notification in TUI/CLI, stop the current activity, and wait for user prompt input before resuming.
5. `cancel_workflow` — cancel a running workflow by ID.
6. `report_phase_result` — submit the Activity Output Contract (§5.3) JSON as phase completion.

Tool shape: single `temporal_workflow` tool with an `action` enum parameter. All actions share one tool definition; the `action` field selects behavior.

Workflow IDs: user-provided or PM-assigned identifiers (not auto-generated UUIDs). This enables human-readable tracking and query.

### 3.4 Async Workflow Model

The Temporal integration must be fully async end-to-end in Python runtime paths.

Baseline roles/queues:

- `pm-team`
- `architect-team`
- `dev-team`
- `qa-team`

Extensible roles (examples):

- `frontend-dev-team`
- `backend-dev-team`

Workflows are composable so future phase insertion/splitting does not require changing core contracts.

Queue resolution rules (v1):

1. Each queue has its own role prompt.
2. Prompts instruct the LLM which queue to target next.
3. The local worker queue binding can be overridden from TUI via `/temporal <queue-name>`.

> **REVIEW NOTE**: The `next_recommendation` field in §5.3 currently only lists `qa-team|architect-team|null`. This is incomplete — Architect needs to recommend `dev-team`, and Dev needs to recommend `qa-team`. The field should accept any valid queue name string, not a fixed enum. Update the contract to say "any valid queue name or null".

### 3.5 PM Router Requirement

PM acts as the router in workflow progression.

- Dev completion is analyzed by PM workflow logic.
- PM router decides next hop:
  - Forward to QA,
  - Return to Architect,
  - Escalate/hold.
- Routing decisions must be durable and queryable in Temporal history.

> **REVIEW NOTE**: PM router is not limited to Dev output — it should also receive Architect and QA completion results. The PRD text says "Dev completion" but the architecture implies PM routes all phase transitions. Clarify: PM is the central router for all inter-phase transitions.

### 3.6 Logging Requirement

Temporal logging must integrate with existing ayder logging policies.

Rules:

1. In CLI-invoked runs, Temporal logs may be shown to the user when logging is enabled.
2. In service/worker runs, Temporal logs should remain non-intrusive to user output and go to log files.
3. Logging behavior should follow existing ayder logging configuration/verbosity controls.

Additional rules:

- No telemetry exporter setup in v1.
- Correlate logs with workflow_id/run_id when available.

### 3.7 Metadata Persistence Requirement

Metadata location is configurable and not strictly tied to `.ayder`.

- `temporal.metadata_dir` can target any project directory in git workflow.
- PM updates task markdown files with status/summary.
- Agent reports can be stored in flexible project paths (best-effort, non-blocking).

---

## 4) High-Level Architecture

### 4.1 System Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          ayder-cli Process                              │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │  CLI / TUI   │───▷│  temporal_workflow│───▷│  Temporal Client      │  │
│  │  (user I/O)  │    │  tool (action     │    │  (lazy init,          │  │
│  │              │    │   enum dispatch)  │    │   config.toml driven) │  │
│  └──────────────┘    └──────────────────┘    └───────────┬───────────┘  │
│         │                                                │              │
│         │  /temporal <queue-name>                         │              │
│         │  starts async queue runner                      │              │
│         │  (Ctrl+C or LLM stops it)                       │              │
└─────────┼────────────────────────────────────────────────┼──────────────┘
          │                                                │
          ▼                                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Temporal Server                                  │
│                     (localhost:7233 default)                             │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ pm-team  │  │architect │  │ dev-team │  │ qa-team  │  │ future   │  │
│  │  queue   │  │  -team   │  │  queue   │  │  queue   │  │ queues   │  │
│  │          │  │  queue   │  │          │  │          │  │(frontend │  │
│  │          │  │          │  │          │  │          │  │ backend) │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │             │             │         │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────┘
        │             │             │             │             │
        ▼             ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Worker Processes                                   │
│    ayder --temporal-task-queue <name> [--prompt <path>] [-w -x ...]     │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Worker Execution Flow                          │  │
│  │                                                                   │  │
│  │  1. Poll queue for activity task                                  │  │
│  │  2. Load role prompt (--prompt or default)                        │  │
│  │  3. Receive job payload (unique contract + branch per job)        │  │
│  │  4. LLM call with tools (scoped by -r/-w/-x/-http flags)         │  │
│  │  5. Iterative tool execution (read/write/shell/search)            │  │
│  │  6. Git commit artifacts on branch                                │  │
│  │  7. Produce Activity Output Contract JSON (§5.3)                  │  │
│  │  8. Heartbeat every 30s during execution                          │  │
│  │  9. Return result → Temporal server → PM router                   │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Crash recovery: Temporal re-queues activity after heartbeat timeout    │
│  Retry: exponential backoff (5s → 60s, max 3 attempts)                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 PM Router Flow

```text
                    ┌─────────────────────┐
                    │  Workflow Start      │
                    │  (PM assigns ID,     │
                    │   dispatches to      │
                    │   architect-team)    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Architect Phase     │
                    │  (design, gate       │
                    │   branch creation)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
              ┌─────│  PM Router           │─────┐
              │     │  (analyze result,    │     │
              │     │   decide next hop)   │     │
              │     └──────────┬──────────┘     │
              │                │                │
     action:escalate    route to next     action:hold
              │           queue                 │
              ▼                │                ▼
     ┌────────────┐           │       ┌────────────┐
     │ Escalate   │           │       │ Hold /     │
     │ to Human   │           │       │ Wait       │
     │ (TUI/CLI)  │           │       │            │
     └────────────┘           │       └────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ dev-team   │  │ qa-team    │  │ architect  │
     │ (code)     │  │ (test)     │  │ -team      │
     │            │  │            │  │ (rework)   │
     └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                           ▼
                    ┌─────────────────────┐
                    │  PM Router           │
                    │  (next decision)     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Success:            │
                    │  Architect merges    │
                    │  to main, PM updates │
                    │  task markdown       │
                    └─────────────────────┘
```

Key principle: default ayder flows remain independent; Temporal path is additive and optional.

---

## 5) Workflow Specifications

### 5.1 Baseline Pipeline (Reference)

Reference path for a feature task:

1. Architect phase
2. Dev phase
3. PM router decision
4. QA phase or back-to-Architect
5. Final PM summary update

### 5.2 Timeout & Retry Defaults

- Workflow `ScheduleToClose` target: 2 hours (7200 sec).
- Activity `StartToClose`: role-dependent (default 900 sec in config).
- Heartbeat interval target: 30 sec.
- Retry policy: exponential backoff (5s initial, 60s max, 3 attempts).

All values configurable in `config.toml`.

### 5.3 Activity Output Contract (v1)

Standard output fields (strict envelope + flexible content):

```json
{
  "contract_version": "1.0",
  "execution_mode": "git|workspace",
  "status": "PASS|FAIL|NEEDS_CLARIFICATION",
  "summary": "short text",
  "notes": "free-form markdown/text",
  "next_recommendation": "<any-valid-queue-name>|null",
  "action": "hold|escalate|null",
  "origin_queue": "pm-team|architect-team|dev-team|qa-team|...",
  "branch_name": "feature/xyz",
  "commit_sha": "40-hex-or-short-sha",
  "report_path": "relative/path/to/report.md",
  "artifacts": ["optional relative paths"]
}
```

Field rules:

1. `contract_version` is required and fixed to `1.0`.
2. `execution_mode` is required and must be `git` or `workspace`.
3. `next_recommendation` expresses routing target — any valid queue name string (e.g., `dev-team`, `qa-team`, `architect-team`).
4. `action` expresses control intent only (`hold` or `escalate`).
5. For normal progression, `action` is `null` (or omitted).
6. When `action` is `hold` or `escalate`, `next_recommendation` should be `null`.
7. PM router treats conflicting values as `NEEDS_CLARIFICATION`.
8. `origin_queue` and `report_path` are required and must be non-empty.
9. `report_path` must be repository-relative and point to a persisted report artifact.
10. If `execution_mode = "git"`, `branch_name` and `commit_sha` are required and must not be `none`.
11. If `execution_mode = "workspace"`, `branch_name` and `commit_sha` must be set to `"none"`.

Contract template:

- See `docs/temporal/CONTRACT_TEMPLATE.md` for copy-paste templates (git mode and workspace mode).

Why this design:

- Freeform-only markdown is not sufficient for routing/automation/validation.
- Overly strict git-only metadata blocks valid workspace-only flows.
- Hybrid model keeps deterministic orchestration while allowing rich narrative in `notes`.

**Branch Strategy**:

- Every job dispatched to a team carries a unique contract and a unique branch in `git` mode.
- In `workspace` mode, jobs still carry a unique contract but use `branch_name: "none"` and `commit_sha: "none"`.
- Architect controls the gate branch and manages PR/MR lifecycle.
- Architect may request dev or QA branches from other teams — each as a distinct job with its own branch.
- On success, Architect handles merge to main.
- `branch_name` in the output contract reflects the branch that phase committed to.
- Implementation does not enforce branch naming conventions — that is governed by the prompt contract.

---

## 6) Prompting & Agent Behavior Contract

Prompts must instruct every role to:

1. Use `temporal_workflow` to report lifecycle events.
2. Return structured phase outcomes.
3. Avoid direct queue assumptions outside provided context.

`docs/temporal/prompts.md` is the prompt contract companion and should remain aligned with this PRD.

---

## 7) Operational Model

### 7.1 Startup

1. Temporal server started externally.
2. Role workers started as separate async processes.
3. ayder client runs normally (Temporal optional).

> **REVIEW NOTE — Worker Runtime Model**: `ayder --temporal-task-queue dev-team` starts a long-running Temporal worker daemon that:
> - Polls the named queue for activities.
> - Executes activities via ayder's LLM call path with tools.
> - Tool permissions (`-x`, `-w`, `-http`) apply per worker invocation — if the worker was started without `-w`, write tools will be denied and the activity fails with a permission error.
> - The worker process stays running until killed.
> - Escalation (`action: escalate`) surfaces to the human via TUI/CLI notification on the PM's session.

### 7.1.1 Required CLI Invocation Patterns (v1)

Examples of required invocation shape:

```bash
ayder --temporal-task-queue dev-team --prompt project/dev/dev-prompt.md
ayder --temporal-task-queue qa-team
```

CLI requirements:

1. `--temporal-task-queue <name>` is the single queue selector for Temporal invocation.
2. A standalone `--temporal-worker` flag is not required in v1.
3. `--prompt <path>` is optional when using `--temporal-task-queue <name>`.
4. If `--prompt` is omitted, the worker uses the default ayder system prompt. For complex team setups with specialized roles, `--prompt` should be provided to scope agent behavior.
5. Temporal-related flags must not affect default non-Temporal flows when unused.
6. Permission flags (`-r`, `-w`, `-x`, `-http`) apply to the worker process and constrain tool availability inside activities.

Note: Global prompt injection behavior for `--prompt <path>` is intentionally specified in a separate document: `docs/PRD_PROMPT.md`.

### 7.1.2 Team Topology Support (v1)

The PRD supports multiple team compositions through queue+prompt configuration, including:

1. Many Dev workers + one PM router.
2. Many QA workers + one PM router.
3. Mixed Architect/Dev/QA pools.
4. Role-split queues (e.g., frontend/backend dev).

Queue naming stays user-defined; behavior is governed by the prompt assigned to each queue.

### 7.2 Disabled Mode

If Temporal is disabled in config:

- `temporal_workflow` returns a clear disabled/runtime-unavailable response.
- Normal ayder behavior continues.

### 7.3 Failure Handling

- Worker crash: Temporal re-queues per heartbeat timeout/retry policy.
- Repeated activity failure: PM router gets failure state and can escalate or abort.

### 7.4 TUI Local Queue Command (Minimal)

Provide a minimal command:

```text
/temporal <queue-name>
```

Behavior:

1. Starts an async Temporal queue runner bound to `<queue-name>` inside the current TUI session.
2. The runner polls the queue and executes activities asynchronously.
3. User can break the runner with `Ctrl+C`, or the LLM can stop it programmatically.
4. Should display current queue status if called without arguments.
5. Does not create a full temporal command family in v1.

---

## 8) Security & Compliance (v1)

1. No telemetry export.
2. Reuse existing ayder permission and tool execution boundaries.
3. Keep metadata/report paths inside project context constraints.
4. Worker processes inherit permission flags from CLI invocation — no implicit privilege escalation.

> **REVIEW NOTE**: Consider whether workers should be sandboxed to their `metadata_dir` subtree or have full project context access. Current design inherits ProjectContext which scopes to project root. This may be acceptable for v1 but should be revisited for multi-tenant/remote worker scenarios.

---

## 9) Success Criteria

1. Default ayder usage remains lightweight when Temporal is disabled.
2. Temporal workflows run asynchronously when enabled and called.
3. `temporal_workflow` is sufficient for lifecycle operations in v1.
4. PM can route between phases (QA vs back-to-Architect) durably.
5. Logging behaves correctly for CLI-visible runs and worker/service runs via existing ayder logging controls.
6. Metadata directory is configurable (not locked to `.ayder`).
7. All phase outputs include valid `commit_sha`, `branch_name`, `origin_queue`, and `report_path`.
8. Escalation reaches human user via TUI/CLI notification.
9. Multiple workers on the same queue receive work without conflicts (Temporal's built-in task distribution).

---

## 10) Implementation Notes / Next Step

This PRD defines the full v1 specification baseline.

Next implementation package should include:

1. Config schema extensions for `[temporal]`.
2. Temporal service abstraction + lazy client initialization.
3. `temporal_workflow` tool definition (single tool, `action` enum) + executor path.
4. PM router workflow and baseline role workflows.
5. Logging mode integration and metadata writer hooks.
6. Worker process entry point for `--temporal-task-queue`.
7. Pydantic model for Activity Output Contract validation.
8. `/temporal <queue-name>` TUI command handler.

### Open Items for Follow-Up

All open items have been resolved. None remaining.
