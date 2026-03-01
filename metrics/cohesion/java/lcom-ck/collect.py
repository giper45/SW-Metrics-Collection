#!/usr/bin/env python3
import argparse
import os
import shutil
import tempfile


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_stdout
from data_manager import build_module_metric_row, numeric_mean, safe_float
from utils import (
    choose_java_input_path,
    find_java_sources,
    metric_output_path,
    read_csv_rows_lowercase,
    resolve_output_file_path,
    utc_timestamp_now,
)
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects)

METRIC_NAME = "lcom"
VARIANT_NAME = "ck-default"
TOOL_NAME = "ck"
TOOL_JAR = "/opt/tools/ck.jar"


def collect_module_value(module_path):
    out_dir = tempfile.mkdtemp(prefix="ck-out-")
    try:
        ck_input = choose_java_input_path(module_path)
        java_sources = find_java_sources(ck_input, vendor_dirs=VENDOR_DIRS)
        if not java_sources:
            return 0.0
        run_command_stdout(
            ["java", "-jar", TOOL_JAR, ck_input, "false", "0", "false", out_dir + os.sep])
        class_csv_path = resolve_output_file_path(out_dir, "class.csv")
        rows = read_csv_rows_lowercase(class_csv_path)
        if not rows:
            return 0.0

        lcom_values = []
        for row in rows:
            parsed = safe_float(row.get("lcom"))
            if parsed is not None:
                lcom_values.append(parsed)
        if not lcom_values:
            return 0.0
        return numeric_mean(lcom_values)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect module-level LCOM with CK")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    version = os.environ.get("CK_VERSION", "unknown")

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path, vendor_dirs=VENDOR_DIRS):
            rows.append(
                build_module_metric_row(
                    project=project,
                    module=module,
                    metric=METRIC_NAME,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=version,
                    parameters={
                        "category": "cohesion",
                        "aggregation": "class_lcom_mean",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "tool_output": "class.csv",
                    },
                    timestamp_utc=timestamp,
                    value=collect_module_value(module_path),
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
