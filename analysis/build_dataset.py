#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
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
    "status",
)

LONG_COLUMNS = [
    "project",
    "run_id",
    "timestamp_utc",
    "component",
    "component_type",
    "metric",
    "status",
    "tool",
    "variant",
    "value",
    "tool_version",
]

WIDE_INDEX_COLUMNS = [
    "project",
    "run_id",
    "timestamp_utc",
    "component",
    "component_type",
]


def _safe_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _canonical_metric(row: Dict) -> str:
    metric = str(row.get("metric", "")).strip()
    submetric = row.get("submetric")
    parameters = row.get("parameters")
    dimension = parameters.get("dimension") if isinstance(parameters, dict) else None

    if isinstance(submetric, str) and submetric.strip():
        return submetric.strip()

    metric_norm = metric.lower().replace("-", "_")
    if metric_norm in {"ce_ca", "ce-ca"} and isinstance(dimension, str):
        dim = dimension.strip().lower().replace("-", "_")
        if dim in {"ce", "ca"}:
            return dim

    return metric


def _validate_row(row: Dict, source: str) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    if missing:
        raise ValueError(f"{source}: missing required fields: {missing}")

    for key in (
        "schema_version",
        "run_id",
        "project",
        "metric",
        "variant",
        "component_type",
        "component",
        "tool",
        "tool_version",
        "timestamp_utc",
    ):
        if not isinstance(row.get(key), str):
            raise ValueError(f"{source}: {key} must be string")

    status = row.get("status")
    if not isinstance(status, str):
        raise ValueError(f"{source}: status must be string")
    if status not in {"ok", "skipped"}:
        raise ValueError(f"{source}: status must be one of ['ok', 'skipped']")

    if not isinstance(row.get("parameters"), dict):
        raise ValueError(f"{source}: parameters must be object")

    value = row.get("value")
    if status == "ok":
        numeric = _safe_float(value)
        if numeric is None:
            raise ValueError(f"{source}: value must be finite number when status=ok")
    else:
        if value is not None:
            raise ValueError(f"{source}: value must be null when status=skipped")


def read_jsonl_rows(input_dir: Path) -> List[Dict]:
    rows: List[Dict] = []
    for jsonl_path in sorted(path for path in input_dir.rglob("*.jsonl") if path.is_file()):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, start=1):
                text = raw.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise ValueError(f"{jsonl_path}:{line_no}: row is not a JSON object")
                if not isinstance(payload.get("status"), str) or not payload.get("status", "").strip():
                    payload["status"] = "skipped" if payload.get("value") is None else "ok"
                _validate_row(payload, f"{jsonl_path}:{line_no}")
                rows.append(payload)
    return rows


def build_long_rows(rows: Iterable[Dict]) -> List[Dict]:
    long_rows: List[Dict] = []
    for row in rows:
        long_rows.append(
            {
                "project": row["project"],
                "run_id": row["run_id"],
                "timestamp_utc": row["timestamp_utc"],
                "component": row["component"],
                "component_type": row["component_type"],
                "metric": _canonical_metric(row),
                "status": row["status"],
                "tool": row["tool"],
                "variant": row["variant"],
                "value": float(row["value"]),
                "tool_version": row["tool_version"],
            }
        )

    return sorted(
        long_rows,
        key=lambda item: (
            item["project"],
            item["run_id"],
            item["timestamp_utc"],
            item["component"],
            item["component_type"],
            item["metric"],
            item["tool"],
            item["variant"],
            item["tool_version"],
            item["value"],
        ),
    )


def _measure_column(metric: str, tool: str, variant: str) -> str:
    return f"{metric}__{tool}__{variant}"


def build_wide_rows(long_rows: Iterable[Dict]) -> Tuple[List[str], List[Dict]]:
    row_map: Dict[Tuple[str, str, str, str, str], Dict[str, str]] = {}
    measure_columns = set()

    for row in long_rows:
        row_key = (
            row["project"],
            row["run_id"],
            row["timestamp_utc"],
            row["component"],
            row["component_type"],
        )
        measure_key = _measure_column(row["metric"], row["tool"], row["variant"])
        measure_columns.add(measure_key)

        if row_key not in row_map:
            row_map[row_key] = {
                "project": row["project"],
                "run_id": row["run_id"],
                "timestamp_utc": row["timestamp_utc"],
                "component": row["component"],
                "component_type": row["component_type"],
            }

        if measure_key in row_map[row_key]:
            raise ValueError(
                "duplicate measurement for "
                f"{row_key} and {measure_key}; disambiguate metric/submetric before pivot"
            )
        row_map[row_key][measure_key] = str(row["value"])

    ordered_measure_columns = sorted(measure_columns)
    ordered_rows = [row_map[key] for key in sorted(row_map.keys())]
    return ordered_measure_columns, ordered_rows


def _write_csv(path: Path, columns: List[str], rows: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _choose_primary_component_type(
    long_rows: List[Dict],
    requested_component_type: str = "",
) -> str:
    requested = str(requested_component_type or "").strip()
    if requested:
        return requested
    counts: Dict[str, int] = defaultdict(int)
    for row in long_rows:
        counts[str(row["component_type"])] += 1
    if not counts:
        return "module"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def build_dataset(input_dir: Path, output_dir: Path, wide_component_type: str = "") -> Dict[str, int]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    rows = read_jsonl_rows(input_dir)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    long_rows = build_long_rows(ok_rows)
    long_path = output_dir / "dataset_long.csv"
    _write_csv(long_path, LONG_COLUMNS, long_rows)

    long_by_component_type: Dict[str, List[Dict]] = defaultdict(list)
    for row in long_rows:
        long_by_component_type[str(row["component_type"])].append(row)

    selected_component_type = _choose_primary_component_type(
        long_rows,
        requested_component_type=wide_component_type,
    )
    if selected_component_type not in long_by_component_type and long_rows:
        raise ValueError(
            f"requested component_type '{selected_component_type}' not found in long dataset; "
            f"available={sorted(long_by_component_type.keys())}"
        )

    selected_measure_columns: List[str] = []
    selected_wide_rows: List[Dict] = []
    for component_type in sorted(long_by_component_type.keys()):
        measure_columns, wide_rows = build_wide_rows(long_by_component_type[component_type])
        _write_csv(
            output_dir / f"dataset_wide_{component_type}.csv",
            WIDE_INDEX_COLUMNS + measure_columns,
            wide_rows,
        )
        if component_type == selected_component_type:
            selected_measure_columns = measure_columns
            selected_wide_rows = wide_rows

    if not long_rows:
        selected_measure_columns, selected_wide_rows = [], []

    wide_path = output_dir / "dataset_wide.csv"
    _write_csv(wide_path, WIDE_INDEX_COLUMNS + selected_measure_columns, selected_wide_rows)

    return {
        "input_rows": len(rows),
        "ok_rows": len(ok_rows),
        "skipped_rows": max(0, len(rows) - len(ok_rows)),
        "long_rows": len(long_rows),
        "wide_rows": len(selected_wide_rows),
        "wide_measure_columns": len(selected_measure_columns),
        "wide_component_type": selected_component_type,
        "wide_component_types": len(long_by_component_type),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build long/wide datasets from normalized JSONL results.")
    parser.add_argument("--in", dest="input_dir", default="results_normalized", help="Input JSONL folder.")
    parser.add_argument("--out", dest="output_dir", default="analysis_out", help="Output dataset folder.")
    parser.add_argument(
        "--wide-component-type",
        dest="wide_component_type",
        default="",
        help="Component type used to build dataset_wide.csv (default: most frequent).",
    )
    args = parser.parse_args()

    summary = build_dataset(
        Path(args.input_dir),
        Path(args.output_dir),
        wide_component_type=str(args.wide_component_type or "").strip(),
    )
    print(
        "Dataset built: "
        f"input_rows={summary['input_rows']} "
        f"ok_rows={summary['ok_rows']} "
        f"skipped_rows={summary['skipped_rows']} "
        f"long_rows={summary['long_rows']} "
        f"wide_rows={summary['wide_rows']} "
        f"wide_measure_columns={summary['wide_measure_columns']} "
        f"wide_component_type={summary['wide_component_type']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
