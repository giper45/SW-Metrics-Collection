#!/usr/bin/env python3
import argparse
import os
import re


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_stdout
from data_manager import build_module_metric_row
from error_manager import InputContractError, OutputContractError, ToolExecutionError
from utils import metric_output_path, utc_timestamp_now
from config import JAVA_BYTECODE_DIR_CANDIDATES as BYTECODE_DIR_CANDIDATES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects,
    list_source_files)
from java_bytecode import discover_module_class_files_with_roots

METRIC_NAME = "ce-ca"
VARIANT_NAME = "jdepend-default"
TOOL_NAME = "jdepend"
TOOL_JAR = "/opt/tools/jdepend.jar"
JAVA_SOURCE_ROOT_CANDIDATES = ("src/main/java", "main/java")


PACKAGE_RE = re.compile(r"^(?:-+\s*)?Package:?\s+(.+)$")
CA_RE = re.compile(r"\bCa:\s*([0-9]+)")
CE_RE = re.compile(r"\bCe:\s*([0-9]+)")
I_RE = re.compile(r"\bI:\s*([0-9]*\.?[0-9]+)")


def parse_jdepend_text(raw_output):
    packages = {}
    current = None

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        package_match = PACKAGE_RE.match(line)
        if package_match:
            current = package_match.group(1).strip()
            packages[current] = {"ca": 0, "ce": 0, "i": 0.0}
            continue

        if current is None:
            continue

        ca_match = CA_RE.search(line)
        if ca_match:
            packages[current]["ca"] = int(ca_match.group(1))

        ce_match = CE_RE.search(line)
        if ce_match:
            packages[current]["ce"] = int(ce_match.group(1))

        i_match = I_RE.search(line)
        if i_match:
            packages[current]["i"] = float(i_match.group(1))

    return packages


def _discover_module_class_files(module_path: str, project_path: str):
    class_files, search_roots, bytecode_inputs = discover_module_class_files_with_roots(
        module_path,
        project_path,
        BYTECODE_DIR_CANDIDATES,
        vendor_dirs=set(),
    )
    return class_files, bytecode_inputs, search_roots


def _direct_java_sources(module_path: str):
    sources = []
    for rel_path in JAVA_SOURCE_ROOT_CANDIDATES:
        source_root = os.path.join(module_path, rel_path)
        if not os.path.isdir(source_root):
            continue
        sources.extend(
            list_source_files(
                source_root,
                vendor_dirs=VENDOR_DIRS,
                include_tests=False,
                source_extensions={".java"},
                test_file_markers=(),
            )
        )
    return sources


def aggregate_ce_ca(module_path, project_path):
    sources = _direct_java_sources(module_path)
    prebuilt_class_files, prebuilt_inputs, search_roots = _discover_module_class_files(module_path, project_path)
    class_files = list(prebuilt_class_files)
    jdepend_inputs = list(prebuilt_inputs)
    if not class_files and sources:
        raise InputContractError(
            f"missing precompiled java bytecode for module '{module_path}'. "
            f"search_roots={search_roots} bytecode_inputs={jdepend_inputs}. "
            "run make prepare-java-bytecode"
        )

    if not class_files:
        return {
            "status": "ok",
            "ce": 0.0,
            "ca": 0.0,
            "class_files_found": 0,
            "java_sources_found": 0,
            "bytecode_inputs": [],
            "bytecode_mode": "not-applicable",
            "compile_exit_code": None,
            "compile_release": None,
        }

    try:
        output = run_command_stdout(["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", *jdepend_inputs])
    except ToolExecutionError as exc:
        raise ToolExecutionError(f"module={module_path}: jdepend_execution_failed") from exc

    packages = parse_jdepend_text(output)
    if not packages:
        raise OutputContractError(f"module={module_path}: jdepend_empty_output")

    ce_total = float(sum(item.get("ce", 0) for item in packages.values()))
    ca_total = float(sum(item.get("ca", 0) for item in packages.values()))
    return {
        "status": "ok",
        "ce": ce_total,
        "ca": ca_total,
        "class_files_found": len(class_files),
        "java_sources_found": len(sources),
        "bytecode_inputs": jdepend_inputs,
        "bytecode_mode": "prebuilt",
        "compile_exit_code": None,
        "compile_release": None,
    }


def build_dimension_row(project, module, dimension, module_stats, timestamp, version):
    status = str(module_stats.get("status", "ok"))
    return build_module_metric_row(
        project=project,
        module=module,
        metric=METRIC_NAME,
        variant=VARIANT_NAME,
        tool=TOOL_NAME,
        tool_version=version,
        parameters={
            "category": "coupling",
            "dimension": dimension,
            "metric_source": "jdepend-bytecode",
            "bytecode_mode": module_stats.get("bytecode_mode", "unknown"),
            "bytecode_inputs": list(module_stats.get("bytecode_inputs", [])),
            "class_files_found": int(module_stats.get("class_files_found", 0)),
            "java_sources_found": int(module_stats.get("java_sources_found", 0)),
            "compile_exit_code": module_stats.get("compile_exit_code"),
            "compile_release": module_stats.get("compile_release"),
            "ignored_dirs": sorted(VENDOR_DIRS),
            "exclude_tests": True,
        },
        timestamp_utc=timestamp,
        value=float(module_stats[dimension]) if status == "ok" else None,
        status=status,
        skip_reason=str(module_stats.get("skip_reason", "invalid_module_input")),
    )


def main():
    parser = argparse.ArgumentParser(description="Collect module-level Ce/Ca with JDepend")
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
    version = os.environ.get("JDEPEND_VERSION", "unknown")

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(
            project,
            project_path,
            vendor_dirs=VENDOR_DIRS):
            module_stats = aggregate_ce_ca(module_path, project_path)
            rows.append(build_dimension_row(project, module, "ce", module_stats, timestamp, version))
            rows.append(build_dimension_row(project, module, "ca", module_stats, timestamp, version))

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
