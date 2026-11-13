"""The status bar starts with the working directory (home shown as ``~``,
long paths shortened from the left) and the rest of the line stays intact."""

from pathlib import Path

import pytest
from rich.cells import cell_len

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import StatusBar

OTHER_LABELS = ["model-label", "effort-label", "mode-label", "token-label", "files-label"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home directory; Path.home() follows $HOME on POSIX."""
    home_dir = (tmp_path / "home").resolve()
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


def _cwd_in(home_dir: Path, monkeypatch, *parts: str) -> Path:
    target = home_dir.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(target)
    return target


def _bar(app) -> StatusBar:
    return app.query_one("#status-bar", StatusBar)


def _text(widget) -> str:
    return widget.render().plain


# -- Pure helpers -----------------------------------------------------------------


def test_abbreviate_home_replaces_the_home_prefix_with_tilde(home):
    from ayder_cli.tui.widgets import _abbreviate_home

    assert _abbreviate_home(home) == "~"
    assert _abbreviate_home(home / "work" / "proj") == "~/work/proj"


def test_abbreviate_home_leaves_other_paths_alone(home):
    from ayder_cli.tui.widgets import _abbreviate_home

    assert _abbreviate_home(Path("/opt/tools")) == "/opt/tools"
    # A sibling that merely shares the textual prefix is not under home.
    assert _abbreviate_home(Path(f"{home}-other") / "proj") == f"{home}-other/proj"


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("~/Vscode/ayder-cli/src", 40, "~/Vscode/ayder-cli/src"),
        ("~/Vscode/ayder-cli/src", 15, "…/ayder-cli/src"),
        ("~/Vscode/ayder-cli/src", 14, "…/src"),
        ("/usr/local/lib/python", 16, "…/lib/python"),
        ("~/averyveryverylongname", 8, "…ongname"),
        ("~/anything", 1, "…"),
        ("~/anything", 0, ""),
    ],
)
def test_shorten_left_keeps_the_last_components(text, width, expected):
    from ayder_cli.tui.widgets import _shorten_left

    shortened = _shorten_left(text, width)
    assert shortened == expected
    assert cell_len(shortened) <= width


# -- In the running app -----------------------------------------------------------


@pytest.mark.anyio
async def test_cwd_is_the_first_status_item(home, monkeypatch):
    _cwd_in(home, monkeypatch, "proj")
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        children = list(_bar(app).children)
        assert children[0].id == "cwd-label"
        assert _text(children[0]) == "~/proj | "
        assert children[0].region.x < app.query_one("#model-label").region.x


@pytest.mark.anyio
async def test_home_directory_is_shown_as_tilde(home, monkeypatch):
    monkeypatch.chdir(home)
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert _text(app.query_one("#cwd-label")) == "~ | "


@pytest.mark.anyio
async def test_long_cwd_is_shortened_from_the_left(home, monkeypatch):
    _cwd_in(home, monkeypatch, "first-long-directory", "second-long-directory", "third-long-directory", "src")
    app = AyderApp(model="test")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        label = app.query_one("#cwd-label")
        shown = _text(label).removesuffix(" | ")
        third = _bar(app).content_region.width // 3
        assert shown.startswith("…/")
        assert shown.endswith("/src")
        assert cell_len(shown) <= third
        assert label.region.width <= third + len(" | ")
        # The separator hugs the next item: no blank gap after the shortened path.
        assert label.region.width == cell_len(_text(label))


@pytest.mark.anyio
async def test_shortened_cwd_label_is_exactly_as_wide_as_its_text(home, monkeypatch):
    _cwd_in(home, monkeypatch, "first-long-directory", "second-long-directory", "third-long-directory", "src")
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        _bar(app).update_context_usage(12000, 65536)
        await pilot.pause()
        await pilot.pause()
        label = app.query_one("#cwd-label")
        model = app.query_one("#model-label")
        assert _text(label).startswith("…/")
        assert label.region.width == cell_len(_text(label))
        assert label.region.right == model.region.x


LONG_DIRS = ("first-long-directory", "second-long-directory", "third-long-directory")


@pytest.mark.anyio
async def test_cwd_keeps_its_tail_at_80_columns_with_a_populated_ctx_label(home, monkeypatch):
    _cwd_in(home, monkeypatch, *LONG_DIRS, "src")
    app = AyderApp(model="test")
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        _bar(app).update_context_usage(12000, 65536)
        await pilot.pause()
        await pilot.pause()
        label = app.query_one("#cwd-label")
        shown = _text(label).removesuffix(" | ")
        assert shown.startswith("…/")
        assert shown.endswith("/src")
        assert label.region.width == cell_len(_text(label))
        # The items on its right may overflow the bar, but never the cwd.
        assert label.region.right <= _bar(app).content_region.right


@pytest.mark.anyio
async def test_cwd_never_shrinks_below_the_last_component(home, monkeypatch):
    basename = "a-very-long-project-directory-name"  # wider than a third of 80 columns
    _cwd_in(home, monkeypatch, *LONG_DIRS, basename)
    app = AyderApp(model="test")
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        assert _text(app.query_one("#cwd-label")) == f"…/{basename} | "


@pytest.mark.anyio
@pytest.mark.parametrize("width", [80, 120])
async def test_cwd_width_does_not_change_when_another_item_grows(width, home, monkeypatch):
    _cwd_in(home, monkeypatch, *LONG_DIRS, "src")
    app = AyderApp(model="test")
    async with app.run_test(size=(width, 30)) as pilot:
        await pilot.pause()
        label = app.query_one("#cwd-label")
        before = (label.region.width, _text(label))

        _bar(app).update_context_usage(12000, 65536)
        _bar(app).set_model("a-much-longer-model-name:70b")
        await pilot.pause()
        await pilot.pause()

        assert (label.region.width, _text(label)) == before
