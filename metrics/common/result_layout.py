#!/usr/bin/env python3
"""Shared filesystem layout helpers for raw and artifact metric results."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


SOFTWARE_METRICS_CATEGORY = "software-metrics"
VULNERABILITIES_CATEGORY = "vulnerabilities"
JSONL_SUBDIR = "jsonl"
ARTIFACTS_SUBDIR = "artifacts"
SARIF_SUBDIR = "sarif"
VULNERABILITY_METRICS = {"vulnerability-findings"}


def metric_result_category(metric_name: str) -> str:
    normalized = str(metric_name or "").strip().lower()
    if normalized in VULNERABILITY_METRICS:
        return VULNERABILITIES_CATEGORY
    return SOFTWARE_METRICS_CATEGORY


def metric_jsonl_dir(results_dir: str | os.PathLike[str], metric_name: str) -> Path:
    return Path(results_dir) / metric_result_category(metric_name) / JSONL_SUBDIR


def metric_output_path(
    results_dir: str | os.PathLike[str],
    project: str,
    timestamp: str,
    metric_name: str,
    tool_name: str,
    variant_name: str,
) -> str:
    filename = f"{project}-{timestamp}-{metric_name}-{tool_name}-{variant_name}.jsonl"
    return str(metric_jsonl_dir(results_dir, metric_name) / filename)


def vulnerability_sarif_path(
    results_dir: str | os.PathLike[str],
    kind: str,
    project: str,
    timestamp_utc: str,
    tool: str,
    variant: str,
    metric_name: str = "vulnerability-findings",
) -> str:
    safe_kind = str(kind or "").strip() or "raw"
    filename = f"{project}-{timestamp_utc}-{metric_name}-{tool}-{variant}.sarif"
    return str(
        Path(results_dir)
        / VULNERABILITIES_CATEGORY
        / ARTIFACTS_SUBDIR
        / SARIF_SUBDIR
        / safe_kind
        / filename
    )


def iter_vulnerability_jsonl_files(results_dir: str | os.PathLike[str]) -> Iterable[Path]:
    root = Path(results_dir)
    for path in sorted(root.rglob("*.jsonl")):
        if not path.is_file():
            continue
        if "-vulnerability-findings-" not in path.name:
            continue
        yield path
