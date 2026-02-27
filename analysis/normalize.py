#!/usr/bin/env python3
import argparse
import json
import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCHEMA_VERSION = "1.0"
CANONICAL_KEYS = [
    "schema_version",
    "run_id",
    "project",
    "metric",
    "variant",
    "component_type",
    "component",
    "submetric",
    "status",
    "skip_reason",
    "value",
    "tool",
    "tool_version",
    "parameters",
    "timestamp_utc",
    "source_tool",
    "source_variant",
    "source_file",
]


def utc_timestamp_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value) -> Optional[float]:
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


def _ordered_row(row: Dict) -> Dict:
    ordered = {}
    for key in CANONICAL_KEYS:
        if key in row:
            ordered[key] = row[key]
    for key in sorted(row.keys()):
        if key not in ordered:
            ordered[key] = row[key]
    return ordered


def _non_empty_string(value) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _legacy_fallback_run_id(source_file: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sw-metrics-legacy-run:{source_file}"))


def _backfill_required_metadata(rows: List[Dict], source_file: str) -> List[Dict]:
    existing_run_ids = {
        run_id
        for run_id in (_non_empty_string(row.get("run_id")) for row in rows)
        if run_id is not None
    }
    default_run_id = (
        next(iter(existing_run_ids))
        if len(existing_run_ids) == 1
        else _legacy_fallback_run_id(source_file)
    )

    normalized: List[Dict] = []
    for row in rows:
        enriched = dict(row)

        run_id = _non_empty_string(enriched.get("run_id"))
        schema_version = _non_empty_string(enriched.get("schema_version"))
        status = _non_empty_string(enriched.get("status"))

        enriched["run_id"] = run_id or default_run_id
        enriched["schema_version"] = schema_version or SCHEMA_VERSION
        if status is None:
            enriched["status"] = "skipped" if enriched.get("value") is None else "ok"
        else:
            enriched["status"] = status
        normalized.append(enriched)
    return normalized


def read_jsonl(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            rows.append(payload)
    return rows


def _is_telemetry_jsonl(path: Path) -> bool:
    return path.name.startswith("metric-runtime-")


def write_jsonl(path: Path, rows: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    _ordered_row(row),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _infer_dimension(row: Dict) -> str:
    params = row.get("parameters")
    if isinstance(params, dict):
        for key in ("dimension", "metric_name", "submetric"):
            raw = params.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip().lower().replace("-", "_")
    submetric = row.get("submetric")
    if isinstance(submetric, str) and submetric.strip():
        return submetric.strip().lower().replace("-", "_")
    metric = row.get("metric")
    if isinstance(metric, str):
        return metric.strip().lower().replace("-", "_")
    return ""


def _infer_module(row: Dict) -> Optional[str]:
    component = row.get("component")
    component_type = str(row.get("component_type", "")).strip().lower()

    if component_type == "module" and isinstance(component, str) and component.strip():
        return component.strip()

    params = row.get("parameters")
    if isinstance(params, dict):
        for key in ("module", "module_name"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    if not isinstance(component, str) or not component.strip():
        return None

    comp = component.strip()
    if "." in comp:
        parent = ".".join(comp.split(".")[:-1]).strip()
        return parent or comp
    if "/" in comp:
        parts = [part for part in comp.split("/") if part]
        if len(parts) > 1:
            return "/".join(parts[:-1])
    return comp


def _derive_cc_from_wmc_nom(rows: List[Dict], source_file: str) -> List[Dict]:
    class_measurements: Dict[Tuple, Dict[str, float]] = defaultdict(dict)

    for row in rows:
        if str(row.get("status", "ok")).strip().lower() != "ok":
            continue
        dimension = _infer_dimension(row)
        if dimension not in {"wmc", "nom"}:
            continue

        value = _safe_float(row.get("value"))
        if value is None:
            continue

        project = row.get("project")
        module = _infer_module(row)
        component = row.get("component")
        if not isinstance(project, str) or not project.strip() or not module:
            continue
        class_id = component if isinstance(component, str) and component.strip() else "__module__"

        key = (
            project.strip(),
            module,
            class_id,
            str(row.get("tool", "unknown")),
            str(row.get("variant", "unknown")),
            str(row.get("tool_version", "unknown")),
            str(row.get("timestamp_utc", utc_timestamp_now())),
            str(row.get("schema_version", "1.0")),
            str(row.get("run_id", "unknown")),
        )
        class_measurements[key][dimension] = value

    module_values: Dict[Tuple, List[float]] = defaultdict(list)

    for class_key, values in class_measurements.items():
        nom = values.get("nom")
        wmc = values.get("wmc")
        if nom is None or wmc is None or nom <= 0.0:
            continue
        module_key = (class_key[0], class_key[1]) + class_key[3:]
        module_values[module_key].append(wmc / nom)

    derived_rows: List[Dict] = []
    for key in sorted(module_values.keys()):
        proxies = module_values[key]
        if not proxies:
            continue
        project, module, source_tool, source_variant, tool_version, timestamp_utc, schema_version, run_id = key
        mean_proxy = round(sum(proxies) / len(proxies), 6)
        normalized_variant = "ck-normalized"
        derived_rows.append(
            {
                "schema_version": schema_version,
                "run_id": run_id,
                "project": project,
                "metric": "cc",
                "variant": normalized_variant,
                "component_type": "module",
                "component": module,
                "status": "ok",
                "value": mean_proxy,
                "tool": source_tool,
                "tool_version": tool_version,
                "parameters": {
                    "derived_from": "wmc/nom",
                    "aggregation": "module-mean",
                    "class_count": len(proxies),
                },
                "timestamp_utc": timestamp_utc,
                "source_tool": source_tool,
                "source_variant": source_variant,
                "source_file": source_file,
            }
        )
    return derived_rows


def _module_from_method_component(row: Dict) -> Optional[str]:
    params = row.get("parameters")
    if isinstance(params, dict):
        for key in ("module", "module_name"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    component = row.get("component")
    if not isinstance(component, str) or not component.strip():
        return None

    component_text = component.strip().replace("\\", "/")
    file_part = component_text.split("::", 1)[0]
    file_part = file_part.lstrip("./")
    if "/" in file_part:
        head = file_part.split("/", 1)[0].strip()
        if head:
            return head
    return file_part or None


def _derive_lizard_module_cc(rows: List[Dict], source_file: str) -> List[Dict]:
    module_values: Dict[Tuple, List[float]] = defaultdict(list)

    for row in rows:
        if str(row.get("status", "ok")).strip().lower() != "ok":
            continue
        if str(row.get("metric", "")).strip() != "cc":
            continue
        if str(row.get("tool", "")).strip() != "lizard":
            continue
        if str(row.get("component_type", "")).strip().lower() != "method":
            continue

        value = _safe_float(row.get("value"))
        if value is None:
            continue

        project = row.get("project")
        module = _module_from_method_component(row)
        if not isinstance(project, str) or not project.strip() or not module:
            continue

        key = (
            project.strip(),
            module,
            str(row.get("tool", "unknown")),
            "lizard-module-mean",
            str(row.get("tool_version", "unknown")),
            str(row.get("timestamp_utc", utc_timestamp_now())),
            str(row.get("schema_version", "1.0")),
            str(row.get("run_id", "unknown")),
            str(row.get("variant", "lizard-default")),
        )
        module_values[key].append(float(value))

    derived_rows: List[Dict] = []
    for key in sorted(module_values.keys()):
        values = module_values[key]
        if not values:
            continue
        project, module, source_tool, derived_variant, tool_version, timestamp_utc, schema_version, run_id, source_variant = key
        derived_rows.append(
            {
                "schema_version": schema_version,
                "run_id": run_id,
                "project": project,
                "metric": "cc",
                "variant": derived_variant,
                "component_type": "module",
                "component": module,
                "status": "ok",
                "value": round(sum(values) / len(values), 6),
                "tool": source_tool,
                "tool_version": tool_version,
                "parameters": {
                    "derived_from": "method_cc",
                    "aggregation": "module-mean",
                    "method_count": len(values),
                },
                "timestamp_utc": timestamp_utc,
                "source_tool": source_tool,
                "source_variant": source_variant,
                "source_file": source_file,
            }
        )

    return derived_rows


def _derive_instability_from_ce_ca(rows: List[Dict], source_file: str) -> List[Dict]:
    ce_ca: Dict[Tuple, Dict[str, Dict[str, Optional[float]]]] = defaultdict(dict)

    def _replace(existing: Optional[Dict], candidate: Dict) -> bool:
        if existing is None:
            return True
        existing_ok = str(existing.get("status", "")).lower() == "ok" and existing.get("value") is not None
        candidate_ok = str(candidate.get("status", "")).lower() == "ok" and candidate.get("value") is not None
        if candidate_ok and not existing_ok:
            return True
        if candidate_ok and existing_ok:
            return True
        return False

    for row in rows:
        dimension = _infer_dimension(row)
        if dimension not in {"ce", "ca"}:
            continue

        metric_norm = str(row.get("metric", "")).strip().lower().replace("-", "_")
        if metric_norm not in {"ce_ca", "ce", "ca"}:
            continue

        project = _non_empty_string(row.get("project"))
        run_id = _non_empty_string(row.get("run_id"))
        timestamp_utc = _non_empty_string(row.get("timestamp_utc"))
        component_type = _non_empty_string(row.get("component_type"))
        component = _non_empty_string(row.get("component"))
        tool = _non_empty_string(row.get("tool"))
        variant = _non_empty_string(row.get("variant"))
        tool_version = _non_empty_string(row.get("tool_version"))
        schema_version = _non_empty_string(row.get("schema_version"))
        if not all([project, run_id, timestamp_utc, component_type, component, tool, variant, tool_version, schema_version]):
            continue

        key = (
            project,
            run_id,
            timestamp_utc,
            component_type,
            component,
            tool,
            variant,
        )
        status = str(row.get("status", "ok")).strip().lower()
        value = _safe_float(row.get("value")) if status == "ok" else None
        candidate = {
            "status": status,
            "value": value,
            "tool_version": tool_version,
            "schema_version": schema_version,
        }
        existing = ce_ca[key].get(dimension)
        if _replace(existing, candidate):
            ce_ca[key][dimension] = candidate

    derived_rows: List[Dict] = []
    for key in sorted(ce_ca.keys()):
        values = ce_ca[key]
        project, run_id, timestamp_utc, component_type, component, source_tool, source_variant = key
        ce_info = values.get("ce")
        ca_info = values.get("ca")

        base_tool_version = "unknown"
        base_schema_version = "1.0"
        for item in (ce_info, ca_info):
            if isinstance(item, dict):
                if isinstance(item.get("tool_version"), str) and item.get("tool_version"):
                    base_tool_version = str(item["tool_version"])
                if isinstance(item.get("schema_version"), str) and item.get("schema_version"):
                    base_schema_version = str(item["schema_version"])

        row = {
            "schema_version": base_schema_version,
            "run_id": run_id,
            "project": project,
            "metric": "instability",
            "variant": f"{source_variant}-derived",
            "component_type": component_type,
            "component": component,
            "tool": source_tool,
            "tool_version": base_tool_version,
            "parameters": {
                "derived_from": "ce-ca",
                "formula": "Ce/(Ce+Ca)",
                "source_metrics": ["ce", "ca"],
                "scope": "component",
                "undefined_when": "Ce+Ca=0",
            },
            "timestamp_utc": timestamp_utc,
            "source_tool": source_tool,
            "source_variant": source_variant,
            "source_file": source_file,
        }

        if not ce_info or not ca_info:
            row["status"] = "skipped"
            row["skip_reason"] = "missing_ce_or_ca"
            row["value"] = None
            derived_rows.append(row)
            continue

        ce_status = str(ce_info.get("status", "")).lower()
        ca_status = str(ca_info.get("status", "")).lower()
        ce_value = _safe_float(ce_info.get("value"))
        ca_value = _safe_float(ca_info.get("value"))
        if ce_status != "ok" or ca_status != "ok" or ce_value is None or ca_value is None:
            row["status"] = "skipped"
            row["skip_reason"] = "missing_ce_or_ca"
            row["value"] = None
            derived_rows.append(row)
            continue

        denom = float(ce_value) + float(ca_value)
        if denom == 0.0:
            row["status"] = "skipped"
            row["skip_reason"] = "zero_denominator"
            row["value"] = None
            derived_rows.append(row)
            continue

        row["status"] = "ok"
        row["value"] = round(float(ce_value) / denom, 6)
        derived_rows.append(row)
    return derived_rows


def normalize_rows(rows: List[Dict], source_file: str) -> List[Dict]:
    canonical_rows = _backfill_required_metadata(rows, source_file=source_file)
    normalized = list(canonical_rows)
    normalized.extend(_derive_cc_from_wmc_nom(canonical_rows, source_file=source_file))
    normalized.extend(_derive_lizard_module_cc(canonical_rows, source_file=source_file))
    normalized.extend(_derive_instability_from_ce_ca(canonical_rows, source_file=source_file))
    return normalized


def normalize_file(input_file: Path, output_file: Path, input_root: Path) -> int:
    rows = read_jsonl(input_file)
    rel_source = str(input_file.relative_to(input_root)).replace("\\", "/")
    normalized_rows = normalize_rows(rows, source_file=rel_source)
    write_jsonl(output_file, normalized_rows)
    return len(normalized_rows) - len(rows)


def normalize_results(input_dir: Path, output_dir: Path) -> Dict[str, int]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    files = sorted(
        path
        for path in input_dir.rglob("*.jsonl")
        if path.is_file() and not _is_telemetry_jsonl(path)
    )

    summary = {"files": 0, "input_rows": 0, "derived_rows": 0, "output_rows": 0}
    for input_file in files:
        rows = read_jsonl(input_file)
        rel = input_file.relative_to(input_dir)
        output_file = output_dir / rel
        rel_source = str(rel).replace("\\", "/")
        output_rows = normalize_rows(rows, source_file=rel_source)
        write_jsonl(output_file, output_rows)

        summary["files"] += 1
        summary["input_rows"] += len(rows)
        summary["output_rows"] += len(output_rows)
        summary["derived_rows"] += max(0, len(output_rows) - len(rows))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize metric JSONL outputs for analysis.")
    parser.add_argument("input_dir", nargs="?", default="results", help="Input JSONL folder (default: results)")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="results_normalized",
        help="Output JSONL folder (default: results_normalized)",
    )
    args = parser.parse_args()

    summary = normalize_results(Path(args.input_dir), Path(args.output_dir))
    print(
        "Normalized files={files} input_rows={input_rows} derived_rows={derived_rows} output_rows={output_rows}".format(
            **summary
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
