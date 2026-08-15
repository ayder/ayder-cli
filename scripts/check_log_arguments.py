#!/usr/bin/env python3
"""Gate: every interpolated logging argument carries a reviewed classification.

A log message is a sink for whatever the caller hands it. `logger.error("{}",
exc)` looks harmless in review and ships the exception's text - paths, request
bodies, credentials - into every prose sink. Reviewing that once is worthless:
the next argument added to the next call is unreviewed again.

This gate freezes the review. It enumerates every interpolated argument of every
logging call under the source root, matches each against a committed baseline of
classified rows, and fails when anything is new, stale, edited, or reclassified.
Adding an argument therefore costs one baseline line and one classification -
which is exactly the review that keeps content out of the message.

Scope of an "interpolated argument" (the frozen census boundary):

  * the arguments a logger level-method interpolates into its message, and
  * the event fields handed to the `emit_event` facade,

but NOT `.bind()/.opt()/.patch()` keywords, which populate `record["extra"]`
rather than `record["message"]`. Constant literals are not rows: they carry no
runtime value. Extra-field exposure is a sink question, not an argument
question, and is deliberately out of this gate's frame.

Receivers are RESOLVED, never name-matched. A binding counts as a logger
because its right-hand side is one - a `get_logger` factory call, `from loguru
import logger`, an alias of either, a class/instance attribute assigned one, a
local function that returns one, or any `.bind/.opt/.patch` chain over one. An
object named `logger` that is not one does not count; an object not named
`logger` that is one does.

Fail-closed coverage. Every one of these exits nonzero:

  * a missing or empty source root, or a file that will not parse;
  * a missing, empty, malformed, duplicated or reclassified baseline row;
  * an unknown classification tag;
  * a logging call whose receiver, message position or `**` splat cannot be
    resolved statically - including `.log(level=..., message=...)` keyword
    forms and an unresolvable `.bind(...)...` chain;
  * a format string whose placeholders do not match the supplied arguments,
    including Python's illegal automatic/manual field mixing;
  * a `%`-style placeholder in a logging literal (legacy-format violation);
  * an argument row that is NEW, REMOVED, CHANGED or RECLASSIFIED.

Baseline format - JSONL, one object per line:

    {"site": {"path","qualname","method","message","arg_index","expr"},
     "class": "<tag>"}

Identity is the `site` object alone and carries no line number, so moving code
inside a file is free while editing what is logged is not. Classification lives
outside the identity so that changing a row's tag reports as RECLASSIFIED
rather than as an unrelated NEW/REMOVED pair. Rows are ordered by the canonical
JSON of `site`, which is total and therefore collision-free.

Report vocabulary:

  NEW           a live argument with no baseline row - unclassified.
  REMOVED       a baseline row with no live argument - stale.
  CHANGED       a baseline row whose call site survives at the same argument
                position but whose message or expression was edited, so the
                granted classification no longer covers it.
  RECLASSIFIED  one identity carrying two different classifications.
  DUPLICATE     one identity repeated under the same classification.
  AMBIGUOUS     two live arguments that share an identity, so no baseline row
                can name either of them unambiguously.
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import string
import sys

# ---------------------------------------------------------------- constants

LEVELS = frozenset({"trace", "debug", "info", "success", "warning", "error",
                    "exception", "critical"})
LOG_METHOD = "log"
LEVEL_METHODS = LEVELS | {LOG_METHOD}
CHAIN_METHODS = frozenset({"bind", "opt", "patch"})

FACADE = "emit_event"
FACTORY = "get_logger"
# The facade module, as `from ...log import`ed anywhere in the package.
LOG_MODULE_SUFFIX = "log"

# Review-visible provenance tags. `ident` is deliberately absent: a single
# generic tag would let any argument in without saying what it is.
VALID_CLASSES = (
    "R-name",     # tool/agent/plugin/model/driver/channel/panel/command names
    "R-id",       # run/session/call ids, generations, short SHAs
    "R-count",    # len(), counts, sizes, tokens, timings, ratios
    "R-status",   # enum-like status/mode/protocol/strategy constants
    "R-class",    # type(x).__name__ - never the value
    "R-path",     # filesystem locations, retained as operational diagnostics
    "content-deferred:5-04",   # known content risk, owned by step 5-04
    "dynamic-trusted",         # dynamic message from a frozen code constant
    "dynamic-deferred:5-04",   # dynamic message content risk, owned by 5-04
)

SITE_KEYS = ("path", "qualname", "method", "message", "arg_index", "expr")

# Same conversion set as the %-style gate; `%%` is stripped before matching.
PCT = re.compile(r"%(?:\([^)]*\))?[-#0 +]*[\d.*]*[hlL]?[scdrfgeixXou]")

# scripts/<this>.py -> repo root. Never cwd-relative: a cwd-derived root is how
# a gate "passes" over an empty tree.
REPO = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO / "src" / "ayder_cli"
BASELINE = pathlib.Path(__file__).resolve().parent / "log_argument_baseline.txt"

# Receiver kinds.
LOGGER = "logger"
FACTORY_KIND = "factory"
CLASS_KIND = "class"
NOT_LOGGER = "not-logger"
UNKNOWN = "unknown"


def _display(p: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


def _canon(site: dict) -> str:
    return json.dumps(site, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def _slot(site: dict) -> tuple:
    return (site["path"], site["qualname"], site["method"], site["arg_index"])


# ---------------------------------------------------------------- arity

def _base_field(name: str) -> str:
    """`user.name` -> `user`; `0[1]` -> `0`; `` (automatic) -> ``."""
    for i, ch in enumerate(name):
        if ch in ".[":
            return name[:i]
    return name


def _collect_fields(fmt: str, out: list[str]) -> None:
    """Every replacement field in `fmt`, recursing into nested format specs."""
    for _literal, field_name, spec, _conv in string.Formatter().parse(fmt):
        if field_name is None:
            continue
        out.append(field_name)
        if spec:
            _collect_fields(spec, out)


class FormatError(Exception):
    """The message cannot be reconciled with its arguments."""


def format_arity(fmt: str) -> tuple[int, set[str]]:
    """(required positional count, required keyword names) for `fmt`.

    Raises FormatError for a malformed template or for Python's illegal mixing
    of automatic and manual field numbering.
    """
    fields: list[str] = []
    try:
        _collect_fields(fmt, fields)
    except ValueError as e:
        raise FormatError(f"malformed format string: {e}") from e

    auto = 0
    numbered: set[int] = set()
    named: set[str] = set()
    for field in fields:
        base = _base_field(field)
        if base == "":
            auto += 1
        elif base.isdigit():
            numbered.add(int(base))
        else:
            named.add(base)

    if auto and numbered:
        raise FormatError(
            "cannot switch between automatic and manual field numbering")
    positional = auto if auto else (max(numbered) + 1 if numbered else 0)
    return positional, named


# ---------------------------------------------------------------- resolution

class _Unsupported(Exception):
    """A shape this gate refuses to guess at."""


def _dict_keys_from_body(name: str, body: list[ast.stmt]) -> set[str] | None:
    """Static keys of a dict-literal local, including constant subscript adds.

    Returns None when the variable is not a plain dict literal, or when any key
    is not a constant string - the two shapes whose key set cannot be read off
    the source.
    """
    keys: set[str] | None = None
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if not isinstance(node.value, ast.Dict):
                        return None
                    if keys is not None:
                        return None          # rebound: not a single literal
                    literal: set[str] = set()
                    for key in node.value.keys:
                        if not (isinstance(key, ast.Constant)
                                and isinstance(key.value, str)):
                            return None
                        literal.add(key.value)
                    for value in node.value.values:
                        if isinstance(value, ast.Starred):
                            return None
                    keys = literal
                elif (isinstance(target, ast.Subscript)
                      and isinstance(target.value, ast.Name)
                      and target.value.id == name):
                    slice_node = target.slice
                    if not (isinstance(slice_node, ast.Constant)
                            and isinstance(slice_node.value, str)):
                        return None
                    if keys is None:
                        return None
                    keys.add(slice_node.value)
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and isinstance(node.func.value, ast.Name)
              and node.func.value.id == name
              and node.func.attr in {"update", "setdefault", "pop", "clear"}):
            return None                       # mutated by a method we cannot read
    return keys


class ModuleAnalysis:
    """Receiver resolution and call enumeration for one module."""

    def __init__(self, path: str, tree: ast.Module) -> None:
        self.path = path
        self.tree = tree
        self.kinds: dict[tuple, str] = {}
        self.problems: list[str] = []
        self.calls: list[dict] = []
        self._parents: dict[ast.AST, ast.AST] = {}
        self._scope_of: dict[ast.AST, tuple[str, str]] = {}
        self._class_body: dict[str, ast.ClassDef] = {}
        self._func_body: dict[tuple[str, str], ast.AST] = {}
        self._index()
        self._bind()

    # -- indexing ---------------------------------------------------------

    def _index(self) -> None:
        """Record each node's parent, enclosing scope id and enclosing class."""
        def walk(node: ast.AST, scope: str, cls: str) -> None:
            for child in ast.iter_child_nodes(node):
                self._parents[child] = node
                if isinstance(child, ast.ClassDef):
                    inner_cls = f"{cls}.{child.name}" if cls else child.name
                    self._class_body[inner_cls] = child
                    self._scope_of[child] = (scope, cls)
                    walk(child, f"{scope}.{child.name}" if scope else child.name,
                         inner_cls)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inner = f"{scope}.{child.name}" if scope else child.name
                    self._scope_of[child] = (scope, cls)
                    self._func_body[(cls, child.name)] = child
                    walk(child, inner, cls)
                else:
                    self._scope_of[child] = (scope, cls)
                    walk(child, scope, cls)
        self._scope_of[self.tree] = ("", "")
        walk(self.tree, "", "")

    def _scope(self, node: ast.AST) -> tuple[str, str]:
        return self._scope_of.get(node, ("", ""))

    # -- binding ----------------------------------------------------------

    def _bind(self) -> None:
        """Resolve every binding to a receiver kind, to a fixed point."""
        # (binding key, value expressions, scope, class, is_function_def)
        assignments: list[tuple[tuple, list[ast.AST], str, str, bool]] = []

        for node in ast.walk(self.tree):
            scope, cls = self._scope(node)

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                tail = module.rsplit(".", 1)[-1]
                for alias in node.names:
                    local = alias.asname or alias.name
                    if module == "loguru" and alias.name == "logger":
                        self.kinds[("name", "", local)] = LOGGER
                    elif tail == LOG_MODULE_SUFFIX and alias.name == FACTORY:
                        self.kinds[("name", "", local)] = FACTORY_KIND
                    elif tail == LOG_MODULE_SUFFIX and alias.name == FACADE:
                        self.kinds[("name", "", local)] = FACADE
                    elif alias.name == LOG_MODULE_SUFFIX and not module.endswith(
                            "." + LOG_MODULE_SUFFIX):
                        self.kinds[("module", "", local)] = LOG_MODULE_SUFFIX

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.rsplit(".", 1)[-1] == LOG_MODULE_SUFFIX:
                        local = alias.asname or alias.name
                        self.kinds[("module", "", local)] = LOG_MODULE_SUFFIX

            elif isinstance(node, ast.ClassDef):
                outer, _ = self._scope(node)
                self.kinds[("name", outer, node.name)] = CLASS_KIND

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                outer, outer_cls = self._scope(node)
                returns = [r.value for r in ast.walk(node)
                           if isinstance(r, ast.Return) and r.value is not None]
                if returns:
                    assignments.append((("name", outer, node.name), returns,
                                        f"{outer}.{node.name}" if outer
                                        else node.name, outer_cls, True))
                else:
                    self.kinds[("name", outer, node.name)] = NOT_LOGGER

            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                if node.value is None:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name):
                        assignments.append((("name", scope, target.id),
                                            [node.value], scope, cls, False))
                    elif (isinstance(target, ast.Attribute)
                          and isinstance(target.value, ast.Name)
                          and target.value.id == "self" and cls):
                        assignments.append((("attr", cls, target.attr),
                                            [node.value], scope, cls, False))

        for _ in range(8):
            changed = False
            for key, values, scope, cls, is_def in assignments:
                kinds = {self.kind_of(v, scope, cls) for v in values}
                resolved = next(iter(kinds)) if len(kinds) == 1 else UNKNOWN
                if is_def:
                    # The NAME of a function that returns a logger is not a
                    # logger; calling it produces one.
                    resolved = FACTORY_KIND if resolved == LOGGER else NOT_LOGGER
                if key[0] == "name" and key in self.kinds and self.kinds[key] in (
                        LOGGER, FACTORY_KIND, FACADE, CLASS_KIND):
                    # An import binding wins over a later shadowing assignment
                    # only when the assignment says nothing.
                    if resolved == UNKNOWN:
                        continue
                if self.kinds.get(key) != resolved:
                    self.kinds[key] = resolved
                    changed = True
            if not changed:
                break

    # -- expression kinds -------------------------------------------------

    def _lookup(self, name: str, scope: str) -> str | None:
        parts = scope.split(".") if scope else []
        while True:
            candidate = ".".join(parts)
            if ("name", candidate, name) in self.kinds:
                return self.kinds[("name", candidate, name)]
            if not parts:
                return None
            parts.pop()

    def _module_alias(self, name: str, scope: str) -> bool:
        parts = scope.split(".") if scope else []
        while True:
            if ("module", ".".join(parts), name) in self.kinds:
                return True
            if not parts:
                return False
            parts.pop()

    def kind_of(self, node: ast.AST, scope: str, cls: str) -> str:
        if isinstance(node, ast.Name):
            found = self._lookup(node.id, scope)
            if found is not None:
                return found
            if self._module_alias(node.id, scope):
                return NOT_LOGGER
            return UNKNOWN

        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                owner = cls
                while owner:
                    if ("attr", owner, node.attr) in self.kinds:
                        return self.kinds[("attr", owner, node.attr)]
                    if ("name", self._class_scope(owner), node.attr) in self.kinds:
                        return self.kinds[("name", self._class_scope(owner),
                                           node.attr)]
                    owner = owner.rsplit(".", 1)[0] if "." in owner else ""
                return UNKNOWN
            if (isinstance(node.value, ast.Name)
                    and self._module_alias(node.value.id, scope)):
                if node.attr == FACTORY:
                    return FACTORY_KIND
                if node.attr == FACADE:
                    return FACADE
                return NOT_LOGGER
            return UNKNOWN

        if isinstance(node, ast.Call):
            func_kind = self.kind_of(node.func, scope, cls)
            if func_kind == FACTORY_KIND:
                return LOGGER
            if func_kind == CLASS_KIND:
                return NOT_LOGGER
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr in CHAIN_METHODS):
                return self.kind_of(node.func.value, scope, cls)
            return UNKNOWN

        if isinstance(node, (ast.Constant, ast.JoinedStr, ast.Dict, ast.List,
                             ast.Set, ast.Tuple, ast.BinOp, ast.Compare,
                             ast.ListComp, ast.DictComp, ast.SetComp,
                             ast.GeneratorExp, ast.Lambda, ast.FormattedValue,
                             ast.UnaryOp)):
            return NOT_LOGGER

        if isinstance(node, ast.IfExp):
            kinds = {self.kind_of(node.body, scope, cls),
                     self.kind_of(node.orelse, scope, cls)}
            return next(iter(kinds)) if len(kinds) == 1 else UNKNOWN

        if isinstance(node, ast.BoolOp):
            kinds = {self.kind_of(v, scope, cls) for v in node.values}
            return next(iter(kinds)) if len(kinds) == 1 else UNKNOWN

        return UNKNOWN

    def _class_scope(self, cls: str) -> str:
        return cls

    # -- splat expansion --------------------------------------------------

    def _enclosing_function(self, node: ast.AST) -> ast.AST | None:
        current = self._parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current
            current = self._parents.get(current)
        return None

    def splat_keys(self, node: ast.AST, call: ast.Call, cls: str) -> list[str]:
        """Static keys of a `**` argument, or raise _Unsupported."""
        if isinstance(node, ast.Dict):
            keys = []
            for key in node.keys:
                if not (isinstance(key, ast.Constant)
                        and isinstance(key.value, str)):
                    raise _Unsupported("`**` dict literal with a dynamic key")
                keys.append(key.value)
            return sorted(keys)

        if isinstance(node, ast.Name):
            func = self._enclosing_function(call)
            if func is None:
                raise _Unsupported(f"`**{node.id}` outside a function body")
            keys = _dict_keys_from_body(node.id, list(func.body))
            if keys is None:
                raise _Unsupported(
                    f"`**{node.id}` is not a statically readable dict literal")
            return sorted(keys)

        if (isinstance(node, ast.Call) and not node.args and not node.keywords
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self" and cls):
            method = self._func_body.get((cls, node.func.attr))
            if method is None:
                raise _Unsupported(
                    f"`**self.{node.func.attr}()` is not defined in this class")
            returns = [r.value for r in ast.walk(method)
                       if isinstance(r, ast.Return) and r.value is not None]
            if len(returns) != 1:
                raise _Unsupported(
                    f"`**self.{node.func.attr}()` has no single return")
            returned = returns[0]
            if isinstance(returned, ast.Dict):
                return self.splat_keys(returned, call, cls)
            if isinstance(returned, ast.Name):
                keys = _dict_keys_from_body(returned.id, list(method.body))
                if keys is None:
                    raise _Unsupported(
                        f"`**self.{node.func.attr}()` returns a dict this gate "
                        f"cannot read statically")
                return sorted(keys)
            raise _Unsupported(
                f"`**self.{node.func.attr}()` returns an unreadable expression")

        raise _Unsupported(f"`**{ast.unparse(node)}` cannot be expanded")


# ---------------------------------------------------------------- scanning

def _qualname(analysis: ModuleAnalysis, node: ast.AST) -> str:
    scope, _cls = analysis._scope(node)
    return scope or "<module>"


def _message_kind(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "literal"
    if isinstance(node, (ast.JoinedStr, ast.BinOp)):
        return "dynamic"
    return "dynamic"


def scan_module(path: str, tree: ast.Module) -> dict:
    """Enumerate the logging calls, rows and findings of one parsed module."""
    analysis = ModuleAnalysis(path, tree)
    rows: list[dict] = []
    # Parallel to `rows`. Lines never enter an identity - moving code inside a
    # file must stay free - but a NEW finding without one is not actionable.
    row_lines: list[int] = []
    findings: list[str] = []
    # (canonical star row, message): reported only when unclassified.
    star_findings: list[tuple[str, str]] = []
    level_calls = 0
    facade_calls = 0
    dynamic_rows = 0
    raw_args = 0
    splats = 0
    splat_keys = 0
    sites_with_args = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        scope, cls = analysis._scope(node)
        qualname = scope or "<module>"
        func = node.func

        # -- the emit_event facade ---------------------------------------
        if analysis.kind_of(func, scope, cls) == FACADE:
            facade_calls += 1
            method = FACADE
            message = None
            call_rows: list[dict] = []
            try:
                for index, arg in enumerate(node.args):
                    if isinstance(arg, ast.Starred):
                        raise _Unsupported("`*args` into emit_event")
                    if isinstance(arg, ast.Constant):
                        continue
                    raw_args += 1
                    call_rows.append({
                        "path": path, "qualname": qualname, "method": method,
                        "message": message, "arg_index": f"pos:{index}",
                        "expr": ast.unparse(arg),
                    })
                for keyword in node.keywords:
                    if keyword.arg is None:
                        splats += 1
                        raw_args += 1
                        keys = analysis.splat_keys(keyword.value, node, cls)
                        splat_keys += len(keys)
                        rendered = ast.unparse(keyword.value)
                        for key in keys:
                            call_rows.append({
                                "path": path, "qualname": qualname,
                                "method": method, "message": message,
                                "arg_index": f"splat:{rendered}:{key}",
                                "expr": f"{rendered}[{key!r}]",
                            })
                        continue
                    if isinstance(keyword.value, ast.Constant):
                        continue
                    raw_args += 1
                    call_rows.append({
                        "path": path, "qualname": qualname, "method": method,
                        "message": message, "arg_index": f"kw:{keyword.arg}",
                        "expr": ast.unparse(keyword.value),
                    })
            except _Unsupported as e:
                findings.append(
                    f"UNSUPPORTED {path}:{node.lineno} {qualname} emit_event: {e}")
                continue
            rows.extend(call_rows)
            row_lines.extend([node.lineno] * len(call_rows))
            if call_rows:
                sites_with_args += 1
            continue

        # -- logger level methods ----------------------------------------
        if not (isinstance(func, ast.Attribute) and func.attr in LEVEL_METHODS):
            continue
        receiver = analysis.kind_of(func.value, scope, cls)
        if receiver != LOGGER:
            chained = (isinstance(func.value, ast.Call)
                       and isinstance(func.value.func, ast.Attribute)
                       and func.value.func.attr in CHAIN_METHODS)
            if receiver == UNKNOWN:
                findings.append(
                    f"UNRESOLVED-RECEIVER {path}:{node.lineno} {qualname} "
                    f"`{ast.unparse(func.value)}.{func.attr}(...)` - a "
                    f"{'logger-like chain' if chained else 'receiver'} this "
                    f"gate cannot resolve to a logger or to a non-logger")
            continue

        level_calls += 1
        method = func.attr
        message_index = 1 if method == LOG_METHOD else 0

        if method == LOG_METHOD:
            bad = [k.arg for k in node.keywords
                   if k.arg in ("level", "message")]
            if bad:
                findings.append(
                    f"UNSUPPORTED {path}:{node.lineno} {qualname} "
                    f".log() keyword form {bad} - only the positional "
                    f".log(level, message, ...) form is verified")
                continue

        if any(isinstance(a, ast.Starred) for a in node.args[:message_index + 1]):
            findings.append(
                f"UNSUPPORTED {path}:{node.lineno} {qualname} "
                f".{method}() message position occupied by `*args`")
            continue
        if len(node.args) <= message_index:
            findings.append(
                f"UNSUPPORTED {path}:{node.lineno} {qualname} "
                f".{method}() has no positional message argument")
            continue

        message_node = node.args[message_index]
        kind = _message_kind(message_node)
        message = message_node.value if kind == "literal" else None
        call_rows = []
        unverifiable: str | None = None

        if kind == "dynamic":
            dynamic_rows += 1
            rows.append({
                "path": path, "qualname": qualname, "method": method,
                "message": None, "arg_index": None,
                "expr": ast.unparse(message_node),
            })
            row_lines.append(node.lineno)

        supplied_positional = 0
        supplied_keywords: set[str] = set()
        try:
            for index, arg in enumerate(node.args[message_index + 1:]):
                if isinstance(arg, ast.Starred):
                    raw_args += 1
                    star_row = {
                        "path": path, "qualname": qualname, "method": method,
                        "message": message, "arg_index": f"star:{index}",
                        "expr": f"*{ast.unparse(arg.value)}",
                    }
                    unverifiable = _canon(star_row)
                    call_rows.append(star_row)
                    continue
                supplied_positional += 1
                if isinstance(arg, ast.Constant):
                    continue
                raw_args += 1
                call_rows.append({
                    "path": path, "qualname": qualname, "method": method,
                    "message": message, "arg_index": f"pos:{index}",
                    "expr": ast.unparse(arg),
                })
            for keyword in node.keywords:
                if keyword.arg is None:
                    splats += 1
                    raw_args += 1
                    keys = analysis.splat_keys(keyword.value, node, cls)
                    splat_keys += len(keys)
                    supplied_keywords.update(keys)
                    rendered = ast.unparse(keyword.value)
                    for key in keys:
                        call_rows.append({
                            "path": path, "qualname": qualname,
                            "method": method, "message": message,
                            "arg_index": f"splat:{rendered}:{key}",
                            "expr": f"{rendered}[{key!r}]",
                        })
                    continue
                supplied_keywords.add(keyword.arg)
                if isinstance(keyword.value, ast.Constant):
                    continue
                raw_args += 1
                call_rows.append({
                    "path": path, "qualname": qualname, "method": method,
                    "message": message, "arg_index": f"kw:{keyword.arg}",
                    "expr": ast.unparse(keyword.value),
                })
        except _Unsupported as e:
            findings.append(
                f"UNSUPPORTED {path}:{node.lineno} {qualname} "
                f".{method}(): {e}")
            continue

        if kind == "literal":
            stripped = message.replace("%%", "")
            if PCT.search(stripped):
                findings.append(
                    f"LEGACY-FORMAT {path}:{node.lineno} {qualname} "
                    f".{method}() message carries a %-style placeholder; "
                    f"loguru formats with str.format and drops the arguments")
            try:
                required, named = format_arity(message)
            except FormatError as e:
                findings.append(
                    f"BAD-FORMAT {path}:{node.lineno} {qualname} "
                    f".{method}(): {e}")
            else:
                if unverifiable:
                    star_findings.append((
                        unverifiable,
                        f"UNVERIFIABLE-ARITY {path}:{node.lineno} {qualname} "
                        f".{method}() splices `*args`; its placeholder count "
                        f"cannot be checked"))
                elif required != supplied_positional:
                    verb = "missing" if required > supplied_positional else "surplus"
                    findings.append(
                        f"ARITY {path}:{node.lineno} {qualname} .{method}() "
                        f"{verb} argument(s): {required} placeholder(s), "
                        f"{supplied_positional} positional argument(s)")
                absent = sorted(named - supplied_keywords)
                if absent:
                    findings.append(
                        f"ARITY {path}:{node.lineno} {qualname} .{method}() "
                        f"named field(s) with no argument: {absent}")

        rows.extend(call_rows)
        row_lines.extend([node.lineno] * len(call_rows))
        if call_rows:
            sites_with_args += 1

    return {
        "rows": rows,
        "row_lines": row_lines,
        "findings": findings,
        "star_findings": star_findings,
        "level_calls": level_calls,
        "facade_calls": facade_calls,
        "dynamic_rows": dynamic_rows,
        "raw_args": raw_args,
        "splats": splats,
        "splat_keys": splat_keys,
        "sites_with_args": sites_with_args,
    }


# ---------------------------------------------------------------- baseline

def load_baseline(path: pathlib.Path) -> tuple[dict[str, str], list[str]]:
    """Return ({canonical site: class}, findings). Every defect fails closed."""
    findings: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    table: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            findings.append(f"MALFORMED baseline line {number}: {e}")
            continue
        if not isinstance(row, dict) or set(row) != {"site", "class"}:
            findings.append(
                f"MALFORMED baseline line {number}: expected exactly the keys "
                f"'site' and 'class'")
            continue
        site, tag = row["site"], row["class"]
        if not isinstance(site, dict) or set(site) != set(SITE_KEYS):
            findings.append(
                f"MALFORMED baseline line {number}: site must carry exactly "
                f"{list(SITE_KEYS)}")
            continue
        if not isinstance(site["path"], str) or not isinstance(
                site["qualname"], str) or not isinstance(site["method"], str) \
                or not isinstance(site["expr"], str):
            findings.append(
                f"MALFORMED baseline line {number}: path/qualname/method/expr "
                f"must be strings")
            continue
        if site["message"] is not None and not isinstance(site["message"], str):
            findings.append(
                f"MALFORMED baseline line {number}: message must be a string "
                f"or null")
            continue
        if site["arg_index"] is not None and not isinstance(
                site["arg_index"], str):
            findings.append(
                f"MALFORMED baseline line {number}: arg_index must be a string "
                f"or null")
            continue
        if tag not in VALID_CLASSES:
            findings.append(
                f"UNKNOWN-CLASS baseline line {number}: {tag!r} is not one of "
                f"{list(VALID_CLASSES)}")
            continue
        key = _canon(site)
        if key in table:
            if table[key] == tag:
                findings.append(f"DUPLICATE baseline row: {key}")
            else:
                findings.append(
                    f"RECLASSIFIED baseline row carries both {table[key]!r} and "
                    f"{tag!r}: {key}")
            continue
        table[key] = tag
    return table, findings


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(SRC_ROOT),
                    help="directory to scan (default: the package source root)")
    ap.add_argument("--baseline", default=str(BASELINE),
                    help="classified baseline (default: next to this script)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"ABORT: source root does not exist: {root}", file=sys.stderr)
        return 2
    py_files = sorted(root.rglob("*.py"))
    if not py_files:
        print(f"ABORT: no Python files under {root}", file=sys.stderr)
        return 2

    # A baseline that is absent or blank is an invocation error, not a clean
    # run: without it every classification in the tree is unreviewed.
    baseline_path = pathlib.Path(args.baseline)
    if not baseline_path.is_file():
        print(f"ABORT: baseline does not exist: {baseline_path}", file=sys.stderr)
        return 2
    if not baseline_path.read_text(encoding="utf-8").strip():
        print(f"ABORT: baseline is empty: {baseline_path}", file=sys.stderr)
        return 2

    findings: list[str] = []
    rows: list[dict] = []
    row_lines: list[int] = []
    star_findings: list[tuple[str, str]] = []
    scanned = 0
    totals = {"level_calls": 0, "facade_calls": 0, "dynamic_rows": 0,
              "raw_args": 0, "splats": 0, "splat_keys": 0, "sites_with_args": 0}

    for p in py_files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as e:
            findings.append(f"UNPARSEABLE {_display(p, root)}: {e}")
            continue
        scanned += 1
        result = scan_module(_display(p, root), tree)
        rows.extend(result["rows"])
        row_lines.extend(result["row_lines"])
        findings.extend(result["findings"])
        star_findings.extend(result["star_findings"])
        for key in totals:
            totals[key] += result[key]

    live: dict[str, dict] = {}
    live_lines: dict[str, int] = {}
    for site, line in zip(rows, row_lines):
        key = _canon(site)
        if key in live:
            findings.append(
                f"AMBIGUOUS two live arguments share an identity "
                f"({site['path']}:{live_lines[key]} and {site['path']}:{line}): "
                f"{key}")
            continue
        live[key] = site
        live_lines[key] = line

    baseline, baseline_findings = load_baseline(baseline_path)
    findings.extend(baseline_findings)

    # `*args` cannot be counted against a placeholder count. The row is still a
    # row: classifying it is the reviewer's explicit acceptance of the gap.
    for key, message in star_findings:
        if key not in baseline:
            findings.append(message)

    new_keys = [k for k in sorted(live) if k not in baseline]
    removed_keys = [k for k in sorted(baseline) if k not in live]

    # Pair a survivor slot before reporting NEW + REMOVED for the same argument.
    live_slots: dict[tuple, list[str]] = {}
    for key, site in live.items():
        live_slots.setdefault(_slot(site), []).append(key)
    removed_slots: dict[tuple, list[str]] = {}
    for key in removed_keys:
        removed_slots.setdefault(_slot(json.loads(key)), []).append(key)

    changed: list[tuple[str, str]] = []
    paired_new: set[str] = set()
    paired_removed: set[str] = set()
    for key in new_keys:
        slot = _slot(live[key])
        candidates = [k for k in removed_slots.get(slot, [])
                      if k not in paired_removed]
        fresh = [k for k in live_slots.get(slot, []) if k in new_keys]
        if len(candidates) == 1 and len(fresh) == 1:
            changed.append((candidates[0], key))
            paired_new.add(key)
            paired_removed.add(candidates[0])

    print(f"scanned {scanned} file(s) of {len(py_files)} discovered under {root}")
    print(f"{totals['level_calls'] + totals['facade_calls']} logging call "
          f"site(s): {totals['level_calls']} level-method + "
          f"{totals['facade_calls']} emit_event facade")
    print(f"{totals['sites_with_args']} call site(s) with >=1 interpolated "
          f"argument")
    dynamic_live = sum(1 for s in live.values() if s["arg_index"] is None)
    print(f"{len(live) - dynamic_live} interpolated argument(s) after static "
          f"splat expansion ({totals['raw_args']} raw, {totals['splats']} "
          f"splat(s) -> {totals['splat_keys']} key(s))")
    print(f"{dynamic_live} dynamic message row(s)")
    print(f"{len(baseline)} baseline row(s) from {baseline_path}")

    for old, fresh in changed:
        print(f"CHANGED at {live[fresh]['path']}:{live_lines[fresh]}\n"
              f"    was {old}\n    now {fresh}")
    for key in new_keys:
        if key not in paired_new:
            print(f"NEW unclassified argument at {live[key]['path']}:"
                  f"{live_lines[key]}: {key}")
    for key in removed_keys:
        if key not in paired_removed:
            print(f"REMOVED stale baseline row ({baseline[key]}): {key}")
    for finding in findings:
        print(finding)

    total = (len(changed) + len(set(new_keys) - paired_new)
             + len(set(removed_keys) - paired_removed) + len(findings))
    if total:
        print(f"FAIL - {total} finding(s)")
        return 1
    print("0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
