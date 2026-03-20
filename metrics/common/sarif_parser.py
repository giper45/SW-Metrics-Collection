#!/usr/bin/env python3
"""Shared SARIF parsing helpers for vulnerability-oriented collectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from error_manager import OutputContractError
from sarif_model import SARIF_VERSION
from vulnerability_model import (
    VULNERABILITY_FINDING_SCHEMA,
    extract_cwe_ids,
    normalize_confidence,
    extract_owasp_tags,
    normalize_severity,
    stable_fingerprint,
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise OutputContractError(f"sarif output not found: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise OutputContractError(f"sarif output is not valid JSON: {target}") from exc
    if not isinstance(payload, dict):
        raise OutputContractError(f"sarif output is not an object: {target}")
    version = _clean_text(payload.get("version"))
    if version != SARIF_VERSION:
        raise OutputContractError(f"unsupported sarif version '{version}' in {target}; expected {SARIF_VERSION}")
    return payload


def _artifact_uri_to_path(uri: str) -> str:
    value = _clean_text(uri)
    if value.startswith("file:"):
        value = value.split("file:", 1)[1]
    return value.lstrip("/").replace("\\", "/")


def _artifact_location_path(location: dict[str, Any]) -> str:
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return ""
    artifact = physical.get("artifactLocation")
    if not isinstance(artifact, dict):
        return ""
    return _artifact_uri_to_path(artifact.get("uri"))


def _region_lines(location: dict[str, Any]) -> tuple[int | None, int | None]:
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return None, None
    region = physical.get("region")
    if not isinstance(region, dict):
        return None, None
    start = region.get("startLine")
    end = region.get("endLine")
    try:
        start_line = int(start) if start is not None else None
    except (TypeError, ValueError):
        start_line = None
    try:
        end_line = int(end) if end is not None else start_line
    except (TypeError, ValueError):
        end_line = start_line
    return start_line, end_line


def _message_text(result: dict[str, Any]) -> str:
    message = result.get("message")
    if isinstance(message, dict):
        text = _clean_text(message.get("text") or message.get("markdown"))
        if text:
            return text
    return ""


def _message_value(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_text(value.get("text") or value.get("markdown"))
    return _clean_text(value)


def _rule_index_map(rules: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {index: rule for index, rule in enumerate(rules) if isinstance(rule, dict)}


def _snippet_text(region: Any) -> str:
    if not isinstance(region, dict):
        return ""
    snippet = region.get("snippet")
    if isinstance(snippet, dict):
        return _clean_text(snippet.get("text") or snippet.get("markdown"))
    return ""


def _location_details(location: dict[str, Any], *, fallback_message: str = "") -> dict[str, Any]:
    path = _artifact_location_path(location)
    start_line, end_line = _region_lines(location)
    physical = location.get("physicalLocation")
    snippet = ""
    if isinstance(physical, dict):
        snippet = _snippet_text(physical.get("region")) or _snippet_text(physical.get("contextRegion"))
    message = _message_value(location.get("message")) or _clean_text(fallback_message)

    details: dict[str, Any] = {}
    if path:
        details["path"] = path
    if start_line is not None:
        details["start_line"] = start_line
    if end_line is not None:
        details["end_line"] = end_line
    if message:
        details["message"] = message
    if snippet:
        details["snippet"] = snippet
    return details


def _extract_flow_steps(result: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    code_flows = result.get("codeFlows")
    if not isinstance(code_flows, list):
        return [], 0

    first_thread_steps: list[dict[str, Any]] = []
    path_count = 0
    for code_flow in code_flows:
        if not isinstance(code_flow, dict):
            continue
        thread_flows = code_flow.get("threadFlows")
        if not isinstance(thread_flows, list):
            continue
        for path_index, thread_flow in enumerate(thread_flows):
            if not isinstance(thread_flow, dict):
                continue
            raw_locations = thread_flow.get("locations")
            if not isinstance(raw_locations, list):
                continue

            thread_steps: list[dict[str, Any]] = []
            for step_index, thread_flow_location in enumerate(raw_locations):
                if not isinstance(thread_flow_location, dict):
                    continue
                location = thread_flow_location.get("location")
                if not isinstance(location, dict):
                    continue
                details = _location_details(
                    location,
                    fallback_message=_message_value(thread_flow_location.get("message")),
                )
                if not details:
                    continue

                execution_order = thread_flow_location.get("executionOrder")
                try:
                    if execution_order is not None:
                        details["execution_order"] = int(execution_order)
                except (TypeError, ValueError):
                    pass

                importance = _clean_text(thread_flow_location.get("importance"))
                if importance:
                    details["importance"] = importance

                kinds = thread_flow_location.get("kinds")
                if isinstance(kinds, list):
                    normalized_kinds = [str(item).strip() for item in kinds if str(item).strip()]
                    if normalized_kinds:
                        details["kinds"] = normalized_kinds

                details["path_index"] = path_index
                details["step_index"] = step_index
                thread_steps.append(details)

            if not thread_steps:
                continue

            path_count += 1
            for index, details in enumerate(thread_steps):
                if index == 0:
                    details["role"] = "source"
                elif index == len(thread_steps) - 1:
                    details["role"] = "sink"
                else:
                    details["role"] = "step"

            if not first_thread_steps:
                first_thread_steps = thread_steps

    return first_thread_steps, path_count


def _level_to_severity(level: Any, properties: dict[str, Any]) -> str:
    security_score = properties.get("security-severity")
    try:
        score = float(str(security_score).strip()) if security_score is not None else None
    except (TypeError, ValueError):
        score = None
    if score is not None:
        if score >= 9.0:
            return "critical"
        if score >= 7.0:
            return "high"
        if score >= 4.0:
            return "medium"
        if score > 0.0:
            return "low"

    normalized_level = str(level or "").strip().lower()
    mapping = {
        "error": "high",
        "warning": "medium",
        "note": "low",
        "none": "info",
    }
    return normalize_severity(mapping.get(normalized_level, normalized_level))


def _tags_from_rule(rule: dict[str, Any], result: dict[str, Any]) -> tuple[list[str], list[str]]:
    rule_properties = rule.get("properties")
    result_properties = result.get("properties")
    tags: list[str] = []
    for candidate in (rule_properties, result_properties):
        if isinstance(candidate, dict):
            raw_tags = candidate.get("tags")
            if isinstance(raw_tags, list):
                tags.extend(str(item) for item in raw_tags)
    text_values = [
        rule.get("name"),
        rule.get("shortDescription", {}).get("text") if isinstance(rule.get("shortDescription"), dict) else "",
        rule.get("fullDescription", {}).get("text") if isinstance(rule.get("fullDescription"), dict) else "",
        _message_text(result),
        *tags,
    ]
    return extract_cwe_ids(*text_values), extract_owasp_tags(*text_values)


def parse_sarif_findings(
    sarif_path: str | os.PathLike[str],
    *,
    scanner_engine: str,
    scanner_family: str = "sast",
) -> list[dict[str, Any]]:
    payload = _load_json(sarif_path)
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise OutputContractError(f"sarif runs missing or invalid: {sarif_path}")

    findings: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        tool = run.get("tool")
        driver = tool.get("driver") if isinstance(tool, dict) else {}
        rules = driver.get("rules") if isinstance(driver, dict) else []
        rule_by_index = _rule_index_map(rules if isinstance(rules, list) else [])
        driver_name = _clean_text(driver.get("name")) or scanner_engine
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            rule = {}
            rule_id = _clean_text(result.get("ruleId"))
            rule_index = result.get("ruleIndex")
            if isinstance(rule_index, int):
                rule = rule_by_index.get(rule_index, {})
            if not rule and rule_id:
                for candidate in rule_by_index.values():
                    if _clean_text(candidate.get("id")) == rule_id:
                        rule = candidate
                        break
            rule_id = rule_id or _clean_text(rule.get("id"))
            rule_name = _clean_text(rule.get("name"))
            if not rule_name:
                short = rule.get("shortDescription")
                if isinstance(short, dict):
                    rule_name = _clean_text(short.get("text"))
            message = _message_text(result) or rule_name or rule_id
            locations = result.get("locations")
            location = locations[0] if isinstance(locations, list) and locations else {}
            primary_location = (
                _location_details(location, fallback_message=message)
                if isinstance(location, dict)
                else {}
            )
            source_path = str(primary_location.get("path", "")).strip()
            start_line = primary_location.get("start_line")
            end_line = primary_location.get("end_line")
            flow_steps, flow_path_count = _extract_flow_steps(result)
            source_location = dict(flow_steps[0]) if flow_steps else {}
            sink_location = dict(flow_steps[-1]) if flow_steps else dict(primary_location)
            observed_features = {
                "primary_location": bool(primary_location),
                "source_location": bool(source_location),
                "sink_location": bool(sink_location),
                "flow_path": bool(flow_steps),
                "code_snippets": bool(
                    primary_location.get("snippet")
                    or source_location.get("snippet")
                    or sink_location.get("snippet")
                    or any(step.get("snippet") for step in flow_steps)
                ),
            }
            properties = {}
            for candidate in (rule.get("properties"), result.get("properties")):
                if isinstance(candidate, dict):
                    properties.update(candidate)
            cwe_ids, owasp_tags = _tags_from_rule(rule, result)

            finding: dict[str, Any] = {
                "schema": VULNERABILITY_FINDING_SCHEMA,
                "scanner_family": scanner_family,
                "scanner_engine": scanner_engine,
                "rule_id": rule_id or driver_name,
                "rule_name": rule_name or rule_id or driver_name,
                "message": message,
                "severity": _level_to_severity(result.get("level"), properties),
                "confidence": normalize_confidence(properties.get("confidence")),
                "category": "security",
                "source_path": source_path,
                "cwe_ids": cwe_ids,
                "owasp_tags": owasp_tags,
                "observed_features": observed_features,
            }

            if start_line is not None:
                finding["start_line"] = start_line
            if end_line is not None:
                finding["end_line"] = end_line
            if primary_location:
                finding["primary_location"] = primary_location
            if source_location:
                finding["source_location"] = source_location
            if sink_location:
                finding["sink_location"] = sink_location
            if flow_steps:
                finding["flow_steps"] = flow_steps
                finding["flow_path_count"] = flow_path_count

            partial_fingerprints = result.get("partialFingerprints")
            if isinstance(partial_fingerprints, dict):
                primary = _clean_text(
                    partial_fingerprints.get("primaryLocationLineHash")
                    or partial_fingerprints.get("primaryLocationStartColumnFingerprint")
                    or next(iter(partial_fingerprints.values()), "")
                )
                if primary:
                    finding["fingerprint"] = primary[:24]
            if "fingerprint" not in finding:
                finding["fingerprint"] = stable_fingerprint(
                    finding["rule_id"],
                    source_path,
                    start_line,
                    end_line,
                    message,
                )

            score_raw = properties.get("security-severity")
            try:
                if score_raw is not None:
                    finding["cvss_score"] = float(str(score_raw).strip())
            except (TypeError, ValueError):
                pass

            class_name = _clean_text(properties.get("class_name"))
            if class_name:
                finding["class_name"] = class_name
            method_name = _clean_text(properties.get("method_name"))
            if method_name:
                finding["method_name"] = method_name
            module_name = _clean_text(properties.get("module"))
            if module_name:
                finding["module"] = module_name
            for key in ("raw_rank", "raw_priority"):
                raw_value = properties.get(key)
                try:
                    if raw_value is not None:
                        finding[key] = int(str(raw_value).strip())
                except (TypeError, ValueError):
                    pass

            if scanner_engine == "dependency-check":
                finding["scanner_family"] = "sca"
                finding["package_name"] = _clean_text(properties.get("packageName") or properties.get("package"))
                finding["package_version"] = _clean_text(properties.get("packageVersion") or properties.get("version"))
                finding["dependency_scope"] = _clean_text(properties.get("scope"))

            findings.append(finding)

    return findings
