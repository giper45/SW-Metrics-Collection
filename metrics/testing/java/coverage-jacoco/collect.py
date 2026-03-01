#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_details
from data_manager import build_module_metric_row
from error_manager import ToolExecutionError, error_fallback_or_raise
from utils import metric_output_path, utc_timestamp_now
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects,
    iter_source_files)

METRIC_NAME = "test-coverage"
VARIANT_NAME = "jacoco-default"
TOOL_NAME = "jacoco"
JACOCO_VERSION = "0.8.11"


def copy_tree(src, dst):
    copied = 0
    for src_file in iter_source_files(src, vendor_dirs=VENDOR_DIRS):
        rel = os.path.relpath(src_file, src)
        dst_file = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
        shutil.copy2(src_file, dst_file)
        copied += 1
    return copied


def get_maven_version():
    out, _, _ = run_command_details(["mvn", "-version"])
    match = re.search(r"Apache Maven\s+([0-9][0-9A-Za-z_.-]*)", out)
    return match.group(1) if match else "unknown"


def _counter_ratio(counter_node):
    missed = float(counter_node.get("missed", "0") or 0)
    covered = float(counter_node.get("covered", "0") or 0)
    total = missed + covered
    if total <= 0:
        return 0.0
    return round(covered / total, 6)


def parse_jacoco_instruction_ratio(xml_path):
    if not os.path.isfile(xml_path):
        return 0.0
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return 0.0

    for counter in root.findall("counter"):
        if counter.get("type") == "INSTRUCTION":
            return _counter_ratio(counter)
    return 0.0


def collect_module_value(module_path):
    staging = tempfile.mkdtemp(prefix="jacoco-project-")
    details = {"maven_exit_code": 0, "maven_ran": False, "pom_found": False}
    try:
        copied = copy_tree(module_path, staging)
        if copied == 0:
            return None, details, "no_files_after_filtering"

        pom_path = os.path.join(staging, "pom.xml")
        if not os.path.isfile(pom_path):
            return 0.0, details, None
        details["pom_found"] = True

        cmd = [
            "mvn",
            "-q",
            "-DskipTests=false",
            "-DfailIfNoTests=false",
            "-Dmaven.test.failure.ignore=true",
            "test",
            f"org.jacoco:jacoco-maven-plugin:{JACOCO_VERSION}:report",
        ]

        try:
            _, _, code = run_command_details(cmd, cwd=staging, allowed_returncodes={0, 1})
        except ToolExecutionError:
            fallback = error_fallback_or_raise(
                "maven_execution_failed",
                category="tool",
                context=f"module={module_path}",
            )
            return None, details, str(fallback["skip_reason"])
        details["maven_exit_code"] = int(code)
        details["maven_ran"] = True

        report_path = os.path.join(staging, "target", "site", "jacoco", "jacoco.xml")
        return parse_jacoco_instruction_ratio(report_path), details, None
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect module-level Java coverage ratio using JaCoCo")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    maven_version = get_maven_version()

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path, vendor_dirs=VENDOR_DIRS):
            value, details, skip_reason = collect_module_value(module_path)

            base_parameters = {
                "category": "testing",
                "scope_filter": "all",
                "counter": "INSTRUCTION",
                "jacoco_version": JACOCO_VERSION,
                "maven_version": maven_version,
                "granularity": "module",
                **details,
            }

            rows.append(
                build_module_metric_row(
                    project=project,
                    module=module,
                    metric=METRIC_NAME,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=JACOCO_VERSION,
                    parameters=base_parameters,
                    timestamp_utc=timestamp,
                    value=float(value) if value is not None else None,
                    status="skipped" if value is None else "ok",
                    skip_reason=skip_reason or "coverage_unavailable",
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
