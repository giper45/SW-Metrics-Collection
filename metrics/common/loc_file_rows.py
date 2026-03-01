#!/usr/bin/env python3
"""Shared helpers for file-level LOC collectors."""

from __future__ import annotations

from config import VENDOR_DIRS
from input_manager import stage_source_tree


def stage_project_files(project_path):
    staging, rel_files = stage_source_tree(project_path, vendor_dirs=VENDOR_DIRS)
    return staging, sorted(rel_files)


def build_file_loc_rows(
    *,
    project,
    metric,
    variant,
    tool,
    tool_version,
    timestamp_utc,
    rel_files,
    values,
):
    base_parameters = {
        "category": "size",
        "count_mode": "code_only",
        "granularity": "file",
        "ignored_dirs": sorted(VENDOR_DIRS),
    }

    if not rel_files:
        return [
            {
                "project": project,
                "metric": metric,
                "variant": variant,
                "component_type": "project",
                "component": project,
                "status": "skipped",
                "skip_reason": "no_files_after_filtering",
                "value": None,
                "tool": tool,
                "tool_version": tool_version,
                "parameters": dict(base_parameters),
                "timestamp_utc": timestamp_utc,
            }
        ]

    rows = []
    for rel in rel_files:
        rows.append(
            {
                "project": project,
                "metric": metric,
                "variant": variant,
                "component_type": "file",
                "component": rel,
                "value": float(values.get(rel, 0.0)),
                "tool": tool,
                "tool_version": tool_version,
                "parameters": dict(base_parameters),
                "timestamp_utc": timestamp_utc,
            }
        )
    return rows
