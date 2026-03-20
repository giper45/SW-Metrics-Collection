from __future__ import annotations

from collections import Counter, defaultdict
import html
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any

from markupsafe import Markup

from .collector_metadata import (
    collector_scope_badge,
    collector_scope_description,
    collector_scope_label,
    collector_scope_sort_key,
    infer_metric_row_scope,
)

try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import (
        CssLexer,
        HtmlLexer,
        JavaLexer,
        JavascriptLexer,
        JsonLexer,
        PhpLexer,
        PythonLexer,
        TextLexer,
        TypeScriptLexer as TypescriptLexer,
        XmlLexer,
        YamlLexer,
        get_lexer_for_filename,
    )
    from pygments.util import ClassNotFound
except ImportError:  # pragma: no cover - fallback for minimal installs
    highlight = None
    HtmlFormatter = None
    CssLexer = HtmlLexer = JavaLexer = JavascriptLexer = JsonLexer = None
    PhpLexer = PythonLexer = TextLexer = TypescriptLexer = XmlLexer = YamlLexer = None
    get_lexer_for_filename = None
    ClassNotFound = Exception

SEVERITY_ORDER = ("critical", "high", "medium", "low", "info", "unknown")
SOURCE_LABELS = {
    "raw": "Raw Collection",
    "normalized": "Normalized Output",
}
TOOL_LABELS = {
    "cloc": "CLOC",
    "ck": "CK",
    "codeql": "CodeQL",
    "ckjm": "CKJM",
    "ckjm-ext": "CKJM Extended",
    "dependency-check": "Dependency-Check",
    "findsecbugs": "FindSecBugs",
    "git": "Git",
    "grype": "Grype",
    "jacoco": "JaCoCo",
    "java-halstead-analyzer": "Java Halstead Analyzer",
    "javaparser": "JavaParser",
    "jdepend": "JDepend",
    "lizard": "Lizard",
    "osv-scanner": "OSV-Scanner",
    "pmd": "PMD",
    "psalm": "Psalm",
    "radon": "Radon",
    "semgrep": "Semgrep",
    "scc": "SCC",
    "spotbugs": "SpotBugs",
    "syft": "Syft",
    "tokei": "Tokei",
}
TOOL_BADGES = {
    "cloc": "primary",
    "ck": "warning",
    "codeql": "dark",
    "ckjm": "secondary",
    "ckjm-ext": "secondary",
    "dependency-check": "warning",
    "findsecbugs": "warning",
    "git": "dark",
    "grype": "danger",
    "jacoco": "success",
    "java-halstead-analyzer": "success",
    "javaparser": "primary",
    "jdepend": "secondary",
    "lizard": "warning",
    "osv-scanner": "dark",
    "pmd": "danger",
    "psalm": "primary",
    "radon": "success",
    "semgrep": "success",
    "scc": "info",
    "spotbugs": "warning",
    "syft": "secondary",
    "tokei": "info",
}
VULNERABILITY_METRIC = "vulnerability-findings"
MAX_METRIC_ROWS = 250
MAX_VULNERABILITY_CARDS = 60
SNIPPET_LANGUAGE_LABELS = {
    "java": "Java",
    "php": "PHP",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "html": "HTML",
    "xml": "XML",
    "json": "JSON",
    "yaml": "YAML",
    "css": "CSS",
    "text": "Text",
}
SNIPPET_LANGUAGE_BADGES = {
    "java": "warning",
    "php": "primary",
    "python": "success",
    "javascript": "info",
    "typescript": "info",
    "html": "secondary",
    "xml": "secondary",
    "json": "dark",
    "yaml": "dark",
    "css": "info",
    "text": "secondary",
}
SNIPPET_FORMATTER = HtmlFormatter(nowrap=True, noclasses=True) if HtmlFormatter else None
SNIPPET_LINE_RE = re.compile(r"^\s*(\d+)\s+\|\s?(.*)$")


def load_result_rows(results_dir: Path, normalized_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_load_rows_for_source("raw", results_dir))
    rows.extend(_load_rows_for_source("normalized", normalized_dir))
    return rows


def build_insights_overview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_summary = []
    selected_source = preferred_source(rows)
    metric_rows = [row for row in rows if row.get("metric") != VULNERABILITY_METRIC]
    vulnerability_rows = [
        row
        for row in rows
        if row.get("metric") == VULNERABILITY_METRIC and _is_total_vulnerability_row(row)
    ]
    preferred_metric_source = preferred_source(metric_rows)
    preferred_vulnerability_source = preferred_source(vulnerability_rows)

    for source_key in ("raw", "normalized"):
        source_rows = [row for row in rows if row["_source"] == source_key]
        metric_rows = [row for row in source_rows if row.get("metric") != VULNERABILITY_METRIC]
        vulnerability_rows = [
            row
            for row in source_rows
            if row.get("metric") == VULNERABILITY_METRIC and _is_total_vulnerability_row(row)
        ]
        total_findings = sum(_vulnerability_total(row) for row in vulnerability_rows)
        source_summary.append(
            {
                "key": source_key,
                "label": SOURCE_LABELS[source_key],
                "row_count": len(source_rows),
                "file_count": len({row["_file_name"] for row in source_rows}),
                "metric_rows": len(metric_rows),
                "vulnerability_rows": len(vulnerability_rows),
                "vulnerability_total": total_findings,
                "projects": len({str(row.get("project", "")).strip() for row in source_rows if row.get("project")}),
            }
        )

    return {
        "preferred_source": selected_source,
        "preferred_metric_source": preferred_metric_source,
        "preferred_vulnerability_source": preferred_vulnerability_source,
        "sources": source_summary,
        "totals": {
            "rows": len(rows),
            "projects": len({str(row.get("project", "")).strip() for row in rows if row.get("project")}),
            "runs": len({str(row.get("run_id", "")).strip() for row in rows if row.get("run_id")}),
            "metrics": len({str(row.get("metric", "")).strip() for row in rows if row.get("metric")}),
        },
    }


def build_vulnerability_view(
    rows: list[dict[str, Any]],
    filters: dict[str, str],
    *,
    src_dir: Path | None = None,
) -> dict[str, Any]:
    vulnerability_rows = [
        row
        for row in rows
        if row.get("metric") == VULNERABILITY_METRIC and _is_total_vulnerability_row(row)
    ]

    options = {
        "sources": _option_values(vulnerability_rows, "_source"),
        "projects": _option_values(vulnerability_rows, "project"),
        "tools": _option_values(vulnerability_rows, "tool"),
        "runs": _option_values(vulnerability_rows, "run_id"),
        "components": _option_values(vulnerability_rows, "component"),
    }

    source_candidates = [
        row
        for row in vulnerability_rows
        if _match_filter(row.get("project"), filters.get("project"))
        and _match_filter(row.get("tool"), filters.get("tool"))
        and _match_filter(row.get("run_id"), filters.get("run_id"))
        and _match_filter(row.get("component"), filters.get("component"))
    ]
    selected_source = filters.get("source") or preferred_source(source_candidates) or preferred_source(vulnerability_rows)
    severity_filter = (filters.get("severity") or "").strip().lower()
    search = (filters.get("search") or "").strip().lower()

    filtered_rows = [
        row
        for row in vulnerability_rows
        if _match_filter(row.get("_source"), selected_source)
        and _match_filter(row.get("project"), filters.get("project"))
        and _match_filter(row.get("tool"), filters.get("tool"))
        and _match_filter(row.get("run_id"), filters.get("run_id"))
        and _match_filter(row.get("component"), filters.get("component"))
    ]

    entries: list[dict[str, Any]] = []
    visible_findings_all: list[dict[str, Any]] = []
    severity_breakdown = Counter({severity: 0 for severity in SEVERITY_ORDER})
    summary_total = 0
    high_priority_total = 0
    truncated_count = 0
    snippet_cache: dict[tuple[str, str, str, int | None, int | None], str] = {}

    for row in filtered_rows:
        parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
        findings = parameters.get("findings") if isinstance(parameters.get("findings"), list) else []
        normalized_findings = [
            _normalize_finding(
                finding,
                row=row,
                fallback_component=str(row.get("component", "")).strip(),
                src_dir=src_dir,
                snippet_cache=snippet_cache,
            )
            for finding in findings
            if isinstance(finding, dict)
        ]
        visible_findings = [
            finding
            for finding in normalized_findings
            if (not severity_filter or finding["severity"] == severity_filter)
            and (not search or _vulnerability_search_blob(row, finding).find(search) >= 0)
        ]

        row_matches_text = not search or search in _row_search_blob(row)
        row_total = _vulnerability_total(row)
        row_severity = _severity_breakdown_from_row(row)
        row_matches_severity = not severity_filter or row_severity.get(severity_filter, 0) > 0

        if search and not visible_findings and not row_matches_text:
            continue
        if severity_filter and not visible_findings and not row_matches_severity:
            continue

        if search or severity_filter:
            for finding in visible_findings:
                severity_breakdown[finding["severity"]] += 1
            summary_total += len(visible_findings)
            high_priority_total += sum(
                1 for finding in visible_findings if finding["severity"] in {"critical", "high"}
            )
        else:
            for severity, count in row_severity.items():
                severity_breakdown[severity] += count
            summary_total += row_total
            high_priority_total += row_severity["critical"] + row_severity["high"]

        if parameters.get("findings_truncated"):
            truncated_count += 1

        visible_findings_all.extend(visible_findings)
        entries.append(
            {
                "row": row,
                "summary_total": row_total,
                "severity_breakdown": row_severity,
                "visible_findings": visible_findings,
                "embedded_findings_count": len(normalized_findings),
                "findings_truncated": bool(parameters.get("findings_truncated")),
                "top_severity": _top_severity(row_severity),
            }
        )

    entries.sort(
        key=lambda entry: (
            -entry["severity_breakdown"].get("critical", 0),
            -entry["severity_breakdown"].get("high", 0),
            -entry["summary_total"],
            str(entry["row"].get("project", "")),
            str(entry["row"].get("component", "")),
        )
    )

    visible_entries = entries[:MAX_VULNERABILITY_CARDS]
    hidden_count = max(0, len(entries) - len(visible_entries))
    unique_rules = len({finding["rule_id"] for finding in visible_findings_all if finding["rule_id"]})
    unique_cwes = len({cwe for finding in visible_findings_all for cwe in finding["cwe_ids"]})

    return {
        "filters": {
            "source": selected_source,
            "project": filters.get("project", ""),
            "tool": filters.get("tool", ""),
            "run_id": filters.get("run_id", ""),
            "component": filters.get("component", ""),
            "severity": severity_filter,
            "search": filters.get("search", ""),
        },
        "options": options,
        "entries": visible_entries,
        "total_entries": len(entries),
        "hidden_count": hidden_count,
        "summary": {
            "findings": summary_total,
            "high_priority": high_priority_total,
            "components": len(entries),
            "rules": unique_rules,
            "cwes": unique_cwes,
            "truncated": truncated_count,
            "tools": len({str(row.get("tool", "")).strip() for row in filtered_rows if row.get("tool")}),
            "tool_names": _option_values(filtered_rows, "tool"),
            "severity_breakdown": dict(severity_breakdown),
        },
    }


def build_metrics_view(
    rows: list[dict[str, Any]],
    filters: dict[str, str],
) -> dict[str, Any]:
    metric_rows = [_decorate_metric_row(row) for row in rows if row.get("metric") != VULNERABILITY_METRIC]

    options = {
        "sources": _option_values(metric_rows, "_source"),
        "projects": _option_values(metric_rows, "project"),
        "metrics": _option_values(metric_rows, "metric"),
        "tools": _option_values(metric_rows, "tool"),
        "collector_scopes": _collector_scope_options(metric_rows),
        "component_types": _option_values(metric_rows, "component_type"),
        "runs": _option_values(metric_rows, "run_id"),
        "statuses": _option_values(metric_rows, "status"),
    }

    source_candidates = []
    for row in metric_rows:
        if not _match_filter(row.get("project"), filters.get("project")):
            continue
        if not _match_filter(row.get("metric"), filters.get("metric")):
            continue
        if not _match_filter(row.get("tool"), filters.get("tool")):
            continue
        if not _match_filter(row.get("_collector_scope"), filters.get("collector_scope")):
            continue
        if not _match_filter(row.get("component_type"), filters.get("component_type")):
            continue
        if not _match_filter(row.get("run_id"), filters.get("run_id")):
            continue
        if not _match_filter(row.get("status"), filters.get("status")):
            continue
        source_candidates.append(row)
    selected_source = filters.get("source") or preferred_source(source_candidates) or preferred_source(metric_rows)
    search = (filters.get("search") or "").strip().lower()

    filtered_rows = []
    for row in metric_rows:
        if not _match_filter(row.get("_source"), selected_source):
            continue
        if not _match_filter(row.get("project"), filters.get("project")):
            continue
        if not _match_filter(row.get("metric"), filters.get("metric")):
            continue
        if not _match_filter(row.get("tool"), filters.get("tool")):
            continue
        if not _match_filter(row.get("_collector_scope"), filters.get("collector_scope")):
            continue
        if not _match_filter(row.get("component_type"), filters.get("component_type")):
            continue
        if not _match_filter(row.get("run_id"), filters.get("run_id")):
            continue
        if not _match_filter(row.get("status"), filters.get("status")):
            continue
        if search and search not in _metric_search_blob(row):
            continue
        filtered_rows.append(row)

    metric_groups: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in filtered_rows:
        grouped[(str(row.get("_collector_scope", "")).strip(), _measure_label(row))].append(row)

    for (scope_key, measure_name), measure_rows in grouped.items():
        numeric_values = [float(row["value"]) for row in measure_rows if _numeric_value(row)]
        metric_groups.append(
            {
                "measure": measure_name,
                "metric": str(measure_rows[0].get("metric", "")).strip(),
                "submetric": str(measure_rows[0].get("submetric", "")).strip(),
                "collector_scope": scope_key,
                "collector_scope_label": collector_scope_label(scope_key),
                "collector_scope_badge": collector_scope_badge(scope_key),
                "collector_scope_description": collector_scope_description(scope_key),
                "rows": len(measure_rows),
                "tools": len({str(row.get("tool", "")).strip() for row in measure_rows if row.get("tool")}),
                "tool_names": _option_values(measure_rows, "tool"),
                "components": len({str(row.get("component", "")).strip() for row in measure_rows if row.get("component")}),
                "latest_timestamp": max(str(row.get("timestamp_utc", "")) for row in measure_rows),
                "min_value": min(numeric_values) if numeric_values else None,
                "max_value": max(numeric_values) if numeric_values else None,
                "avg_value": mean(numeric_values) if numeric_values else None,
            }
        )

    metric_groups.sort(
        key=lambda item: (
            collector_scope_sort_key(item["collector_scope"]),
            item["measure"],
            -item["rows"],
        )
    )
    visible_rows = sorted(
        filtered_rows,
        key=lambda row: (
            str(row.get("timestamp_utc", "")),
            str(row.get("project", "")),
            str(row.get("metric", "")),
            str(row.get("component", "")),
        ),
        reverse=True,
    )[:MAX_METRIC_ROWS]

    return {
        "filters": {
            "source": selected_source,
            "project": filters.get("project", ""),
            "metric": filters.get("metric", ""),
            "tool": filters.get("tool", ""),
            "collector_scope": filters.get("collector_scope", ""),
            "component_type": filters.get("component_type", ""),
            "run_id": filters.get("run_id", ""),
            "status": filters.get("status", ""),
            "search": filters.get("search", ""),
        },
        "options": options,
        "rows": visible_rows,
        "total_rows": len(filtered_rows),
        "hidden_count": max(0, len(filtered_rows) - len(visible_rows)),
        "groups": metric_groups[:12],
        "summary": {
            "rows": len(filtered_rows),
            "projects": len({str(row.get("project", "")).strip() for row in filtered_rows if row.get("project")}),
            "metrics": len({str(row.get("metric", "")).strip() for row in filtered_rows if row.get("metric")}),
            "components": len({str(row.get("component", "")).strip() for row in filtered_rows if row.get("component")}),
            "tools": len({str(row.get("tool", "")).strip() for row in filtered_rows if row.get("tool")}),
            "tool_names": _option_values(filtered_rows, "tool"),
            "collector_scopes": len(
                {str(row.get("_collector_scope", "")).strip() for row in filtered_rows if row.get("_collector_scope")}
            ),
            "scope_names": [
                item["key"]
                for item in _collector_scope_breakdown(filtered_rows)
            ],
            "scope_breakdown": _collector_scope_breakdown(filtered_rows),
        },
    }


def preferred_source(rows: list[dict[str, Any]]) -> str:
    sources = {str(row.get("_source", "")).strip() for row in rows}
    if "normalized" in sources:
        return "normalized"
    if "raw" in sources:
        return "raw"
    return ""


def source_label(source_key: str) -> str:
    return SOURCE_LABELS.get(source_key, source_key)


def tool_label(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    if not normalized:
        return "Unknown tool"
    return TOOL_LABELS.get(normalized.lower(), normalized)


def tool_badge(tool_name: str) -> str:
    normalized = str(tool_name or "").strip().lower()
    if not normalized:
        return "secondary"
    return TOOL_BADGES.get(normalized, "secondary")


def severity_badge(severity: str) -> str:
    mapping = {
        "critical": "danger",
        "high": "warning",
        "medium": "primary",
        "low": "success",
        "info": "secondary",
        "unknown": "dark",
    }
    return mapping.get(str(severity).strip().lower(), "secondary")


def metric_badge(metric_name: str) -> str:
    mapping = {
        "loc": "primary",
        "cc": "warning",
        "wmc": "warning",
        "nom": "info",
        "ce-ca": "secondary",
        "instability": "dark",
        "lcom": "danger",
        "duplication-rate": "danger",
        "maintainability-index": "success",
        "test-coverage": "success",
        "class-count": "primary",
        "package-count": "secondary",
    }
    return mapping.get(str(metric_name).strip().lower(), "secondary")


def format_number(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.3f}".rstrip("0").rstrip(".")


def _load_rows_for_source(source_key: str, directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return rows

    for file_path in sorted(path for path in directory.rglob("*.jsonl") if path.is_file()):
        if file_path.name.startswith("metric-runtime-"):
            continue
        for line_number, raw_line in enumerate(
            file_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            payload["_source"] = source_key
            payload["_source_label"] = SOURCE_LABELS[source_key]
            payload["_file_name"] = file_path.name
            payload["_file_path"] = str(file_path)
            payload["_line_number"] = line_number
            rows.append(payload)
    return rows


def _option_values(rows: list[dict[str, Any]], field: str) -> list[str]:
    values = {str(row.get(field, "")).strip() for row in rows if str(row.get(field, "")).strip()}
    return sorted(values)


def _match_filter(value: Any, expected: str | None) -> bool:
    expected = str(expected or "").strip()
    if not expected:
        return True
    return str(value or "").strip() == expected


def _row_search_blob(row: dict[str, Any]) -> str:
    parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
    values = [
        row.get("project"),
        row.get("component"),
        row.get("tool"),
        row.get("variant"),
        row.get("run_id"),
        parameters.get("tool_notice"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _vulnerability_search_blob(row: dict[str, Any], finding: dict[str, Any]) -> str:
    flow_steps = finding.get("flow_steps") if isinstance(finding.get("flow_steps"), list) else []
    values = [
        _row_search_blob(row),
        finding.get("rule_id"),
        finding.get("rule_name"),
        finding.get("message"),
        finding.get("source_path"),
        finding.get("primary_location", {}).get("path") if isinstance(finding.get("primary_location"), dict) else "",
        finding.get("source_location", {}).get("path") if isinstance(finding.get("source_location"), dict) else "",
        finding.get("sink_location", {}).get("path") if isinstance(finding.get("sink_location"), dict) else "",
        finding.get("class_name"),
        finding.get("method_name"),
        " ".join(finding.get("cwe_ids", [])),
        " ".join(finding.get("owasp_tags", [])),
        " ".join(str(step.get("path", "")) for step in flow_steps if isinstance(step, dict)),
        " ".join(str(step.get("message", "")) for step in flow_steps if isinstance(step, dict)),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _metric_search_blob(row: dict[str, Any]) -> str:
    values = [
        row.get("project"),
        row.get("metric"),
        row.get("submetric"),
        row.get("tool"),
        row.get("variant"),
        row.get("component"),
        row.get("component_type"),
        row.get("run_id"),
        row.get("_collector_scope"),
        row.get("_collector_scope_label"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _decorate_metric_row(row: dict[str, Any]) -> dict[str, Any]:
    scope_key = infer_metric_row_scope(row)
    enriched = dict(row)
    enriched["_collector_scope"] = scope_key
    enriched["_collector_scope_label"] = collector_scope_label(scope_key)
    enriched["_collector_scope_badge"] = collector_scope_badge(scope_key)
    enriched["_collector_scope_description"] = collector_scope_description(scope_key)
    return enriched


def _collector_scope_options(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    scopes = {str(row.get("_collector_scope", "")).strip() for row in rows if row.get("_collector_scope")}
    return [
        {
            "key": scope,
            "label": collector_scope_label(scope),
            "badge": collector_scope_badge(scope),
        }
        for scope in sorted(scopes, key=collector_scope_sort_key)
    ]


def _collector_scope_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes = {str(row.get("_collector_scope", "")).strip() for row in rows if row.get("_collector_scope")}
    breakdown: list[dict[str, Any]] = []
    for scope in sorted(scopes, key=collector_scope_sort_key):
        scope_rows = [row for row in rows if row.get("_collector_scope") == scope]
        breakdown.append(
            {
                "key": scope,
                "label": collector_scope_label(scope),
                "badge": collector_scope_badge(scope),
                "description": collector_scope_description(scope),
                "rows": len(scope_rows),
                "tools": len({str(row.get("tool", "")).strip() for row in scope_rows if row.get("tool")}),
                "metrics": len({str(row.get("metric", "")).strip() for row in scope_rows if row.get("metric")}),
            }
        )
    return breakdown


def _severity_breakdown_from_row(row: dict[str, Any]) -> Counter:
    parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
    summary = parameters.get("summary") if isinstance(parameters.get("summary"), dict) else {}
    counts = Counter({severity: 0 for severity in SEVERITY_ORDER})
    for severity in SEVERITY_ORDER:
        counts[severity] = int(summary.get(f"severity_{severity}", 0) or 0)
    return counts


def _top_severity(counts: Counter) -> str:
    for severity in SEVERITY_ORDER:
        if counts.get(severity, 0) > 0:
            return severity
    return "unknown"


def _vulnerability_total(row: dict[str, Any]) -> int:
    parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
    summary = parameters.get("summary") if isinstance(parameters.get("summary"), dict) else {}
    total = summary.get("total")
    if total is not None:
        return int(total or 0)
    value = row.get("value")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_finding(
    finding: dict[str, Any],
    *,
    row: dict[str, Any],
    fallback_component: str,
    src_dir: Path | None,
    snippet_cache: dict[tuple[str, str, str, int | None, int | None], str],
) -> dict[str, Any]:
    severity = str(finding.get("severity", "unknown")).strip().lower() or "unknown"
    project = str(row.get("project", "")).strip()
    module = str(finding.get("module", "")).strip() or fallback_component
    primary_location_input = finding.get("primary_location")
    if not isinstance(primary_location_input, dict) or not primary_location_input:
        primary_location_input = {
            "path": str(finding.get("source_path", "")).strip(),
            "start_line": finding.get("start_line"),
            "end_line": finding.get("end_line"),
            "message": str(finding.get("message", "")).strip(),
        }

    primary_location = _normalize_location(
        primary_location_input,
        project=project,
        module=module,
        src_dir=src_dir,
        snippet_cache=snippet_cache,
    )
    source_location = _normalize_location(
        finding.get("source_location") if isinstance(finding.get("source_location"), dict) else {},
        project=project,
        module=module,
        src_dir=src_dir,
        snippet_cache=snippet_cache,
    )
    sink_location = _normalize_location(
        finding.get("sink_location") if isinstance(finding.get("sink_location"), dict) else primary_location_input,
        project=project,
        module=module,
        src_dir=src_dir,
        snippet_cache=snippet_cache,
    )
    flow_steps_raw = finding.get("flow_steps") if isinstance(finding.get("flow_steps"), list) else []
    flow_steps = [
        _normalize_location(
            step,
            project=project,
            module=module,
            src_dir=src_dir,
            snippet_cache=snippet_cache,
        )
        for step in flow_steps_raw
        if isinstance(step, dict)
    ]
    flow_steps = [step for step in flow_steps if step]
    if not source_location and flow_steps:
        source_location = dict(flow_steps[0])
    if not sink_location and flow_steps:
        sink_location = dict(flow_steps[-1])
    flow_path_count = _safe_int(finding.get("flow_path_count")) or (1 if flow_steps else 0)

    observed_features = {
        "primary_location": bool(primary_location),
        "source_location": bool(source_location),
        "sink_location": bool(sink_location),
        "flow_path": bool(flow_steps),
        "code_snippets": bool(
            primary_location.get("has_snippet")
            or source_location.get("has_snippet")
            or sink_location.get("has_snippet")
            or any(step.get("has_snippet") for step in flow_steps)
        ),
    }
    observed_features_input = finding.get("observed_features")
    if isinstance(observed_features_input, dict):
        for key in observed_features:
            if key in observed_features_input:
                observed_features[key] = bool(observed_features_input[key])

    snippet_count = sum(
        1
        for item in [primary_location, source_location, sink_location, *flow_steps]
        if item.get("has_snippet")
    )

    return {
        "severity": severity if severity in SEVERITY_ORDER else "unknown",
        "rule_id": str(finding.get("rule_id", "")).strip(),
        "rule_name": str(finding.get("rule_name", "")).strip(),
        "message": str(finding.get("message", "")).strip(),
        "source_path": primary_location.get("path", ""),
        "start_line": primary_location.get("start_line"),
        "end_line": primary_location.get("end_line"),
        "confidence": str(finding.get("confidence", "")).strip(),
        "class_name": str(finding.get("class_name", "")).strip(),
        "method_name": str(finding.get("method_name", "")).strip(),
        "module": module,
        "cwe_ids": [str(item).strip() for item in finding.get("cwe_ids", []) if str(item).strip()],
        "owasp_tags": [str(item).strip() for item in finding.get("owasp_tags", []) if str(item).strip()],
        "fingerprint": str(finding.get("fingerprint", "")).strip(),
        "tool": str(row.get("tool", "")).strip(),
        "variant": str(row.get("variant", "")).strip(),
        "project": project,
        "component": fallback_component,
        "primary_location": primary_location,
        "source_location": source_location,
        "sink_location": sink_location,
        "flow_steps": flow_steps,
        "flow_path_count": flow_path_count,
        "observed_features": observed_features,
        "feature_rows": [
            {
                "key": "primary_location",
                "label": "Primary location",
                "available": observed_features["primary_location"],
                "value": primary_location.get("display_label", "N/A") if observed_features["primary_location"] else "N/A",
            },
            {
                "key": "source_location",
                "label": "Source",
                "available": observed_features["source_location"],
                "value": source_location.get("display_label", "N/A") if observed_features["source_location"] else "N/A",
            },
            {
                "key": "sink_location",
                "label": "Sink",
                "available": observed_features["sink_location"],
                "value": sink_location.get("display_label", "N/A") if observed_features["sink_location"] else "N/A",
            },
            {
                "key": "flow_trace",
                "label": "Flow trace",
                "available": observed_features["flow_path"],
                "value": (
                    f"{len(flow_steps)} steps"
                    + (f" across {flow_path_count} path(s)" if flow_path_count > 1 else "")
                )
                if observed_features["flow_path"]
                else "N/A",
            },
            {
                "key": "code_snippets",
                "label": "Code snippets",
                "available": observed_features["code_snippets"],
                "value": f"{snippet_count} snippet(s) available" if observed_features["code_snippets"] else "N/A",
            },
        ],
    }


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _line_label(start_line: int | None, end_line: int | None) -> str:
    if start_line is None:
        return ""
    if end_line is None or end_line == start_line:
        return f"line {start_line}"
    return f"lines {start_line}-{end_line}"


def _display_label(path: str, start_line: int | None, end_line: int | None) -> str:
    line_label = _line_label(start_line, end_line)
    if path and line_label:
        return f"{path} ({line_label})"
    return path or line_label or "N/A"


def _snippet_language_from_path(path: str) -> str:
    suffix = Path(str(path or "").strip()).suffix.lower()
    mapping = {
        ".java": "java",
        ".php": "php",
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".html": "html",
        ".htm": "html",
        ".xml": "xml",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".css": "css",
    }
    return mapping.get(suffix, "text")


def _snippet_lexer(path: str):
    language = _snippet_language_from_path(path)
    if PhpLexer and language == "php":
        return PhpLexer(startinline=True)
    if JavaLexer and language == "java":
        return JavaLexer()
    if PythonLexer and language == "python":
        return PythonLexer()
    if JavascriptLexer and language == "javascript":
        return JavascriptLexer()
    if TypescriptLexer and language == "typescript":
        return TypescriptLexer()
    if HtmlLexer and language == "html":
        return HtmlLexer()
    if XmlLexer and language == "xml":
        return XmlLexer()
    if JsonLexer and language == "json":
        return JsonLexer()
    if YamlLexer and language == "yaml":
        return YamlLexer()
    if CssLexer and language == "css":
        return CssLexer()
    if get_lexer_for_filename:
        try:
            return get_lexer_for_filename(path or "snippet.txt")
        except ClassNotFound:
            pass
    return TextLexer() if TextLexer else None


def _highlight_snippet_html(snippet: str, *, path: str) -> Markup:
    text = str(snippet or "")
    if not text:
        return Markup("")

    line_items = []
    parsed_lines = []
    for raw_line in text.splitlines():
        match = SNIPPET_LINE_RE.match(raw_line)
        if not match:
            parsed_lines = []
            break
        parsed_lines.append((int(match.group(1)), match.group(2)))
    if parsed_lines:
        line_items = parsed_lines
    else:
        line_items = [(None, raw_line) for raw_line in text.splitlines()]

    lexer = _snippet_lexer(path)
    if highlight and lexer and SNIPPET_FORMATTER:
        rendered_lines = []
        for line_number, code_line in line_items:
            highlighted = highlight(code_line, lexer, SNIPPET_FORMATTER).rstrip("\n")
            if line_number is not None:
                prefix = f'<span style="color: #6c757d; user-select: none;">{line_number:>4} | </span>'
                rendered_lines.append(prefix + highlighted)
            else:
                rendered_lines.append(highlighted)
        return Markup("\n".join(rendered_lines))
    return Markup(html.escape(text))


def _normalize_location(
    location: dict[str, Any],
    *,
    project: str,
    module: str,
    src_dir: Path | None,
    snippet_cache: dict[tuple[str, str, str, int | None, int | None], str],
) -> dict[str, Any]:
    if not isinstance(location, dict):
        return {}

    path = str(location.get("path") or location.get("source_path") or "").strip()
    start_line = _safe_int(location.get("start_line"))
    end_line = _safe_int(location.get("end_line"))
    message = str(location.get("message", "")).strip()
    snippet = str(location.get("snippet", "")).rstrip()
    if not snippet and path:
        snippet = _snippet_from_source(
            project=project,
            module=module,
            location_path=path,
            start_line=start_line,
            end_line=end_line,
            src_dir=src_dir,
            snippet_cache=snippet_cache,
        )

    role = str(location.get("role", "")).strip()
    if not any([path, message, snippet, start_line is not None, end_line is not None, role]):
        return {}

    language_key = _snippet_language_from_path(path)
    return {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "message": message,
        "snippet": snippet,
        "has_snippet": bool(snippet),
        "snippet_html": _highlight_snippet_html(snippet, path=path) if snippet else Markup(""),
        "language_key": language_key,
        "language_label": SNIPPET_LANGUAGE_LABELS.get(language_key, "Text"),
        "language_badge": SNIPPET_LANGUAGE_BADGES.get(language_key, "secondary"),
        "line_label": _line_label(start_line, end_line),
        "display_label": _display_label(path, start_line, end_line),
        "role": role,
        "path_index": _safe_int(location.get("path_index")),
        "step_index": _safe_int(location.get("step_index")),
        "execution_order": _safe_int(location.get("execution_order")),
        "importance": str(location.get("importance", "")).strip(),
        "kinds": [str(item).strip() for item in location.get("kinds", []) if str(item).strip()]
        if isinstance(location.get("kinds"), list)
        else [],
    }


def _snippet_from_source(
    *,
    project: str,
    module: str,
    location_path: str,
    start_line: int | None,
    end_line: int | None,
    src_dir: Path | None,
    snippet_cache: dict[tuple[str, str, str, int | None, int | None], str],
) -> str:
    cache_key = (project, module, location_path, start_line, end_line)
    if cache_key in snippet_cache:
        return snippet_cache[cache_key]

    snippet_cache[cache_key] = ""
    if src_dir is None or not project or not location_path or start_line is None:
        return ""

    source_file = _resolve_source_file(
        src_dir=src_dir,
        project=project,
        module=module,
        location_path=location_path,
    )
    if source_file is None:
        return ""

    try:
        lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    if not lines:
        return ""

    region_end = end_line if end_line is not None else start_line
    start_index = max(1, start_line - 1)
    end_index = min(len(lines), region_end + 1)
    snippet = "\n".join(
        f"{line_number:>4} | {lines[line_number - 1]}"
        for line_number in range(start_index, end_index + 1)
    ).rstrip()
    snippet_cache[cache_key] = snippet
    return snippet


def _resolve_source_file(
    *,
    src_dir: Path,
    project: str,
    module: str,
    location_path: str,
) -> Path | None:
    project_root = (src_dir / project).resolve()
    normalized_path = str(location_path).strip().lstrip("/")
    candidates = [project_root / normalized_path]
    if module and module not in {"", ".", "/", project}:
        candidates.append(project_root / module / normalized_path)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            resolved.relative_to(project_root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _measure_label(row: dict[str, Any]) -> str:
    submetric = str(row.get("submetric", "")).strip()
    if submetric:
        return submetric
    return str(row.get("metric", "")).strip()


def _numeric_value(row: dict[str, Any]) -> bool:
    try:
        float(row.get("value"))
    except (TypeError, ValueError):
        return False
    return True


def _is_total_vulnerability_row(row: dict[str, Any]) -> bool:
    submetric = str(row.get("submetric", "")).strip()
    return not submetric or submetric == "vulnerability_total"
