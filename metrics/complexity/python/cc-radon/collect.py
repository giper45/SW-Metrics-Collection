#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
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

METRIC_NAME = "cc"
VARIANT_NAME = "radon-default"
TOOL_NAME = "radon"
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


def list_python_files(project_path):
    files = []
    for root, dirnames, filenames in os.walk(project_path):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d) and not is_test_dir(d))
        for filename in sorted(filenames):
            if filename.startswith(".") or not filename.endswith(".py"):
                continue
            files.append(os.path.join(root, filename))
    return files


def run_command(cmd, dry_run):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return ""
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout


def get_tool_version(dry_run):
    output = run_command([TOOL_NAME, "--version"], dry_run).strip()
    if dry_run:
        return "dry-run"
    match = re.search(r"(\d+(?:\.\d+)+)", output)
    return match.group(1) if match else (output or "unknown")


def parse_radon_nodes(raw_output):
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return []

    rows = []
    if not isinstance(payload, dict):
        return rows

    for path, nodes in sorted(payload.items()):
        if not isinstance(path, str) or not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            cc_value = node.get("complexity")
            if not isinstance(cc_value, (int, float)):
                continue
            rows.append(
                {
                    "path": normalize_path(path),
                    "name": str(node.get("name", "<anonymous>")),
                    "lineno": int(node.get("lineno", 0) or 0),
                    "endline": int(node.get("endline", 0) or 0),
                    "type": str(node.get("type", "function")),
                    "value": float(cc_value),
                }
            )
    return rows


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def build_method_component(project_path, file_path, name, lineno):
    rel = normalize_path(os.path.relpath(file_path, project_path))
    return f"{rel}::{name}@L{int(lineno)}"


def collect_project_rows(project, project_path, tool_version, timestamp, dry_run):
    python_files = list_python_files(project_path)
    if not python_files:
        return [
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_python_sources",
                "value": None,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        ]

    cmd = [TOOL_NAME, "cc", "-j", "-s"] + python_files
    output = run_command(cmd, dry_run)
    if dry_run:
        return []

    parsed = parse_radon_nodes(output)
    if not parsed:
        return [
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_python_methods_detected",
                "value": None,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        ]

    rows = []
    for item in parsed:
        component = build_method_component(project_path, item["path"], item["name"], item["lineno"])
        rows.append(
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "method",
                "component": component,
                "value": item["value"],
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": {
                    "category": "complexity",
                    "language": "python",
                    "granularity": "method",
                    "method_name": item["name"],
                    "method_type": item["type"],
                    "start_line": item["lineno"],
                    "end_line": item["endline"],
                    "ignored_dirs": sorted(VENDOR_DIRS),
                },
                "timestamp_utc": timestamp,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Collect method-level Python CC with radon")
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

    version = get_tool_version(args.dry_run)
    os.makedirs(args.results_dir, exist_ok=True)

    for project, project_path in projects:
        rows = collect_project_rows(project, project_path, version, timestamp, args.dry_run)

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
