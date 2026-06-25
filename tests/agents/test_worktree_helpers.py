"""Tests for agents/worktree.py git helpers (spec 05, Task 1)."""

import os
import shutil
import subprocess

import pytest

from ayder_cli.agents.worktree import (
    add_worktree,
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
