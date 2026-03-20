#!/usr/bin/env python3
"""Shared type definitions for collector data structures."""

from typing import Any, Callable, Literal, Mapping, MutableMapping, NotRequired, TypedDict


MetricStatus = Literal["ok", "skipped"]
VulnerabilitySeverity = Literal["critical", "high", "medium", "low", "info", "unknown"]
VulnerabilityConfidence = Literal["high", "medium", "low", "unknown"]
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


class VulnerabilityFinding(TypedDict, total=False):
    schema: str
    scanner_family: str
    scanner_engine: str
    rule_id: str
    rule_name: str
    message: str
    severity: VulnerabilitySeverity
    confidence: VulnerabilityConfidence
    category: str
    module: str
    class_name: str
    method_name: str
    source_path: str
    start_line: int
    end_line: int
    fingerprint: str
    cwe_ids: list[str]
    owasp_tags: list[str]
    cvss_score: float
    package_name: str
    package_version: str
    dependency_scope: str
    raw_rank: int
    raw_priority: int
    primary_location: dict[str, Any]
    source_location: dict[str, Any]
    sink_location: dict[str, Any]
    flow_steps: list[dict[str, Any]]
    flow_path_count: int
    observed_features: dict[str, bool]


class VulnerabilitySummary(TypedDict):
    total: int
    severity_critical: int
    severity_high: int
    severity_medium: int
    severity_low: int
    severity_info: int
    severity_unknown: int
    unique_rules: int
    unique_cwes: int


RowCustomiser = Callable[[MutableMapping[str, Any]], Mapping[str, Any]]
