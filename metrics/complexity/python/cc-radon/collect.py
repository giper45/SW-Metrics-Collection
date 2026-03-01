#!/usr/bin/env python3
import argparse
import json
import os


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import detect_tool_version, run_collector, run_command_stdout
from error_manager import OutputContractError
from utils import metric_output_path, utc_timestamp_now
from config import TEST_DIR_NAMES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_projects,
    list_source_files,
    normalize_path)

METRIC_NAME = "cc"
VARIANT_NAME = "radon-default"
TOOL_NAME = "radon"


def list_python_files(project_path):
    return list_source_files(
        project_path,
        vendor_dirs=VENDOR_DIRS,
        include_tests=False,
        test_dir_names=TEST_DIR_NAMES,
        test_file_markers=(),
        source_extensions={".py"})


def parse_radon_nodes(raw_output):
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise OutputContractError("radon output is not valid JSON") from exc

    rows = []
    if not isinstance(payload, dict):
        raise OutputContractError("radon output JSON root must be an object")

    for path, nodes in sorted(payload.items()):
        if not isinstance(path, str) or not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            cc_value = node.get("complexity")
            if not isinstance(cc_value, (int, float)):
                continue
            rows.append(
                {
                    "path": normalize_path(path),
                    "name": str(node.get("name", "<anonymous>")),
                    "lineno": int(node.get("lineno", 0) or 0),
                    "endline": int(node.get("endline", 0) or 0),
                    "type": str(node.get("type", "function")),
                    "value": float(cc_value),
                }
            )
    return rows


def build_method_component(project_path, file_path, name, lineno):
    rel = normalize_path(os.path.relpath(file_path, project_path))
    return f"{rel}::{name}@L{int(lineno)}"


def collect_project_rows(project, project_path, tool_version, timestamp):
    python_files = list_python_files(project_path)
    if not python_files:
        return [
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_python_sources",
                "value": None,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        ]

    cmd = [TOOL_NAME, "cc", "-j", "-s"] + python_files
    output = run_command_stdout(cmd)
    parsed = parse_radon_nodes(output)
    if not parsed:
        return [
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_python_methods_detected",
                "value": None,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        ]

    rows = []
    for item in parsed:
        component = build_method_component(project_path, item["path"], item["name"], item["lineno"])
        rows.append(
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "method",
                "component": component,
                "value": item["value"],
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "method_name": item["name"],
                    "method_type": item["type"],
                    "start_line": item["lineno"],
                    "end_line": item["endline"],
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Collect method-level Python CC with radon")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    version = detect_tool_version([TOOL_NAME, "--version"])
    os.makedirs(args.results_dir, exist_ok=True)

    for project, project_path in projects:
        rows = collect_project_rows(project, project_path, version, timestamp)

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
