#!/usr/bin/env python3
import argparse
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector
from utils import metric_output_path, utc_timestamp_now
from config import GENERIC_SOURCE_EXTENSIONS as SOURCE_EXTENSIONS, TEST_DIR_NAMES, TEST_FILE_MARKERS, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_projects,
    list_source_files,
    normalize_path)

import lizard

METRIC_NAME = "cc"
VARIANT_NAME = "lizard-default"
TOOL_NAME = "lizard"
INCLUDE_TESTS = False


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


def collect_project_rows(project, project_path, tool_version, timestamp):
    source_files = list_source_files(
        project_path,
        vendor_dirs=VENDOR_DIRS,
        include_tests=INCLUDE_TESTS,
        test_dir_names=TEST_DIR_NAMES,
        test_file_markers=TEST_FILE_MARKERS,
        source_extensions=SOURCE_EXTENSIONS)
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
                seen_components=seen_components)
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
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(
        discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS),
        app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = getattr(lizard, "__version__", "unknown")

    for project, project_path in projects:
        rows = collect_project_rows(project, project_path, tool_version, timestamp)

        target = metric_output_path(
            args.results_dir,
            project,
            timestamp,
            METRIC_NAME,
            TOOL_NAME,
            VARIANT_NAME,
        )
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
