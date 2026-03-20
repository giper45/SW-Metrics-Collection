#!/usr/bin/env python3
"""Shared collector utilities for result writing and project/run metadata.

Historical note:
- This module started as a pure JSONL writer helper.
"""

import json
import os
import subprocess
import uuid
from collections import OrderedDict
from pathlib import Path

from common_types import MetricRow, RowCustomiser
from data_manager import apply_row_customiser, is_finite_number, is_number, normalize_row_scalars

SCHEMA_VERSION = "1.0"
DEFAULT_STATUS = "ok"
ALLOWED_STATUSES = {"ok", "skipped"}

REQUIRED_FIELDS = {
    "project",
    "metric",
    "variant",
    "component_type",
    "component",
    "value",
    "tool",
    "tool_version",
    "parameters",
    "timestamp_utc",
    "schema_version",
    "run_id",
    "status",
}

OPTIONAL_FIELDS = {"submetric", "skip_reason"}

CANONICAL_ORDER = [
    "schema_version",
    "run_id",
    "project",
    "metric",
    "variant",
    "component_type",
    "component",
    "submetric",
    "status",
    "skip_reason",
    "value",
    "tool",
    "tool_version",
    "parameters",
    "timestamp_utc",
]


def resolve_app_dir(default="/app"):
    candidate = (
        os.environ.get("SRC_ROOT")
        or os.environ.get("METRIC_APP_DIR")
        or default
    )
    return str(candidate).strip() or default


def resolve_results_dir(default="/results"):
    candidate = (
        os.environ.get("RESULTS_DIR")
        or os.environ.get("METRIC_RESULTS_DIR")
        or default
    )
    return str(candidate).strip() or default


def filter_projects(projects, app_dir=None):
    app_dir = str(app_dir or resolve_app_dir()).strip()
    selected = list(projects)

    project_name = str(os.environ.get("PROJECT_NAME", "")).strip()
    repo_subdir = str(os.environ.get("REPO_SUBDIR", "")).strip()
    required_name = project_name or repo_subdir
    if required_name:
        selected = [
            item
            for item in selected
            if str(item[0]).strip() == required_name
            or os.path.basename(str(item[1]).rstrip("/")) == required_name
        ]

    if selected:
        return selected

    if required_name and os.path.isdir(os.path.join(app_dir, required_name)):
        return [(required_name, os.path.join(app_dir, required_name))]
    return selected


def generate_run_id():
    """Generate a run id.

    Returns:
        str: Taken from env (`METRIC_RUN_ID`/`RUN_ID`) or a fresh UUID4.
    """
    forced = (os.environ.get("METRIC_RUN_ID") or os.environ.get("RUN_ID") or "").strip()
    if forced:
        return forced
    return str(uuid.uuid4())


def _is_number(value):
    return is_number(value)


def _safe_run(cmd):
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip()


def _project_git_metadata(project_name, app_dir="/app"):
    """Return repo commit and dirty

    Args:
        project_name (str): the project name
        app_dir (str, optional): the folder . Defaults to "/app".

    Returns:
        dict: An object containing repo_commit and repo_dirty
    """
    if not isinstance(project_name, str) or not project_name.strip():
        return {"repo_commit": "unknown", "repo_dirty": False}

    project_path = os.path.join(app_dir, project_name)
    if not os.path.isdir(project_path):
        return {"repo_commit": "unknown", "repo_dirty": False}

    commit = _safe_run(["git", "-C", project_path, "rev-parse", "HEAD"]) or "unknown"
    dirty_raw = _safe_run(["git", "-C", project_path, "status", "--porcelain"])
    dirty = bool(dirty_raw) if dirty_raw is not None else False
    return {"repo_commit": commit, "repo_dirty": dirty}


def _inject_repo_metadata(row, app_dir="/app", cache=None):
    cache = cache if cache is not None else {}
    parameters = row.get("parameters")
    if not isinstance(parameters, dict):
        return row

    project = row.get("project")
    if project not in cache:
        cache[project] = _project_git_metadata(project, app_dir=app_dir)
    metadata = cache[project]

    updated_parameters = dict(parameters)
    updated_parameters.setdefault("repo_commit", metadata["repo_commit"])
    updated_parameters.setdefault("repo_dirty", metadata["repo_dirty"])
    updated = dict(row)
    updated["parameters"] = updated_parameters
    return updated


def _validate_row(row, required_fields=None, allow_optional=None):
    if not isinstance(row, dict):
        raise ValueError("row must be a JSON object")

    required = set(required_fields or REQUIRED_FIELDS)
    allowed_optional = set(OPTIONAL_FIELDS | set(allow_optional or []))
    keys = set(row.keys())
    missing = sorted(required - keys)
    extra = sorted(keys - required - allowed_optional)
    if missing:
        raise ValueError(f"missing required keys: {missing}")
    if extra:
        raise ValueError(f"unexpected keys: {extra}")

    for key in ("schema_version", "run_id", "project", "metric", "variant", "component_type", "component", "tool", "tool_version", "timestamp_utc"):
        if not isinstance(row.get(key), str):
            raise ValueError(f"{key} must be string")

    status = row.get("status")
    if not isinstance(status, str):
        raise ValueError("status must be string")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of: {sorted(ALLOWED_STATUSES)}")

    if status == "ok":
        if not _is_number(row.get("value")):
            raise ValueError("value must be number when status=ok")
        if not is_finite_number(row.get("value")):
            raise ValueError("value must be finite when status=ok")
    else:
        if row.get("value") is not None:
            raise ValueError("value must be null when status=skipped")
        if "skip_reason" in row and not isinstance(row.get("skip_reason"), str):
            raise ValueError("skip_reason must be string")

    if not isinstance(row.get("parameters"), dict):
        raise ValueError("parameters must be object")

    if "submetric" in row and not isinstance(row["submetric"], str):
        raise ValueError("submetric must be string")


def _ordered_row(row, canonical_order=None):
    order = list(canonical_order or CANONICAL_ORDER)
    ordered = OrderedDict()
    for key in order:
        if key in row:
            ordered[key] = row[key]
    for key in sorted(row.keys()):
        if key not in ordered:
            ordered[key] = row[key]
    return ordered


def enrich_row(row, run_id, schema_version=SCHEMA_VERSION):
    """Attach schema/run metadata and normalize default status."""
    enriched = dict(row)
    enriched["schema_version"] = schema_version
    enriched["run_id"] = run_id
    enriched["status"] = str(enriched.get("status", DEFAULT_STATUS))
    return enriched


def write_jsonl_rows(
    path: str,
    rows: list[MetricRow],
    run_id: str,
    schema_version: str = SCHEMA_VERSION,
    allow_optional=None,
    required_fields=None,
    canonical_order=None,
    row_customiser: RowCustomiser | None = None,
):
    """Validate/enrich rows and write canonical JSONL output."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    metadata_cache = {}
    prepared = apply_row_customiser(
        [
            _inject_repo_metadata(
                enrich_row(row, run_id=run_id, schema_version=schema_version),
                app_dir=resolve_app_dir("/app"),
                cache=metadata_cache,
            )
            for row in rows
        ],
        row_customiser=row_customiser,
    )
    required = set(required_fields or REQUIRED_FIELDS)
    required.update({"schema_version", "run_id"})
    for index, row in enumerate(prepared, start=1):
        try:
            _validate_row(row, required_fields=required, allow_optional=allow_optional)
        except ValueError as exc:
            raise ValueError(f"row {index}: {exc}") from exc

    with open(path, "w", encoding="utf-8") as handle:
        for row in prepared:
            serializable_row = normalize_row_scalars(_ordered_row(row, canonical_order=canonical_order))
            handle.write(
                json.dumps(
                    serializable_row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
