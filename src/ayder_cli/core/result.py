"""Result types for tool execution — str subclasses for backwards compatibility."""

from typing import Union


class ToolSuccess(str):
    """Successful tool result. Behaves as a str in all contexts."""

    def __new__(cls, value: str = ""):
        return super().__new__(cls, value)

    @property
    def is_success(self) -> bool:
        return True

    @property
    def is_error(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"ToolSuccess({super().__repr__()})"


class ToolError(str):
    """Error tool result with category metadata."""

    _category: str

    def __new__(cls, value: str, category: str = "general"):
        instance = super().__new__(cls, value)
        instance._category = category
        return instance

    @property
    def category(self) -> str:
        return self._category

    @property
    def is_success(self) -> bool:
        return False

    @property
    def is_error(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"ToolError({super().__repr__()}, category={self.category!r})"


class ToolResultText(str):
    """A tool result's text with the status the chat loop knows for it (R4a).

    ``status`` is ``ok``, ``error``, ``denied``, ``skipped``, ``not_run`` or ``interrupted``. The
    loop hands it to ``on_tool_complete`` so a receiver can show the real status instead of
    guessing it from the text; history keeps the plain text.
    """

    _status: str

    def __new__(cls, value: str, status: str):
        instance = super().__new__(cls, value)
        instance._status = status
        return instance

    @property
    def status(self) -> str:
        return self._status

    def __repr__(self) -> str:
        return f"ToolResultText({super().__repr__()}, status={self._status!r})"


ToolResult = Union[ToolSuccess, ToolError]
