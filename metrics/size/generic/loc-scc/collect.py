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

METRIC_NAME = "loc"
VARIANT_NAME = "scc-default"
TOOL_NAME = "scc"
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


def stage_project_tree(project_path):
    staging = tempfile.mkdtemp(prefix="metric-input-")
    rel_files = []

    for root, dirnames, filenames in os.walk(project_path):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d))
        for filename in sorted(filenames):
            if filename.startswith("."):
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


def parse_scc_file_values(payload, staging_root):
    values = {}
    staging_norm = normalize_path(staging_root).rstrip("/")

    def consume_file_row(row):
        if not isinstance(row, dict):
            return
        name = row.get("Location") or row.get("location") or row.get("Name") or row.get("name")
        code = row.get("Code") if "Code" in row else row.get("code")
        if not isinstance(name, str) or not isinstance(code, (int, float)):
            return
        if name.strip().lower() == "total":
            return
        path_norm = normalize_path(name)
        if path_norm.startswith(staging_norm + "/"):
            rel = path_norm[len(staging_norm) + 1 :]
        else:
            rel = path_norm.lstrip("./")
        values[normalize_path(rel)] = float(code)

    if isinstance(payload, list):
        for language_row in payload:
            if not isinstance(language_row, dict):
                continue
            files = language_row.get("Files") or language_row.get("files")
            if isinstance(files, list):
                for file_row in files:
                    consume_file_row(file_row)
            else:
                consume_file_row(language_row)
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for row in value:
                    consume_file_row(row)
            elif isinstance(value, dict):
                files = value.get("Files") or value.get("files")
                if isinstance(files, list):
                    for file_row in files:
                        consume_file_row(file_row)
                else:
                    consume_file_row(value)

    return values


def parse_scc_json(payload):
    if isinstance(payload, dict):
        totals = payload.get("totals")
        if isinstance(totals, dict) and isinstance(totals.get("Code"), (int, float)):
            return int(totals["Code"])
        if isinstance(payload.get("Code"), (int, float)):
            return int(payload["Code"])
        return 0

    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and str(row.get("Name", "")).lower() == "total":
                if isinstance(row.get("Code"), (int, float)):
                    return int(row["Code"])
        return sum(int(row["Code"]) for row in payload if isinstance(row, dict) and isinstance(row.get("Code"), (int, float)))

    return 0


def collect_project_values(project_path, dry_run):
    staging, rel_files = stage_project_tree(project_path)
    report_path = os.path.join(staging, "scc-report.json")
    try:
        if not rel_files:
            return rel_files, {}
        run_command(
            [
                TOOL_NAME,
                "--by-file",
                "--format",
                "json",
                "--output",
                report_path,
                "--no-cocomo",
                "--no-complexity",
                staging,
            ],
            dry_run,
        )
        if dry_run or not os.path.isfile(report_path):
            return rel_files, {}
        with open(report_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return rel_files, parse_scc_file_values(payload, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect file-level LOC using scc")
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
                    "skip_reason": "no_files_after_filtering",
                    "value": None,
                    "tool": TOOL_NAME,
                    "tool_version": version,
                    "parameters": {
                        "category": "size",
                        "count_mode": "code_only",
                        "granularity": "file",
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
                        "tool_version": version,
                        "parameters": {
                            "category": "size",
                            "count_mode": "code_only",
                            "granularity": "file",
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
