"""Tests for agents/worktree.py git helpers (spec 05, Task 1)."""

import os
import shutil
import subprocess

import pytest

from ayder_cli.agents.worktree import (
    add_worktree,
    branch_head,
    detect_base_branch,
    is_git_repo,
    remove_worktree,
    slugify_branch,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _init_repo(path):
    """A git repo on branch 'main' with one commit. Returns the repo path str."""
    root = str(path)
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", root],
                   capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=root, capture_output=True, check=True)
    return root


def test_slugify_takes_last_segment():
    assert slugify_branch("agent/add-auth") == "add-auth"
    assert slugify_branch("feature/x/y") == "y"
    assert slugify_branch("plain") == "plain"


def test_slugify_sanitizes_and_falls_back():
    assert slugify_branch("agent/weird name!@#") == "weird-name"
    assert slugify_branch("///") == "agent"


def test_is_git_repo_false_for_plain_dir(tmp_path):
    assert is_git_repo(str(tmp_path)) is False


@needs_git
def test_is_git_repo_true_in_repo(tmp_path):
    root = _init_repo(tmp_path)
    assert is_git_repo(root) is True


@needs_git
def test_detect_base_branch_returns_main(tmp_path):
    root = _init_repo(tmp_path)
    assert detect_base_branch(root) == "main"


@needs_git
def test_add_and_remove_worktree(tmp_path):
    root = _init_repo(tmp_path)
    wt = os.path.join(root, ".ayder", "worktrees", "feat-x")
    add_worktree(root, wt, "agent/feat-x", "main")
    assert os.path.isdir(wt)
    listing = subprocess.run(["git", "worktree", "list"], cwd=root,
                             capture_output=True, text=True).stdout
    assert wt in listing
    remove_worktree(root, wt)
    assert not os.path.isdir(wt)
    listing2 = subprocess.run(["git", "worktree", "list"], cwd=root,
                              capture_output=True, text=True).stdout
    assert wt not in listing2


@needs_git
def test_add_worktree_reuses_existing_branch(tmp_path):
    root = _init_repo(tmp_path)
    subprocess.run(["git", "branch", "agent/exists"], cwd=root, check=True)
    wt = os.path.join(root, ".ayder", "worktrees", "exists")
    add_worktree(root, wt, "agent/exists", "main")  # must not error on existing branch
    assert os.path.isdir(wt)
    remove_worktree(root, wt)


@needs_git
def test_add_worktree_raises_on_bad_base(tmp_path):
    root = _init_repo(tmp_path)
    wt = os.path.join(root, ".ayder", "worktrees", "bad")
    with pytest.raises(RuntimeError):
        add_worktree(root, wt, "agent/bad", "no-such-base-ref")


@needs_git
def test_branch_head_resolves_and_misses(tmp_path):
    root = _init_repo(tmp_path)
    head = branch_head(root, "main")
    assert head is not None and len(head) >= 7
    assert branch_head(root, "no-such-branch") is None


def test_branch_head_none_for_non_git(tmp_path):
    assert branch_head(str(tmp_path), "main") is None


def test_remove_worktree_failure_logs_path_only_with_stack(monkeypatch, loguru_caplog):
    """The failure MESSAGE carries the worktree path and nothing else.

    Subprocess error text is arbitrary git/OS output, so it is removed from
    `record["message"]`; the exception is attached instead (deliberate, per
    CR-2) so the stack still reaches a debugging sink.
    """
    sentinel = "git-said: /secret/token=hunter2"

    def _boom(*a, **k):
        raise OSError(sentinel)

    monkeypatch.setattr("ayder_cli.agents.worktree.subprocess.run", _boom)

    # Best-effort helper: still must not raise.
    remove_worktree("/repo", "/repo/.ayder/worktrees/feat-x")

    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("worktree remove/prune failed for")]
    assert hits, "remove-failure record never emitted"
    assert hits[0]["level"].name == "WARNING"
    assert "/repo/.ayder/worktrees/feat-x" in hits[0]["message"]
    assert sentinel not in loguru_caplog.text
    assert "hunter2" not in loguru_caplog.text
    # The exception is attached rather than interpolated.
    assert hits[0]["exception"] is not None
    assert hits[0]["exception"].type is OSError
