#!/usr/bin/env python3
"""Shared source input preparation helpers for collectors."""

import os
import shutil
import tempfile

from config import TEST_DIR_NAMES as DEFAULT_TEST_DIR_NAMES
from config import TEST_FILE_MARKERS as DEFAULT_TEST_FILE_MARKERS
from config import VENDOR_DIRS as DEFAULT_VENDOR_DIRS


def default_app_dir(default="/app"):
    candidate = (
        os.environ.get("SRC_ROOT")
        or os.environ.get("METRIC_APP_DIR")
        or default
    )
    return str(candidate).strip() or default


def default_results_dir(default="/results"):
    candidate = (
        os.environ.get("RESULTS_DIR")
        or os.environ.get("METRIC_RESULTS_DIR")
        or default
    )
    return str(candidate).strip() or default


def add_common_cli_args(
    parser,
    *,
    app_default="/app",
    results_default="/results",
    app_help="Mounted source directory.",
    results_help="Output directory.",
):
    parser.add_argument("--app-dir", default=default_app_dir(app_default), help=app_help)
    parser.add_argument(
        "--results-dir",
        default=default_results_dir(results_default),
        help=results_help,
    )


def normalize_path(path):
    return str(path).replace("\\", "/")


def _as_set(values, default):
    return set(values) if values is not None else set(default)


def _as_tuple(values, default):
    return tuple(values) if values is not None else tuple(default)


def is_ignored_dir(name, vendor_dirs=None):
    if not isinstance(name, str):
        return False
    vendors = _as_set(vendor_dirs, DEFAULT_VENDOR_DIRS)
    return name.startswith(".") or name in vendors


def is_test_dir(name, test_dir_names=None):
    lowered = str(name or "").lower()
    names = {part.lower() for part in _as_set(test_dir_names, DEFAULT_TEST_DIR_NAMES)}
    return lowered in names or lowered.startswith("test")


def is_test_file(name, test_file_markers=None):
    lowered = str(name or "").lower()
    markers = _as_tuple(test_file_markers, DEFAULT_TEST_FILE_MARKERS)
    return any(marker in lowered for marker in markers)


def discover_projects(app_dir, vendor_dirs=None):
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return []
    projects = []
    for name in entries:
        path = os.path.join(app_dir, name)
        if os.path.isdir(path) and not is_ignored_dir(name, vendor_dirs=vendor_dirs):
            projects.append((name, path))
    return projects


def discover_modules(project_name, project_path, vendor_dirs=None):
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []
    modules = []
    for name in entries:
        path = os.path.join(project_path, name)
        if os.path.isdir(path) and not is_ignored_dir(name, vendor_dirs=vendor_dirs):
            modules.append((name, path))
    return modules or [(project_name, project_path)]


def iter_source_files(
    root_path,
    *,
    vendor_dirs=None,
    include_tests=True,
    test_dir_names=None,
    test_file_markers=None,
    source_extensions=None,
    include_hidden_files=False,
):
    normalized_exts = None
    if source_extensions is not None:
        normalized_exts = {str(ext).lower() for ext in source_extensions}

    for root, dirnames, filenames in os.walk(root_path):
        allowed_dirs = []
        for dirname in sorted(dirnames):
            if is_ignored_dir(dirname, vendor_dirs=vendor_dirs):
                continue
            if not include_tests and is_test_dir(dirname, test_dir_names=test_dir_names):
                continue
            allowed_dirs.append(dirname)
        dirnames[:] = allowed_dirs

        for filename in sorted(filenames):
            if not include_hidden_files and filename.startswith("."):
                continue
            if not include_tests and is_test_file(filename, test_file_markers=test_file_markers):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if normalized_exts is not None and ext not in normalized_exts:
                continue
            path = os.path.join(root, filename)
            if os.path.isfile(path):
                yield path


def list_source_files(
    root_path,
    *,
    vendor_dirs=None,
    include_tests=True,
    test_dir_names=None,
    test_file_markers=None,
    source_extensions=None,
    include_hidden_files=False,
):
    return list(
        iter_source_files(
            root_path,
            vendor_dirs=vendor_dirs,
            include_tests=include_tests,
            test_dir_names=test_dir_names,
            test_file_markers=test_file_markers,
            source_extensions=source_extensions,
            include_hidden_files=include_hidden_files,
        )
    )


def stage_source_tree(
    source_root,
    *,
    vendor_dirs=None,
    include_tests=True,
    test_dir_names=None,
    test_file_markers=None,
    source_extensions=None,
    include_hidden_files=False,
    staging_prefix="metric-input-",
):
    staging_dir = tempfile.mkdtemp(prefix=staging_prefix)
    rel_files = []
    for src in iter_source_files(
        source_root,
        vendor_dirs=vendor_dirs,
        include_tests=include_tests,
        test_dir_names=test_dir_names,
        test_file_markers=test_file_markers,
        source_extensions=source_extensions,
        include_hidden_files=include_hidden_files,
    ):
        rel = normalize_path(os.path.relpath(src, source_root))
        dst = os.path.join(staging_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        rel_files.append(rel)
    return staging_dir, rel_files


def choose_first_existing_dir(base_path, relative_candidates, fallback=None):
    for rel in relative_candidates:
        candidate = os.path.join(base_path, rel)
        if os.path.isdir(candidate):
            return candidate
    return fallback if fallback is not None else base_path


def discover_class_files(base_dir, vendor_dirs=None):
    return list_source_files(
        base_dir,
        vendor_dirs=vendor_dirs,
        include_tests=True,
        source_extensions={".class"},
    )


def discover_module_class_files(module_path, bytecode_dir_candidates, vendor_dirs=None):
    class_files = []
    seen = set()
    inputs = []
    for rel_dir in bytecode_dir_candidates:
        candidate_dir = os.path.join(module_path, rel_dir)
        if not os.path.isdir(candidate_dir):
            continue
        inputs.append(candidate_dir)
        for class_file in discover_class_files(candidate_dir, vendor_dirs=vendor_dirs):
            if class_file in seen:
                continue
            seen.add(class_file)
            class_files.append(class_file)
    return class_files, inputs
