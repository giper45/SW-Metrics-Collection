#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import tempfile


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import detect_tool_version, run_collector, run_command_stdout
from utils import metric_output_path, utc_timestamp_now
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_projects,
    is_ignored_dir,
    normalize_path,
    stage_source_tree)

METRIC_NAME = "loc"
VARIANT_NAME = "tokei-default"
TOOL_NAME = "tokei"

def extract_tokei_file_values(node, staging_root_norm, out):
    if isinstance(node, dict):
        name = node.get("name")
        code = node.get("code")
        stats = node.get("stats")
        if isinstance(stats, dict) and isinstance(stats.get("code"), (int, float)):
            code = stats.get("code")
        if isinstance(name, str) and isinstance(code, (int, float)):
            path_norm = normalize_path(name)
            if path_norm.startswith(staging_root_norm + "/"):
                rel = path_norm[len(staging_root_norm) + 1 :]
            else:
                rel = path_norm.lstrip("./")
            out[normalize_path(rel)] = float(code)

        for value in node.values():
            extract_tokei_file_values(value, staging_root_norm, out)
        return

    if isinstance(node, list):
        for value in node:
            extract_tokei_file_values(value, staging_root_norm, out)


def parse_tokei_file_values(raw_output, staging_root):
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return {}

    values = {}
    extract_tokei_file_values(payload, normalize_path(staging_root).rstrip("/"), values)
    return values


def parse_tokei_json(raw_output):
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    total_data = payload.get("Total")
    if isinstance(total_data, dict) and isinstance(total_data.get("code"), (int, float)):
        return int(total_data["code"])
    total = 0
    for name, value in payload.items():
        if name == "Total":
            continue
        if isinstance(value, dict) and isinstance(value.get("code"), (int, float)):
            total += int(value["code"])
    return total


def collect_project_values(project_path):
    staging, rel_files = stage_source_tree(project_path, vendor_dirs=VENDOR_DIRS)
    rel_files = sorted(rel_files)
    try:
        if not rel_files:
            return rel_files, {}
        output = run_command_stdout([TOOL_NAME, "--files", "--output", "json", staging])
        return rel_files, parse_tokei_file_values(output, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect file-level LOC using tokei")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)
    if not projects:
        return 0

    version = detect_tool_version([TOOL_NAME, "--version"])
    os.makedirs(args.results_dir, exist_ok=True)

    for project, project_path in projects:
        rel_files, values = collect_project_values(project_path)
        rows = []

        if not rel_files:
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "project",
                    "component": project,
                    "status": "skipped",
                    "skip_reason": "no_files_after_filtering",
                    "value": None,
                    "tool": TOOL_NAME,
                    "tool_version": version,
                    "parameters": {
                        "category": "size",
                        "count_mode": "code_only",
                        "granularity": "file",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                    },
                    "timestamp_utc": timestamp,
                }
            )
        else:
            for rel in rel_files:
                rows.append(
                    {
                        "project": project,
                        "metric": METRIC_NAME,
                        "variant": VARIANT_NAME,
                        "component_type": "file",
                        "component": rel,
                        "value": float(values.get(rel, 0.0)),
                        "tool": TOOL_NAME,
                        "tool_version": version,
                        "parameters": {
                            "category": "size",
                            "count_mode": "code_only",
                            "granularity": "file",
                            "ignored_dirs": sorted(VENDOR_DIRS),
                        },
                        "timestamp_utc": timestamp,
                    }
                )

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
