#!/usr/bin/env python
"""Logging-migration gates.

One implementation, invoked per batch by the Phase 2 `-M` steps. Every gate
exits nonzero on a defect and prints how many files and calls it examined, so
a silent pass cannot be mistaken for coverage.

Call-site identity is `module-path :: qualname :: message-prefix [:: ordinal]`.
The prefix is the literal text *before the first placeholder*, which is the
part a mechanical conversion leaves untouched:

    f"Stream completed: {n} chunks total"  ->  "Stream completed: {} chunks total"
    "agent done: run #%d agent='%s'"       ->  "agent done: run #{} agent='{}'"

Line numbers are display hints only. Nothing is gated on them.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import string
import sys

# Resolved from this file, not the cwd — pytest and a shell invoked from a
# subdirectory must both see the same tree.
SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "ayder_cli"
LEVELS = {"trace", "debug", "info", "success", "warning", "error", "exception", "critical"}
LOGGER_NAMES = {"logger", "llm_log", "tool_log"}
PCT = re.compile(r"%(?:\([^)]*\))?[-#0 +]*[\d.*]*[hlL]?[scdrfgeixXou]")

BATCHES: dict[str, list[str]] = {
    "providers": [
        "providers/retry.py",
        "providers/impl/openai.py",
        "providers/impl/ollama.py",
        "providers/impl/claude.py",
        "providers/impl/gemini.py",
        "providers/impl/qwen.py",
        "providers/impl/ollama_drivers/registry.py",
        "providers/impl/ollama_drivers/generic_xml.py",
    ],
    "loops-core": [
        "loops/chat_loop.py",
        "core/ollama_context_manager.py",
        "core/default_context_manager.py",
        "core/config.py",
        "core/cache_monitor.py",
    ],
    "tools-root": [
        "tools/plugin_manager.py", "tools/utils.py", "tools/definition.py",
        "tools/hooks.py", "tools/builtins/context.py", "tools/registry.py",
        "tools/plugin_github.py", "tools/execution.py", "tools/builtins/notes.py",
        "tools/builtins/search.py", "cli_runner.py", "prompts.py",
        "tools/builtins/filesystem.py", "tools/builtins/utils_tools.py",
    ],
    "agents-tui": [
        "agents/registry.py", "agents/runner.py", "agents/callbacks.py",
        "agents/worktree.py", "agents/tool.py", "tui/app.py",
    ],
}


class _Collector(ast.NodeVisitor):
    """Every logger call in one module, with its enclosing qualname."""

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.calls: list[dict] = []
        self.foreign: list[tuple[int, str]] = []   # logger-ish names we do not know

    def _push(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _push
    visit_AsyncFunctionDef = _push
    visit_ClassDef = _push

    def visit_Call(self, node):
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and f.attr in LEVELS
            and isinstance(f.value, ast.Name)
            and f.value.id in LOGGER_NAMES
        ):
            self.calls.append(
                {
                    "line": node.lineno,
                    "level": f.attr,
                    "binding": f.value.id,
                    "qualname": ".".join(self.scope) or "<module>",
                    "fmt": _format_text(node),
                    "canon": _canonical(node),
                    "nargs": len(node.args) - 1,
                    "kwnames": {k.arg for k in node.keywords if k.arg},
                    "node": node,
                }
            )
        elif (
            isinstance(f, ast.Attribute)
            and f.attr in LEVELS
            and isinstance(f.value, ast.Name)
            and "log" in f.value.id.lower()
        ):
            # A logger-looking name we do not recognise. Collecting nothing for
            # it would hide the call from every gate.
            self.foreign.append((node.lineno, f.value.id))
        self.generic_visit(node)


def _format_text(node: ast.Call) -> str | None:
    """The message as written: literal for str, brace-collapsed for f-strings."""
    if not node.args:
        return None
    a = node.args[0]
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return a.value
    if isinstance(a, ast.JoinedStr):
        out = []
        for v in a.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
            else:
                out.append("{}")
        return "".join(out)
    return None


_BRACE = re.compile(r"\{[^{}]*\}")


def _canonical(node: ast.Call) -> str | None:
    """The message with every placeholder collapsed to `{}`.

    This form is *invariant across the mechanical conversion*, which is what
    makes it usable as an identity:

        "Context[%s]: %d/%d (%.0f%%)"   -> "Context[{}]: {}/{} ({}%)"
        "Context[{}]: {}/{} ({:.0f}%)"  -> "Context[{}]: {}/{} ({}%)"

    The `%ds` trap resolves correctly: `%d` collapses and the literal `s`
    survives, exactly as it does in the converted `{}s`.
    """
    if not node.args:
        return None
    a = node.args[0]
    if isinstance(a, ast.JoinedStr):
        parts = []
        for v in a.values:
            parts.append(_collapse(str(v.value)) if isinstance(v, ast.Constant) else "{}")
        return "".join(parts)
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return _collapse(a.value)
    return None


def _collapse(text: str) -> str:
    text = _BRACE.sub("{}", text)
    text = PCT.sub("{}", text)
    return text.replace("%%", "%")


def collect(rels: list[str], problems: list[str] | None = None) -> list[dict]:
    """Log calls across `rels`.

    A missing or unparseable file appends to `problems` — it is a finding, not a
    note on stderr. Silently skipping one let a deleted file still reach PASS.
    """
    out = []
    for rel in rels:
        p = SRC / rel
        if not p.exists():
            if problems is not None:
                problems.append(f"MISSING-FILE {rel}")
            continue
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError as e:
            if problems is not None:
                problems.append(f"UNPARSEABLE {rel}: {e}")
            continue
        c = _Collector()
        c.visit(tree)
        for call in c.calls:
            call["module"] = rel
            out.append(call)
        if problems is not None:
            problems.extend(f"UNKNOWN-LOGGER {rel} line {ln}: {name!r}"
                            for ln, name in c.foreign)
    return out


# ---------------------------------------------------------------- resolver


def resolve(identity: str, calls: list[dict]) -> dict:
    """`module :: qualname :: prefix [:: ordinal]` -> exactly one call.

    Raises on zero or multiple matches. Never gates on a line number.
    """
    parts = [p.strip() for p in identity.split("::")]
    if len(parts) == 4:
        module, qualname, prefix, ordinal_s = parts
        ordinal = int(ordinal_s)
    elif len(parts) == 3:
        module, qualname, prefix = parts
        ordinal = None
    else:
        raise ValueError(f"malformed identity (need 3 or 4 ::-parts): {identity!r}")

    hits = [
        c
        for c in calls
        if c["module"] == module
        and c["qualname"] == qualname
        and c["canon"] is not None
        and c["canon"].strip().startswith(prefix.strip())
    ]
    hits.sort(key=lambda c: c["line"])

    if not hits:
        raise LookupError(f"UNRESOLVED (0 matches): {identity}")
    if ordinal is not None:
        if not 1 <= ordinal <= len(hits):
            raise LookupError(
                f"ORDINAL {ordinal} out of range 1..{len(hits)}: {identity}"
            )
        return hits[ordinal - 1]
    if len(hits) > 1:
        raise LookupError(
            f"AMBIGUOUS ({len(hits)} matches, add an ordinal): {identity}\n"
            + "\n".join(f"    #{i+1} line {h['line']}" for i, h in enumerate(hits))
        )
    return hits[0]


# ------------------------------------------------------------------- gates


def gate_percent(calls: list[dict]) -> list[str]:
    """No %-style interpolation may reach loguru."""
    bad = []
    for c in calls:
        if c["nargs"] >= 1 and c["fmt"] and PCT.search(c["fmt"]):
            bad.append(f"PERCENT-STYLE {c['module']} line {c['line']}: {c['fmt'][:60]!r}")
    return bad


def gate_placeholders(calls: list[dict]) -> list[str]:
    """Placeholder count must equal argument count.

    Uses string.Formatter so `{:.0f}`, `{!r}`, and `{}` all count, and a
    literal `{{` does not.
    """
    bad = []
    for c in calls:
        if c["fmt"] is None or (c["nargs"] < 1 and not c["kwnames"]):
            continue
        try:
            fields = [
                field
                for _lit, field, _spec, _conv in string.Formatter().parse(c["fmt"])
                if field is not None
            ]
        except ValueError as e:
            bad.append(f"UNPARSEABLE {c['module']} line {c['line']}: {e}")
            continue
        positional = sum(1 for f in fields if f == "" or f.isdigit())
        named = {f for f in fields if f and not f.isdigit()}
        if positional != c["nargs"] or named != c["kwnames"]:
            bad.append(
                f"ARITY {c['module']} line {c['line']}: "
                f"{positional} slot(s)/{sorted(named)} vs {c['nargs']} arg(s)/"
                f"{sorted(c['kwnames'])} — {c['fmt'][:60]!r}"
            )
    return bad


def gate_fstrings(calls: list[dict]) -> list[str]:
    """No logging f-string may survive (what ruff G004 will enforce repo-wide).

    Works off the already-parsed collector output. Re-parsing here would raise
    SyntaxError on a file whose parse failure `collect()` has *already* recorded
    as UNPARSEABLE — killing the run with a traceback before a single finding or
    the batch summary printed.
    """
    return [
        f"F-STRING {c['module']} line {c['line']}"
        for c in calls
        if c["node"].args and isinstance(c["node"].args[0], ast.JoinedStr)
    ]


def gate_binding(rels: list[str], expected: dict[str, str]) -> list[str]:
    """Each module binds the channel §C8 assigns it, via the facade."""
    bad = []
    for rel in rels:
        p = SRC / rel
        if not p.exists():
            continue
        text = p.read_text()
        if "logging.getLogger" in text:
            bad.append(f"STDLIB-LOGGER {rel}")
        if re.search(r"^from loguru import", text, re.M):
            bad.append(f"DIRECT-LOGURU {rel}")
        if rel in NO_LOGGER:
            # Binding deliberately deleted — Phase 3 adds one back on purpose.
            if "get_logger" in text or re.search(r"^import logging$", text, re.M):
                bad.append(f"DEAD-BINDING-NOT-REMOVED {rel}")
            continue
        want = expected.get(rel)
        if want is None:
            continue
        found = set(re.findall(r'get_logger\(\s*"([a-z]+)"\s*\)', text))
        if not found:
            bad.append(f"NO-BINDING {rel} (expected {want})")
        elif found != set(want.split("|")):
            bad.append(f"CHANNEL {rel}: bound {sorted(found)}, expected {want}")
    return bad


CHANNELS: dict[str, str] = {
    "providers/retry.py": "llm",
    "providers/impl/openai.py": "llm",
    "providers/impl/ollama.py": "llm",
    "providers/impl/claude.py": "llm",
    "providers/impl/gemini.py": "llm",
    "providers/impl/qwen.py": "llm",
    "providers/impl/ollama_drivers/registry.py": "llm",
    "providers/impl/ollama_drivers/generic_xml.py": "llm",
    "loops/chat_loop.py": "llm|tool",
    "core/ollama_context_manager.py": "context",
    "core/default_context_manager.py": "context",
    "core/cache_monitor.py": "context",
    "core/config.py": "core",
    "tools/plugin_manager.py": "plugin",
    "tools/plugin_github.py": "plugin",
    "tools/definition.py": "plugin",
    "tools/utils.py": "tool",
    "tools/hooks.py": "tool",
    "tools/registry.py": "tool",
    "tools/execution.py": "tool",
    "tools/builtins/notes.py": "tool",
    "tools/builtins/search.py": "tool",
    "tools/builtins/context.py": "context",
    "cli_runner.py": "core",
    "prompts.py": "core",
    "agents/registry.py": "agent",
    "agents/runner.py": "agent",
    "agents/callbacks.py": "agent",
    "agents/worktree.py": "agent",
    "tui/app.py": "ui",
}

# Modules whose logger binding is deliberately deleted, not converted.
NO_LOGGER = {
    "tools/builtins/filesystem.py",
    "tools/builtins/utils_tools.py",
    "agents/tool.py",
}

# Frozen census. A batch that opens fewer files, or holds a different number of
# log calls, has lost or gained a record — which every `-M` step forbids.
CENSUS: dict[str, tuple[int, int]] = {      # batch -> (files, calls)
    "providers": (8, 35),
    "loops-core": (5, 38),
    "tools-root": (14, 33),
    "agents-tui": (6, 23),
}

# chat_loop.py holds two loggers (§C8). Every one of its 21 calls is pinned to
# one of them by identity, so a misroute cannot hide behind "both are declared".
CHAT_LOOP_ROUTING: dict[str, str] = {
    "Calling LLM with history:": "llm_log",
    "Message {} [{}]:": "llm_log",
    "LLM stream cancelled": "llm_log",
    "LLM stream failed": "llm_log",
    "LLM returned empty response": "llm_log",
    "LLM Response Content Length:": "llm_log",
    "LLM Reasoning Length:": "llm_log",
    "LLM Tool Calls:": "llm_log",
    "Model thought but provided no content": "llm_log",
    "Malformed tool arguments for": "llm_log",
    "Tool '{}' called with missing args": "tool_log",
    "Tool execution cancelled:": "tool_log",
    "Tool execution failed for": "tool_log",
    "Appending Tool Result": "tool_log",
    "Appending Tool Error": "tool_log",
    "Tool arguments JSON parse failed:": "tool_log",
    "Recovered tool arguments via raw_decode": "tool_log",
    "Recovered tool arguments via truncated JSON repair": "tool_log",
    "Could not recover tool arguments": "tool_log",
    "Concatenated tool call JSON parse stopped": "tool_log",
    "Expanding concatenated tool call": "tool_log",
}


def gate_census(batch: str, rels: list[str], calls: list[dict]) -> list[str]:
    """Files opened and calls found must match the frozen census."""
    want_files, want_calls = CENSUS[batch]
    opened = sum(1 for r in rels if (SRC / r).exists())
    bad = []
    if opened != want_files:
        bad.append(f"CENSUS-FILES {batch}: opened {opened}, expected {want_files}")
    if len(calls) != want_calls:
        bad.append(
            f"CENSUS-CALLS {batch}: found {len(calls)}, expected {want_calls} "
            f"— a `-M` step may not add or remove a log record"
        )
    return bad


def gate_routing(calls: list[dict]) -> list[str]:
    """Every chat_loop.py call is pinned to llm_log or tool_log by identity."""
    mine = [c for c in calls if c["module"] == "loops/chat_loop.py"]
    if not mine:
        return []
    bad = []
    seen = set()
    for c in mine:
        canon = (c["canon"] or "").strip()
        match = next((k for k in CHAT_LOOP_ROUTING if canon.startswith(k)), None)
        if match is None:
            bad.append(f"UNROUTED loops/chat_loop.py line {c['line']}: {canon[:50]!r}")
            continue
        seen.add(match)
        want = CHAT_LOOP_ROUTING[match]
        if c["binding"] != want:
            bad.append(
                f"MISROUTED loops/chat_loop.py line {c['line']}: "
                f"{canon[:44]!r} uses {c['binding']}, expected {want}"
            )
    missing = set(CHAT_LOOP_ROUTING) - seen
    for m in sorted(missing):
        bad.append(f"ROUTE-MISSING loops/chat_loop.py: no call matches {m!r}")
    return bad


def do_resolve(identity: str) -> int:
    calls = collect(sorted({*CHANNELS, *NO_LOGGER}))
    try:
        hit = resolve(identity, calls)
    except (LookupError, ValueError) as e:
        print(f"FAIL {e}")
        return 1
    print(
        f"OK  {hit['module']} :: {hit['qualname']}\n"
        f"    level={hit['level'].upper()}  binding={hit['binding']}  "
        f"args={hit['nargs']}\n"
        f"    line={hit['line']}   (display hint only — not gated)\n"
        f"    canonical={hit['canon']!r}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolve", metavar="IDENTITY",
                    help="resolve one C14 identity and print its current line")
    ap.add_argument("--batch", choices=sorted(BATCHES))
    ap.add_argument("--skip", default="", help="comma-separated gate names to skip")
    args = ap.parse_args()

    if args.resolve:
        return do_resolve(args.resolve)
    if not args.batch:
        ap.error("one of --batch or --resolve is required")

    rels = BATCHES[args.batch]
    problems: list[str] = []
    calls = collect(rels, problems)
    expected = {r: CHANNELS[r] for r in rels if r in CHANNELS}
    skip = {s for s in args.skip.split(",") if s}

    findings: list[str] = list(problems)
    ran = []
    for name, fn in (
        ("census", lambda: gate_census(args.batch, rels, calls)),
        ("percent", lambda: gate_percent(calls)),
        ("placeholders", lambda: gate_placeholders(calls)),
        ("fstrings", lambda: gate_fstrings(calls)),
        ("binding", lambda: gate_binding(rels, expected)),
        ("routing", lambda: gate_routing(calls)),
    ):
        if name in skip:
            continue
        ran.append(name)
        findings += fn()

    opened = sum(1 for r in rels if (SRC / r).exists())
    want_files, want_calls = CENSUS[args.batch]
    print(
        f"batch={args.batch}  files={opened}/{want_files}  "
        f"calls={len(calls)}/{want_calls}  gates={','.join(ran)}"
    )
    if findings:
        for f in findings:
            print(f"  {f}")
        print(f"FAIL — {len(findings)} defect(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
