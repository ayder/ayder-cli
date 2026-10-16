"""Built-in skills sync to ~/.ayder/builtin/skills by stamp (spec 4.3).

Kind: new interface (the parent has no sync and ships no skill).
"""

from __future__ import annotations

from pathlib import Path

from ayder_cli.core import skills as sk


def _packaged(name="engineering", text="---\ndescription: Build\n---\nRules v1"):
    skill_dir = sk.PACKAGED_SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")


def _reset():
    sk._builtin_root = None


def test_first_sync_copies_and_stamps():
    _packaged()
    root = sk.builtin_skills_root()
    assert root == sk.BUILTIN_HOME / "skills"
    assert (root / "engineering" / "SKILL.md").read_text(encoding="utf-8").endswith("Rules v1")
    assert (sk.BUILTIN_HOME / "STAMP").read_text(encoding="utf-8").split()[1]


def test_same_stamp_writes_nothing():
    _packaged()
    sk.builtin_skills_root()
    marker = sk.BUILTIN_HOME / "skills" / "engineering" / "SKILL.md"
    before = marker.stat().st_mtime_ns
    _reset()
    sk.builtin_skills_root()
    assert marker.stat().st_mtime_ns == before


def test_changed_content_replaces_the_copy():
    _packaged()
    sk.builtin_skills_root()
    _packaged(text="---\ndescription: Build\n---\nRules v2")
    _reset()
    root = sk.builtin_skills_root()
    assert root == sk.BUILTIN_HOME / "skills"
    assert (root / "engineering" / "SKILL.md").read_text(encoding="utf-8").endswith("Rules v2")


def test_user_skills_are_never_touched():
    _packaged()
    user = sk.USER_SKILLS_DIR / "engineering"
    user.mkdir(parents=True)
    (user / "SKILL.md").write_text("Mine", encoding="utf-8")
    sk.builtin_skills_root()
    assert (user / "SKILL.md").read_text(encoding="utf-8") == "Mine"
    [info] = sk.discover_all(Path("/nonexistent"))
    assert (info.layer, info.description) == ("user", "Mine")


def test_failed_sync_falls_back_to_the_packaged_copy(monkeypatch, loguru_caplog):
    _packaged()

    def boom(*args, **kwargs):
        raise PermissionError("read-only home")

    monkeypatch.setattr(sk.shutil, "copytree", boom)
    assert sk.builtin_skills_root() == sk.PACKAGED_SKILLS_DIR
    assert "were not synced" in loguru_caplog.text


def test_sync_runs_once_per_process(monkeypatch):
    _packaged()
    calls = []
    real = sk._sync_builtin_skills
    monkeypatch.setattr(sk, "_sync_builtin_skills", lambda: calls.append(1) or real())
    sk.builtin_skills_root()
    sk.builtin_skills_root()
    assert calls == [1]


def test_the_real_package_ships_engineering():
    """The wheel content: src/ayder_cli/skills/engineering/SKILL.md (kind: new interface)."""
    real = Path(sk.__file__).resolve().parent.parent / "skills" / "engineering" / "SKILL.md"
    text = real.read_text(encoding="utf-8")
    fields, body = sk.parse_frontmatter(text)
    assert fields["name"] == "engineering" and fields["description"]
    assert text.isascii()
    assert len(text.splitlines()) < 130


def test_pycache_does_not_change_the_stamp():
    _packaged()
    first = sk._packaged_stamp()
    cache = sk.PACKAGED_SKILLS_DIR / "engineering" / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_bytes(b"\0")
    assert sk._packaged_stamp() == first
