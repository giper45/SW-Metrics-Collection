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

METRIC_NAME = "test-coverage"
VARIANT_NAME = "jacoco-default"
TOOL_NAME = "jacoco"
JACOCO_VERSION = "0.8.11"

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


def copy_tree(src, dst):
    copied = 0
    for root, dirnames, filenames in os.walk(src):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            src_file = os.path.join(root, filename)
            if not os.path.isfile(src_file):
                continue
            rel = os.path.relpath(src_file, src)
            dst_file = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
    return copied


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


def get_maven_version(dry_run):
    out, _, _ = run_command(["mvn", "-version"], dry_run)
    if dry_run:
        return "dry-run"
    match = re.search(r"Apache Maven\s+([0-9][0-9A-Za-z_.-]*)", out)
    return match.group(1) if match else "unknown"


def _counter_ratio(counter_node):
    missed = float(counter_node.get("missed", "0") or 0)
    covered = float(counter_node.get("covered", "0") or 0)
    total = missed + covered
    if total <= 0:
        return 0.0
    return round(covered / total, 6)


def parse_jacoco_instruction_ratio(xml_path):
    if not os.path.isfile(xml_path):
        return 0.0
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return 0.0

    for counter in root.findall("counter"):
        if counter.get("type") == "INSTRUCTION":
            return _counter_ratio(counter)
    return 0.0


def parse_jacoco_file_instruction_ratios(xml_path):
    if not os.path.isfile(xml_path):
        return {}
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return {}

    values = {}
    for package_node in root.findall("package"):
        package_name = package_node.get("name", "")
        for source_node in package_node.findall("sourcefile"):
            source_name = source_node.get("name")
            if not isinstance(source_name, str) or not source_name:
                continue
            counter = None
            for candidate in source_node.findall("counter"):
                if candidate.get("type") == "INSTRUCTION":
                    counter = candidate
                    break
            if counter is None:
                continue
            package_prefix = normalize_path(package_name).strip("/")
            rel = f"{package_prefix}/{source_name}" if package_prefix else source_name
            values[normalize_path(rel)] = _counter_ratio(counter)
    return values


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def collect_project_values(project_path, dry_run):
    staging = tempfile.mkdtemp(prefix="jacoco-project-")
    details = {"maven_exit_code": 0, "maven_ran": False}
    try:
        copied = copy_tree(project_path, staging)
        if copied == 0:
            return None, details, "no_files_after_filtering"

        pom_path = os.path.join(staging, "pom.xml")
        if not os.path.isfile(pom_path):
            return None, details, "pom_xml_not_found"

        cmd = [
            "mvn",
            "-q",
            "-DskipTests=false",
            "-DfailIfNoTests=false",
            "-Dmaven.test.failure.ignore=true",
            "test",
            f"org.jacoco:jacoco-maven-plugin:{JACOCO_VERSION}:report",
        ]

        if dry_run:
            run_command(cmd, True, cwd=staging)
            details["maven_ran"] = True
            return {}, details, None

        _, _, code = run_command(cmd, False, cwd=staging, allowed_returncodes={0, 1})
        details = {"maven_exit_code": int(code), "maven_ran": True}

        report_path = os.path.join(staging, "target", "site", "jacoco", "jacoco.xml")
        values = parse_jacoco_file_instruction_ratios(report_path)
        if not values:
            return None, details, "jacoco_report_missing_or_empty"

        return values, details, None
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Collect file-level Java coverage ratio using JaCoCo")
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
    maven_version = get_maven_version(args.dry_run)

    for project, project_path in projects:
        values, details, skip_reason = collect_project_values(project_path, args.dry_run)
        rows = []

        base_parameters = {
            "category": "testing",
            "scope_filter": "all",
            "counter": "INSTRUCTION",
            "jacoco_version": JACOCO_VERSION,
            "maven_version": maven_version,
            "granularity": "file",
            **details,
        }

        if values is None:
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "project",
                    "component": project,
                    "status": "skipped",
                    "skip_reason": skip_reason or "coverage_unavailable",
                    "value": None,
                    "tool": TOOL_NAME,
                    "tool_version": JACOCO_VERSION if not args.dry_run else "dry-run",
                    "parameters": base_parameters,
                    "timestamp_utc": timestamp,
                }
            )
        else:
            for rel, ratio in sorted(values.items()):
                rows.append(
                    {
                        "project": project,
                        "metric": METRIC_NAME,
                        "variant": VARIANT_NAME,
                        "component_type": "file",
                        "component": rel,
                        "value": float(ratio),
                        "tool": TOOL_NAME,
                        "tool_version": JACOCO_VERSION if not args.dry_run else "dry-run",
                        "parameters": base_parameters,
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
