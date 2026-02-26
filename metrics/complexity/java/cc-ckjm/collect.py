#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

_COMMON_DIR = None
for _parent in Path(__file__).resolve().parents:
    _candidate = _parent / "common" / "result_writer.py"
    if _candidate.is_file():
        _COMMON_DIR = _candidate.parent
        break
if _COMMON_DIR and str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from result_writer import filter_projects, generate_run_id, run_collector, write_jsonl_rows

METRIC_NAME = "wmc"
VARIANT_NAME = "ckjm-raw"
TOOL_NAME = "ckjm"
CK_JAR = "/opt/tools/ck.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}
TEST_PACKAGE_TOKENS = {"test", "tests", "testing", "spec", "specs"}
TEST_CLASS_RE = re.compile(r"(?:^|\.)(test|tests|it|spec)$", re.IGNORECASE)


def utc_timestamp_now():
    forced = os.environ.get("METRIC_TIMESTAMP_UTC") or os.environ.get("METRIC_TIMESTAMP")
    if forced:
        return forced
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_ignored_dir(name):
    return name.startswith(".") or name in VENDOR_DIRS


def is_test_dir(name):
    lowered = name.lower()
    return lowered in TEST_DIR_NAMES or lowered.startswith("test")


def discover_projects(app_dir):
    try:
        entries = sorted(os.listdir(app_dir))
    except OSError:
        return []
    return [
        (name, os.path.join(app_dir, name))
        for name in entries
        if os.path.isdir(os.path.join(app_dir, name)) and not is_ignored_dir(name)
    ]


def discover_modules(project_name, project_path):
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []
    modules = [
        (name, os.path.join(project_path, name))
        for name in entries
        if os.path.isdir(os.path.join(project_path, name)) and not is_ignored_dir(name)
    ]
    return modules or [(project_name, project_path)]


def find_java_sources(module_path):
    sources = []
    for root, dirnames, filenames in os.walk(module_path):
        dirnames[:] = sorted(
            d for d in dirnames if not is_ignored_dir(d) and not is_test_dir(d)
        )
        for filename in sorted(filenames):
            if filename.endswith(".java") and not filename.startswith("."):
                sources.append(os.path.join(root, filename))
    return sources


def choose_java_input_path(module_path):
    candidates = [
        os.path.join(module_path, "main", "java"),
        os.path.join(module_path, "src", "main", "java"),
        module_path,
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return module_path


def run_command(cmd, dry_run):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return ""
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\n"
            f"stdout: {completed.stdout}\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout


def resolve_ck_csv_path(out_dir, filename):
    path = os.path.join(out_dir, filename)
    if os.path.isfile(path):
        return path
    fallback = f"{out_dir}{filename}"
    if os.path.isfile(fallback):
        return fallback
    return path


def _normalize_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").strip().lower())


def _resolve_column(fieldnames, candidates):
    if not fieldnames:
        return None
    by_norm = {_normalize_key(col): col for col in fieldnames}
    for candidate in candidates:
        found = by_norm.get(_normalize_key(candidate))
        if found:
            return found
    return None


def _safe_float(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _extract_package(row, package_col, class_col):
    package_name = (row.get(package_col, "") if package_col else "").strip()
    if package_name:
        return package_name
    class_name = (row.get(class_col, "") if class_col else "").strip()
    if "." in class_name:
        return class_name.rsplit(".", 1)[0]
    return ""


def _is_test_package(package_name, class_name):
    package_tokens = {part.lower() for part in package_name.split(".") if part}
    if package_tokens & TEST_PACKAGE_TOKENS:
        return True

    simple_name = class_name.split(".")[-1] if class_name else ""
    lowered = simple_name.lower()
    if lowered.endswith("test") or lowered.endswith("tests") or lowered.endswith("spec"):
        return True
    return bool(TEST_CLASS_RE.search(simple_name))


def _percentile(values, p):
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(float(v) for v in values)
    rank = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_values[lo]
    frac = rank - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def parse_ckjm_wmc_values(raw_output):
    values = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            values.append(float(parts[1]))
        except ValueError:
            continue
    return values


def compute_cc_proxy_from_ckjm(class_csv_path):
    """
    Compute module-level CC proxy statistics from class-level CK/CKJM CSV.
    Per class:
      cc_proxy_class = WMC / NOM
      NOM == 0 => class ignored

    Test classes/packages are excluded.
    Missing or invalid values are ignored.
    """
    if not os.path.isfile(class_csv_path):
        return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

    with open(class_csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []

        wmc_col = _resolve_column(fieldnames, ["wmc"])
        nom_col = _resolve_column(
            fieldnames,
            ["nom", "number_of_methods", "methods", "totalMethodsQty", "total_methods_qty"],
        )
        class_col = _resolve_column(fieldnames, ["class", "class_name", "type", "type_name", "fqn", "name"])
        package_col = _resolve_column(fieldnames, ["package", "package_name", "pkg", "namespace"])

        if not wmc_col or not nom_col:
            return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

        class_values = []
        for row in reader:
            wmc = _safe_float(row.get(wmc_col))
            nom = _safe_float(row.get(nom_col))
            if wmc is None or nom is None or nom <= 0.0:
                continue

            class_name = (row.get(class_col, "") if class_col else "").strip()
            package_name = _extract_package(row, package_col, class_col)
            if _is_test_package(package_name, class_name):
                continue

            class_values.append(wmc / nom)

    if not class_values:
        return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

    return {
        "cc_proxy_mean": round(sum(class_values) / len(class_values), 6),
        "cc_proxy_max": round(max(class_values), 6),
        "cc_proxy_p95": round(_percentile(class_values, 95.0), 6),
        "valid_classes": len(class_values),
    }


def compute_wmc_nom_totals_from_ckjm(class_csv_path):
    if not os.path.isfile(class_csv_path):
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    with open(class_csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []

        wmc_col = _resolve_column(fieldnames, ["wmc"])
        nom_col = _resolve_column(
            fieldnames,
            ["nom", "number_of_methods", "methods", "totalMethodsQty", "total_methods_qty"],
        )
        class_col = _resolve_column(fieldnames, ["class", "class_name", "type", "type_name", "fqn", "name"])
        package_col = _resolve_column(fieldnames, ["package", "package_name", "pkg", "namespace"])

        if not wmc_col or not nom_col:
            return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

        wmc_total = 0.0
        nom_total = 0.0
        valid_classes = 0
        skipped_nom_zero = 0

        for row in reader:
            wmc = _safe_float(row.get(wmc_col))
            nom = _safe_float(row.get(nom_col))
            if wmc is None or nom is None:
                continue

            class_name = (row.get(class_col, "") if class_col else "").strip()
            package_name = _extract_package(row, package_col, class_col)
            if _is_test_package(package_name, class_name):
                continue

            if nom <= 0.0:
                skipped_nom_zero += 1
                continue

            wmc_total += float(wmc)
            nom_total += float(nom)
            valid_classes += 1

    return {
        "wmc": round(wmc_total, 6),
        "nom": round(nom_total, 6),
        "valid_classes": int(valid_classes),
        "skipped_nom_zero": int(skipped_nom_zero),
    }


def collect_module_raw_stats(module_path, dry_run):
    java_input = choose_java_input_path(module_path)
    sources = find_java_sources(java_input)
    if not sources:
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    out_dir = tempfile.mkdtemp(prefix="ck-out-")
    try:
        run_command(
            ["java", "-jar", CK_JAR, java_input, "false", "0", "false", out_dir + os.sep],
            dry_run,
        )
        if dry_run:
            return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}
        class_csv = resolve_ck_csv_path(out_dir, "class.csv")
        return compute_wmc_nom_totals_from_ckjm(class_csv)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def build_raw_rows(project, module, stats, tool_version, timestamp):
    base_parameters = {
        "category": "complexity",
        "language": "java",
        "exclude_tests": True,
        "aggregation": "class_sum_to_module",
        "valid_classes": int(stats.get("valid_classes", 0)),
        "skipped_nom_zero": int(stats.get("skipped_nom_zero", 0)),
        "ignored_dirs": sorted(VENDOR_DIRS),
    }
    return [
        {
            "project": project,
            "component": module,
            "component_type": "module",
            "metric": "wmc",
            "tool": TOOL_NAME,
            "variant": VARIANT_NAME,
            "value": float(stats.get("wmc", 0.0)),
            "tool_version": tool_version,
            "parameters": dict(base_parameters, dimension="wmc"),
            "timestamp_utc": timestamp,
        },
        {
            "project": project,
            "component": module,
            "component_type": "module",
            "metric": "nom",
            "tool": TOOL_NAME,
            "variant": VARIANT_NAME,
            "value": float(stats.get("nom", 0.0)),
            "tool_version": tool_version,
            "parameters": dict(base_parameters, dimension="nom"),
            "timestamp_utc": timestamp,
        },
    ]


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect raw module-level WMC and NOM with CKJM/CK")
    parser.add_argument("--app-dir", default=os.environ.get("SRC_ROOT", os.environ.get("METRIC_APP_DIR", "/app")))
    parser.add_argument("--results-dir", default=os.environ.get("RESULTS_DIR", os.environ.get("METRIC_RESULTS_DIR", "/results")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir), app_dir=args.app_dir)
    if not projects:
        if args.dry_run:
            print("DRY_RUN: no projects discovered")
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    version = os.environ.get("CKJM_VERSION", "unknown") if not args.dry_run else "dry-run"

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path):
            stats = collect_module_raw_stats(module_path, args.dry_run)
            rows.extend(build_raw_rows(project, module, stats, version, timestamp))

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
