#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import tempfile


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector, run_command_stdout
from data_manager import build_module_metric_rows, numeric_max, numeric_mean, numeric_percentile, read_csv_rows, safe_float
from utils import (
    choose_java_input_path,
    find_java_sources,
    metric_output_path,
    resolve_output_file_path,
    utc_timestamp_now,
)
from config import VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects)

METRIC_NAME = "wmc"
VARIANT_NAME = "ck-raw"
TOOL_NAME = "ck"
CK_JAR = "/opt/tools/ck.jar"

TEST_PACKAGE_TOKENS = {"test", "tests", "testing", "spec", "specs"}
TEST_CLASS_RE = re.compile(r"(?:^|\.)(test|tests|it|spec)$", re.IGNORECASE)


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


def parse_ck_wmc_values(raw_output):
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


def compute_cc_proxy_from_ck_csv(class_csv_path):
    """
    Compute module-level CC proxy statistics from class-level CK CSV.
    Per class:
      cc_proxy_class = WMC / NOM
      NOM == 0 => class ignored

    Test classes/packages are excluded.
    Missing or invalid values are ignored.
    """
    if not os.path.isfile(class_csv_path):
        return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

    rows = read_csv_rows(class_csv_path)
    if not rows:
        return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

    fieldnames = list(rows[0].keys())
    wmc_col = _resolve_column(fieldnames, ["wmc"])
    nom_col = _resolve_column(
        fieldnames,
        ["nom", "number_of_methods", "methods", "totalMethodsQty", "total_methods_qty"])
    class_col = _resolve_column(fieldnames, ["class", "class_name", "type", "type_name", "fqn", "name"])
    package_col = _resolve_column(fieldnames, ["package", "package_name", "pkg", "namespace"])

    if not wmc_col or not nom_col:
        return {"cc_proxy_mean": 0.0, "cc_proxy_max": 0.0, "cc_proxy_p95": 0.0, "valid_classes": 0}

    class_values = []
    for row in rows:
        wmc = safe_float(row.get(wmc_col))
        nom = safe_float(row.get(nom_col))
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
        "cc_proxy_mean": numeric_mean(class_values),
        "cc_proxy_max": numeric_max(class_values),
        "cc_proxy_p95": numeric_percentile(class_values, 95.0),
        "valid_classes": len(class_values),
    }


# Backward-compatibility aliases (legacy ckjm naming).
def parse_ckjm_wmc_values(raw_output):
    return parse_ck_wmc_values(raw_output)


def compute_cc_proxy_from_ckjm(class_csv_path):
    return compute_cc_proxy_from_ck_csv(class_csv_path)


def compute_wmc_nom_totals_from_ck(class_csv_path):
    if not os.path.isfile(class_csv_path):
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    rows = read_csv_rows(class_csv_path)
    if not rows:
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    fieldnames = list(rows[0].keys())
    wmc_col = _resolve_column(fieldnames, ["wmc"])
    nom_col = _resolve_column(
        fieldnames,
        ["nom", "number_of_methods", "methods", "totalMethodsQty", "total_methods_qty"])
    class_col = _resolve_column(fieldnames, ["class", "class_name", "type", "type_name", "fqn", "name"])
    package_col = _resolve_column(fieldnames, ["package", "package_name", "pkg", "namespace"])

    if not wmc_col or not nom_col:
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    wmc_total = 0.0
    nom_total = 0.0
    valid_classes = 0
    skipped_nom_zero = 0

    for row in rows:
        wmc = safe_float(row.get(wmc_col))
        nom = safe_float(row.get(nom_col))
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


def collect_module_raw_stats(module_path):
    java_input = choose_java_input_path(module_path)
    sources = find_java_sources(java_input)
    if not sources:
        return {"wmc": 0.0, "nom": 0.0, "valid_classes": 0, "skipped_nom_zero": 0}

    out_dir = tempfile.mkdtemp(prefix="ck-out-")
    try:
        run_command_stdout(
            ["java", "-jar", CK_JAR, java_input, "false", "0", "false", out_dir + os.sep])
        class_csv = resolve_output_file_path(out_dir, "class.csv")
        return compute_wmc_nom_totals_from_ck(class_csv)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def build_raw_rows(project, module, stats, tool_version, timestamp):
    return build_module_metric_rows(
        project=project,
        module=module,
        variant=VARIANT_NAME,
        tool=TOOL_NAME,
        tool_version=tool_version,
        timestamp_utc=timestamp,
        default_metric=METRIC_NAME,
        base_parameters={
            "category": "complexity",
            "language": "java",
            "exclude_tests": True,
            "aggregation": "class_sum_to_module",
            "valid_classes": int(stats.get("valid_classes", 0)),
            "skipped_nom_zero": int(stats.get("skipped_nom_zero", 0)),
            "ignored_dirs": sorted(VENDOR_DIRS),
        },
        specs=[
            {
                "value": float(stats.get("wmc", 0.0)),
                "parameters": {"dimension": "wmc"},
            },
            {
                "metric": "nom",
                "value": float(stats.get("nom", 0.0)),
                "parameters": {"dimension": "nom"},
            },
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Collect raw module-level WMC and NOM with CK")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(
        discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS),
        app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    version = os.environ.get("CK_VERSION", "unknown")

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(
            project,
            project_path,
            vendor_dirs=VENDOR_DIRS):
            stats = collect_module_raw_stats(module_path)
            rows.extend(build_raw_rows(project, module, stats, version, timestamp))

        target = metric_output_path(
            args.results_dir,
            project,
            timestamp,
            METRIC_NAME,
            TOOL_NAME,
            VARIANT_NAME,
        )
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
