"""
Structural Python code editor using LibCST (Concrete Syntax Tree).

Provides CST-based manipulation: get, list_all, replace, delete, rename,
add_decorator, add_import, verify. Treats code as a tree, preserving
indentation and comments during transformations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import libcst as cst

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess


def python_editor(
    project_ctx: ProjectContext,
    file_path: str,
    method: str,
    params: str = "{}",
) -> str:
    """Unified structural Python code editor.

    Args:
        project_ctx: Project context for path validation.
        file_path: Path to the Python file to edit.
        method: Operation to perform (get, list_all, replace, delete, rename,
                add_decorator, add_import, verify).
        params: JSON string with method-specific parameters.

    Returns:
        ToolSuccess with result or ToolError with details.
    """
    abs_path = project_ctx.validate_path(file_path)

    try:
        parsed_params = json.loads(params) if params else {}
    except json.JSONDecodeError as e:
        return ToolError(f"Invalid JSON in params: {e}", "validation")

    if not isinstance(parsed_params, dict):
        return ToolError("params must be a JSON object", "validation")

    try:
        backend = PythonEditorBackend(abs_path)
        result = backend.call(method, parsed_params)
        return ToolSuccess(result)
    except FileNotFoundError:
        return ToolError(f"File not found: {file_path}", "execution")
    except Exception as e:
        return ToolError(f"STRUCTURAL_ERROR: {e}", "execution")


class PythonEditorBackend:
    """CST-based Python code manipulation backend."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        source = file_path.read_text()
        self.tree = cst.parse_module(source)

    def call(self, method: str, params: Dict[str, Any]) -> str:
        dispatch = {
            "get": self._get,
            "list_all": self._list_all,
            "replace": self._replace,
            "delete": self._delete,
            "rename": self._rename,
            "add_decorator": self._add_decorator,
            "add_import": self._add_import,
            "verify": self._verify,
        }
        handler = dispatch.get(method)
        if handler is None:
            raise ValueError(
                f"Unknown method '{method}'. "
                f"Available: {', '.join(dispatch.keys())}"
            )
        return handler(params)

    # ------------------------------------------------------------------
    # Read-only methods
    # ------------------------------------------------------------------

    def _get(self, params: Dict[str, Any]) -> str:
        target = params.get("target_name")
        if not target:
            raise ValueError("Missing required parameter: target_name")

        node = self._resolve_node(target)
        if node is None:
            raise ValueError(f"Symbol '{target}' not found")

        return self.tree.code_for_node(node)

    def _list_all(self, params: Dict[str, Any]) -> str:
        symbols: list[str] = []

        for stmt in self.tree.body:
            node = _unwrap_statement(stmt)
            if isinstance(node, cst.FunctionDef):
                symbols.append(f"func: {node.name.value}")
            elif isinstance(node, cst.ClassDef):
                symbols.append(f"class: {node.name.value}")
                for class_stmt in node.body.body:
                    inner = _unwrap_statement(class_stmt)
                    if isinstance(inner, cst.FunctionDef):
                        symbols.append(
                            f"  method: {node.name.value}.{inner.name.value}"
                        )
                    elif isinstance(inner, cst.ClassDef):
                        symbols.append(
                            f"  class: {node.name.value}.{inner.name.value}"
                        )
            elif isinstance(node, cst.Assign):
                for target_node in node.targets:
                    if isinstance(target_node.target, cst.Name):
                        symbols.append(f"var: {target_node.target.value}")
            elif isinstance(node, cst.AnnAssign) and isinstance(
                node.target, cst.Name
            ):
                symbols.append(f"var: {node.target.value}")

        return "\n".join(symbols) if symbols else "No symbols found."

    def _verify(self, params: Dict[str, Any]) -> str:
        source = self.file_path.read_text()
        try:
            cst.parse_module(source)
            return "File is valid Python."
        except cst.ParserSyntaxError as e:
            return f"Syntax error: {e}"

    # ------------------------------------------------------------------
    # Transformation methods
    # ------------------------------------------------------------------

    def _replace(self, params: Dict[str, Any]) -> str:
        target = params.get("target_name")
        new_code = params.get("new_code")
        if not target or not new_code:
            raise ValueError("Missing required parameters: target_name, new_code")

        transformer = _ReplaceTransformer(target, new_code)
        new_tree = transformer.visit(self.tree)

        if not transformer.replaced:
            raise ValueError(f"Symbol '{target}' not found for replacement")

        self._write(new_tree)
        return f"Replaced '{target}' successfully."

    def _delete(self, params: Dict[str, Any]) -> str:
        target = params.get("target_name")
        if not target:
            raise ValueError("Missing required parameter: target_name")

        transformer = _DeleteTransformer(target)
        new_tree = transformer.visit(self.tree)

        if not transformer.deleted:
            raise ValueError(f"Symbol '{target}' not found for deletion")

        self._write(new_tree)
        return f"Deleted '{target}' successfully."

    def _rename(self, params: Dict[str, Any]) -> str:
        old_name = params.get("old_name")
        new_name = params.get("new_name")
        if not old_name or not new_name:
            raise ValueError("Missing required parameters: old_name, new_name")

        transformer = _RenameTransformer(old_name, new_name)
        new_tree = transformer.visit(self.tree)
        self._write(new_tree)
        return f"Renamed '{old_name}' to '{new_name}' (definition + all references)."

    def _add_decorator(self, params: Dict[str, Any]) -> str:
        target = params.get("target_name")
        decorator = params.get("decorator")
        if not target or not decorator:
            raise ValueError("Missing required parameters: target_name, decorator")

        dec_str = decorator.lstrip("@")

        transformer = _DecoratorTransformer(target, dec_str)
        new_tree = transformer.visit(self.tree)

        if not transformer.applied:
            raise ValueError(f"Symbol '{target}' not found for decorator")

        self._write(new_tree)
        return f"Added @{dec_str} to '{target}'."

    def _add_import(self, params: Dict[str, Any]) -> str:
        module = params.get("module")
        name = params.get("name")
        if not module and not name:
            raise ValueError("Missing required parameter: module (and optionally name)")

        transformer = _ImportTransformer(module, name)
        new_tree = transformer.visit(self.tree)
        self._write(new_tree)

        if name:
            return f"Added 'from {module} import {name}'."
        return f"Added 'import {module}'."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write(self, new_tree: cst.Module) -> None:
        self.file_path.write_text(new_tree.code)
        self.tree = new_tree

    def _resolve_node(self, name: str) -> Any:
        """Resolve a symbol name, supporting dotted names like 'Class.method'."""
        parts = name.split(".")

        top_node: Any = None
        for stmt in self.tree.body:
            node = _unwrap_statement(stmt)
            if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
                if node.name.value == parts[0]:
                    top_node = node
                    break
            elif isinstance(node, cst.Assign):
                for target in node.targets:
                    if isinstance(target.target, cst.Name) and target.target.value == parts[0]:
                        top_node = node
                        break
                if top_node:
                    break
            elif isinstance(node, cst.AnnAssign):
                if isinstance(node.target, cst.Name) and node.target.value == parts[0]:
                    top_node = node
                    break

        if top_node is None:
            return None

        current = top_node
        for part in parts[1:]:
            if not isinstance(current, cst.ClassDef):
                return None
            found = False
            for class_stmt in current.body.body:
                inner = _unwrap_statement(class_stmt)
                if isinstance(inner, (cst.FunctionDef, cst.ClassDef)):
                    if inner.name.value == part:
                        current = inner
                        found = True
                        break
            if not found:
                return None

        return current


# ======================================================================
# Transformers
# ======================================================================


def _unwrap_statement(stmt: Any) -> Any:
    """Unwrap a SimpleStatementLine to get the inner node."""
    if isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1:
        return stmt.body[0]
    return stmt


def _matches_name(node: Any, target: str) -> bool:
    """Check if a top-level statement matches the target name."""
    inner = _unwrap_statement(node)
    if isinstance(inner, (cst.FunctionDef, cst.ClassDef)):
        return inner.name.value == target
    if isinstance(inner, cst.Assign):
        for t in inner.targets:
            if isinstance(t.target, cst.Name) and t.target.value == target:
                return True
    if isinstance(inner, cst.AnnAssign) and isinstance(inner.target, cst.Name):
        return inner.target.value == target
    return False


class _ReplaceTransformer:
    """Replace a top-level symbol with new code."""

    def __init__(self, target: str, new_code: str):
        self.target = target
        self.new_code = new_code
        self.replaced = False
        self._target_parts = target.split(".")

    def visit(self, tree: cst.Module) -> cst.Module:
        if len(self._target_parts) == 1:
            return self._replace_top_level(tree)
        return self._replace_nested(tree)

    def _replace_top_level(self, tree: cst.Module) -> cst.Module:
        new_stmt = cst.parse_statement(self.new_code.strip())
        new_body: list[Any] = []
        for stmt in tree.body:
            if _matches_name(stmt, self.target):
                new_body.append(new_stmt)
                self.replaced = True
            else:
                new_body.append(stmt)
        return tree.with_changes(body=new_body)

    def _replace_nested(self, tree: cst.Module) -> cst.Module:
        class_name = self._target_parts[0]
        method_name = self._target_parts[1]
        new_stmt = cst.parse_statement(self.new_code.strip())

        new_body: list[Any] = []
        for stmt in tree.body:
            inner = _unwrap_statement(stmt)
            if isinstance(inner, cst.ClassDef) and inner.name.value == class_name:
                new_class_body: list[Any] = []
                for class_stmt in inner.body.body:
                    class_inner = _unwrap_statement(class_stmt)
                    if (
                        isinstance(class_inner, (cst.FunctionDef, cst.ClassDef))
                        and class_inner.name.value == method_name
                    ):
                        new_class_body.append(new_stmt)
                        self.replaced = True
                    else:
                        new_class_body.append(class_stmt)
                new_class = inner.with_changes(
                    body=inner.body.with_changes(body=new_class_body)
                )
                if isinstance(stmt, cst.SimpleStatementLine):
                    new_body.append(stmt)
                else:
                    new_body.append(new_class)
            else:
                new_body.append(stmt)
        return tree.with_changes(body=new_body)


class _DeleteTransformer:
    """Delete a top-level or nested symbol."""

    def __init__(self, target: str):
        self.target = target
        self.deleted = False
        self._target_parts = target.split(".")

    def visit(self, tree: cst.Module) -> cst.Module:
        if len(self._target_parts) == 1:
            return self._delete_top_level(tree)
        return self._delete_nested(tree)

    def _delete_top_level(self, tree: cst.Module) -> cst.Module:
        new_body: list[Any] = []
        for stmt in tree.body:
            if _matches_name(stmt, self.target):
                self.deleted = True
            else:
                new_body.append(stmt)
        return tree.with_changes(body=new_body)

    def _delete_nested(self, tree: cst.Module) -> cst.Module:
        class_name = self._target_parts[0]
        method_name = self._target_parts[1]

        new_body: list[Any] = []
        for stmt in tree.body:
            inner = _unwrap_statement(stmt)
            if isinstance(inner, cst.ClassDef) and inner.name.value == class_name:
                new_class_body: list[Any] = []
                for class_stmt in inner.body.body:
                    class_inner = _unwrap_statement(class_stmt)
                    if (
                        isinstance(class_inner, (cst.FunctionDef, cst.ClassDef))
                        and class_inner.name.value == method_name
                    ):
                        self.deleted = True
                    else:
                        new_class_body.append(class_stmt)

                if not new_class_body:
                    new_class_body.append(cst.parse_statement("    pass\n"))

                new_class = inner.with_changes(
                    body=inner.body.with_changes(body=new_class_body)
                )
                new_body.append(new_class)
            else:
                new_body.append(stmt)
        return tree.with_changes(body=new_body)


class _RenameTransformer:
    """Rename a symbol and all its references in the file."""

    def __init__(self, old_name: str, new_name: str):
        self.old_name = old_name
        self.new_name = new_name

    def visit(self, tree: cst.Module) -> cst.Module:
        old = self.old_name
        new = self.new_name

        class _Visitor(cst.CSTTransformer):
            def leave_Name(
                self, original_node: cst.Name, updated_node: cst.Name
            ) -> cst.Name:
                if original_node.value == old:
                    return updated_node.with_changes(value=new)
                return updated_node

        return tree.visit(_Visitor())


class _DecoratorTransformer:
    """Add a decorator to a function or class."""

    def __init__(self, target: str, decorator_str: str):
        self.target = target
        self.decorator_str = decorator_str
        self.applied = False

    def visit(self, tree: cst.Module) -> cst.Module:
        dec_expr = cst.parse_expression(self.decorator_str)
        new_dec = cst.Decorator(decorator=dec_expr)
        target = self.target

        class _Visitor(cst.CSTTransformer):
            def __init__(inner_self):
                super().__init__()
                inner_self.applied = False

            def leave_FunctionDef(
                inner_self,
                original_node: cst.FunctionDef,
                updated_node: cst.FunctionDef,
            ) -> cst.FunctionDef:
                if original_node.name.value == target:
                    inner_self.applied = True
                    return updated_node.with_changes(
                        decorators=[*original_node.decorators, new_dec]
                    )
                return updated_node

            def leave_ClassDef(
                inner_self,
                original_node: cst.ClassDef,
                updated_node: cst.ClassDef,
            ) -> cst.ClassDef:
                if original_node.name.value == target:
                    inner_self.applied = True
                    return updated_node.with_changes(
                        decorators=[*original_node.decorators, new_dec]
                    )
                return updated_node

        visitor = _Visitor()
        result = tree.visit(visitor)
        self.applied = visitor.applied
        return result


class _ImportTransformer:
    """Add an import statement at the top of the module."""

    def __init__(self, module: Optional[str], name: Optional[str]):
        self.module = module
        self.name = name

    def visit(self, tree: cst.Module) -> cst.Module:
        if self.name:
            stmt_code = f"from {self.module} import {self.name}\n"
        else:
            stmt_code = f"import {self.module}\n"

        new_import = cst.parse_statement(stmt_code)

        new_body = list(tree.body)
        insert_idx = 0
        for i, stmt in enumerate(new_body):
            inner = _unwrap_statement(stmt)
            if isinstance(inner, (cst.Import, cst.ImportFrom)):
                insert_idx = i + 1

        new_body.insert(insert_idx, new_import)
        return tree.with_changes(body=new_body)
