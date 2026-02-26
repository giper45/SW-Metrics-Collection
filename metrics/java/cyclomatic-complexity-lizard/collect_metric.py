#!/usr/bin/env python3
import json
import os
import re
from collections import defaultdict
from pathlib import Path
import sys

import lizard

_COMMON_DIR = None
for _parent in Path(__file__).resolve().parents:
    _candidate = _parent / "common" / "result_writer.py"
    if _candidate.is_file():
        _COMMON_DIR = _candidate.parent
        break
if _COMMON_DIR and str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from result_writer import generate_run_id, write_jsonl_rows

APP_DIR = "/app"
RESULTS_DIR = "/results"
OUTPUT_FILENAME = "cyclomatic-complexity-package.jsonl"
METRIC_NAME = "cyclomatic_complexity"
AGGREGATION_LEVEL = "package"
DEFAULT_PROJECT = "project"
DEFAULT_COMPONENT = "(default)"
PACKAGE_PATTERN = re.compile(r"^\s*package\s+([A-Za-z_][\w\.]*)\s*;")


def discover_java_files(root_dir):
    java_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            if filename.endswith(".java"):
                java_files.append(os.path.join(dirpath, filename))
    return java_files


def infer_project_name(root_dir):
    env_project = os.environ.get("PROJECT_NAME")
    if env_project:
        return env_project

    try:
        candidates = []
        for name in os.listdir(root_dir):
            full = os.path.join(root_dir, name)
            if os.path.isdir(full) and not name.startswith("."):
                candidates.append(name)
        if len(candidates) == 1:
            return candidates[0]
    except OSError:
        pass

    return DEFAULT_PROJECT


def parse_package_name(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = PACKAGE_PATTERN.match(line)
                if match:
                    return match.group(1)
    except OSError:
        return DEFAULT_COMPONENT
    return DEFAULT_COMPONENT


def get_timestamp():
    override = os.environ.get("METRIC_TIMESTAMP")
    if override:
        return override

    # Deterministic default that can be overridden via METRIC_TIMESTAMP.
    return "1970-01-01T00:00:00Z"


def analyze(java_files):
    package_by_file = {}
    for path in java_files:
        canonical = os.path.realpath(path)
        package_by_file[canonical] = parse_package_name(path)

    package_totals = defaultdict(int)
    for pkg in package_by_file.values():
        package_totals[pkg] += 0

    file_infos = list(lizard.analyze(java_files))
    for file_info in file_infos:
        canonical = os.path.realpath(file_info.filename)
        package = package_by_file.get(canonical, DEFAULT_COMPONENT)
        for func in file_info.function_list:
            package_totals[package] += int(func.cyclomatic_complexity)

    return dict(sorted(package_totals.items(), key=lambda item: item[0]))


def write_output(project, package_totals, results_dir, run_id):
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, OUTPUT_FILENAME)
    timestamp = get_timestamp()
    tool_version = getattr(lizard, "__version__", "unknown")

    rows = []
    for package_name, cc_value in package_totals.items():
        rows.append(
            {
                "project": project,
                "component": package_name,
                "metric": METRIC_NAME,
                "value": cc_value,
                "tool": "lizard",
                "tool_version": tool_version,
                "aggregation_level": AGGREGATION_LEVEL,
                "timestamp": timestamp,
            }
        )

    write_jsonl_rows(
        output_path,
        rows,
        run_id=run_id,
        required_fields={
            "project",
            "component",
            "metric",
            "value",
            "tool",
            "tool_version",
            "aggregation_level",
            "timestamp",
        },
        canonical_order=[
            "schema_version",
            "run_id",
            "project",
            "component",
            "metric",
            "value",
            "tool",
            "tool_version",
            "aggregation_level",
            "timestamp",
        ],
    )


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    run_id = generate_run_id()

    project = infer_project_name(APP_DIR)
    java_files = discover_java_files(APP_DIR)

    if java_files:
        package_totals = analyze(java_files)
    else:
        package_totals = {}

    write_output(project, package_totals, RESULTS_DIR, run_id)


if __name__ == "__main__":
    main()
