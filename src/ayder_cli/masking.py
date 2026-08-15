"""Credential masking for rendered log text. Imports only `re`.

Applied by the prose sinks (main file, error file, console) AFTER Loguru has
rendered a record to its final string, which is the only point where every
carrier is visible at once: the message, interpolated arguments, the exception
string and its notes, and the source lines Loguru prints inside a traceback.
Trace JSONL is deliberately NOT masked - it is machine-read structured output,
not prose, and masking it would corrupt the schema.

The rules run in a FIXED order and the order is load-bearing:

    url -> auth -> bearer -> sk -> kv

`url` first so that URL userinfo is already redacted before the broad `kv`
matcher can see a password that happens to sit next to a `token:` username.
`auth` before `bearer` so a header line is rewritten exactly once and ends in
`<redacted:auth>` rather than being rewritten twice. `sk` before `kv` so
`api_key=sk-...` keeps its key and reports the more specific family. The `kv`
value carries a `(?!<redacted:)` lookahead, so no rule can ever consume an
already-masked value - which is what makes the whole pipeline idempotent by
construction.

What is deliberately NOT claimed. These shapes pass through unmasked and are
named here as the residual, not pinned by any test: uppercase `SK-`, Stripe
`sk_live_`, quoted values spanning a newline, prose "bearer <word>" that is not
a credential, unknown URL forms, and arbitrary unknown secrets. Masking known
shapes does not make arbitrary logged text secret; it removes the credential
families this project actually handles.

Newlines are never added or removed: every pattern that scans to end-of-line
uses `[^\\r\\n]` or `[^\\S\\r\\n]`, so a record's line structure survives
masking exactly.
"""
from __future__ import annotations

import re

MASK_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("url", re.compile(
        r"(?i)\b([a-z][a-z0-9+.\-]*://)([^/\s:@]+):([^/\s@]+)@"),
        r"\1\2:<redacted:url>@"),
    ("auth", re.compile(
        r"(?i)(?<![A-Za-z0-9_])(authorization)([^\S\r\n]*[=:][^\S\r\n]*)[^\r\n]+"),
        r"\1\2<redacted:auth>"),
    ("bearer", re.compile(
        r"(?i)(?<![A-Za-z0-9_-])bearer[^\S\r\n]+([\"']?)[A-Za-z0-9._~+/=-]+\1"),
        r"<redacted:bearer>"),
    ("sk", re.compile(
        r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{8,}"),
        r"<redacted:sk>"),
    ("kv", re.compile(
        r"(?i)(api[_-]?key|apikey|token|secret|password|passwd)"
        r"([^\S\r\n]*[=:][^\S\r\n]*)"
        r"((?!<redacted:)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\S+))"),
        r"\1\2<redacted:kv>"),
]


def mask(text: str) -> str:
    """Redact known credential shapes in already-rendered text.

    Pure and total: no I/O, no logging call (a logging call here would recurse
    through the very sink that is masking), and every pattern is single
    quantifier / linear, so hostile input cannot make it backtrack.
    """
    for _name, pattern, repl in MASK_RULES:
        text = pattern.sub(repl, text)
    return text
