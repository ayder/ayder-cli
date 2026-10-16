"""Skill discovery, frontmatter, delivery blocks and the active set.

tests/conftest.py points PACKAGED_SKILLS_DIR and USER_SKILLS_DIR at empty
temporary directories for every test, so nothing here reads ~/.ayder.
"""

from __future__ import annotations

import os

import pytest

from ayder_cli.core import skills as sk


def _skill(root, name, text="# Title\nBody line", files=None):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    for rel, content in (files or {}).items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return skill_dir


def _project(tmp_path):
    return tmp_path / "proj"


def _project_skills(tmp_path):
    return _project(tmp_path) / ".ayder" / "skills"


# -- frontmatter ---------------------------------------------------------------


def test_frontmatter_fields_and_body():
    fields, body = sk.parse_frontmatter(
        '---\nname: eng\ndescription: "Build things"\n# note\n\n---\n\n# Eng\nDo it\n'
    )
    assert fields == {"name": "eng", "description": "Build things"}
    assert body == "# Eng\nDo it"


def test_no_frontmatter_returns_text_unchanged():
    assert sk.parse_frontmatter("# Eng\nDo it") == ({}, "# Eng\nDo it")


@pytest.mark.parametrize(
    "text",
    ["---\nname: eng\n# never closed\nbody", "---\njust words\n---\nbody"],
)
def test_malformed_frontmatter_delivers_whole_text(text):
    assert sk.parse_frontmatter(text) == ({}, text)


def test_description_falls_back_to_first_body_line(tmp_path):
    skill_dir = _skill(tmp_path, "eng", "---\nname: eng\n---\n# Heading\n\nFirst line\n")
    assert sk.read_skill_info(skill_dir, "user").description == "First line"


def test_directory_name_wins_over_declared_name(tmp_path):
    skill_dir = _skill(tmp_path, "eng", "---\nname: other\n---\nBody")
    assert sk.read_skill_info(skill_dir, "user").name == "eng"


@pytest.mark.parametrize(
    ("content", "problem"),
    [("", "empty"), ("   \n", "empty"), ("x" * (64 * 1024 + 1), "over 64 KB")],
)
def test_unloadable_skill_reports_problem(tmp_path, content, problem):
    skill_dir = _skill(tmp_path, "eng", content)
    assert sk.read_skill_info(skill_dir, "user").problem == problem


# -- layers ----------------------------------------------------------------------


def test_later_layer_overrides_by_name(tmp_path):
    _skill(sk.PACKAGED_SKILLS_DIR, "eng", "Builtin body")
    _skill(sk.USER_SKILLS_DIR, "eng", "User body")
    _skill(_project_skills(tmp_path), "eng", "Project body")
    _skill(sk.USER_SKILLS_DIR, "notes", "Notes body")

    found = {info.name: info for info in sk.discover_all(_project(tmp_path))}

    assert sorted(found) == ["eng", "notes"]
    assert found["eng"].layer == "project"
    assert found["notes"].layer == "user"


def test_discovery_skips_dirs_without_skill_md(tmp_path):
    (_project_skills(tmp_path) / "empty-dir").mkdir(parents=True)
    (_project_skills(tmp_path) / "file").write_text("", encoding="utf-8")
    assert sk.discover_all(_project(tmp_path)) == []


def test_list_line_shows_layer_description_and_problem(tmp_path):
    ok = sk.read_skill_info(_skill(tmp_path, "eng", "---\ndescription: Build\n---\nB"), "builtin")
    bad = sk.read_skill_info(_skill(tmp_path, "bad", ""), "project")
    assert sk.list_line(ok) == "- eng (builtin): Build"
    assert sk.list_line(bad) == "- bad (project) [cannot load: empty]"


# -- blocks ----------------------------------------------------------------------


def test_block_strips_frontmatter_and_lists_files(tmp_path):
    skill_dir = _skill(
        tmp_path,
        "eng",
        "---\nname: eng\ndescription: Build\n---\n# Eng\nDo it\n",
        files={"ref/check.md": "x", "plan.md": "y"},
    )
    block = sk.render_skill_block(sk.read_skill_info(skill_dir, "user"))
    assert block == (
        "### SKILL LOADED: eng\n"
        f"Source: user ({skill_dir})\n"
        'Files: plan.md, ref/check.md (read with skill(action="read", name="eng", path=...))\n'
        "\n# Eng\nDo it\n\n### END SKILL: eng"
    )


def test_block_without_files_has_no_files_line(tmp_path):
    block = sk.render_skill_block(sk.read_skill_info(_skill(tmp_path, "eng", "Body"), "user"))
    assert "Files:" not in block


def test_block_refuses_unloadable_skill(tmp_path):
    result = sk.render_skill_block(sk.read_skill_info(_skill(tmp_path, "eng", ""), "user"))
    assert isinstance(result, sk.ToolError)
    assert "empty" in result


# -- resources -----------------------------------------------------------------


def test_resource_inside_skill_resolves(tmp_path):
    skill_dir = _skill(tmp_path, "eng", files={"ref/a.md": "A"})
    info = sk.read_skill_info(skill_dir, "user")
    assert sk.resolve_resource(info, "ref/a.md") == skill_dir / "ref" / "a.md"


@pytest.mark.parametrize("rel", ["../outside.md", "/etc/passwd", "SKILL.md", "ref/../SKILL.md"])
def test_resource_escape_or_skill_md_is_refused(tmp_path, rel):
    (tmp_path / "outside.md").write_text("secret", encoding="utf-8")
    info = sk.read_skill_info(_skill(tmp_path, "eng", files={"ref/a.md": "A"}), "user")
    with pytest.raises(ValueError):
        sk.resolve_resource(info, rel)


def test_resource_symlink_out_is_refused(tmp_path):
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
    skill_dir = _skill(tmp_path, "eng")
    os.symlink(tmp_path / "secret.md", skill_dir / "link.md")
    with pytest.raises(ValueError):
        sk.resolve_resource(sk.read_skill_info(skill_dir, "user"), "link.md")


def test_missing_resource_raises_file_not_found(tmp_path):
    info = sk.read_skill_info(_skill(tmp_path, "eng"), "user")
    with pytest.raises(FileNotFoundError):
        sk.resolve_resource(info, "nope.md")


# -- active set ------------------------------------------------------------------


def _block(name, body="Body"):
    return f"### SKILL LOADED: {name}\nSource: user (x)\n\n{body}\n\n### END SKILL: {name}"


def test_active_set_follows_loads_and_unloads():
    messages = [
        {"role": "system", "content": "### SKILL LOADED: fake"},  # system is ignored
        {"role": "tool", "content": _block("eng")},
        {"role": "user", "content": _block("design") + "\n\nthen do this"},
        {"role": "tool", "content": "### SKILL UNLOADED: eng\nStop following ..."},
    ]
    active = sk.active_skills(messages)
    assert [(load.name, load.index) for load in active] == [("design", 2)]
    assert active[0].block == _block("design")


def test_unload_all_notice_removes_every_name():
    messages = [
        {"role": "tool", "content": _block("a")},
        {"role": "tool", "content": _block("b")},
        {"role": "tool", "content": sk.unload_notice(["a", "b"])},
    ]
    assert sk.active_skills(messages) == []


def test_reload_after_unload_counts_from_new_index():
    messages = [
        {"role": "tool", "content": _block("a")},
        {"role": "tool", "content": sk.unload_notice(["a"])},
        {"role": "tool", "content": _block("a", "Second")},
    ]
    [load] = sk.active_skills(messages)
    assert (load.index, "Second" in load.block) == (2, True)


def test_non_string_content_is_ignored():
    assert sk.active_skills([{"role": "user", "content": [{"type": "text"}]}]) == []


def test_marker_inside_other_content_is_not_a_load():
    quoted = "1: ---\n2: name: eng\n3: ### SKILL LOADED: eng\n"
    assert sk.active_skills([{"role": "tool", "content": quoted}]) == []
