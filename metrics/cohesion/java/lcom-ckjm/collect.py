#!/usr/bin/env python3
import argparse
import math
import os
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

from result_writer import filter_projects, generate_run_id, run_collector, write_jsonl_rows

METRIC_NAME = "lcom"
VARIANT_NAME = "ckjm-default"
TOOL_NAME = "ckjm"
CKJM_MAIN_CLASS = "gr.spinellis.ckjm.MetricsFilter"
CKJM_CLASSPATH = "/opt/tools/ckjm.jar:/opt/tools/commons-lang3.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
BYTECODE_DIR_CANDIDATES = (
    "target/classes",
    "build/classes/java/main",
    "build/classes/kotlin/main",
    "build/classes",
    "out/production",
)


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


def run_command(cmd, dry_run, stdin_text=""):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return
    completed = subprocess.run(
        cmd,
        input=str(stdin_text),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout or ""


def discover_class_files(base_dir):
    files = []
    for root, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d))
        for filename in sorted(filenames):
            if filename.endswith(".class") and not filename.startswith("."):
                files.append(os.path.join(root, filename))
    return files


def discover_module_class_files(module_path):
    class_files = []
    seen = set()
    for rel_dir in BYTECODE_DIR_CANDIDATES:
        candidate_dir = os.path.join(module_path, rel_dir)
        if not os.path.isdir(candidate_dir):
            continue
        for path in discover_class_files(candidate_dir):
            if path in seen:
                continue
            seen.add(path)
            class_files.append(path)
    return class_files


def safe_float(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def parse_ckjm_lcom_values(raw_output):
    values = []
    for line in str(raw_output or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 7:
            continue
        # CKJM plain output format:
        # class WMC DIT NOC CBO RFC LCOM Ca NPM
        lcom_value = safe_float(parts[6])
        if lcom_value is None:
            continue
        values.append(float(lcom_value))
    return values


def mean_numeric(values):
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def collect_module_stats(module_path, dry_run):
    class_files = discover_module_class_files(module_path)
    if not class_files:
        return {"value": 0.0, "class_files_found": 0, "classes_measured": 0}

    output = run_command(
        [
            "java",
            "-cp",
            CKJM_CLASSPATH,
            CKJM_MAIN_CLASS,
        ],
        dry_run,
        stdin_text="\n".join(class_files) + "\n",
    )
    if dry_run:
        return {"value": 0.0, "class_files_found": len(class_files), "classes_measured": 0}

    lcom_values = parse_ckjm_lcom_values(output)
    return {
        "value": mean_numeric(lcom_values),
        "class_files_found": len(class_files),
        "classes_measured": len(lcom_values),
    }


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect module-level LCOM with CKJM")
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
    version = os.environ.get("CKJM_VERSION", "unknown") if not args.dry_run else "dry-run"

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path):
            module_stats = collect_module_stats(module_path, args.dry_run)
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module,
                    "value": module_stats["value"],
                    "tool": TOOL_NAME,
                    "tool_version": version,
                    "parameters": {
                        "category": "cohesion",
                        "aggregation": "class_lcom_mean",
                        "metric_source": "dspinellis-ckjm-bytecode",
                        "class_files_found": int(module_stats["class_files_found"]),
                        "classes_measured": int(module_stats["classes_measured"]),
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "tool_output": "plain-text",
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
