#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_stdout
from data_manager import build_module_metric_row, numeric_mean, safe_float
from error_manager import InputContractError, OutputContractError
from utils import (
    choose_java_input_path,
    find_java_sources,
    metric_output_path,
    utc_timestamp_now,
)
from config import JAVA_BYTECODE_DIR_CANDIDATES as BYTECODE_DIR_CANDIDATES, TEST_DIR_NAMES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects)
from java_bytecode import discover_module_class_files_with_roots

METRIC_NAME = "lcom"
VARIANT_NAME = "ckjm-default"
TOOL_NAME = "ckjm"
CKJM_MAIN_CLASS = "gr.spinellis.ckjm.MetricsFilter"
CKJM_CLASSPATH = "/opt/tools/ckjm.jar:/opt/tools/commons-lang3.jar"


def parse_ckjm_lcom_values(raw_output):
    values = []
    for line in str(raw_output or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 7:
            continue
        # CKJM plain output format:
        # class WMC DIT NOC CBO RFC LCOM Ca NPM
        lcom_value = safe_float(parts[6])
        if lcom_value is None:
            continue
        values.append(float(lcom_value))
    return values


def collect_module_stats(module_path: str, project_path: str) -> Dict[str, object]:
    source_input = choose_java_input_path(module_path)
    java_sources = find_java_sources(
        source_input,
        vendor_dirs=VENDOR_DIRS,
        test_dir_names=TEST_DIR_NAMES,
    )
    class_files, search_roots, scanned_inputs = discover_module_class_files_with_roots(
        module_path,
        project_path,
        BYTECODE_DIR_CANDIDATES,
        vendor_dirs=VENDOR_DIRS,
    )
    if not class_files:
        if java_sources:
            raise InputContractError(
                f"missing precompiled java bytecode for module '{module_path}'. "
                f"search_roots={search_roots} bytecode_inputs={scanned_inputs}. "
                "run make prepare-java-bytecode"
            )
        return {
            "value": 0.0,
            "class_files_found": 0,
            "classes_measured": 0,
            "java_sources_found": len(java_sources),
            "search_roots": search_roots,
            "bytecode_inputs": scanned_inputs,
        }

    output = run_command_stdout(
        [
            "java",
            "-cp",
            CKJM_CLASSPATH,
            CKJM_MAIN_CLASS,
        ],
        stdin_text="\n".join(class_files) + "\n")
    lcom_values = parse_ckjm_lcom_values(output)
    if not lcom_values:
        raise OutputContractError(
            f"ckjm output did not contain parseable LCOM values for module '{module_path}'"
        )
    return {
        "value": numeric_mean(lcom_values),
        "class_files_found": len(class_files),
        "classes_measured": len(lcom_values),
        "java_sources_found": len(java_sources),
        "search_roots": search_roots,
        "bytecode_inputs": scanned_inputs,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect module-level LCOM with CKJM")
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
    version = os.environ.get("CKJM_VERSION", "unknown")

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(
            project,
            project_path,
            vendor_dirs=VENDOR_DIRS):
            module_stats = collect_module_stats(module_path, project_path)
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
                        "metric_source": "dspinellis-ckjm-bytecode",
                        "class_files_found": int(module_stats["class_files_found"]),
                        "classes_measured": int(module_stats["classes_measured"]),
                        "java_sources_found": int(module_stats["java_sources_found"]),
                        "class_search_roots": list(module_stats["search_roots"]),
                        "bytecode_inputs": list(module_stats["bytecode_inputs"]),
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "tool_output": "plain-text",
                    },
                    timestamp_utc=timestamp,
                    value=module_stats["value"],
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
