#!/usr/bin/env python3
import argparse
import os

import lizard

from data_manager import build_module_metric_row, numeric_mean
from error_manager import ToolExecutionError
from result_executor import run_collector
from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from utils import (
    choose_java_input_path,
    find_java_sources,
    metric_output_path,
    utc_timestamp_now,
)
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects,
)

METRIC_NAME = "cc"
VARIANT_NAME = "lizard-default"
TOOL_NAME = "lizard"

def _collect_module_complexities(java_sources):
    if not java_sources:
        return []
    try:
        file_infos = lizard.analyze(java_sources)
    except Exception as exc:
        raise ToolExecutionError("lizard analysis failed") from exc

    values = []
    for file_info in file_infos:
        for fn in getattr(file_info, "function_list", []) or []:
            try:
                values.append(float(fn.cyclomatic_complexity))
            except (TypeError, ValueError):
                continue
    return values


def main():
    parser = argparse.ArgumentParser(description="Collect module-level Java CC with lizard")
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
        rows = []
        for module, module_path in discover_modules(project, project_path, vendor_dirs=VENDOR_DIRS):
            source_root = choose_java_input_path(module_path)
            java_sources = find_java_sources(source_root, vendor_dirs=VENDOR_DIRS)
            complexities = _collect_module_complexities(java_sources)
            rows.append(
                build_module_metric_row(
                    project=project,
                    module=module,
                    metric=METRIC_NAME,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=tool_version,
                    parameters={
                        "category": "complexity",
                        "granularity": "module",
                        "aggregation": "method_cc_mean",
                        "source_extensions": [".java"],
                        "source_files_found": len(java_sources),
                        "methods_measured": len(complexities),
                        "ignored_dirs": sorted(VENDOR_DIRS),
                    },
                    timestamp_utc=timestamp,
                    value=numeric_mean(complexities),
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
