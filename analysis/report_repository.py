#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

from analysis.agreement import compute_agreement_rows


def _read_jsonl_rows(root: Path) -> List[Dict]:
    rows: List[Dict] = []
    for path in sorted(root.rglob("*.jsonl")):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                text = raw.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def _read_csv_rows(path: Path) -> List[Dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _safe_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _project_metadata(normalized_rows: Iterable[Dict]) -> Dict[str, Dict]:
    per_project: Dict[str, Dict] = defaultdict(lambda: {
        "run_ids": set(),
        "repo_commits": set(),
        "repo_dirty": False,
        "status_counts": defaultdict(int),
    })

    for row in normalized_rows:
        project = row.get("project")
        if not isinstance(project, str) or not project.strip():
            continue

        project_meta = per_project[project]
        run_id = row.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            project_meta["run_ids"].add(run_id.strip())

        status = str(row.get("status", "ok"))
        project_meta["status_counts"][status] += 1

        params = row.get("parameters")
        if isinstance(params, dict):
            repo_commit = params.get("repo_commit")
            if isinstance(repo_commit, str) and repo_commit.strip():
                project_meta["repo_commits"].add(repo_commit.strip())

            repo_dirty = params.get("repo_dirty")
            if isinstance(repo_dirty, bool):
                project_meta["repo_dirty"] = project_meta["repo_dirty"] or repo_dirty

    return per_project


def _group_long_by_project(long_rows: Iterable[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for row in long_rows:
        project = row.get("project")
        if isinstance(project, str) and project.strip():
            grouped[project].append(dict(row))
    return grouped


def _metric_level_summary(project: str, rows: List[Dict], agreement_rows: List[Dict], meta: Dict) -> List[Dict]:
    by_metric: Dict[str, List[Dict]] = defaultdict(list)
    for row in rows:
        by_metric[str(row.get("metric", ""))].append(row)

    agreement_by_metric: Dict[str, List[Dict]] = defaultdict(list)
    for row in agreement_rows:
        agreement_by_metric[str(row.get("metric", ""))].append(row)

    repo_commit = "|".join(sorted(meta.get("repo_commits", set()))) or "unknown"
    run_ids = sorted(meta.get("run_ids", set()))
    status_counts = meta.get("status_counts", {})

    out_rows = []
    for metric in sorted(by_metric.keys()):
        metric_rows = by_metric[metric]
        components = {(r.get("component_type"), r.get("component")) for r in metric_rows}
        tools = sorted({str(r.get("tool", "")) for r in metric_rows})
        variants = sorted({str(r.get("variant", "")) for r in metric_rows})
        component_types = sorted({str(r.get("component_type", "")) for r in metric_rows})

        metric_agreement = agreement_by_metric.get(metric, [])
        valid_metric_agreement = [
            row for row in metric_agreement if not str(row.get("notes", "")).strip()
        ]
        rho_values = [_safe_float(r.get("spearman_rho")) for r in valid_metric_agreement]
        rho_values = [value for value in rho_values if value is not None]
        common_values = [_safe_float(r.get("n_common")) for r in valid_metric_agreement]
        common_values = [int(v) for v in common_values if v is not None]

        out_rows.append(
            {
                "project": project,
                "metric": metric,
                "run_ids": ",".join(run_ids),
                "repo_commit": repo_commit,
                "repo_dirty": str(bool(meta.get("repo_dirty", False))).lower(),
                "raw_rows_ok": int(status_counts.get("ok", 0)),
                "raw_rows_skipped": int(status_counts.get("skipped", 0)),
                "n_rows_metric": len(metric_rows),
                "n_components": len(components),
                "component_types": ",".join(component_types),
                "n_tools": len(tools),
                "tools": ",".join(tools),
                "variants": ",".join(variants),
                "agreement_pairs": len(valid_metric_agreement),
                "agreement_mean_rho": round(sum(rho_values) / len(rho_values), 6) if rho_values else "",
                "agreement_min_common": min(common_values) if common_values else "",
                "agreement_max_common": max(common_values) if common_values else "",
            }
        )

    return out_rows


def build_repo_report(normalized_dir: Path, long_csv: Path) -> List[Dict]:
    normalized_rows = _read_jsonl_rows(normalized_dir)
    long_rows = _read_csv_rows(long_csv)

    long_by_project = _group_long_by_project(long_rows)
    meta_by_project = _project_metadata(normalized_rows)

    output_rows: List[Dict] = []
    for project in sorted(set(long_by_project.keys()) | set(meta_by_project.keys())):
        project_long = long_by_project.get(project, [])

        typed_rows = []
        for row in project_long:
            copied = dict(row)
            copied["value"] = float(copied["value"])
            typed_rows.append(copied)

        agreement_rows = compute_agreement_rows(typed_rows, min_common=2)
        output_rows.extend(
            _metric_level_summary(
                project=project,
                rows=typed_rows,
                agreement_rows=agreement_rows,
                meta=meta_by_project.get(project, {}),
            )
        )

    return sorted(output_rows, key=lambda row: (row["project"], row["metric"]))


def _write_report_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "project",
        "metric",
        "run_ids",
        "repo_commit",
        "repo_dirty",
        "raw_rows_ok",
        "raw_rows_skipped",
        "n_rows_metric",
        "n_components",
        "component_types",
        "n_tools",
        "tools",
        "variants",
        "agreement_pairs",
        "agreement_mean_rho",
        "agreement_min_common",
        "agreement_max_common",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_report_json(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projects": sorted({row["project"] for row in rows}),
        "metrics": sorted({row["metric"] for row in rows}),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-repository experiment report.")
    parser.add_argument("--normalized", dest="normalized_dir", default="results_normalized", help="Normalized JSONL folder.")
    parser.add_argument("--long", dest="long_csv", default="analysis_out/dataset_long.csv", help="dataset_long.csv path.")
    parser.add_argument("--out", dest="out_csv", default="analysis_out/repo_report.csv", help="Output CSV report path.")
    parser.add_argument("--out-json", dest="out_json", default="analysis_out/repo_report.json", help="Output JSON report path.")
    args = parser.parse_args()

    rows = build_repo_report(Path(args.normalized_dir), Path(args.long_csv))
    _write_report_csv(Path(args.out_csv), rows)
    _write_report_json(Path(args.out_json), rows)

    print(
        "Repo report built: "
        f"rows={len(rows)} "
        f"projects={len({row['project'] for row in rows})} "
        f"metrics={len({row['metric'] for row in rows})}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
