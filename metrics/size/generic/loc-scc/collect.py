#!/usr/bin/env python3
import argparse
import json
import os
import shutil


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import detect_tool_version, run_collector, run_command_stdout
from error_manager import OutputContractError
from loc_file_rows import build_file_loc_rows, stage_project_files
from utils import metric_output_path, utc_timestamp_now
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_projects,
    normalize_path)

METRIC_NAME = "loc"
VARIANT_NAME = "scc-default"
TOOL_NAME = "scc"

def parse_scc_file_values(payload, staging_root):
    if not isinstance(payload, (list, dict)):
        raise OutputContractError("scc output JSON root must be an array or object")

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


def collect_project_values(project_path):
    staging, rel_files = stage_project_files(project_path)
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
            raise OutputContractError(f"scc report not found: {report_path}")
        try:
            with open(report_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise OutputContractError(f"scc report is not valid JSON: {report_path}") from exc
        return rel_files, parse_scc_file_values(payload, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect file-level LOC using scc")
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
        rel_files, values = collect_project_values(project_path)
        rows = build_file_loc_rows(
            project=project,
            metric=METRIC_NAME,
            variant=VARIANT_NAME,
            tool=TOOL_NAME,
            tool_version=version,
            timestamp_utc=timestamp,
            rel_files=rel_files,
            values=values,
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
