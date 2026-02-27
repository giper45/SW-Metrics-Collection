#!/usr/bin/env python3
import argparse
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


def _parse_expected_tokens(raw_values: Iterable[str]) -> Set[Tuple[str, str, str]]:
    expected: Set[Tuple[str, str, str]] = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        pieces = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
        for token in pieces:
            for separator in ("|", ":"):
                if separator in token:
                    parts = [part.strip() for part in token.split(separator)]
                    if len(parts) == 3 and all(parts):
                        expected.add((parts[0], parts[1], parts[2]))
                    break
    return expected


def _choose_primary_component_type(
    counts: Dict[str, int],
    preferred: str = "",
) -> str:
    preferred_type = str(preferred or "").strip()
    if preferred_type:
        return preferred_type
    if not counts:
        return "file"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _timestamp_bounds(values: Iterable[str]) -> Tuple[str, str]:
    timestamps = sorted({value for value in values if isinstance(value, str) and value.strip()})
    if not timestamps:
        now_utc = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        return now_utc, now_utc
    return timestamps[0], timestamps[-1]


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _resolve_manifest_run_id(requested_run_id: str, observed_run_ids: Set[str]) -> str:
    requested = str(requested_run_id or "").strip()
    if requested:
        if not _valid_uuid(requested):
            raise ValueError(f"invalid run_id format: {requested}")
        return requested

    valid_observed = sorted(run_id for run_id in observed_run_ids if _valid_uuid(run_id))
    if len(valid_observed) == 1:
        return valid_observed[0]
    if len(valid_observed) > 1:
        namespace = ",".join(valid_observed)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sw-metrics-manifest:{namespace}"))
    return str(uuid.uuid4())


def _status_from_counts(total_rows: int, run_ids: Set[str], missing_expected: Set[Tuple[str, str, str]], parse_errors: int) -> str:
    if total_rows == 0:
        return "failed"
    if parse_errors > 0:
        return "partial"
    if len(run_ids) != 1:
        return "partial"
    if missing_expected:
        return "partial"
    return "ok"


def _is_telemetry_jsonl(path: Path) -> bool:
    return path.name.startswith("metric-runtime-")


def build_manifest(
    results_dir: Path,
    run_id: str = "",
    expected_variants: Optional[Set[Tuple[str, str, str]]] = None,
    preferred_component_type: str = "",
    language: str = "java",
) -> Dict:
    expected_variants = expected_variants or set()

    rows_total = 0
    parse_errors = 0
    outputs: List[Dict] = []
    run_ids: Set[str] = set()
    projects: Set[str] = set()
    timestamps: List[str] = []
    observed_variants: Set[Tuple[str, str, str]] = set()
    component_type_counts: Dict[str, int] = defaultdict(int)
    commit_by_project: Dict[str, Set[str]] = defaultdict(set)

    for jsonl_path in sorted(results_dir.rglob("*.jsonl")):
        if not jsonl_path.is_file():
            continue
        if _is_telemetry_jsonl(jsonl_path):
            continue

        file_rows = 0
        file_projects: Set[str] = set()
        file_metrics: Set[Tuple[str, str, str]] = set()
        file_status_counts: Dict[str, int] = defaultdict(int)

        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, start=1):
                text = raw.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                if not isinstance(row, dict):
                    parse_errors += 1
                    continue

                row_run_id = str(row.get("run_id", "")).strip()
                if run_id and row_run_id != run_id:
                    continue

                rows_total += 1
                file_rows += 1
                if row_run_id:
                    run_ids.add(row_run_id)

                project = str(row.get("project", "")).strip()
                if project:
                    projects.add(project)
                    file_projects.add(project)

                timestamp_utc = str(row.get("timestamp_utc", "")).strip()
                if timestamp_utc:
                    timestamps.append(timestamp_utc)

                metric = str(row.get("metric", "")).strip()
                tool = str(row.get("tool", "")).strip()
                variant = str(row.get("variant", "")).strip()
                if metric and tool and variant:
                    observed_variants.add((metric, tool, variant))
                    file_metrics.add((metric, tool, variant))

                status = str(row.get("status", "ok")).strip() or "ok"
                file_status_counts[status] += 1

                component_type = str(row.get("component_type", "")).strip()
                if component_type:
                    component_type_counts[component_type] += 1

                params = row.get("parameters")
                if isinstance(params, dict):
                    repo_commit = params.get("repo_commit")
                    if isinstance(repo_commit, str) and repo_commit.strip() and project:
                        commit_by_project[project].add(repo_commit.strip())

        if file_rows > 0:
            outputs.append(
                {
                    "file": str(jsonl_path.relative_to(results_dir)).replace("\\", "/"),
                    "rows": file_rows,
                    "projects": sorted(file_projects),
                    "variants": sorted(f"{m}|{t}|{v}" for (m, t, v) in file_metrics),
                    "status_counts": dict(sorted(file_status_counts.items())),
                }
            )

    missing_expected = expected_variants - observed_variants
    timestamp_start, timestamp_end = _timestamp_bounds(timestamps)
    manifest_status = _status_from_counts(rows_total, run_ids, missing_expected, parse_errors)

    run_id_value = _resolve_manifest_run_id(
        requested_run_id=str(run_id or "").strip(),
        observed_run_ids=run_ids,
    )

    primary_component_type = _choose_primary_component_type(
        component_type_counts,
        preferred=preferred_component_type,
    )

    git_commit: object
    if len(projects) == 1:
        project = next(iter(projects))
        commits = sorted(commit_by_project.get(project, set()))
        git_commit = commits[0] if len(commits) == 1 else ("|".join(commits) if commits else "unknown")
    else:
        git_commit = {
            project: ("|".join(sorted(commits)) if commits else "unknown")
            for project, commits in sorted(commit_by_project.items())
        }

    return {
        "schema_version": "1.0",
        "language": str(language or "java").strip() or "java",
        "run_id": run_id_value,
        "projects": sorted(projects),
        "timestamp_utc_start": timestamp_start,
        "timestamp_utc_end": timestamp_end,
        "component_type_primary": primary_component_type,
        "variants_expected": sorted(f"{m}|{t}|{v}" for (m, t, v) in expected_variants),
        "variants_observed": sorted(f"{m}|{t}|{v}" for (m, t, v) in observed_variants),
        "missing_variants": sorted(f"{m}|{t}|{v}" for (m, t, v) in missing_expected),
        "outputs": outputs,
        "git_commit": git_commit,
        "git_url": "unknown",
        "status": manifest_status,
        "rows_total": rows_total,
        "parse_errors": parse_errors,
        "run_ids_seen": sorted(run_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build run manifest from raw metric JSONL files.")
    parser.add_argument("--results-dir", dest="results_dir", default="results", help="Raw results folder.")
    parser.add_argument("--run-id", dest="run_id", default="", help="Run id to include (optional).")
    parser.add_argument("--out", dest="output_path", default="", help="Output manifest path.")
    parser.add_argument(
        "--expected",
        dest="expected",
        action="append",
        default=[],
        help="Expected variants as metric|tool|variant (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--primary-component-type",
        dest="component_type",
        default="",
        help="Preferred primary component_type in manifest.",
    )
    parser.add_argument("--language", dest="language", default="java", help="Experiment language label.")
    args = parser.parse_args()

    expected = _parse_expected_tokens(args.expected)
    results_dir = Path(args.results_dir)
    manifest = build_manifest(
        results_dir=results_dir,
        run_id=str(args.run_id or "").strip(),
        expected_variants=expected,
        preferred_component_type=str(args.component_type or "").strip(),
        language=str(args.language or "java").strip() or "java",
    )
    output_path = Path(args.output_path or (results_dir / f"manifest-{manifest['run_id'] or 'unknown'}.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "Manifest built: "
        f"run_id={manifest['run_id']} "
        f"projects={len(manifest['projects'])} "
        f"rows_total={manifest['rows_total']} "
        f"status={manifest['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
