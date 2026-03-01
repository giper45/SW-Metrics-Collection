#!/usr/bin/env python3
"""Centralized error taxonomy and policy for collectors."""

from __future__ import annotations

import os


ERROR_MODE_FAIL_FAST = "fail-fast"
ERROR_MODE_LEGACY_SKIP = "legacy-skip"
VALID_ERROR_MODES = {ERROR_MODE_FAIL_FAST}


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
    if raw != ERROR_MODE_FAIL_FAST:
        return ERROR_MODE_FAIL_FAST
    return ERROR_MODE_FAIL_FAST


def is_fail_fast_mode():
    return error_mode() == ERROR_MODE_FAIL_FAST


def _compose_message(skip_reason, context=None):
    reason = str(skip_reason or "unknown_error")
    if not context:
        return reason
    return f"{context}: {reason}"


def error_fallback_or_raise(skip_reason, *, category="tool", context=None):
    """Raise typed errors for collector failures."""
    message = _compose_message(skip_reason, context=context)
    if category == "input":
        raise InputContractError(message)
    if category == "output":
        raise OutputContractError(message)
    raise ErrorPolicyViolation(message)
