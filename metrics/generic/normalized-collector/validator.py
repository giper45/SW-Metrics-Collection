#!/usr/bin/env python3
from __future__ import annotations

import math
from typing import Dict, List

REQUIRED_COLUMNS = [
    "entity_type",
    "entity_id",
    "metric_name",
    "metric_value",
    "unit",
    "language",
    "tool_key",
    "variant_key",
    "scope_filter",
    "path_hint",
]

ALLOWED_ENTITY_TYPES = {"project", "module", "file", "function", "class"}
ALLOWED_METRICS = {
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
ALLOWED_UNITS = {"count", "ratio"}
ALLOWED_LANGUAGES = {"java", "python", "mixed", "unknown"}


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be string")
    result = value.strip()
    if field_name != "path_hint" and result == "":
        raise ValueError(f"{field_name} must be non-empty string")
    return result


def _as_float(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise ValueError(f"{field_name} must be float-compatible") from exc
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"{field_name} must be finite float")
    return number


def validate_row(row: Dict[str, object]) -> Dict[str, object]:
    missing = [column for column in REQUIRED_COLUMNS if column not in row]
    if missing:
        raise ValueError(f"missing columns: {missing}")

    normalized = {column: row.get(column, "") for column in REQUIRED_COLUMNS}

    normalized["entity_type"] = _required_text(normalized["entity_type"], "entity_type")
    if normalized["entity_type"] not in ALLOWED_ENTITY_TYPES:
        raise ValueError(f"entity_type not allowed: {normalized['entity_type']}")

    normalized["entity_id"] = _required_text(normalized["entity_id"], "entity_id")
    normalized["metric_name"] = _required_text(normalized["metric_name"], "metric_name")
    if normalized["metric_name"] not in ALLOWED_METRICS:
        raise ValueError(f"metric_name not canonical: {normalized['metric_name']}")

    normalized["metric_value"] = _as_float(normalized["metric_value"], "metric_value")

    normalized["unit"] = _required_text(normalized["unit"], "unit")
    if normalized["unit"] not in ALLOWED_UNITS:
        raise ValueError(f"unit not allowed: {normalized['unit']}")

    normalized["language"] = _required_text(normalized["language"], "language")
    if normalized["language"] not in ALLOWED_LANGUAGES:
        raise ValueError(f"language not allowed: {normalized['language']}")

    normalized["tool_key"] = _required_text(normalized["tool_key"], "tool_key")
    normalized["variant_key"] = _required_text(normalized["variant_key"], "variant_key")
    normalized["scope_filter"] = _required_text(normalized["scope_filter"], "scope_filter")
    normalized["path_hint"] = _required_text(str(normalized["path_hint"]), "path_hint")

    return normalized


def validate_and_normalize_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    return [validate_row(row) for row in rows]
