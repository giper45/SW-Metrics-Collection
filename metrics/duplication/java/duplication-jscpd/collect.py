#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
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

METRIC_NAME = "duplication-rate"
VARIANT_NAME = "jscpd-default"
TOOL_NAME = "jscpd"
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}
VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}


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
        filtered = []
        for dirname in sorted(dirnames):
            if is_ignored_dir(dirname) or is_test_dir(dirname):
                continue
            filtered.append(dirname)
        dirnames[:] = filtered

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


def run_command(cmd, dry_run, cwd=None, allowed_returncodes=None):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return "", "", 0

    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    allowed = set(allowed_returncodes or {0})
    if completed.returncode not in allowed:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout, completed.stderr, completed.returncode


def get_tool_version(dry_run):
    out, _, _ = run_command([TOOL_NAME, "--version"], dry_run)
    if dry_run:
        return "dry-run"
    match = re.search(r"(\d+(?:\.\d+)+)", out)
    return match.group(1) if match else (out.strip() or "unknown")


def parse_jscpd_ratio(report_path):
    if not os.path.isfile(report_path):
        return 0.0

    try:
        payload = json.loads(open(report_path, "r", encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return 0.0

    stats = payload.get("statistics", {}) if isinstance(payload, dict) else {}
    total = stats.get("total", {}) if isinstance(stats, dict) else {}

    percentage = total.get("percentage")
    if isinstance(percentage, (int, float)):
        return round(float(percentage) / 100.0, 6)

    duplicated_lines = total.get("duplicatedLines")
    lines = total.get("lines")
    if isinstance(duplicated_lines, (int, float)) and isinstance(lines, (int, float)) and lines > 0:
        return round(float(duplicated_lines) / float(lines), 6)

    return 0.0


def parse_jscpd_file_rates(report_path, staging_root):
    if not os.path.isfile(report_path):
        return {}

    try:
        payload = json.loads(open(report_path, "r", encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return {}

    sources = (
        payload.get("statistics", {})
        .get("formats", {})
        .get("java", {})
        .get("sources", {})
    )
    if not isinstance(sources, dict):
        return {}

    values = {}
    staging_norm = normalize_path(staging_root).rstrip("/")
    for path, stats in sources.items():
        if not isinstance(path, str) or not isinstance(stats, dict):
            continue
        lines = stats.get("lines")
        duplicated = stats.get("duplicatedLines")
        if not isinstance(lines, (int, float)) or lines <= 0:
            ratio = 0.0
        elif not isinstance(duplicated, (int, float)):
            ratio = 0.0
        else:
            ratio = float(duplicated) / float(lines)

        path_norm = normalize_path(path)
        if path_norm.startswith(staging_norm + "/"):
            rel = path_norm[len(staging_norm) + 1 :]
        else:
            rel = path_norm.lstrip("./")
        values[normalize_path(rel)] = round(max(0.0, min(1.0, ratio)), 6)

    return values


def collect_project_values(project_path, dry_run):
    staging, rel_files = stage_filtered_java_tree(project_path)
    report_dir = tempfile.mkdtemp(prefix="jscpd-report-")
    try:
        if not rel_files:
            return rel_files, {}

        cmd = [
            TOOL_NAME,
            "--format",
            "java",
            "--min-lines",
            "5",
            "--min-tokens",
            "20",
            "--threshold",
            "100",
            "--reporters",
            "json",
            "--output",
            report_dir,
            staging,
        ]
        run_command(cmd, dry_run, allowed_returncodes={0, 1})

        if dry_run:
            return rel_files, {}
        report_path = os.path.join(report_dir, "jscpd-report.json")
        return rel_files, parse_jscpd_file_rates(report_path, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(report_dir, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect file-level duplication ratio with jscpd")
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
                        "category": "duplication",
                        "scope_filter": "no_tests",
                        "granularity": "file",
                        "min_lines": 5,
                        "min_tokens": 20,
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
                            "category": "duplication",
                            "scope_filter": "no_tests",
                            "granularity": "file",
                            "min_lines": 5,
                            "min_tokens": 20,
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
