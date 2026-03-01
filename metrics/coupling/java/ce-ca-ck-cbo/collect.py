#!/usr/bin/env python3
import argparse
import os
import shutil
import tempfile


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_stdout
from data_manager import build_module_metric_rows, first_numeric_value, numeric_sum
from utils import (
    choose_java_input_path,
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

METRIC_NAME = "ce-ca"
VARIANT_NAME = "ck-ce-ca-proxy"
TOOL_NAME = "ck"
TOOL_JAR = "/opt/tools/ck.jar"


def sum_numeric(rows, keys):
    return numeric_sum(first_numeric_value(row, keys) for row in rows)


def collect_module_values(module_path):
    out_dir = tempfile.mkdtemp(prefix="ck-out-")
    try:
        ck_input = choose_java_input_path(module_path)
        run_command_stdout(
            ["java", "-jar", TOOL_JAR, ck_input, "false", "0", "false", out_dir + os.sep])
        rows = read_csv_rows_lowercase(resolve_output_file_path(out_dir, "class.csv"))
        ce_value = sum_numeric(rows, ["ce", "fanout", "fan_out", "out_degree"])
        ca_value = sum_numeric(rows, ["ca", "fanin", "fan_in", "in_degree"])
        cbo_value = sum_numeric(rows, ["cbo"])
        return ce_value, ca_value, cbo_value
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect module-level Ce/Ca proxies with CK")
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
            ce_value, ca_value, cbo_value = collect_module_values(module_path)
            rows.extend(
                build_module_metric_rows(
                    project=project,
                    module=module,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=version,
                    timestamp_utc=timestamp,
                    default_metric=METRIC_NAME,
                    base_parameters={
                        "category": "coupling",
                        "aggregation": "module-class-sum",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "tool_output": "class.csv",
                    },
                    specs=[
                        {
                            "value": ce_value,
                            "parameters": {"dimension": "ce", "proxy_source": "ce|fanout"},
                        },
                        {
                            "value": ca_value,
                            "parameters": {"dimension": "ca", "proxy_source": "ca|fanin"},
                        },
                        {
                            "metric": "cbo",
                            "value": cbo_value,
                            "parameters": {"dimension": "cbo"},
                        },
                    ],
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
