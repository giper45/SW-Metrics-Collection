#!/usr/bin/env python3
"""Shared type definitions for collector data structures."""

from typing import Any, Callable, Literal, Mapping, MutableMapping, NotRequired, TypedDict


MetricStatus = Literal["ok", "skipped"]
ProjectEntry = tuple[str, str]


class MetricRow(TypedDict):
    project: str
    metric: str
    variant: str
    component_type: str
    component: str
    value: float | int | None
    tool: str
    tool_version: str
    parameters: dict[str, Any]
    timestamp_utc: str
    schema_version: NotRequired[str]
    run_id: NotRequired[str]
    status: NotRequired[MetricStatus | str]
    skip_reason: NotRequired[str]
    submetric: NotRequired[str]


class ModuleMetricSpec(TypedDict):
    value: float | int | None
    metric: NotRequired[str]
    status: NotRequired[MetricStatus | str]
    skip_reason: NotRequired[str]
    submetric: NotRequired[str]
    parameters: NotRequired[dict[str, Any]]


class NormalizedMetricRow(TypedDict):
    entity_type: str
    entity_id: str
    metric_name: str
    metric_value: float
    unit: str
    language: str
    tool_key: str
    variant_key: str
    scope_filter: str
    path_hint: str


RowCustomiser = Callable[[MutableMapping[str, Any]], Mapping[str, Any]]
