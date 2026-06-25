"""Git worktree helpers for agent isolation.

Pure subprocess wrappers around system `git`. The registry calls these OFF the
event loop via ``asyncio.to_thread``; they must stay synchronous and dependency
free (stdlib only).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
_GIT_TIMEOUT = 120


def slugify_branch(branch: str) -> str:
    """Last path segment of a branch, sanitized to ``[A-Za-z0-9._-]``.

    ``agent/add-auth`` -> ``add-auth``. Falls back to ``agent`` if empty.
    """
    last = branch.rstrip("/").split("/")[-1]
    slug = _SLUG_RE.sub("-", last).strip("-")
    return slug or "agent"


def is_git_repo(root: str) -> bool:
    """True iff ``root`` is inside a git work tree and git is on PATH."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def detect_base_branch(root: str) -> str:
    """Best-effort default branch: ``origin/HEAD`` -> ``main`` -> current ref.

    No AGENTS.md logic — choosing the base is the orchestrator's job; this is
    only the fallback when no ``base_branch`` is passed.
    """
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("/", 1)[-1]  # 'origin/main' -> 'main'
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "main"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return "main"
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "HEAD"


def add_worktree(repo_root: str, worktree_path: str, branch: str, base: str) -> None:
    """Create a worktree at ``worktree_path`` on ``branch`` forked from ``base``.

    Reuses an existing branch (checks it out without ``-b``). Raises
    ``RuntimeError`` if neither the create nor the reuse form succeeds.
    """
    os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
    new = subprocess.run(
        ["git", "worktree", "add", worktree_path, "-b", branch, base],
        cwd=repo_root, capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    if new.returncode == 0:
        return
    reuse = subprocess.run(
        ["git", "worktree", "add", worktree_path, branch],
        cwd=repo_root, capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    if reuse.returncode == 0:
        return
    raise RuntimeError(
        f"git worktree add failed for branch '{branch}' (base '{base}'): "
        f"{new.stderr.strip()} | reuse: {reuse.stderr.strip()}"
    )


def remove_worktree(repo_root: str, worktree_path: str) -> None:
    """Force-remove a worktree and prune admin files. Best-effort: logs, never raises."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=repo_root, capture_output=True, text=True, timeout=60,
        )
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_root, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("worktree remove/prune failed for %s: %s", worktree_path, e)


def branch_head(repo_root: str, branch: str) -> str | None:
    """Return the commit sha at the tip of ``branch``, or None if it cannot be
    resolved. Used to detect whether an agent actually committed (head moved)."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", branch],
            cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and sha else None
