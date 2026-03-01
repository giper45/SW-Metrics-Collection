#!/usr/bin/env python3
"""Collector runtime execution helpers (error -> exit-code mapping)."""

import re
import subprocess
import sys

from error_manager import InputContractError, OutputContractError, ToolExecutionError

EXIT_INPUT_ERROR = 2
EXIT_TOOL_ERROR = 3
EXIT_OUTPUT_ERROR = 4

def _render_command(cmd):
    if isinstance(cmd, (list, tuple)):
        return " ".join(str(part) for part in cmd)
    return str(cmd)


def run_command_details(
    cmd,
    *,
    cwd=None,
    stdin_text=None,
    allowed_returncodes=None,
    timeout_sec=None,
):
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            input=None if stdin_text is None else str(stdin_text),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(
            f"command timed out after {timeout_sec}s: {_render_command(cmd)}"
        ) from exc
    allowed = set(allowed_returncodes or {0})
    if completed.returncode not in allowed:
        raise ToolExecutionError(
            f"command failed ({completed.returncode}): {_render_command(cmd)}\n"
            f"stdout: {completed.stdout}\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout or "", completed.stderr or "", int(completed.returncode)


def run_command_stdout(
    cmd,
    *,
    cwd=None,
    stdin_text=None,
    allowed_returncodes=None,
    timeout_sec=None,
):
    stdout, _, _ = run_command_details(
        cmd,
        cwd=cwd,
        stdin_text=stdin_text,
        allowed_returncodes=allowed_returncodes,
        timeout_sec=timeout_sec,
    )
    return stdout


def detect_tool_version(command, *, pattern=r"(\d+(?:\.\d+)+)", fallback="unknown"):
    output = run_command_stdout(command).strip()
    if not output:
        return str(fallback)
    match = re.search(pattern, output)
    if not match:
        return output or str(fallback)
    return match.group(1)


def execute_collector(main_fn):
    """Execute a collector main function with standardized exit-code mapping."""
    try:
        code = main_fn()
        if isinstance(code, int):
            return int(code)
        return 0
    except InputContractError as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except ToolExecutionError as exc:
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except OutputContractError as exc:
        print(f"OUTPUT_ERROR: {exc}", file=sys.stderr)
        return EXIT_OUTPUT_ERROR
    except FileNotFoundError as exc:
        print(f"INPUT_ERROR: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except RuntimeError as exc:
        # Compatibility path for legacy collectors still raising RuntimeError.
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except ValueError as exc:
        print(f"OUTPUT_ERROR: {exc}", file=sys.stderr)
        return EXIT_OUTPUT_ERROR


def run_collector(main_fn):
    """Backward-compatible alias for :func:`execute_collector`."""
    return execute_collector(main_fn)
