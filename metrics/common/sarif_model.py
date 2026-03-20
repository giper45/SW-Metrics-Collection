#!/usr/bin/env python3
"""Shared SARIF contract helpers for vulnerability collectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from result_layout import vulnerability_sarif_path as resolve_vulnerability_sarif_path

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_REPORT_CONTRACT = f"sarif-{SARIF_VERSION}"
MAVIS_NORMALIZED_SARIF_PROFILE = "mavis-normalized-sarif-v1"


def build_sarif_log(
    *,
    driver_name: str,
    driver_version: str = "",
    rules: list[dict[str, Any]] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    driver: dict[str, Any] = {"name": driver_name}
    if str(driver_version).strip():
        driver["version"] = str(driver_version).strip()
    if rules:
        driver["rules"] = rules

    run: dict[str, Any] = {
        "tool": {"driver": driver},
        "results": results or [],
    }
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [run],
    }


def write_sarif_log(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_sarif_log(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def merge_sarif_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for payload in logs:
        if not isinstance(payload, dict):
            continue
        payload_runs = payload.get("runs")
        if isinstance(payload_runs, list):
            runs.extend(run for run in payload_runs if isinstance(run, dict))
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": runs,
    }


def vulnerability_sarif_path(
    results_dir: str | os.PathLike[str],
    kind: str,
    project: str,
    timestamp_utc: str,
    tool: str,
    variant: str,
    metric_name: str = "vulnerability-findings",
) -> str:
    return resolve_vulnerability_sarif_path(
        results_dir,
        kind,
        project,
        timestamp_utc,
        tool,
        variant,
        metric_name=metric_name,
    )


def _severity_to_level(severity: str) -> str:
    normalized = str(severity or "").strip().lower()
    if normalized in {"critical", "high"}:
        return "error"
    if normalized == "medium":
        return "warning"
    if normalized in {"low", "info"}:
        return "note"
    return "warning"


def _severity_to_security_score(severity: str) -> str:
    normalized = str(severity or "").strip().lower()
    mapping = {
        "critical": "9.5",
        "high": "8.0",
        "medium": "5.0",
        "low": "2.0",
        "info": "0.1",
        "unknown": "0.0",
    }
    return mapping.get(normalized, "0.0")


def _sarif_location_from_details(location: dict[str, Any]) -> dict[str, Any]:
    path = str(location.get("path", "")).strip()
    physical: dict[str, Any] = {}
    if path:
        physical["artifactLocation"] = {"uri": path}

    start_line = location.get("start_line")
    end_line = location.get("end_line")
    snippet = str(location.get("snippet", "")).strip()
    region: dict[str, Any] = {}
    if start_line is not None:
        region["startLine"] = int(start_line)
    if end_line is not None and end_line != start_line:
        region["endLine"] = int(end_line)
    if snippet:
        region["snippet"] = {"text": snippet}
    if region:
        physical["region"] = region

    location_payload: dict[str, Any] = {}
    if physical:
        location_payload["physicalLocation"] = physical

    message = str(location.get("message", "")).strip()
    if message:
        location_payload["message"] = {"text": message}
    return location_payload


def build_canonical_vulnerability_sarif(
    *,
    project: str,
    tool: str,
    variant: str,
    tool_version: str,
    findings: list[dict[str, Any]],
    scanner_family: str,
    source_jsonl: str = "",
    source_sarif: str = "",
    partial: bool = False,
    generation_mode: str = "from_raw_sarif",
) -> dict[str, Any]:
    rules_by_id: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for finding in findings:
        rule_id = str(finding.get("rule_id", "")).strip() or tool
        rule_name = str(finding.get("rule_name", "")).strip() or rule_id
        severity = str(finding.get("severity", "unknown")).strip().lower() or "unknown"
        cwe_ids = [str(item).strip() for item in (finding.get("cwe_ids") or []) if str(item).strip()]
        owasp_tags = [str(item).strip() for item in (finding.get("owasp_tags") or []) if str(item).strip()]
        tags = ["security", *cwe_ids, *owasp_tags]

        if rule_id not in rules_by_id:
            rule_properties: dict[str, Any] = {
                "tags": tags,
                "security-severity": str(finding.get("cvss_score", _severity_to_security_score(severity))),
            }
            rules_by_id[rule_id] = {
                "id": rule_id,
                "name": rule_name,
                "shortDescription": {"text": rule_name},
                "properties": rule_properties,
            }

        result_properties: dict[str, Any] = {
            "scanner_family": str(finding.get("scanner_family", scanner_family)).strip() or scanner_family,
            "scanner_engine": str(finding.get("scanner_engine", tool)).strip() or tool,
            "normalized_severity": severity,
            "normalized_confidence": str(finding.get("confidence", "unknown")).strip() or "unknown",
            "category": str(finding.get("category", "security")).strip() or "security",
            "tags": tags,
            "cwe_ids": cwe_ids,
            "owasp_tags": owasp_tags,
        }
        for key in (
            "class_name",
            "method_name",
            "module",
            "package_name",
            "package_version",
            "dependency_scope",
            "fingerprint",
        ):
            value = finding.get(key)
            if value not in (None, "", []):
                result_properties[key] = value
        for key in ("start_line", "end_line", "raw_rank", "raw_priority"):
            value = finding.get(key)
            if value is not None:
                result_properties[key] = value
        if finding.get("cvss_score") is not None:
            result_properties["cvss_score"] = finding.get("cvss_score")
        observed_features = finding.get("observed_features")
        if isinstance(observed_features, dict):
            result_properties["observed_features"] = {
                str(key): bool(value) for key, value in observed_features.items()
            }
        flow_path_count = finding.get("flow_path_count")
        try:
            if flow_path_count is not None:
                result_properties["flow_path_count"] = int(flow_path_count)
        except (TypeError, ValueError):
            pass

        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": _severity_to_level(severity),
            "message": {"text": str(finding.get("message", "")).strip() or rule_name},
            "properties": result_properties,
        }

        primary_location = finding.get("primary_location")
        if isinstance(primary_location, dict) and primary_location:
            result["locations"] = [_sarif_location_from_details(primary_location)]
        else:
            source_path = str(finding.get("source_path", "")).strip()
            if source_path:
                physical: dict[str, Any] = {"artifactLocation": {"uri": source_path}}
                start_line = finding.get("start_line")
                end_line = finding.get("end_line")
                if start_line is not None:
                    region: dict[str, Any] = {"startLine": int(start_line)}
                    if end_line is not None:
                        region["endLine"] = int(end_line)
                    physical["region"] = region
                result["locations"] = [{"physicalLocation": physical}]

        flow_steps = finding.get("flow_steps")
        if isinstance(flow_steps, list):
            thread_flow_locations = []
            for step in flow_steps:
                if not isinstance(step, dict):
                    continue
                step_location = _sarif_location_from_details(step)
                if not step_location:
                    continue
                thread_flow_location: dict[str, Any] = {"location": step_location}
                execution_order = step.get("execution_order")
                try:
                    if execution_order is not None:
                        thread_flow_location["executionOrder"] = int(execution_order)
                except (TypeError, ValueError):
                    pass
                importance = str(step.get("importance", "")).strip()
                if importance:
                    thread_flow_location["importance"] = importance
                kinds = step.get("kinds")
                if isinstance(kinds, list):
                    normalized_kinds = [str(item).strip() for item in kinds if str(item).strip()]
                    if normalized_kinds:
                        thread_flow_location["kinds"] = normalized_kinds
                thread_flow_locations.append(thread_flow_location)
            if thread_flow_locations:
                result["codeFlows"] = [
                    {
                        "threadFlows": [
                            {
                                "locations": thread_flow_locations,
                            }
                        ]
                    }
                ]

        fingerprint = str(finding.get("fingerprint", "")).strip()
        if fingerprint:
            result["partialFingerprints"] = {"primaryLocationLineHash": fingerprint}
        results.append(result)

    payload = build_sarif_log(
        driver_name="MAVIS Normalized Vulnerability SARIF",
        driver_version="1.0",
        rules=list(rules_by_id.values()),
        results=results,
    )
    run = payload["runs"][0]
    run["properties"] = {
        "report_contract": SARIF_REPORT_CONTRACT,
        "mavis_profile": MAVIS_NORMALIZED_SARIF_PROFILE,
        "project": project,
        "metric": "vulnerability-findings",
        "tool": tool,
        "variant": variant,
        "tool_version": tool_version,
        "scanner_family": scanner_family,
        "generation_mode": generation_mode,
        "partial": bool(partial),
        "source_jsonl": source_jsonl,
        "source_sarif": source_sarif,
    }
    return payload
