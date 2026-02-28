#!/usr/bin/env python3
import argparse
import csv
import json
import os
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

METRIC_NAME = "lcom"
VARIANT_NAME = "ck-default"
TOOL_NAME = "ck"
TOOL_JAR = "/opt/tools/ck.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def discover_modules(project_name, project_path):
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []
    modules = [
        (name, os.path.join(project_path, name))
        for name in entries
        if os.path.isdir(os.path.join(project_path, name)) and not is_ignored_dir(name)
    ]
    return modules or [(project_name, project_path)]


def run_command(cmd, dry_run):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )


def choose_ck_input_path(module_path):
    candidates = [
        os.path.join(module_path, "main", "java"),
        os.path.join(module_path, "src", "main", "java"),
        module_path,
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return module_path


def resolve_ck_csv_path(out_dir, filename):
    path = os.path.join(out_dir, filename)
    if os.path.isfile(path):
        return path
    fallback = f"{out_dir}{filename}"
    if os.path.isfile(fallback):
        return fallback
    return path


def parse_ck_csv(class_csv_path):
    rows = []
    if not os.path.isfile(class_csv_path):
        return rows
    with open(class_csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({k.strip().lower(): v for k, v in row.items()})
    return rows


def mean_numeric(rows, key):
    values = []
    for row in rows:
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            values.append(float(raw))
        except ValueError:
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def collect_module_value(module_path, dry_run):
    out_dir = tempfile.mkdtemp(prefix="ck-out-")
    try:
        ck_input = choose_ck_input_path(module_path)
        run_command(
            ["java", "-jar", TOOL_JAR, ck_input, "false", "0", "false", out_dir + os.sep],
            dry_run,
        )
        if dry_run:
            return 0.0
        rows = parse_ck_csv(resolve_ck_csv_path(out_dir, "class.csv"))
        return mean_numeric(rows, "lcom")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect module-level LCOM with CK")
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
    version = os.environ.get("CK_VERSION", "unknown") if not args.dry_run else "dry-run"

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path):
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module,
                    "value": collect_module_value(module_path, args.dry_run),
                    "tool": TOOL_NAME,
                    "tool_version": version,
                    "parameters": {
                        "category": "cohesion",
                        "aggregation": "class_lcom_mean",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "tool_output": "class.csv",
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
