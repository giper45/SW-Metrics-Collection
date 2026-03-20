#!/usr/bin/env python3
"""Shared utility helpers used across collectors."""

import os
from datetime import datetime, timezone

from config import TEST_DIR_NAMES as DEFAULT_TEST_DIR_NAMES, VENDOR_DIRS as DEFAULT_VENDOR_DIRS
from data_manager import read_csv_rows
from input_manager import choose_first_existing_dir, list_source_files
from result_layout import metric_output_path

JAVA_SOURCE_EXTENSIONS = {".java"}
JAVA_INPUT_DIR_CANDIDATES = ("main/java", "src/main/java")


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_java_sources(module_path, *, vendor_dirs=None, test_dir_names=None):
    return list_source_files(
        module_path,
        vendor_dirs=DEFAULT_VENDOR_DIRS if vendor_dirs is None else vendor_dirs,
        include_tests=False,
        test_dir_names=DEFAULT_TEST_DIR_NAMES if test_dir_names is None else test_dir_names,
        test_file_markers=(),
        source_extensions=JAVA_SOURCE_EXTENSIONS,
    )


def choose_java_input_path(
    module_path,
    *,
    relative_candidates=JAVA_INPUT_DIR_CANDIDATES,
    fallback_to_module=True,
):
    return choose_first_existing_dir(
        module_path,
        relative_candidates,
        fallback=module_path if fallback_to_module else None,
    )


def resolve_output_file_path(out_dir, filename):
    path = os.path.join(out_dir, filename)
    if os.path.isfile(path):
        return path
    fallback = f"{out_dir}{filename}"
    if os.path.isfile(fallback):
        return fallback
    return path


def read_csv_rows_lowercase(path):
    return read_csv_rows(path, lowercase_columns=True)
