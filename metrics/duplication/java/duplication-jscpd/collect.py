#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import tempfile


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import detect_tool_version, run_collector, run_command_details
from data_manager import build_module_metric_row
from error_manager import ToolExecutionError, error_fallback_or_raise
from utils import metric_output_path, utc_timestamp_now
from config import TEST_DIR_NAMES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects,
    stage_source_tree)

METRIC_NAME = "duplication-rate"
VARIANT_NAME = "jscpd-default"
TOOL_NAME = "jscpd"


def stage_filtered_java_tree(project_path):
    staging, rel_files = stage_source_tree(
        project_path,
        vendor_dirs=VENDOR_DIRS,
        include_tests=False,
        test_dir_names=TEST_DIR_NAMES,
        test_file_markers=(),
        source_extensions={".java"})
    return staging, sorted(rel_files)


def parse_jscpd_ratio(report_path):
    if not os.path.isfile(report_path):
        return 0.0

    try:
        payload = json.loads(open(report_path, "r", encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return 0.0

    stats = payload.get("statistics", {}) if isinstance(payload, dict) else {}
    total = stats.get("total", {}) if isinstance(stats, dict) else {}

    percentage = total.get("percentage")
    if isinstance(percentage, (int, float)):
        return round(float(percentage) / 100.0, 6)

    duplicated_lines = total.get("duplicatedLines")
    lines = total.get("lines")
    if isinstance(duplicated_lines, (int, float)) and isinstance(lines, (int, float)) and lines > 0:
        return round(float(duplicated_lines) / float(lines), 6)

    return 0.0


def collect_module_value(module_path):
    staging, rel_files = stage_filtered_java_tree(module_path)
    report_dir = tempfile.mkdtemp(prefix="jscpd-report-")
    try:
        if not rel_files:
            return None, {"files_analyzed": 0}, "no_java_files_after_filtering"

        cmd = [
            TOOL_NAME,
            "--format",
            "java",
            "--min-lines",
            "5",
            "--min-tokens",
            "20",
            "--threshold",
            "100",
            "--reporters",
            "json",
            "--output",
            report_dir,
            staging,
        ]
        try:
            run_command_details(cmd, allowed_returncodes={0, 1})
        except ToolExecutionError:
            fallback = error_fallback_or_raise(
                "jscpd_execution_failed",
                category="tool",
                context=f"module={module_path}",
            )
            return None, {"files_analyzed": len(rel_files)}, str(fallback["skip_reason"])

        report_path = os.path.join(report_dir, "jscpd-report.json")
        if not os.path.isfile(report_path):
            fallback = error_fallback_or_raise(
                "jscpd_report_missing",
                category="output",
                context=f"module={module_path}",
            )
            return None, {"files_analyzed": len(rel_files)}, str(fallback["skip_reason"])
        return parse_jscpd_ratio(report_path), {"files_analyzed": len(rel_files)}, None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(report_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect module-level duplication ratio with jscpd")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = detect_tool_version([TOOL_NAME, "--version"])

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path, vendor_dirs=VENDOR_DIRS):
            value, details, skip_reason = collect_module_value(module_path)
            parameters = {
                "category": "duplication",
                "scope_filter": "no_tests",
                "granularity": "module",
                "min_lines": 5,
                "min_tokens": 20,
                "ignored_dirs": sorted(VENDOR_DIRS),
                **details,
            }
            rows.append(
                build_module_metric_row(
                    project=project,
                    module=module,
                    metric=METRIC_NAME,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=tool_version,
                    parameters=parameters,
                    timestamp_utc=timestamp,
                    value=float(value) if value is not None else None,
                    status="skipped" if value is None else "ok",
                    skip_reason=skip_reason,
                )
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
