#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Tuple

from analysis.utils import safe_float, safe_int


PAIR_COLUMNS = [
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

SUMMARY_COLUMNS = [
    "metric",
    "pairs",
    "rho_mean",
    "rho_median",
    "rho_min",
    "rho_max",
    "n_common_min",
    "n_common_max",
]



def _read_agreement_rows(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [column for column in PAIR_COLUMNS if column not in header]
        if missing:
            raise ValueError(f"{path}: missing required columns: {missing}")
        rows = [dict(row) for row in reader]
    return rows


def _write_csv(path: Path, columns: List[str], rows: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _intertool_valid_rows(rows: Iterable[Dict], min_common: int = 2) -> List[Dict]:
    out: List[Dict] = []
    for row in rows:
        notes = str(row.get("notes", "")).strip()
        rho = safe_float(row.get("spearman_rho"))
        n_common = safe_int(row.get("n_common"))
        tool_a = str(row.get("tool_a", "")).strip()
        tool_b = str(row.get("tool_b", "")).strip()
        if notes:
            continue
        if rho is None:
            continue
        if n_common is None or n_common < int(min_common):
            continue
        if not tool_a or not tool_b or tool_a == tool_b:
            continue

        normalized = dict(row)
        normalized["n_common"] = n_common
        normalized["spearman_rho"] = rho
        out.append(normalized)

    return sorted(
        out,
        key=lambda item: (
            str(item.get("run_id", "")),
            str(item.get("metric", "")),
            str(item.get("tool_a", "")),
            str(item.get("variant_a", "")),
            str(item.get("tool_b", "")),
            str(item.get("variant_b", "")),
        ),
    )


def _normalized_variant_score(variant: str) -> int:
    return 1 if "normalized" in str(variant or "").strip().lower() else 0


def _pair_key(row: Dict) -> Tuple[str, str, str, str, str]:
    return (
        str(row.get("run_id", "")),
        str(row.get("metric", "")),
        str(row.get("component_type", "")),
        str(row.get("tool_a", "")),
        str(row.get("tool_b", "")),
    )


def _select_final_pairs(rows: Iterable[Dict]) -> List[Dict]:
    best_by_key: Dict[Tuple[str, str, str, str, str], Dict] = {}
    for row in rows:
        key = _pair_key(row)
        candidate = dict(row)

        score = (
            _normalized_variant_score(candidate.get("variant_a", ""))
            + _normalized_variant_score(candidate.get("variant_b", "")),
            -int(candidate.get("n_common", 0)),
            -float(candidate.get("spearman_rho", 0.0)),
            str(candidate.get("variant_a", "")),
            str(candidate.get("variant_b", "")),
        )
        candidate["_score"] = score

        current = best_by_key.get(key)
        if current is None or score < current["_score"]:
            best_by_key[key] = candidate

    selected = []
    for row in best_by_key.values():
        cleaned = dict(row)
        cleaned.pop("_score", None)
        selected.append(cleaned)

    return sorted(
        selected,
        key=lambda item: (
            str(item.get("run_id", "")),
            str(item.get("metric", "")),
            str(item.get("tool_a", "")),
            str(item.get("variant_a", "")),
            str(item.get("tool_b", "")),
            str(item.get("variant_b", "")),
        ),
    )


def _summarize_by_metric(rows: Iterable[Dict]) -> List[Dict]:
    by_metric: Dict[str, List[Dict]] = {}
    for row in rows:
        metric = str(row.get("metric", ""))
        by_metric.setdefault(metric, []).append(row)

    out: List[Dict] = []
    for metric in sorted(by_metric.keys()):
        metric_rows = by_metric[metric]
        rho_values = [float(r["spearman_rho"]) for r in metric_rows]
        common_values = [int(r["n_common"]) for r in metric_rows]
        out.append(
            {
                "metric": metric,
                "pairs": len(metric_rows),
                "rho_mean": sum(rho_values) / len(rho_values),
                "rho_median": float(median(rho_values)),
                "rho_min": min(rho_values),
                "rho_max": max(rho_values),
                "n_common_min": min(common_values),
                "n_common_max": max(common_values),
            }
        )
    return out


def _fmt_float(value: float) -> str:
    text = f"{float(value):.6f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _tex_escape(text: str) -> str:
    escaped = str(text)
    replacements = {
        "\\": "\\textbackslash{}",
        "_": "\\_",
        "&": "\\&",
        "%": "\\%",
        "#": "\\#",
        "$": "\\$",
        "{": "\\{",
        "}": "\\}",
    }
    for src, dst in replacements.items():
        escaped = escaped.replace(src, dst)
    return escaped


def _write_tex_summary(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Cross-tool agreement summary used in the paper.}",
        "\\label{tab:agreement-summary-auto}",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Metric & Pairs & Mean $\\rho$ & Median $\\rho$ & Min $\\rho$ & Max $\\rho$ \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            f"{_tex_escape(row['metric'])} & {int(row['pairs'])} & "
            f"{_fmt_float(row['rho_mean'])} & {_fmt_float(row['rho_median'])} & "
            f"{_fmt_float(row['rho_min'])} & {_fmt_float(row['rho_max'])} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_tex_pairs(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Inter-tool agreement pairs selected for paper reporting.}",
        "\\label{tab:agreement-pairs-auto}",
        "\\begin{tabular}{llrr}",
        "\\toprule",
        "Metric & Tool pair & $\\rho$ & Component \\\\",
        "\\midrule",
    ]
    for row in rows:
        tool_pair = f"{row['tool_a']} vs {row['tool_b']}"
        lines.append(
            f"{_tex_escape(row['metric'])} & {_tex_escape(tool_pair)} & "
            f"{_fmt_float(float(row['spearman_rho']))} & {_tex_escape(str(row['component_type']))} \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_paper_tables(
    agreement_csv: Path,
    out_dir: Path,
    tex_dir: Path,
    min_common: int = 2,
) -> Dict[str, int]:
    rows = _read_agreement_rows(agreement_csv)
    intertool_valid = _intertool_valid_rows(rows, min_common=min_common)
    final_pairs = _select_final_pairs(intertool_valid)
    summary = _summarize_by_metric(final_pairs)

    intertool_path = out_dir / "agreement_intertool_valid.csv"
    final_pairs_path = out_dir / "agreement_final_pairs.csv"
    summary_path = out_dir / "agreement_final_summary.csv"

    _write_csv(intertool_path, PAIR_COLUMNS, intertool_valid)
    _write_csv(final_pairs_path, PAIR_COLUMNS, final_pairs)
    _write_csv(summary_path, SUMMARY_COLUMNS, summary)

    _write_tex_pairs(tex_dir / "agreement_pairs.tex", final_pairs)
    _write_tex_summary(tex_dir / "agreement_summary.tex", summary)

    return {
        "agreement_rows": len(rows),
        "intertool_valid_rows": len(intertool_valid),
        "final_pairs_rows": len(final_pairs),
        "summary_rows": len(summary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build paper-ready agreement tables from agreement.csv.")
    parser.add_argument("--agreement", default="analysis_out/agreement.csv", help="Input agreement CSV.")
    parser.add_argument("--out-dir", default="analysis_out", help="Output directory for CSV tables.")
    parser.add_argument("--tex-dir", default="paper/tables", help="Output directory for LaTeX table snippets.")
    parser.add_argument("--min-common", type=int, default=2, help="Minimum n_common to keep rows (default: 2).")
    args = parser.parse_args()

    summary = build_paper_tables(
        agreement_csv=Path(args.agreement),
        out_dir=Path(args.out_dir),
        tex_dir=Path(args.tex_dir),
        min_common=max(1, int(args.min_common)),
    )
    print(
        "Paper tables built: "
        f"agreement_rows={summary['agreement_rows']} "
        f"intertool_valid_rows={summary['intertool_valid_rows']} "
        f"final_pairs_rows={summary['final_pairs_rows']} "
        f"summary_rows={summary['summary_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
