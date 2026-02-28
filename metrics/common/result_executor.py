#!/usr/bin/env python3
"""Collector runtime execution helpers (error -> exit-code mapping)."""

import sys

EXIT_INPUT_ERROR = 2
EXIT_TOOL_ERROR = 3
EXIT_OUTPUT_ERROR = 4


class InputContractError(Exception):
    pass


class ToolExecutionError(Exception):
    pass


class OutputContractError(Exception):
    pass


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
        print(f"TOOL_ERROR: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except ValueError as exc:
        print(f"OUTPUT_ERROR: {exc}", file=sys.stderr)
        return EXIT_OUTPUT_ERROR


def run_collector(main_fn):
    """Backward-compatible alias for :func:`execute_collector`."""
    return execute_collector(main_fn)

