#!/usr/bin/env python3
import argparse
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

METRIC_NAME = "cc"
VARIANT_NAME = "lizard-default"
TOOL_NAME = "lizard"
INCLUDE_TESTS = False

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


def normalize_path(path):
    return path.replace("\\", "/")


def is_ignored_dir(name):
    return name.startswith(".") or name in VENDOR_DIRS


def is_test_dir(name):
    lowered = name.lower()
    return lowered in TEST_DIR_NAMES or lowered.startswith("test")


def is_test_file(name):
    lowered = name.lower()
    return any(marker in lowered for marker in TEST_FILE_MARKERS)


def discover_projects(app_dir):
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return []
    return [
        (name, os.path.join(app_dir, name))
        for name in entries
        if os.path.isdir(os.path.join(app_dir, name)) and not is_ignored_dir(name)
    ]


def list_source_files(project_path):
    files = []
    for root, dirnames, filenames in os.walk(project_path):
        allowed = []
        for dirname in sorted(dirnames):
            if is_ignored_dir(dirname):
                continue
            if not INCLUDE_TESTS and is_test_dir(dirname):
                continue
            allowed.append(dirname)
        dirnames[:] = allowed

        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            if not INCLUDE_TESTS and is_test_file(filename):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext and ext not in SOURCE_EXTENSIONS:
                continue
            files.append(os.path.join(root, filename))
    return files


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def build_method_component(file_path, project_path, function_name, start_line):
    rel = normalize_path(os.path.relpath(file_path, project_path))
    return f"{rel}::{function_name}@L{int(start_line)}"


def build_unique_method_component(file_path, project_path, function_name, start_line, seen_components):
    base_component = build_method_component(file_path, project_path, function_name, start_line)
    occurrence = int(seen_components.get(base_component, 0)) + 1
    seen_components[base_component] = occurrence
    if occurrence == 1:
        return base_component, occurrence
    return f"{base_component}#dup{occurrence}", occurrence


def collect_project_rows(project, project_path, tool_version, timestamp, dry_run):
    source_files = list_source_files(project_path)
    if dry_run:
        preview = [TOOL_NAME] + source_files[:8]
        suffix = " ..." if len(source_files) > 8 else ""
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in preview) + suffix)

    if not source_files:
        return [
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_source_files",
                "value": None,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "granularity": "method",
                    "include_tests": INCLUDE_TESTS,
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        ]

    if dry_run:
        return []

    rows = []
    seen_components = {}
    for file_info in lizard.analyze(source_files):
        file_path = normalize_path(file_info.filename)
        for fn in file_info.function_list:
            component, occurrence = build_unique_method_component(
                file_path=file_path,
                project_path=project_path,
                function_name=fn.name,
                start_line=fn.start_line,
                seen_components=seen_components,
            )
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "method",
                    "component": component,
                    "value": float(fn.cyclomatic_complexity),
                    "tool": TOOL_NAME,
                    "tool_version": tool_version,
                    "parameters": {
                        "category": "complexity",
                        "granularity": "method",
                        "method_name": str(fn.name),
                        "start_line": int(fn.start_line),
                        "end_line": int(fn.end_line),
                        "component_collision_index": occurrence,
                        "nloc": int(getattr(fn, "length", 0)),
                        "include_tests": INCLUDE_TESTS,
                        "ignored_dirs": sorted(VENDOR_DIRS),
                    },
                    "timestamp_utc": timestamp,
                }
            )

    if rows:
        return rows

    return [
        {
            "project": project,
            "metric": METRIC_NAME,
            "variant": VARIANT_NAME,
            "component_type": "project",
            "component": project,
            "status": "skipped",
            "skip_reason": "no_methods_detected",
            "value": None,
            "tool": TOOL_NAME,
            "tool_version": tool_version,
            "parameters": {
                "category": "complexity",
                "granularity": "method",
                "include_tests": INCLUDE_TESTS,
                "ignored_dirs": sorted(VENDOR_DIRS),
            },
            "timestamp_utc": timestamp,
        }
    ]


def main():
    parser = argparse.ArgumentParser(description="Collect method-level CC with lizard")
    parser.add_argument("--app-dir", default=os.environ.get("SRC_ROOT", os.environ.get("METRIC_APP_DIR", "/app")))
    parser.add_argument("--results-dir", default=os.environ.get("RESULTS_DIR", os.environ.get("METRIC_RESULTS_DIR", "/results")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)
    if not projects:
        if args.dry_run:
            print("DRY_RUN: no projects discovered")
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = "dry-run" if args.dry_run else getattr(lizard, "__version__", "unknown")

    for project, project_path in projects:
        rows = collect_project_rows(project, project_path, tool_version, timestamp, args.dry_run)

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
