#!/usr/bin/env python3
"""Gate: every broad exception handler must satisfy the logging policy.

Verdicts:
  PASS    - a reachable satisfying statement was found
  FAIL    - swallows silently, or exits without satisfying
  REPORT  - branches before satisfying; needs a human
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

LEVELS = {"trace", "debug", "info", "success", "warning", "error",
          "exception", "critical"}
BROAD = {"Exception", "BaseException"}

# Resolved from this file, not the cwd: scripts/<this>.py -> repo root.
REPO = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO / "src" / "ayder_cli"
DEFAULT_BASELINE = REPO / "scripts" / "exception_baseline.txt"

# Frozen census (§C10). A different number means the gate is looking at the
# wrong tree, or the census moved without the plan being updated.
EXPECTED_BROAD = 125
BRANCHING = (ast.If, ast.Try, ast.For, ast.While, ast.With, ast.Match)
TERMINAL = (ast.Return, ast.Break, ast.Continue, ast.Pass)


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """Bare `except:` is NOT in scope — see CONTRACTS C10."""
    t = handler.type
    if t is None:
        return False
    if isinstance(t, ast.Name):
        return t.id in BROAD
    if isinstance(t, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id in BROAD for e in t.elts)
    return False


LOGGERS = {"logger", "llm_log", "tool_log"}


def _approved_receiver(node: ast.expr) -> bool:
    """Only the §C8 bindings satisfy the policy.

    Without this, any object's `.exception()`/`.opt()` would pass — a Future's
    `.exception()` being the obvious trap.
    """
    return isinstance(node, ast.Name) and node.id in LOGGERS


def _is_exception_log(node: ast.stmt) -> bool:
    """Either logger.opt(exception=True).<level>(...) or logger.exception(...)."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    call = node.value
    if not isinstance(call.func, ast.Attribute):
        return False

    # Form 2: logger.exception(...) — loguru shorthand, carries the exception.
    # ruff TRY400 actively pushes code toward this, so it MUST be accepted —
    # but only on a real logger. `future.exception()` must not satisfy policy.
    if call.func.attr == "exception":
        return _approved_receiver(call.func.value)

    # Form 1: logger.opt(exception=True).<level>(...)
    if call.func.attr not in LEVELS:
        return False
    recv = call.func.value
    if not (isinstance(recv, ast.Call) and isinstance(recv.func, ast.Attribute)
            and recv.func.attr == "opt"
            and _approved_receiver(recv.func.value)):
        return False
    return any(kw.arg == "exception" and getattr(kw.value, "value", None) is True
               for kw in recv.keywords)


def _is_failure_return(node: ast.stmt) -> bool:
    """ToolError(...) or ExecutionResult(success=False, ...) — nothing else."""
    if not isinstance(node, ast.Return) or node.value is None:
        return False
    v = node.value
    if not isinstance(v, ast.Call):
        return False
    name = getattr(v.func, "id", None) or getattr(v.func, "attr", None)

    if name == "ToolError":
        return True
    if name == "ExecutionResult":
        # success=True is a SUCCESS return and satisfies nothing.
        return any(kw.arg == "success" and getattr(kw.value, "value", None) is False
                   for kw in v.keywords)
    return False


def _satisfies(node: ast.stmt) -> bool:
    return (isinstance(node, ast.Raise)
            or _is_failure_return(node)
            or _is_exception_log(node))


def _has_reasoned_marker(line: str) -> bool:
    """`# noqa: AYDER-EXC <reason>` — the reason text is mandatory.

    A bare marker records no decision, so it must not suppress.
    """
    idx = line.find("AYDER-EXC")
    if idx == -1:
        return False
    return bool(line[idx + len("AYDER-EXC"):].strip(" :-\t"))


def _verdict(handler: ast.ExceptHandler) -> str:
    for stmt in handler.body:
        if _satisfies(stmt):
            return "PASS"
        if isinstance(stmt, BRANCHING):
            return "REPORT"
        if isinstance(stmt, TERMINAL):
            return "FAIL"        # exits without satisfying
    return "FAIL"                 # fell off the end


def _broad_handlers(path: str, tree: ast.AST) -> list[tuple[ast.ExceptHandler, str]]:
    """Yield (handler, stable_id), id = `path::qualname::ordinal`.

    NEVER key a finding by line number. Step 3-02 inserts an import into 15
    files and every handler below it shifts; each remediation shifts the rest
    again. A line-keyed baseline reports every untouched handler as a new
    finding on the very next commit. This id survives both — verified: 119
    handlers, 119 unique ids, byte-identical after prepending imports and
    after editing a handler body.
    """
    out: list[tuple[ast.ExceptHandler, str]] = []
    stack: list[str] = []
    counter: dict[str, int] = {}

    class _V(ast.NodeVisitor):
        def _scope(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

        def visit_Try(self, node):
            for h in node.handlers:
                if _is_broad(h):
                    key = f"{path}::{'.'.join(stack) or '<module>'}"
                    counter[key] = counter.get(key, 0) + 1
                    out.append((h, f"{key}::{counter[key]}"))
            self.generic_visit(node)

        # PEP 654 `except*` groups parse to a distinct node type (ast.TryStar,
        # not ast.Try) with the same `.handlers` shape. Without this alias they
        # are invisible to the census: generic_visit walks straight through
        # into the ExceptHandler children and every `except* Exception:` is
        # silently uncounted rather than silently failing — the gate would
        # report success over a hole in its own coverage.
        visit_TryStar = visit_Try

    _V().visit(tree)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(SRC_ROOT))
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--expect-broad", type=int, default=None,
                    help="fail unless exactly this many broad handlers are found")
    args = ap.parse_args()

    root = pathlib.Path(args.path)
    if not root.is_dir():
        print(f"ABORT: source root does not exist: {root}", file=sys.stderr)
        return 2
    py_files = sorted(root.rglob("*.py"))
    if not py_files:
        print(f"ABORT: no Python files under {root}", file=sys.stderr)
        return 2

    findings: list = []
    problems: list[str] = []
    broad_total = 0
    examined = 0
    for p in py_files:
        text = p.read_text()
        lines = text.splitlines()
        try:
            tree = ast.parse(text, filename=str(p))
        except SyntaxError as e:
            # Never skip silently — an unparseable file is a hole in coverage.
            problems.append(f"UNPARSEABLE {p}: {e}")
            continue
        examined += 1
        try:
            # REPOSITORY-relative, so ids read `src/ayder_cli/...` exactly as
            # they did before the root was resolved absolutely. The per-directory
            # steps grep on that prefix; changing it would silently break them.
            rel = str(p.resolve().relative_to(REPO))
        except ValueError:
            rel = str(p)
        for node, stable_id in _broad_handlers(rel, tree):
            broad_total += 1
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            if _has_reasoned_marker(line):
                continue
            v = _verdict(node)
            if v != "PASS":
                # The KEY is verdict + stable id, and nothing else. The line
                # number is carried alongside for humans and is never compared.
                findings.append((f"{v} {stable_id}", f"{rel}:{node.lineno}"))

    keys = {k for k, _ in findings}
    where = dict(findings)

    # Coverage summary on EVERY run, before any verdict is printed.
    print(f"files={examined}/{len(py_files)}  broad={broad_total}  "
          f"findings={len(keys)}  root={root}")

    if problems:
        for x in problems:
            print(f"  {x}")
        print(f"FAIL — {len(problems)} unparseable file(s)")
        return 1

    expect = args.expect_broad
    if expect is None and root.resolve() == SRC_ROOT.resolve():
        expect = EXPECTED_BROAD                  # full-tree run: census is frozen
    if expect is not None and broad_total != expect:
        print(f"FAIL — census: found {broad_total} broad handlers, expected {expect}")
        return 1

    if args.write_baseline:
        pathlib.Path(args.baseline).write_text("\n".join(sorted(keys)) + "\n")
        print(f"baseline written: {len(keys)} findings")
        return 0

    for k in sorted(keys):
        print(f"{k}\t# {where[k]}")          # location is display only

    baseline = pathlib.Path(args.baseline)
    if not baseline.exists():
        print(f"\n{len(keys)} findings (no baseline)")
        return 0

    # PER-FINDING comparison on the stable id. A count check would let one
    # finding vanish while a new one appears and still pass.
    allowed = {line.split("\t")[0].strip() for line in baseline.read_text().splitlines()
               if line.strip()}
    new = sorted(keys - allowed)
    if new:
        print(f"\n{len(new)} NEW finding(s) not in baseline:")
        for n in new:
            print(f"  {n}\t# {where[n]}")
        return 1
    fixed = len(allowed) - len(keys & allowed)
    print(f"\n{len(keys)} findings, 0 new, {fixed} fixed since baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
