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
VARIANT_NAME = "scc-default"
TOOL_NAME = "scc"

def parse_scc_file_values(payload, staging_root):
    values = {}
    staging_norm = normalize_path(staging_root).rstrip("/")

    def consume_file_row(row):
        if not isinstance(row, dict):
            return
        name = row.get("Location") or row.get("location") or row.get("Name") or row.get("name")
        code = row.get("Code") if "Code" in row else row.get("code")
        if not isinstance(name, str) or not isinstance(code, (int, float)):
            return
        if name.strip().lower() == "total":
            return
        path_norm = normalize_path(name)
        if path_norm.startswith(staging_norm + "/"):
            rel = path_norm[len(staging_norm) + 1 :]
        else:
            rel = path_norm.lstrip("./")
        values[normalize_path(rel)] = float(code)

    if isinstance(payload, list):
        for language_row in payload:
            if not isinstance(language_row, dict):
                continue
            files = language_row.get("Files") or language_row.get("files")
            if isinstance(files, list):
                for file_row in files:
                    consume_file_row(file_row)
            else:
                consume_file_row(language_row)
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for row in value:
                    consume_file_row(row)
            elif isinstance(value, dict):
                files = value.get("Files") or value.get("files")
                if isinstance(files, list):
                    for file_row in files:
                        consume_file_row(file_row)
                else:
                    consume_file_row(value)

    return values


def parse_scc_json(payload):
    if isinstance(payload, dict):
        totals = payload.get("totals")
        if isinstance(totals, dict) and isinstance(totals.get("Code"), (int, float)):
            return int(totals["Code"])
        if isinstance(payload.get("Code"), (int, float)):
            return int(payload["Code"])
        return 0

    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and str(row.get("Name", "")).lower() == "total":
                if isinstance(row.get("Code"), (int, float)):
                    return int(row["Code"])
        return sum(int(row["Code"]) for row in payload if isinstance(row, dict) and isinstance(row.get("Code"), (int, float)))

    return 0


def collect_project_values(project_path):
    staging, rel_files = stage_source_tree(project_path, vendor_dirs=VENDOR_DIRS)
    rel_files = sorted(rel_files)
    report_path = os.path.join(staging, "scc-report.json")
    try:
        if not rel_files:
            return rel_files, {}
        run_command_stdout(
            [
                TOOL_NAME,
                "--by-file",
                "--format",
                "json",
                "--output",
                report_path,
                "--no-cocomo",
                "--no-complexity",
                staging,
            ])
        if not os.path.isfile(report_path):
            return rel_files, {}
        with open(report_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return rel_files, parse_scc_file_values(payload, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect file-level LOC using scc")
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
