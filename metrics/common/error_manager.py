#!/usr/bin/env python3
"""Centralized error taxonomy and policy for collectors."""

from __future__ import annotations

import os


ERROR_MODE_FAIL_FAST = "fail-fast"
ERROR_MODE_LEGACY_SKIP = "legacy-skip"
VALID_ERROR_MODES = {ERROR_MODE_FAIL_FAST, ERROR_MODE_LEGACY_SKIP}


class CollectorError(Exception):
    """Base class for controlled collector failures."""


class InputContractError(CollectorError):
    """Invalid or missing input/precondition."""


class ToolExecutionError(CollectorError):
    """External tool execution failure."""


class OutputContractError(CollectorError):
    """Output/data validation or parsing failure."""


class ErrorPolicyViolation(ToolExecutionError):
    """Violation raised when an error fallback is disallowed by policy."""


def error_mode(default=ERROR_MODE_FAIL_FAST):
    raw = str(os.environ.get("METRIC_ERROR_MODE", default)).strip().lower()
    return raw if raw in VALID_ERROR_MODES else default


def is_fail_fast_mode():
    return error_mode() == ERROR_MODE_FAIL_FAST


def _compose_message(skip_reason, context=None):
    reason = str(skip_reason or "unknown_error")
    if not context:
        return reason
    return f"{context}: {reason}"


def error_fallback_or_raise(skip_reason, *, category="tool", context=None):
    """Centralized policy gate for handling error-driven skips.

    In `fail-fast` mode (default), this raises a typed exception and stops the run.
    In `legacy-skip` mode, this returns a `{"status": "skipped", "skip_reason": ...}` dict.
    """
    message = _compose_message(skip_reason, context=context)
    if is_fail_fast_mode():
        if category == "input":
            raise InputContractError(message)
        if category == "output":
            raise OutputContractError(message)
        raise ErrorPolicyViolation(message)
    return {"status": "skipped", "skip_reason": str(skip_reason or "collector_skipped")}

