#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
import sys

_COMMON_DIR = None
for _parent in Path(__file__).resolve().parents:
    _candidate = _parent / "common" / "result_writer.py"
    if _candidate.is_file():
        _COMMON_DIR = _candidate.parent
        break
if _COMMON_DIR and str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector

METRIC_NAME = "static-warnings"
VARIANT_NAME = "checkstyle-default"
TOOL_NAME = "checkstyle"
CHECKSTYLE_CONFIG = "/opt/metric/checkstyle.xml"
CHECKSTYLE_JAR = "/opt/tools/checkstyle.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_path(path):
    return path.replace("\\", "/")


def is_ignored_dir(name):
    return name.startswith(".") or name in VENDOR_DIRS


def is_test_dir(name):
    lowered = name.lower()
    return lowered in TEST_DIR_NAMES or lowered.startswith("test")


def discover_projects(app_dir):
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return []
    return [
        (name, os.path.join(app_dir, name))
        for name in entries
        if os.path.isdir(os.path.join(app_dir, name)) and not is_ignored_dir(name)
    ]


def stage_filtered_java_tree(project_path):
    staging = tempfile.mkdtemp(prefix="metric-input-")
    rel_files = []
    for root, dirnames, filenames in os.walk(project_path):
        dirnames[:] = sorted(
            d for d in dirnames if not is_ignored_dir(d) and not is_test_dir(d)
        )
        for filename in sorted(filenames):
            if filename.startswith(".") or not filename.endswith(".java"):
                continue
            src = os.path.join(root, filename)
            if not os.path.isfile(src):
                continue
            rel = normalize_path(os.path.relpath(src, project_path))
            dst = os.path.join(staging, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            rel_files.append(rel)
    return staging, sorted(rel_files)


def run_command(cmd, dry_run, allowed_returncodes=None):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return "", "", 0

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    allowed = set(allowed_returncodes or {0})
    if completed.returncode not in allowed:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout, completed.stderr, completed.returncode


def get_tool_version(dry_run):
    stdout, stderr, _ = run_command(["java", "-jar", CHECKSTYLE_JAR, "-V"], dry_run)
    if dry_run:
        return "dry-run"
    output = (stdout + "\n" + stderr).strip()
    match = re.search(r"(\d+(?:\.\d+)+)", output)
    return match.group(1) if match else (output or "unknown")


def parse_checkstyle_file_violations(report_path, staging_root):
    if not os.path.isfile(report_path):
        return {}
    try:
        root = ET.parse(report_path).getroot()
    except ET.ParseError:
        return {}

    staging_norm = normalize_path(staging_root).rstrip("/")
    values = {}
    for file_node in root.findall("file"):
        raw_name = file_node.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        path_norm = normalize_path(raw_name)
        if path_norm.startswith(staging_norm + "/"):
            rel = path_norm[len(staging_norm) + 1 :]
        else:
            rel = path_norm.lstrip("./")
        count = len(file_node.findall("error"))
        values[normalize_path(rel)] = float(count)
    return values


def parse_checkstyle_violations(report_path):
    return float(sum(parse_checkstyle_file_violations(report_path, "").values()))


def collect_project_values(project_path, dry_run):
    staging, rel_files = stage_filtered_java_tree(project_path)
    report_dir = tempfile.mkdtemp(prefix="checkstyle-report-")
    report_path = os.path.join(report_dir, "report.xml")
    try:
        if not rel_files:
            return rel_files, {}

        cmd = [
            "java",
            "-jar",
            CHECKSTYLE_JAR,
            "-c",
            CHECKSTYLE_CONFIG,
            "-f",
            "xml",
            "-o",
            report_path,
            staging,
        ]
        # Checkstyle may return number of violations.
        run_command(cmd, dry_run, allowed_returncodes=set(range(256)))
        if dry_run:
            return rel_files, {}
        return rel_files, parse_checkstyle_file_violations(report_path, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(report_dir, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect file-level static warning counts via checkstyle")
    parser.add_argument("--app-dir", default=os.environ.get("SRC_ROOT", os.environ.get("METRIC_APP_DIR", "/app")))
    parser.add_argument("--results-dir", default=os.environ.get("RESULTS_DIR", os.environ.get("METRIC_RESULTS_DIR", "/results")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)
    if not projects:
        if args.dry_run:
            print("DRY_RUN: no projects discovered")
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = get_tool_version(args.dry_run)

    for project, project_path in projects:
        rel_files, values = collect_project_values(project_path, args.dry_run)
        rows = []

        if not rel_files:
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "project",
                    "component": project,
                    "status": "skipped",
                    "skip_reason": "no_java_files_after_filtering",
                    "value": None,
                    "tool": TOOL_NAME,
                    "tool_version": tool_version,
                    "parameters": {
                        "category": "quality",
                        "granularity": "file",
                        "scope_filter": "no_tests",
                        "config": "line-length-100 + need-braces",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                    },
                    "timestamp_utc": timestamp,
                }
            )
        else:
            for rel in rel_files:
                rows.append(
                    {
                        "project": project,
                        "metric": METRIC_NAME,
                        "variant": VARIANT_NAME,
                        "component_type": "file",
                        "component": rel,
                        "value": float(values.get(rel, 0.0)),
                        "tool": TOOL_NAME,
                        "tool_version": tool_version,
                        "parameters": {
                            "category": "quality",
                            "granularity": "file",
                            "scope_filter": "no_tests",
                            "config": "line-length-100 + need-braces",
                            "ignored_dirs": sorted(VENDOR_DIRS),
                        },
                        "timestamp_utc": timestamp,
                    }
                )

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue

        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
