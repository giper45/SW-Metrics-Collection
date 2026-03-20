#!/usr/bin/env python3
"""Shared helpers for JavaParser-based structural inventory collectors."""

from __future__ import annotations

import json
import os
import shutil

from config import TEST_DIR_NAMES, VENDOR_DIRS
from error_manager import OutputContractError
from input_manager import stage_source_tree
from result_executor import run_command_stdout

JAVA_INVENTORY_CLASSPATH = "/opt/metric/bin:/opt/metric/lib/javaparser-core.jar"
JAVA_INVENTORY_MAIN_CLASS = "JavaInventoryTool"
JAVA_SOURCE_EXTENSIONS = {".java"}

REQUIRED_KEYS = (
    "files_scanned",
    "class_count",
    "record_count",
    "interface_count",
    "enum_count",
    "package_count",
    "unnamed_package_files",
    "parse_errors",
)


def empty_inventory() -> dict[str, int]:
    return {
        "files_scanned": 0,
        "class_count": 0,
        "record_count": 0,
        "interface_count": 0,
        "enum_count": 0,
        "package_count": 0,
        "unnamed_package_files": 0,
        "parse_errors": 0,
    }


def stage_java_project_sources(project_path: str) -> tuple[str, list[str]]:
    staging_root, rel_files = stage_source_tree(
        project_path,
        vendor_dirs=VENDOR_DIRS,
        include_tests=False,
        test_dir_names=TEST_DIR_NAMES,
        test_file_markers=(),
        source_extensions=JAVA_SOURCE_EXTENSIONS,
        staging_prefix="javaparser-input-",
    )
    return staging_root, sorted(rel_files)


def _require_non_negative_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutputContractError(f"javaparser inventory field '{key}' must be numeric")
    integer = int(value)
    if float(value) != float(integer) or integer < 0:
        raise OutputContractError(f"javaparser inventory field '{key}' must be a non-negative integer")
    return integer


def parse_inventory_output(raw_output: str) -> dict[str, int]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise OutputContractError("javaparser inventory output is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise OutputContractError("javaparser inventory output must be a JSON object")

    output: dict[str, int] = {}
    for key in REQUIRED_KEYS:
        output[key] = _require_non_negative_int(payload, key)
    return output


def collect_java_inventory(project_path: str, *, timeout_sec: int = 120) -> tuple[list[str], dict[str, int]]:
    staging_root, rel_files = stage_java_project_sources(project_path)
    try:
        if not rel_files:
            return rel_files, empty_inventory()

        classpath = str(
            os.environ.get("JAVA_INVENTORY_CLASSPATH", JAVA_INVENTORY_CLASSPATH)
        ).strip() or JAVA_INVENTORY_CLASSPATH
        main_class = str(
            os.environ.get("JAVA_INVENTORY_MAIN_CLASS", JAVA_INVENTORY_MAIN_CLASS)
        ).strip() or JAVA_INVENTORY_MAIN_CLASS

        stdout = run_command_stdout(
            ["java", "-cp", classpath, main_class, "--root", staging_root],
            timeout_sec=timeout_sec,
        )
        return rel_files, parse_inventory_output(stdout)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
