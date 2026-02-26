#!/usr/bin/env python3
import argparse
import csv
import math
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REQUIRED_LONG_COLUMNS = (
    "project",
    "run_id",
    "timestamp_utc",
    "component",
    "component_type",
    "metric",
    "tool",
    "variant",
    "value",
    "tool_version",
)

AGREEMENT_COLUMNS = [
    "run_id",
    "metric",
    "component_type",
    "tool_a",
    "variant_a",
    "tool_b",
    "variant_b",
    "n_common",
    "spearman_rho",
    "notes",
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


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _pearson(x: List[float], y: List[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx = _mean(x)
    my = _mean(y)
    dx = [val - mx for val in x]
    dy = [val - my for val in y]
    num = sum(a * b for a, b in zip(dx, dy))
    den_x = math.sqrt(sum(a * a for a in dx))
    den_y = math.sqrt(sum(b * b for b in dy))
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (den_x * den_y)


def _rankdata(values: List[float]) -> List[float]:
    indexed = sorted((val, idx) for idx, val in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][0] == indexed[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][1]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(x: List[float], y: List[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    return _pearson(_rankdata(x), _rankdata(y))


def read_long_csv(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [col for col in REQUIRED_LONG_COLUMNS if col not in header]
        if missing:
            raise ValueError(f"{path}: missing required columns: {missing}")

        rows = []
        for line_no, row in enumerate(reader, start=2):
            value = _safe_float(row.get("value"))
            if value is None:
                raise ValueError(f"{path}:{line_no}: invalid numeric value")
            normalized = dict(row)
            normalized["value"] = float(value)
            rows.append(normalized)
        return rows


def _measure_key(row: Dict) -> Tuple[str, str]:
    return str(row["tool"]), str(row["variant"])


def _entity_key(row: Dict) -> Tuple[str, str, str]:
    return str(row["project"]), str(row["component_type"]), str(row["component"])


def _component_scope(
    values_a: Dict[Tuple[str, str, str], float],
    values_b: Dict[Tuple[str, str, str], float],
    common_entities: List[Tuple[str, str, str]],
) -> str:
    if common_entities:
        types = sorted({entity[1] for entity in common_entities})
    else:
        types = sorted({entity[1] for entity in values_a.keys()} | {entity[1] for entity in values_b.keys()})
    if not types:
        return "unknown"
    if len(types) == 1:
        return types[0]
    return "|".join(types)


def compute_agreement_rows(long_rows: List[Dict], min_common: int = 2) -> List[Dict]:
    grouped: Dict[Tuple[str, str], Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]] = {}

    for row in long_rows:
        group_key = (str(row["run_id"]), str(row["metric"]))
        measure_key = _measure_key(row)
        entity_key = _entity_key(row)

        grouped.setdefault(group_key, {})
        grouped[group_key].setdefault(measure_key, {})
        if entity_key in grouped[group_key][measure_key]:
            raise ValueError(
                f"duplicate measure for run={group_key[0]} metric={group_key[1]} "
                f"tool={measure_key[0]} variant={measure_key[1]} entity={entity_key}"
            )
        grouped[group_key][measure_key][entity_key] = float(row["value"])

    agreement_rows: List[Dict] = []
    for group_key in sorted(grouped.keys()):
        run_id, metric = group_key
        measures = grouped[group_key]
        for measure_a, measure_b in combinations(sorted(measures.keys()), 2):
            values_a = measures[measure_a]
            values_b = measures[measure_b]
            common_entities = sorted(set(values_a.keys()) & set(values_b.keys()))

            vec_a = [values_a[entity] for entity in common_entities]
            vec_b = [values_b[entity] for entity in common_entities]
            rho = spearman_rho(vec_a, vec_b) if len(common_entities) >= 2 else None
            notes = ""
            if len(common_entities) < 2:
                notes = "n_common<2"
            elif len(common_entities) < max(1, int(min_common)):
                notes = "insufficient_common_points"

            agreement_rows.append(
                {
                    "run_id": run_id,
                    "metric": metric,
                    "component_type": _component_scope(values_a, values_b, common_entities),
                    "tool_a": measure_a[0],
                    "variant_a": measure_a[1],
                    "tool_b": measure_b[0],
                    "variant_b": measure_b[1],
                    "n_common": len(common_entities),
                    "spearman_rho": round(float(rho), 6) if rho is not None and math.isfinite(rho) else None,
                    "notes": notes,
                }
            )

    return agreement_rows


def write_agreement_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row["run_id"],
            row["metric"],
            row["tool_a"],
            row["variant_a"],
            row["tool_b"],
            row["variant_b"],
        ),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AGREEMENT_COLUMNS)
        writer.writeheader()
        for row in ordered_rows:
            writer.writerow(row)


def run_agreement(input_csv: Path, output_csv: Path, min_common: int = 2) -> Dict[str, int]:
    long_rows = read_long_csv(Path(input_csv))
    agreement_rows = compute_agreement_rows(long_rows, min_common=min_common)
    write_agreement_csv(Path(output_csv), agreement_rows)
    return {
        "long_rows": len(long_rows),
        "agreement_rows": len(agreement_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute inter-tool agreement per metric from dataset_long.csv.")
    parser.add_argument("--in", dest="input_csv", default="analysis_out/dataset_long.csv", help="Input long CSV.")
    parser.add_argument("--out", dest="output_csv", default="analysis_out/agreement.csv", help="Output agreement CSV.")
    parser.add_argument(
        "--min-common",
        dest="min_common",
        type=int,
        default=2,
        help="Minimum number of shared components required to emit an agreement row (default: 2).",
    )
    args = parser.parse_args()

    summary = run_agreement(Path(args.input_csv), Path(args.output_csv), min_common=max(1, int(args.min_common)))
    print(
        "Agreement built: "
        f"long_rows={summary['long_rows']} "
        f"agreement_rows={summary['agreement_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
