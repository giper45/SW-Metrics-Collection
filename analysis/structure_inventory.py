#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from analysis.utils import safe_float

STRUCTURE_COLUMNS = [
    "project",
    "loc",
    "class_count",
    "package_count",
    "loc_run_id",
    "class_count_run_id",
    "package_count_run_id",
]


def _is_telemetry_jsonl(path: Path) -> bool:
    return path.name.startswith("metric-runtime-")


def _read_jsonl_rows(root: Path) -> List[Dict]:
    rows: List[Dict] = []
    for path in sorted(root.rglob("*.jsonl")):
        if not path.is_file() or _is_telemetry_jsonl(path):
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


def _row_ok(row: Dict) -> bool:
    return str(row.get("status", "ok")).strip() == "ok"


def _text(value: object) -> str:
    return str(value or "").strip()


def _latest_key(run_id: str, timestamp_utc: str) -> Tuple[str, str]:
    return timestamp_utc, run_id


def _latest_loc_group(
    rows: Iterable[Dict],
    *,
    tool: str,
    variant: str,
    run_id: str = "",
) -> Dict[str, Dict]:
    grouped: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)
    for row in rows:
        if not _row_ok(row):
            continue
        if _text(row.get("metric")) != "loc":
            continue
        if _text(row.get("tool")) != tool or _text(row.get("variant")) != variant:
            continue
        if _text(row.get("component_type")) != "file":
            continue

        row_run_id = _text(row.get("run_id"))
        row_timestamp = _text(row.get("timestamp_utc"))
        row_project = _text(row.get("project"))
        if not row_project or not row_run_id or not row_timestamp:
            continue
        if run_id and row_run_id != run_id:
            continue

        grouped[(row_project, row_run_id, row_timestamp)].append(dict(row))

    latest_by_project: Dict[str, Dict] = {}
    for (project, group_run_id, group_timestamp), group_rows in grouped.items():
        current = latest_by_project.get(project)
        candidate = {
            "project": project,
            "run_id": group_run_id,
            "timestamp_utc": group_timestamp,
            "rows": group_rows,
        }
        if current is None or _latest_key(group_run_id, group_timestamp) > _latest_key(
            current["run_id"],
            current["timestamp_utc"],
        ):
            latest_by_project[project] = candidate
    return latest_by_project


def _latest_project_metric(
    rows: Iterable[Dict],
    *,
    metric: str,
    tool: str,
    variant: str,
    run_id: str = "",
) -> Dict[str, Dict]:
    latest_by_project: Dict[str, Dict] = {}
    for row in rows:
        if not _row_ok(row):
            continue
        if _text(row.get("metric")) != metric:
            continue
        if _text(row.get("tool")) != tool or _text(row.get("variant")) != variant:
            continue
        if _text(row.get("component_type")) != "project":
            continue

        row_run_id = _text(row.get("run_id"))
        row_timestamp = _text(row.get("timestamp_utc"))
        row_project = _text(row.get("project"))
        if not row_project or not row_run_id or not row_timestamp:
            continue
        if run_id and row_run_id != run_id:
            continue

        current = latest_by_project.get(row_project)
        candidate = dict(row)
        if current is None or _latest_key(row_run_id, row_timestamp) > _latest_key(
            _text(current.get("run_id")),
            _text(current.get("timestamp_utc")),
        ):
            latest_by_project[row_project] = candidate
    return latest_by_project


def build_structure_inventory(
    results_dir: Path,
    *,
    run_id: str = "",
    loc_tool: str = "cloc",
    loc_variant: str = "cloc-default",
    class_tool: str = "javaparser",
    class_variant: str = "javaparser-default",
    package_tool: str = "javaparser",
    package_variant: str = "javaparser-default",
) -> List[Dict]:
    rows = _read_jsonl_rows(results_dir)

    loc_by_project = _latest_loc_group(
        rows,
        tool=loc_tool,
        variant=loc_variant,
        run_id=run_id,
    )
    class_by_project = _latest_project_metric(
        rows,
        metric="class-count",
        tool=class_tool,
        variant=class_variant,
        run_id=run_id,
    )
    package_by_project = _latest_project_metric(
        rows,
        metric="package-count",
        tool=package_tool,
        variant=package_variant,
        run_id=run_id,
    )

    projects = sorted(set(loc_by_project.keys()) | set(class_by_project.keys()) | set(package_by_project.keys()))
    output_rows: List[Dict] = []
    for project in projects:
        loc_group = loc_by_project.get(project)
        class_row = class_by_project.get(project)
        package_row = package_by_project.get(project)

        loc_value: Optional[float] = None
        loc_run_id = ""
        if loc_group is not None:
            values = [safe_float(row.get("value")) for row in loc_group["rows"]]
            numeric_values = [value for value in values if value is not None]
            loc_value = round(sum(numeric_values), 6) if numeric_values else 0.0
            loc_run_id = _text(loc_group.get("run_id"))

        class_value = safe_float(class_row.get("value")) if class_row else None
        package_value = safe_float(package_row.get("value")) if package_row else None

        output_rows.append(
            {
                "project": project,
                "loc": loc_value,
                "class_count": class_value,
                "package_count": package_value,
                "loc_run_id": loc_run_id,
                "class_count_run_id": _text(class_row.get("run_id")) if class_row else "",
                "package_count_run_id": _text(package_row.get("run_id")) if package_row else "",
            }
        )

    return output_rows


def _write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STRUCTURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projects": sorted(row["project"] for row in rows),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-repository structural inventory from metric results.")
    parser.add_argument("--results-dir", default="results", help="Raw metric results folder.")
    parser.add_argument("--run-id", default="", help="Optional run id filter.")
    parser.add_argument("--loc-tool", default="cloc", help="Tool used for LOC aggregation.")
    parser.add_argument("--loc-variant", default="cloc-default", help="Variant used for LOC aggregation.")
    parser.add_argument("--class-tool", default="javaparser", help="Tool used for class count.")
    parser.add_argument("--class-variant", default="javaparser-default", help="Variant used for class count.")
    parser.add_argument("--package-tool", default="javaparser", help="Tool used for package count.")
    parser.add_argument("--package-variant", default="javaparser-default", help="Variant used for package count.")
    parser.add_argument("--out-csv", default="analysis_out/structure_inventory.csv", help="Output CSV path.")
    parser.add_argument("--out-json", default="analysis_out/structure_inventory.json", help="Output JSON path.")
    args = parser.parse_args()

    rows = build_structure_inventory(
        Path(args.results_dir),
        run_id=_text(args.run_id),
        loc_tool=_text(args.loc_tool) or "cloc",
        loc_variant=_text(args.loc_variant) or "cloc-default",
        class_tool=_text(args.class_tool) or "javaparser",
        class_variant=_text(args.class_variant) or "javaparser-default",
        package_tool=_text(args.package_tool) or "javaparser",
        package_variant=_text(args.package_variant) or "javaparser-default",
    )
    _write_csv(Path(args.out_csv), rows)
    _write_json(Path(args.out_json), rows)

    print(
        "Structure inventory built: "
        f"projects={len(rows)} "
        f"with_loc={sum(1 for row in rows if row['loc'] is not None)} "
        f"with_class_count={sum(1 for row in rows if row['class_count'] is not None)} "
        f"with_package_count={sum(1 for row in rows if row['package_count'] is not None)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
