#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path


from result_writer import generate_run_id
from result_executor import run_collector, run_command_details
from data_manager import apply_row_customiser, write_csv_rows
from common_types import NormalizedMetricRow
from config import GENERIC_SOURCE_EXTENSIONS as SOURCE_EXTENSIONS
from config import TEST_DIR_NAMES, VENDOR_DIRS
from utils import utc_timestamp_now
from typing import Dict, List, Optional

from validator import REQUIRED_COLUMNS, validate_and_normalize_rows

EXCLUDED_DIR_NAMES = set(TEST_DIR_NAMES) | set(VENDOR_DIRS) | {"vendor"}

CANONICAL_METRICS = {
    "loc_code",
    "loc_comment",
    "loc_blank",
    "loc_total",
    "cc_mean",
    "cc_max",
    "ce",
    "ca",
    "instability",
    "lcom_mean",
}


def should_skip_dir(name: str) -> bool:
    return name.lower() in EXCLUDED_DIR_NAMES


def has_source_files(root: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        for filename in sorted(filenames):
            if Path(filename).suffix.lower() in SOURCE_EXTENSIONS:
                return True
    return False


def discover_projects(app_root: Path) -> List[Path]:
    if not app_root.is_dir():
        return []

    projects: List[Path] = []
    for child in sorted(app_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if (child / ".git").exists() or has_source_files(child):
            projects.append(child)
    return projects


def copy_filtered_project(source_project: Path) -> Path:
    staging_root = Path(tempfile.mkdtemp(prefix="metric-src-"))

    for dirpath, dirnames, filenames in os.walk(source_project):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        current = Path(dirpath)
        rel = current.relative_to(source_project)

        for filename in sorted(filenames):
            source_file = current / filename
            target_file = staging_root / rel / filename
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

    return staging_root


def detect_language(project_root: Path) -> str:
    has_java = False
    has_python = False

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        for filename in sorted(filenames):
            ext = Path(filename).suffix.lower()
            if ext == ".java":
                has_java = True
            elif ext == ".py":
                has_python = True

    if has_java and has_python:
        return "mixed"
    if has_java:
        return "java"
    if has_python:
        return "python"
    return "unknown"


def resolve_tool_version(version_override: str, version_command: str) -> str:
    if version_override:
        return version_override

    if not version_command.strip():
        return "unknown"

    try:
        stdout, stderr, _ = run_command_details(shlex.split(version_command))
    except Exception:
        return "unknown"

    raw = (stdout or stderr or "").strip()
    if not raw:
        return "unknown"

    first_line = raw.splitlines()[0].strip()
    match = re.search(r"\d+(?:\.\d+)+", first_line)
    return match.group(0) if match else first_line[:128]


def normalize_metric_name(raw_name: str, metric_key: str) -> str:
    normalized = (raw_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "code": "loc_code",
        "comment": "loc_comment",
        "comments": "loc_comment",
        "blank": "loc_blank",
        "total": "loc_total",
        "loc": "loc_total",
        "cc": "cc_mean",
        "avg_cc": "cc_mean",
        "mean_cc": "cc_mean",
        "max_cc": "cc_max",
        "i": "instability",
    }

    if normalized in aliases:
        return aliases[normalized]
    if normalized in CANONICAL_METRICS:
        return normalized

    fallback = {
        "loc": "loc_total",
        "cc": "cc_mean",
        "instability": "instability",
        "lcom": "lcom_mean",
    }
    return fallback.get(metric_key, normalized)


def default_unit(metric_name: str) -> str:
    return "ratio" if metric_name == "instability" else "count"


def cloc_rows_from_json(
    payload: Dict,
    entity_type: str,
    entity_id: str,
    language: str,
    tool_key: str,
    variant_key: str,
    scope_filter: str,
    path_hint: str) -> List[Dict]:
    summary = payload.get("SUM", {}) if isinstance(payload, dict) else {}
    code = float(summary.get("code", 0) or 0)
    comment = float(summary.get("comment", 0) or 0)
    blank = float(summary.get("blank", 0) or 0)
    total = code + comment + blank

    base = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "unit": "count",
        "language": language,
        "tool_key": tool_key,
        "variant_key": variant_key,
        "scope_filter": scope_filter,
        "path_hint": path_hint,
    }

    return [
        {**base, "metric_name": "loc_code", "metric_value": code},
        {**base, "metric_name": "loc_comment", "metric_value": comment},
        {**base, "metric_name": "loc_blank", "metric_value": blank},
        {**base, "metric_name": "loc_total", "metric_value": total},
    ]


def parse_raw_output(
    stdout: str,
    metric_key: str,
    tool_key: str,
    entity_type: str,
    entity_id: str,
    language: str,
    variant_key: str,
    scope_filter: str,
    path_hint: str) -> List[Dict]:
    rows: List[Dict] = []

    if metric_key == "loc" and tool_key == "cloc":
        try:
            payload = json.loads(stdout or "{}")
            if isinstance(payload, dict):
                return cloc_rows_from_json(
                    payload,
                    entity_type,
                    entity_id,
                    language,
                    tool_key,
                    variant_key,
                    scope_filter,
                    path_hint)
        except Exception:
            pass

    parsed: Optional[object]
    try:
        parsed = json.loads(stdout)
    except Exception:
        parsed = None

    if isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue

            metric_name = normalize_metric_name(
                str(item.get("metric_name") or item.get("metric") or metric_key),
                metric_key)
            raw_value = item.get("metric_value", item.get("value", 0))
            try:
                metric_value = float(raw_value)
            except Exception:
                continue

            rows.append(
                {
                    "entity_type": str(item.get("entity_type") or entity_type),
                    "entity_id": str(item.get("entity_id") or entity_id),
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "unit": str(item.get("unit") or default_unit(metric_name)),
                    "language": str(item.get("language") or language),
                    "tool_key": str(item.get("tool_key") or tool_key),
                    "variant_key": str(item.get("variant_key") or variant_key),
                    "scope_filter": str(item.get("scope_filter") or scope_filter),
                    "path_hint": str(item.get("path_hint") or path_hint),
                }
            )

    elif isinstance(parsed, dict):
        for key in sorted(parsed.keys()):
            value = parsed[key]
            if isinstance(value, (int, float)):
                metric_name = normalize_metric_name(str(key), metric_key)
                rows.append(
                    {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "metric_name": metric_name,
                        "metric_value": float(value),
                        "unit": default_unit(metric_name),
                        "language": language,
                        "tool_key": tool_key,
                        "variant_key": variant_key,
                        "scope_filter": scope_filter,
                        "path_hint": path_hint,
                    }
                )

    if not rows:
        line_pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*$")
        for raw_line in (stdout or "").splitlines():
            match = line_pattern.match(raw_line.strip())
            if not match:
                continue

            metric_name = normalize_metric_name(match.group(1), metric_key)
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "metric_name": metric_name,
                    "metric_value": float(match.group(2)),
                    "unit": default_unit(metric_name),
                    "language": language,
                    "tool_key": tool_key,
                    "variant_key": variant_key,
                    "scope_filter": scope_filter,
                    "path_hint": path_hint,
                }
            )

    return rows


def write_csv(path: Path, rows: List[NormalizedMetricRow]) -> None:
    write_csv_rows(path, rows, columns=REQUIRED_COLUMNS)


def write_manifest(path: Path, manifest: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def apply_project_row_customisation(rows: List[Dict], path_hint: str) -> List[Dict]:
    def _customiser(row: Dict) -> Dict:
        updated = dict(row)
        if not str(updated.get("path_hint", "")).strip():
            updated["path_hint"] = path_hint
        return updated

    return apply_row_customiser(rows, row_customiser=_customiser)


def run_for_project(
    project_path: Path,
    run_id: str,
    app_root: Path,
    results_root: Path,
    schema_version: str,
    metric_key: str,
    tool_key: str,
    variant_key: str,
    tool_version: str,
    container_image: str,
    command_template: str,
    entity_type: str,
    scope_filter: str) -> str:
    output_dir = results_root / project_path.name / run_id / metric_key / tool_key
    manifest_path = output_dir / "manifest.json"
    data_path = output_dir / "data.csv"

    status = "success"
    error_message: Optional[str] = None
    rows: List[Dict] = []
    command_executed = ""
    filtered_project: Optional[Path] = None

    try:
        filtered_project = copy_filtered_project(project_path)
        language = detect_language(filtered_project)
        entity_id = project_path.name
        path_hint = str(project_path.relative_to(app_root))

        formatted_command = command_template.format(
            project_path=str(filtered_project),
            original_project_path=str(project_path),
            project_name=project_path.name)
        command_args = shlex.split(formatted_command)
        command_executed = " ".join(shlex.quote(arg) for arg in command_args)

        stdout, _, _ = run_command_details(command_args)

        parsed_rows = parse_raw_output(
            stdout=stdout,
            metric_key=metric_key,
            tool_key=tool_key,
            entity_type=entity_type,
            entity_id=entity_id,
            language=language,
            variant_key=variant_key,
            scope_filter=scope_filter,
            path_hint=path_hint)
        rows = apply_project_row_customisation(
            validate_and_normalize_rows(parsed_rows),
            path_hint=path_hint,
        )

    except Exception as exc:
        status = "error"
        error_message = str(exc)
        rows = []

    finally:
        if filtered_project is not None:
            shutil.rmtree(filtered_project, ignore_errors=True)

    write_csv(data_path, rows)

    manifest = {
        "schema_version": schema_version,
        "project": project_path.name,
        "run_id": run_id,
        "metric_key": metric_key,
        "tool_key": tool_key,
        "tool_version": tool_version,
        "container_image": container_image,
        "source_path": str(project_path),
        "generated_at_utc": utc_timestamp_now(),
        "command": command_executed or command_template,
        "status": status,
    }
    if error_message:
        manifest["error_message"] = error_message

    write_manifest(manifest_path, manifest)
    return status


def main() -> int:
    app_root = Path(os.environ.get("SRC_ROOT", os.environ.get("APP_ROOT", "/app")))
    results_root = Path(os.environ.get("RESULTS_DIR", os.environ.get("RESULTS_ROOT", "/results")))

    schema_version = os.environ.get("SCHEMA_VERSION", "1.0")
    metric_key = os.environ.get("METRIC_KEY", "loc").strip()
    tool_key = os.environ.get("TOOL_KEY", "cloc").strip()
    variant_key = os.environ.get("VARIANT_KEY", "default").strip() or "default"
    entity_type = os.environ.get("ENTITY_TYPE", "project").strip() or "project"
    scope_filter = os.environ.get("SCOPE_FILTER", "no_tests").strip() or "no_tests"
    container_image = os.environ.get("CONTAINER_IMAGE", "normalized-collector:latest").strip()

    command_template = os.environ.get("COMMAND", "").strip()
    if not command_template:
        command_template = "cloc --json --quiet --skip-uniqueness {project_path}"

    tool_version = resolve_tool_version(
        version_override=os.environ.get("TOOL_VERSION", "").strip(),
        version_command=os.environ.get("TOOL_VERSION_COMMAND", "cloc --version").strip())

    run_id = generate_run_id()
    projects = discover_projects(app_root)
    required_project = (
        os.environ.get("PROJECT_NAME")
        or os.environ.get("REPO_SUBDIR")
        or ""
    ).strip()
    if required_project:
        projects = [project for project in projects if project.name == required_project]
        if not projects and (app_root / required_project).is_dir():
            projects = [app_root / required_project]
    if not projects:
        return 0

    any_error = False
    for project_path in projects:
        status = run_for_project(
            project_path=project_path,
            run_id=run_id,
            app_root=app_root,
            results_root=results_root,
            schema_version=schema_version,
            metric_key=metric_key,
            tool_key=tool_key,
            variant_key=variant_key,
            tool_version=tool_version,
            container_image=container_image,
            command_template=command_template,
            entity_type=entity_type,
            scope_filter=scope_filter)
        if status != "success":
            any_error = True

    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
