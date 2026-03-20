#!/usr/bin/env python3
"""Shared collector configuration (overridable via environment)."""

import os


def _split_csv(raw):
    values = []
    for item in str(raw or "").split(","):
        value = str(item).strip()
        if value:
            values.append(value)
    return values


def _env_set(name, default_values):
    raw = os.environ.get(name)
    if raw is None:
        return set(default_values)
    return set(_split_csv(raw))


def _env_tuple(name, default_values):
    raw = os.environ.get(name)
    if raw is None:
        return tuple(default_values)
    return tuple(_split_csv(raw))


def _normalize_extensions(values):
    out = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if not text.startswith("."):
            text = "." + text
        out.add(text)
    return out


VENDOR_DIRS = _env_set(
    "METRIC_VENDOR_DIRS",
    {"node_modules", "target", "build", ".venv", "venv", ".git"},
)

TEST_DIR_NAMES = _env_set(
    "METRIC_TEST_DIR_NAMES",
    {"test", "tests", "__tests__", "spec", "specs", "testing"},
)

TEST_FILE_MARKERS = _env_tuple(
    "METRIC_TEST_FILE_MARKERS",
    ("_test.", "test_", "spec.", ".spec."),
)

JAVA_BYTECODE_DIR_CANDIDATES = _env_tuple(
    "METRIC_JAVA_BYTECODE_DIRS",
    (
        "target/classes",
        "build/classes/java/main",
        "build/classes/kotlin/main",
        "build/classes",
        "build/WEB-INF/classes",
        "out/production",
    ),
)

GENERIC_SOURCE_EXTENSIONS = _normalize_extensions(
    _env_set(
        "METRIC_SOURCE_EXTENSIONS",
        {
            ".c",
            ".h",
            ".cc",
            ".cpp",
            ".cxx",
            ".hpp",
            ".hh",
            ".java",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".py",
            ".go",
            ".rb",
            ".rs",
            ".swift",
            ".kt",
            ".kts",
            ".php",
            ".m",
            ".mm",
            ".cs",
            ".scala",
        },
    )
)
