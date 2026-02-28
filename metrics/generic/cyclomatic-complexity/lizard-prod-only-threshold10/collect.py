#!/usr/bin/env python3
import argparse
import json
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
import sys

_COMMON_DIR = None
for _parent in Path(__file__).resolve().parents:
    _candidate = _parent / "common" / "result_writer.py"
    if _candidate.is_file():
        _COMMON_DIR = _candidate.parent
        break
if _COMMON_DIR and str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector

import lizard

METRIC_NAME = "cyclomatic-complexity"
VARIANT_NAME = "lizard-prod-only-threshold10"
TOOL_NAME = "lizard"
INCLUDE_TESTS = False
THRESHOLD_MIN = 10

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}
TEST_FILE_MARKERS = ("_test.", "test_", "spec.", ".spec.")
SOURCE_EXTENSIONS = {
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".java", ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rb",
    ".rs", ".swift", ".kt", ".kts", ".php", ".m", ".mm", ".cs", ".scala",
}


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_ignored_dir(name):
    return name.startswith(".") or name in VENDOR_DIRS


def is_test_dir(name):
    lowered = name.lower()
    return lowered in TEST_DIR_NAMES or lowered.startswith("test")


def is_test_file(name):
    lowered = name.lower()
    return any(marker in lowered for marker in TEST_FILE_MARKERS)


def discover_projects(app_dir):
    projects = []
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return projects

    for name in entries:
        path = os.path.join(app_dir, name)
        if os.path.isdir(path) and not is_ignored_dir(name):
            projects.append((name, path))
    return projects


def discover_modules(project_name, project_path):
    modules = []
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []

    for name in entries:
        path = os.path.join(project_path, name)
        if os.path.isdir(path) and not is_ignored_dir(name):
            modules.append((name, path))

    if not modules:
        modules.append((project_name, project_path))
    return modules


def list_source_files(module_path, include_tests):
    files = []
    for root, dirnames, filenames in os.walk(module_path):
        filtered_dirs = []
        for dirname in sorted(dirnames):
            if is_ignored_dir(dirname):
                continue
            if not include_tests and is_test_dir(dirname):
                continue
            filtered_dirs.append(dirname)
        dirnames[:] = filtered_dirs

        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            if not include_tests and is_test_file(filename):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext and ext not in SOURCE_EXTENSIONS:
                continue
            files.append(os.path.join(root, filename))

    return files


def compute_module_mean_cc(module_path, include_tests, threshold_min, dry_run):
    source_files = list_source_files(module_path, include_tests)

    if dry_run:
        cmd_preview = [TOOL_NAME] + source_files[:10]
        suffix = " ..." if len(source_files) > 10 else ""
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd_preview) + suffix)
        return 0.0

    if not source_files:
        return 0.0

    complexities = []
    for file_info in lizard.analyze(source_files):
        for function in file_info.function_list:
            cc_value = int(function.cyclomatic_complexity)
            if threshold_min is not None and cc_value < threshold_min:
                continue
            complexities.append(cc_value)

    if not complexities:
        return 0.0

    return round(sum(complexities) / len(complexities), 6)


def write_project_results(results_dir, project, timestamp_utc, rows, run_id):
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(
        results_dir,
        f"{project}-{timestamp_utc}-{METRIC_NAME}-{VARIANT_NAME}.jsonl",
    )
    write_jsonl_rows(output_path, rows, run_id=run_id)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Collect cyclomatic complexity using lizard.")
    parser.add_argument("--app-dir", default="/app", help="Mounted source directory.")
    parser.add_argument("--results-dir", default="/results", help="Output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    timestamp_utc = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)

    if not projects:
        if args.dry_run:
            print("DRY_RUN: no projects discovered under /app")
        return 0

    tool_version = "dry-run" if args.dry_run else getattr(lizard, "__version__", "unknown")

    for project_name, project_path in projects:
        modules = discover_modules(project_name, project_path)
        rows = []

        for module_name, module_path in modules:
            value = compute_module_mean_cc(module_path, INCLUDE_TESTS, THRESHOLD_MIN, args.dry_run)
            rows.append(
                {
                    "project": project_name,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module_name,
                    "value": value,
                    "tool": TOOL_NAME,
                    "tool_version": tool_version,
                    "parameters": {
                        "include_tests": INCLUDE_TESTS,
                        "threshold_min": THRESHOLD_MIN,
                        "ignore_hidden_dirs": True,
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "ignored_test_dirs": sorted(TEST_DIR_NAMES) if not INCLUDE_TESTS else [],
                        "ignored_test_file_markers": list(TEST_FILE_MARKERS) if not INCLUDE_TESTS else [],
                    },
                    "timestamp_utc": timestamp_utc,
                }
            )

        if args.dry_run:
            print(
                "DRY_RUN:",
                f"would write {len(rows)} row(s) to /results/{project_name}-{timestamp_utc}-{METRIC_NAME}-{VARIANT_NAME}.jsonl",
            )
        else:
            write_project_results(args.results_dir, project_name, timestamp_utc, rows, run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
