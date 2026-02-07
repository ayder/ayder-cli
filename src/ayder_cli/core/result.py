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
        return f"ToolError({super().__repr__()}, category={self._category!r})"


ToolResult = Union[ToolSuccess, ToolError]
