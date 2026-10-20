"""
Shared regex matching utilities for file grep tools.

Ported from upstream Open WebUI v0.11.0 `backend/open_webui/tools/knowledge_fs.py`.
Only the matching helpers are included here; the upstream filesystem-style
command interface (ls/cat/find/...) is not part of this fork. The module path and
function signatures are kept identical to upstream so the grep tools in
`builtin.py` can be diffed against it directly.
"""

import contextvars
import logging
import re
import time
from contextlib import contextmanager

import regex

log = logging.getLogger(__name__)

# Matching time allowed per tool call. Backtracking cost is exponential in the length of the
# matched text, so capping the pattern or the line does not bound it.
MATCH_BUDGET_SECONDS = 2.0


class MatchBudgetExceeded(Exception):
    """A tool call spent its whole matching budget, so the caller reports it."""


class MatchBudget:
    """Matching time remaining, counted only inside search() so awaits do not consume it."""

    def __init__(self):
        self.remaining = MATCH_BUDGET_SECONDS


# Scoped to the running task, so one budget covers every matcher a command builds without
# threading it through each handler.
_active_budget: contextvars.ContextVar = contextvars.ContextVar(
    "kb_match_budget", default=None
)


@contextmanager
def match_budget():
    """Bound the matching time of one tool call rather than of each search it runs."""
    token = _active_budget.set(MatchBudget())
    try:
        yield
    finally:
        _active_budget.reset(token)


def is_regex_pattern(pattern: str) -> bool:
    """Detect if a pattern looks like regex (|, .*, .+, \\d, \\w, \\s, [...])."""
    return (
        "|" in pattern
        or ".*" in pattern
        or ".+" in pattern
        or ".?" in pattern
        or "\\d" in pattern
        or "\\w" in pattern
        or "\\s" in pattern
        or bool(re.search(r"\[.+\]", pattern))
    )


def normalize_regex(pattern: str) -> str:
    """Normalize POSIX BRE patterns to Python regex (\\| becomes |)."""
    return pattern.replace("\\|", "|")


def build_matcher(
    pattern: str, case_insensitive: bool = False, use_regex: bool = False
) -> tuple:
    """Build a matcher function. Returns (match_fn, error_str_or_None)."""
    if not use_regex and is_regex_pattern(pattern):
        use_regex = True

    if use_regex:
        normalized = normalize_regex(pattern)
        try:
            re_flags = regex.IGNORECASE if case_insensitive else 0
            compiled = regex.compile(normalized, re_flags)
        except regex.error as e:
            return None, f"Invalid regex: {e}"

        budget = _active_budget.get() or MatchBudget()

        def matches(line: str) -> bool:
            started = time.monotonic()
            try:
                # A negative timeout disables it, so an exhausted budget must not reach search().
                if budget.remaining <= 0:
                    raise TimeoutError
                return bool(compiled.search(line, timeout=budget.remaining))
            except TimeoutError:
                raise MatchBudgetExceeded(
                    f"Search exceeded {MATCH_BUDGET_SECONDS:g}s, narrow the pattern"
                ) from None
            finally:
                budget.remaining -= time.monotonic() - started

        return matches, None
    else:
        sp = pattern.lower() if case_insensitive else pattern
        return (lambda line: sp in (line.lower() if case_insensitive else line)), None
