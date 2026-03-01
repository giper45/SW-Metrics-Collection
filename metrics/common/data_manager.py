#!/usr/bin/env python3
"""Shared data handling utilities based on pandas and NumPy."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from common_types import MetricRow, ModuleMetricSpec, RowCustomiser


def _to_python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def normalize_row_scalars(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _to_python_scalar(value) for key, value in row.items()}


def apply_row_customiser(
    rows: Iterable[Mapping[str, Any]],
    row_customiser: RowCustomiser | None = None,
) -> list[dict[str, Any]]:
    normalized = [normalize_row_scalars(row) for row in rows]
    if row_customiser is None:
        return normalized

    out: list[dict[str, Any]] = []
    for row in normalized:
        custom = row_customiser(dict(row))
        out.append(normalize_row_scalars(dict(custom)))
    return out


def build_module_metric_row(
    *,
    project: str,
    module: str,
    metric: str,
    variant: str,
    tool: str,
    tool_version: str,
    parameters: Mapping[str, Any] | None,
    timestamp_utc: str,
    value: float | int | None = None,
    status: str = "ok",
    skip_reason: str | None = None,
    submetric: str | None = None,
) -> MetricRow:
    row: MetricRow = {
        "project": str(project),
        "metric": str(metric),
        "variant": str(variant),
        "component_type": "module",
        "component": str(module),
        "tool": str(tool),
        "tool_version": str(tool_version),
        "parameters": dict(parameters or {}),
        "timestamp_utc": str(timestamp_utc),
        "value": value,
        "status": "ok",
    }

    if submetric:
        row["submetric"] = str(submetric)

    normalized_status = str(status or "ok")
    if normalized_status == "skipped":
        row["status"] = "skipped"
        row["skip_reason"] = str(skip_reason or "collector_skipped")
        row["value"] = None
    else:
        row["status"] = "ok"
        row["value"] = value
    return row


def build_module_metric_rows(
    *,
    project: str,
    module: str,
    variant: str,
    tool: str,
    tool_version: str,
    timestamp_utc: str,
    default_metric: str,
    specs: Sequence[ModuleMetricSpec],
    base_parameters: Mapping[str, Any] | None = None,
) -> list[MetricRow]:
    rows: list[MetricRow] = []
    shared_parameters = dict(base_parameters or {})
    for spec in specs:
        spec_parameters = dict(spec.get("parameters", {}))
        merged_parameters = dict(shared_parameters)
        merged_parameters.update(spec_parameters)
        rows.append(
            build_module_metric_row(
                project=project,
                module=module,
                metric=str(spec.get("metric", default_metric)),
                variant=variant,
                tool=tool,
                tool_version=tool_version,
                parameters=merged_parameters,
                timestamp_utc=timestamp_utc,
                value=spec.get("value"),
                status=str(spec.get("status", "ok")),
                skip_reason=spec.get("skip_reason"),
                submetric=spec.get("submetric"),
            )
        )
    return rows


def rows_to_dataframe(
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    records = [normalize_row_scalars(row) for row in rows]
    frame = pd.DataFrame(records)
    if columns is None:
        return frame

    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, list(columns)]


def dataframe_to_rows(
    frame: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if columns is not None:
        for column in columns:
            if column not in frame.columns:
                frame[column] = ""
        frame = frame.loc[:, list(columns)]
    records = frame.to_dict(orient="records")
    return [normalize_row_scalars(record) for record in records]


def write_csv_rows(
    path: str | os.PathLike[str] | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame = rows_to_dataframe(rows, columns=columns)
    frame.to_csv(target, index=False)


def read_csv_rows(
    path: str | os.PathLike[str] | Path,
    *,
    lowercase_columns: bool = False,
) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        return []

    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    if lowercase_columns:
        frame.rename(columns=lambda name: str(name).strip().lower(), inplace=True)
    return dataframe_to_rows(frame)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return float(parsed)


def _numeric_array(values: Iterable[Any]) -> np.ndarray:
    collected: list[float] = []
    for value in values:
        parsed = safe_float(value)
        if parsed is None:
            continue
        collected.append(parsed)
    if not collected:
        return np.asarray([], dtype=np.float64)
    return np.asarray(collected, dtype=np.float64)


def numeric_mean(values: Iterable[Any], *, default: float = 0.0, precision: int = 6) -> float:
    numbers = _numeric_array(values)
    if numbers.size == 0:
        return float(default)
    return round(float(np.mean(numbers)), precision)


def numeric_sum(values: Iterable[Any], *, default: float = 0.0, precision: int = 6) -> float:
    numbers = _numeric_array(values)
    if numbers.size == 0:
        return float(default)
    return round(float(np.sum(numbers)), precision)


def numeric_max(values: Iterable[Any], *, default: float = 0.0, precision: int = 6) -> float:
    numbers = _numeric_array(values)
    if numbers.size == 0:
        return float(default)
    return round(float(np.max(numbers)), precision)


def numeric_percentile(
    values: Iterable[Any],
    percentile: float,
    *,
    default: float = 0.0,
    precision: int = 6,
) -> float:
    numbers = _numeric_array(values)
    if numbers.size == 0:
        return float(default)
    return round(float(np.percentile(numbers, percentile)), precision)


def first_numeric_value(row: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        parsed = safe_float(row.get(key))
        if parsed is not None:
            return parsed
    return None


def is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, np.number)):
        return True
    return False


def is_finite_number(value: Any) -> bool:
    if not is_number(value):
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
