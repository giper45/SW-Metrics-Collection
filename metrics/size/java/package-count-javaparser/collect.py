#!/usr/bin/env python3
import argparse
import os

from config import VENDOR_DIRS
from input_manager import add_common_cli_args, discover_projects
from java_inventory import collect_java_inventory
from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector
from utils import metric_output_path, utc_timestamp_now

METRIC_NAME = "package-count"
VARIANT_NAME = "javaparser-default"
TOOL_NAME = "javaparser"


def build_project_row(project, inventory, rel_files, tool_version, timestamp_utc):
    parameters = {
        "category": "size",
        "language": "java",
        "granularity": "project",
        "source_files_scanned": int(inventory["files_scanned"]),
        "classes_found": int(inventory["class_count"]),
        "records_found": int(inventory["record_count"]),
        "interfaces_found": int(inventory["interface_count"]),
        "enums_found": int(inventory["enum_count"]),
        "unnamed_package_files": int(inventory["unnamed_package_files"]),
        "parse_errors": int(inventory["parse_errors"]),
        "ignored_dirs": sorted(VENDOR_DIRS),
        "exclude_tests": True,
    }

    if not rel_files:
        return {
            "project": project,
            "metric": METRIC_NAME,
            "variant": VARIANT_NAME,
            "component_type": "project",
            "component": project,
            "status": "skipped",
            "skip_reason": "no_java_files_after_filtering",
            "value": None,
            "tool": TOOL_NAME,
            "tool_version": tool_version,
            "parameters": parameters,
            "timestamp_utc": timestamp_utc,
        }

    return {
        "project": project,
        "metric": METRIC_NAME,
        "variant": VARIANT_NAME,
        "component_type": "project",
        "component": project,
        "value": float(inventory["package_count"]),
        "tool": TOOL_NAME,
        "tool_version": tool_version,
        "parameters": parameters,
        "timestamp_utc": timestamp_utc,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect project-level package count using JavaParser")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(
        discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS),
        app_dir=args.app_dir,
    )
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    version = str(os.environ.get("JAVAPARSER_VERSION", "unknown")).strip() or "unknown"

    for project, project_path in projects:
        rel_files, inventory = collect_java_inventory(project_path)
        rows = [build_project_row(project, inventory, rel_files, version, timestamp)]
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
