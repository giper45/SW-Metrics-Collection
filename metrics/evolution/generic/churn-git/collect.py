#!/usr/bin/env python3
import argparse
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

from result_writer import filter_projects, generate_run_id, run_collector, write_jsonl_rows

METRIC_NAME = "code-churn"
VARIANT_NAME = "git-default"
TOOL_NAME = "git"

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


def is_test_path(path):
    segments = [part.lower() for part in path.split("/") if part]
    for segment in segments:
        if segment in TEST_DIR_NAMES or segment.startswith("test"):
            return True
    return False


def contains_ignored_dir(path):
    segments = [part for part in path.split("/") if part]
    return any(seg in VENDOR_DIRS or seg.startswith(".") for seg in segments)


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
    out, _, _ = run_command(["git", "--version"], dry_run)
    if dry_run:
        return "dry-run"
    match = re.search(r"(\d+(?:\.\d+)+)", out)
    return match.group(1) if match else (out.strip() or "unknown")


def find_git_root(project_path, dry_run):
    out, _, code = run_command(
        ["git", "-C", project_path, "rev-parse", "--show-toplevel"],
        dry_run,
        allowed_returncodes={0, 128},
    )
    if dry_run:
        return project_path
    if code != 0:
        return None
    root = out.strip()
    return root or None


def parse_git_numstat_file_map(raw_output, project_prefix=""):
    totals = {}
    prefix = normalize_path(project_prefix).strip("/")

    for line in raw_output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_raw, deleted_raw, file_path = parts
        file_norm = normalize_path(file_path)

        if prefix:
            if file_norm == prefix:
                rel = ""
            elif file_norm.startswith(prefix + "/"):
                rel = file_norm[len(prefix) + 1 :]
            else:
                continue
        else:
            rel = file_norm

        rel = rel.strip()
        if not rel:
            continue
        if is_test_path(rel) or contains_ignored_dir(rel):
            continue

        try:
            added = int(added_raw) if added_raw.isdigit() else 0
            deleted = int(deleted_raw) if deleted_raw.isdigit() else 0
        except ValueError:
            continue

        totals[rel] = totals.get(rel, 0.0) + float(added + deleted)

    return {k: round(v, 6) for k, v in totals.items()}


def parse_git_numstat(raw_output):
    return round(sum(parse_git_numstat_file_map(raw_output).values()), 6)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def common_parameters():
    return {
        "category": "evolution",
        "granularity": "file",
        "scope_filter": "no_tests",
        "formula": "sum(added+deleted)",
        "ignored_dirs": sorted(VENDOR_DIRS),
    }


def skipped_project_row(project, tool_version, timestamp, skip_reason):
    return {
        "project": project,
        "metric": METRIC_NAME,
        "variant": VARIANT_NAME,
        "component_type": "project",
        "component": project,
        "status": "skipped",
        "skip_reason": skip_reason,
        "value": None,
        "tool": TOOL_NAME,
        "tool_version": tool_version,
        "parameters": common_parameters(),
        "timestamp_utc": timestamp,
    }


def classify_git_log_failure(error_text):
    text = str(error_text or "").lower()
    if (
        "read-only file system" in text
        and (
            "promisor remote" in text
            or "fetch-pack" in text
            or "tmp_pack_" in text
        )
    ):
        return "partial_clone_read_only"
    return "git_log_failed"


def collect_project_rows(project, project_path, tool_version, timestamp, dry_run):
    git_root = find_git_root(project_path, dry_run)
    if git_root is None:
        return [skipped_project_row(project, tool_version, timestamp, "not_a_git_repository")]

    rel_project = normalize_path(os.path.relpath(project_path, git_root))
    if rel_project == ".":
        rel_project = ""

    cmd = ["git", "-C", git_root, "log", "--numstat", "--format=tformat:"]
    if rel_project:
        cmd.extend(["--", rel_project])

    try:
        stdout, _, _ = run_command(cmd, dry_run)
    except RuntimeError as exc:
        reason = classify_git_log_failure(str(exc))
        return [skipped_project_row(project, tool_version, timestamp, reason)]
    if dry_run:
        return []

    file_values = parse_git_numstat_file_map(stdout, project_prefix=rel_project)
    if not file_values:
        return [skipped_project_row(project, tool_version, timestamp, "no_trackable_files")]

    rows = []
    for rel, value in sorted(file_values.items()):
        rows.append(
            {
                "project": project,
                "metric": METRIC_NAME,
                "variant": VARIANT_NAME,
                "component_type": "file",
                "component": rel,
                "value": value,
                "tool": TOOL_NAME,
                "tool_version": tool_version,
                "parameters": common_parameters(),
                "timestamp_utc": timestamp,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Collect file-level code churn from git history")
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
        rows = collect_project_rows(project, project_path, tool_version, timestamp, args.dry_run)

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue

        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
