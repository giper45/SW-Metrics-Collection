from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any


COLLECTOR_SCOPE_ORDER = ("generic", "java", "python", "php", "unknown")
COLLECTOR_SCOPE_LABELS = {
    "generic": "Generic",
    "java": "Java",
    "python": "Python",
    "php": "PHP",
    "unknown": "Unclassified",
}
COLLECTOR_SCOPE_DESCRIPTIONS = {
    "generic": "Works across repositories regardless of language.",
    "java": "Collector tailored to Java repositories.",
    "python": "Collector tailored to Python repositories.",
    "php": "Collector tailored to PHP repositories.",
    "unknown": "Collector scope could not be inferred from the current data.",
}
COLLECTOR_SCOPE_BADGES = {
    "generic": "secondary",
    "java": "warning",
    "python": "success",
    "php": "primary",
    "unknown": "dark",
}
KNOWN_COLLECTOR_SCOPES = frozenset(COLLECTOR_SCOPE_LABELS) - {"unknown"}
TOOL_SCOPE_OVERRIDES = {
    "cloc": "generic",
    "tokei": "generic",
    "scc": "generic",
    "lizard": "generic",
    "git": "generic",
    "normalized-collector": "generic",
    "ck": "java",
    "ckjm": "java",
    "codeql": "java",
    "dependency-check": "java",
    "jacoco": "java",
    "java-halstead-analyzer": "java",
    "javaparser": "java",
    "jdepend": "java",
    "jscpd": "java",
    "pmd": "java",
    "spotbugs": "java",
    "radon": "python",
    "psalm": "php",
}
COMPONENT_EXTENSION_SCOPES = {
    ".java": "java",
    ".py": "python",
    ".php": "php",
}
VARIANT_SCOPE_PATTERN = re.compile(r"(^|[-_/])(generic|java|python|php)([-_/]|$)")
METRICS_PATH_PATTERN = re.compile(r"metrics/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+")


def normalize_collector_scope(scope: str | None) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized in KNOWN_COLLECTOR_SCOPES:
        return normalized
    if normalized == "unknown":
        return normalized
    return "unknown"


def collector_scope_label(scope: str | None) -> str:
    normalized = normalize_collector_scope(scope)
    return COLLECTOR_SCOPE_LABELS[normalized]


def collector_scope_description(scope: str | None) -> str:
    normalized = normalize_collector_scope(scope)
    return COLLECTOR_SCOPE_DESCRIPTIONS[normalized]


def collector_scope_badge(scope: str | None) -> str:
    normalized = normalize_collector_scope(scope)
    return COLLECTOR_SCOPE_BADGES[normalized]


def collector_scope_sort_key(scope: str | None) -> int:
    normalized = normalize_collector_scope(scope)
    try:
        return COLLECTOR_SCOPE_ORDER.index(normalized)
    except ValueError:
        return len(COLLECTOR_SCOPE_ORDER)


def extract_collector_scope_from_text(text: str) -> str | None:
    for match in METRICS_PATH_PATTERN.finditer(str(text or "")):
        parts = [part.strip().lower() for part in match.group(0).split("/") if part.strip()]
        for part in parts:
            if part in KNOWN_COLLECTOR_SCOPES:
                return part
    return None


def infer_metric_row_scope(row: dict[str, Any]) -> str:
    parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
    declared_scope = normalize_collector_scope(parameters.get("collector_scope"))
    if declared_scope != "unknown":
        return declared_scope

    tool_name = str(row.get("tool", "")).strip().lower()
    if tool_name in TOOL_SCOPE_OVERRIDES:
        return TOOL_SCOPE_OVERRIDES[tool_name]

    variant = str(row.get("variant", "")).strip().lower()
    match = VARIANT_SCOPE_PATTERN.search(variant)
    if match:
        return match.group(2)

    component = str(row.get("component", "")).strip()
    suffix = PurePosixPath(component).suffix.lower()
    if suffix in COMPONENT_EXTENSION_SCOPES:
        return COMPONENT_EXTENSION_SCOPES[suffix]

    return "unknown"
