# Temporal Activity Contract Template

Use this contract as the required output envelope for all role activities.

## Rules

- Always return valid JSON.
- Keep `summary` concise.
- Put rich details and reasoning in `notes` (Markdown allowed).
- `next_recommendation` may be any valid queue name (e.g., `dev-team`, `qa-team`, `architect-team`, `pm-team`) or `null`.
- If `action` is `hold` or `escalate`, then `next_recommendation` must be `null`.
- Set `execution_mode` based on how work was done:
  - `git`: branch + commit are real values.
  - `workspace`: no git branch/commit used (`"none"`).
- `origin_queue` and `report_path` must always be non-empty.

## Template (Git Mode)

```json
{
  "contract_version": "1.0",
  "execution_mode": "git",
  "status": "PASS",
  "summary": "Implemented feature and validated tests.",
  "notes": "## Work Done\n- Added API handler\n- Updated tests\n\n## Risks\n- Minor edge-case pending",
  "next_recommendation": "qa-team",
  "action": null,
  "origin_queue": "dev-team",
  "branch_name": "feature/task-123-auth",
  "commit_sha": "a1b2c3d4",
  "report_path": "reports/task-123/dev-report.md",
  "artifacts": [
    "src/module/auth.py",
    "tests/test_auth.py"
  ]
}
```

## Template (Workspace Mode / No Git)

```json
{
  "contract_version": "1.0",
  "execution_mode": "workspace",
  "status": "PASS",
  "summary": "Validated src/ and tests/ changes without git operations.",
  "notes": "## Work Done\n- Worked directly on workspace files\n- Executed targeted tests\n\n## Limitation\n- No branch or commit created by design",
  "next_recommendation": "qa-team",
  "action": null,
  "origin_queue": "dev-team",
  "branch_name": "none",
  "commit_sha": "none",
  "report_path": "reports/task-123/dev-report.md",
  "artifacts": [
    "src/module/auth.py",
    "tests/test_auth.py"
  ]
}
```

Workspace mode requirements:

- `branch_name` must be exactly `"none"`.
- `commit_sha` must be exactly `"none"`.
- `report_path` remains mandatory and repository-relative.

## Escalation Example

```json
{
  "contract_version": "1.0",
  "execution_mode": "workspace",
  "status": "NEEDS_CLARIFICATION",
  "summary": "Blocked by ambiguous acceptance criteria.",
  "notes": "Need confirmation on expected error behavior for invalid token.",
  "next_recommendation": null,
  "action": "escalate",
  "origin_queue": "qa-team",
  "branch_name": "none",
  "commit_sha": "none",
  "report_path": "reports/task-123/qa-blocked.md",
  "artifacts": []
}
```
