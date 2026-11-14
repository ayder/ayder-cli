"""ayder does not override Textual's private API.

Textual's `_`-prefixed methods can change in any release, and an override of
one is how ayder once pinned the chat to its end (ChatView._size_updated and
release_anchor) and forced synchronized output on
(AyderApp._on_terminal_supports_synchronized_output). The chat now follows the
stream through the public `anchor()` API only.

Two TextArea key and paste handlers are the only allowed shadows; they are
outside the scope of this guard.
"""

import importlib
import inspect
import pkgutil

import ayder_cli.tui
from ayder_cli.tui.widgets import ChatView

ALLOWED = {
    ("ayder_cli.tui.widgets._SubmitTextArea", "_on_key"),
    ("ayder_cli.tui.widgets._SubmitTextArea", "_on_paste"),
}


def _shadows() -> set[tuple[str, str]]:
    """(class, name) for every ayder.tui class member that shadows a `_x` member of a textual base."""
    seen: set[type] = set()
    found: set[tuple[str, str]] = set()
    for info in pkgutil.walk_packages(ayder_cli.tui.__path__, "ayder_cli.tui."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not cls.__module__.startswith("ayder_cli.tui") or cls in seen:
                continue
            seen.add(cls)
            textual_bases = [b for b in cls.__mro__[1:] if b.__module__.startswith("textual")]
            for name, member in vars(cls).items():
                is_dunder = name.startswith("__") and name.endswith("__")
                is_callable = inspect.isfunction(member) or isinstance(
                    member, (property, classmethod, staticmethod)
                )
                if (
                    name.startswith("_")
                    and not is_dunder
                    and is_callable
                    and any(name in vars(base) for base in textual_bases)
                ):
                    found.add((f"{cls.__module__}.{cls.__qualname__}", name))
    return found


def test_no_ayder_tui_class_shadows_a_private_textual_method():
    assert _shadows() == ALLOWED


def test_chat_view_does_not_override_release_anchor():
    """Follow-at-the-end is Widget.anchor() / release_anchor() as Textual ships them."""
    assert "release_anchor" not in vars(ChatView)
