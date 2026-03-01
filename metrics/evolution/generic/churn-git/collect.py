#!/usr/bin/env python3
import argparse
import os


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import detect_tool_version, run_collector, run_command_details
from error_manager import ToolExecutionError
from utils import metric_output_path, utc_timestamp_now
from config import TEST_DIR_NAMES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_projects,
    is_ignored_dir,
    normalize_path)

METRIC_NAME = "code-churn"
VARIANT_NAME = "git-default"
TOOL_NAME = "git"


def is_test_path(path):
    segments = [part.lower() for part in path.split("/") if part]
    for segment in segments:
        if segment in TEST_DIR_NAMES or segment.startswith("test"):
            return True
    return False


def contains_ignored_dir(path):
    segments = [part for part in path.split("/") if part]
    return any(seg in VENDOR_DIRS or seg.startswith(".") for seg in segments)


def find_git_root(project_path):
    out, _, code = run_command_details(
        ["git", "-C", project_path, "rev-parse", "--show-toplevel"],
        allowed_returncodes={0, 128})
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


def collect_project_rows(project, project_path, tool_version, timestamp):
    git_root = find_git_root(project_path)
    if git_root is None:
        return [skipped_project_row(project, tool_version, timestamp, "not_a_git_repository")]

    rel_project = normalize_path(os.path.relpath(project_path, git_root))
    if rel_project == ".":
        rel_project = ""

    cmd = ["git", "-C", git_root, "log", "--numstat", "--format=tformat:"]
    if rel_project:
        cmd.extend(["--", rel_project])

    try:
        stdout, _, _ = run_command_details(cmd)
    except ToolExecutionError as exc:
        reason = classify_git_log_failure(str(exc))
        raise ToolExecutionError(f"project={project}: {reason}") from exc
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
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = detect_tool_version(["git", "--version"])

    for project, project_path in projects:
        rows = collect_project_rows(project, project_path, tool_version, timestamp)

        target = metric_output_path(
            args.results_dir,
            project,
            timestamp,
            METRIC_NAME,
            TOOL_NAME,
            VARIANT_NAME,
        )
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
