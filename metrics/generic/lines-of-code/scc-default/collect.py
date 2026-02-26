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

from result_writer import filter_projects, generate_run_id, run_collector, write_jsonl_rows

METRIC_NAME = "lines-of-code"
VARIANT_NAME = "scc-default"
TOOL_NAME = "scc"
VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_ignored_dir(name):
    return name.startswith(".") or name in VENDOR_DIRS


def discover_projects(app_dir):
    projects = []
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return projects

    for name in entries:
        path = os.path.join(app_dir, name)
        if os.path.isdir(path) and not is_ignored_dir(name):
            projects.append((name, path))
    return projects


def discover_modules(project_name, project_path):
    modules = []
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []

    for name in entries:
        path = os.path.join(project_path, name)
        if os.path.isdir(path) and not is_ignored_dir(name):
            modules.append((name, path))

    if not modules:
        modules.append((project_name, project_path))
    return modules


def stage_filtered_tree(module_path):
    staging_dir = tempfile.mkdtemp(prefix="metric-input-")
    copied = 0

    for root, dirnames, filenames in os.walk(module_path):
        dirnames[:] = sorted([d for d in dirnames if not is_ignored_dir(d)])
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            src = os.path.join(root, filename)
            if not os.path.isfile(src):
                continue

            rel_path = os.path.relpath(src, module_path)
            dst = os.path.join(staging_dir, rel_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    return staging_dir, copied


def run_command(cmd, dry_run):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return ""

    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\\n"
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


def parse_scc_json(payload):
    if isinstance(payload, dict):
        totals = payload.get("totals")
        if isinstance(totals, dict):
            code_value = totals.get("Code")
            if isinstance(code_value, (int, float)):
                return int(code_value)
        code_value = payload.get("Code")
        if isinstance(code_value, (int, float)):
            return int(code_value)
        return 0

    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                name = str(row.get("Name", "")).strip().lower()
                code_value = row.get("Code")
                if name == "total" and isinstance(code_value, (int, float)):
                    return int(code_value)

        total = 0
        for row in payload:
            if isinstance(row, dict):
                code_value = row.get("Code")
                if isinstance(code_value, (int, float)):
                    total += int(code_value)
        return total

    return 0


def collect_module_value(module_path, dry_run):
    staging_dir, copied = stage_filtered_tree(module_path)
    output_json_path = os.path.join(staging_dir, "scc-output.json")
    try:
        if copied == 0:
            return 0

        run_command(
            [
                TOOL_NAME,
                "--format",
                "json",
                "--output",
                output_json_path,
                "--no-cocomo",
                "--no-complexity",
                staging_dir,
            ],
            dry_run,
        )

        if dry_run:
            return 0

        if not os.path.isfile(output_json_path):
            return 0

        with open(output_json_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return parse_scc_json(payload)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def write_project_results(results_dir, project, timestamp_utc, rows, run_id):
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(
        results_dir,
        f"{project}-{timestamp_utc}-{METRIC_NAME}-{VARIANT_NAME}.jsonl",
    )
    write_jsonl_rows(output_path, rows, run_id=run_id)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Collect lines-of-code using scc.")
    parser.add_argument("--app-dir", default="/app", help="Mounted source directory.")
    parser.add_argument("--results-dir", default="/results", help="Output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args()

    timestamp_utc = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)

    if not projects:
        if args.dry_run:
            print("DRY_RUN: no projects discovered under /app")
        return 0

    tool_version = get_tool_version(args.dry_run)

    for project_name, project_path in projects:
        modules = discover_modules(project_name, project_path)
        rows = []

        for module_name, module_path in modules:
            value = collect_module_value(module_path, args.dry_run)
            rows.append(
                {
                    "project": project_name,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module_name,
                    "value": value,
                    "tool": TOOL_NAME,
                    "tool_version": tool_version,
                    "parameters": {
                        "count_mode": "code_only",
                        "ignore_hidden_dirs": True,
                        "ignored_dirs": sorted(VENDOR_DIRS),
                    },
                    "timestamp_utc": timestamp_utc,
                }
            )

        if args.dry_run:
            print(
                "DRY_RUN:",
                f"would write {len(rows)} row(s) to /results/{project_name}-{timestamp_utc}-{METRIC_NAME}-{VARIANT_NAME}.jsonl",
            )
        else:
            write_project_results(args.results_dir, project_name, timestamp_utc, rows, run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
