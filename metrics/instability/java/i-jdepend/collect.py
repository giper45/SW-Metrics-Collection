#!/usr/bin/env python3
import argparse
import json
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

METRIC_NAME = "instability"
VARIANT_NAME = "jdepend-default"
TOOL_NAME = "jdepend"
TOOL_JAR = "/opt/tools/jdepend.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}

PACKAGE_RE = re.compile(r"^Package\s+(.+)$")
CA_RE = re.compile(r"\bCa:\s*([0-9]+)")
CE_RE = re.compile(r"\bCe:\s*([0-9]+)")
I_RE = re.compile(r"\bI:\s*([0-9]*\.?[0-9]+)")
JAVA_PACKAGE_DECL_RE = re.compile(r"^\s*package\s+([A-Za-z_][\w.]*)\s*;")
JAVA_IMPORT_DECL_RE = re.compile(r"^\s*import\s+(?:static\s+)?([A-Za-z_][\w.]*)(?:\.\*)?\s*;")


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


def infer_source_root(java_file):
    directory = os.path.dirname(java_file)
    try:
        with open(java_file, "r", encoding="utf-8", errors="ignore") as handle:
            for _ in range(80):
                line = handle.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped.startswith("package ") and ";" in stripped:
                    package_name = stripped[len("package ") : stripped.index(";")].strip()
                    if not package_name:
                        break
                    suffix = os.path.join(*package_name.split("."))
                    if directory.endswith(suffix):
                        root = directory[: -len(suffix)].rstrip(os.sep)
                        return root or os.sep
                    break
    except OSError:
        return None
    return None


def discover_source_roots(project_path, module_sources):
    roots = set()
    for source in find_java_sources(project_path):
        inferred = infer_source_root(source)
        if inferred:
            roots.add(inferred)
    if roots:
        return sorted(roots)
    return sorted({os.path.dirname(source) for source in module_sources})


def run_command(cmd, dry_run):
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return ""
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(cmd)}\\n"
            f"stdout: {completed.stdout}\\n"
            f"stderr: {completed.stderr}"
        )
    return completed.stdout


def parse_jdepend_text(raw_output):
    packages = {}
    current = None

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        package_match = PACKAGE_RE.match(line)
        if package_match:
            current = package_match.group(1).strip()
            packages[current] = {"ca": 0, "ce": 0, "i": None}
            continue

        if current is None:
            continue

        ca_match = CA_RE.search(line)
        if ca_match:
            packages[current]["ca"] = int(ca_match.group(1))

        ce_match = CE_RE.search(line)
        if ce_match:
            packages[current]["ce"] = int(ce_match.group(1))

        i_match = I_RE.search(line)
        if i_match:
            packages[current]["i"] = float(i_match.group(1))

    return packages


def parse_java_packages_and_imports(sources):
    package_to_imports = {}
    package_names = set()

    for source in sources:
        package_name = None
        imports = set()
        try:
            with open(source, "r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("//") or line.startswith("*"):
                        continue
                    package_match = JAVA_PACKAGE_DECL_RE.match(line)
                    if package_match:
                        package_name = package_match.group(1).strip()
                        continue
                    import_match = JAVA_IMPORT_DECL_RE.match(line)
                    if import_match:
                        imports.add(import_match.group(1).strip())
        except OSError:
            continue

        if not package_name:
            continue

        package_names.add(package_name)
        package_to_imports.setdefault(package_name, set()).update(imports)

    return package_names, package_to_imports


def match_known_package(import_path, known_packages):
    candidates = [
        package
        for package in known_packages
        if import_path == package or import_path.startswith(package + ".")
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def aggregate_source_instability(sources):
    package_names, package_to_imports = parse_java_packages_and_imports(sources)
    if not package_names:
        return 0.0

    ce_by_package = {}
    for package in package_names:
        deps = set()
        for import_path in package_to_imports.get(package, set()):
            matched = match_known_package(import_path, package_names)
            if matched and matched != package:
                deps.add(matched)
        ce_by_package[package] = deps

    ca_by_package = {package: set() for package in package_names}
    for package, deps in ce_by_package.items():
        for dep in deps:
            ca_by_package.setdefault(dep, set()).add(package)

    values = []
    for package in sorted(package_names):
        ce_val = float(len(ce_by_package.get(package, set())))
        ca_val = float(len(ca_by_package.get(package, set())))
        denom = ce_val + ca_val
        values.append(0.0 if denom == 0 else ce_val / denom)

    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def compute_module_instability(project_path, module_path, dry_run):
    sources = find_java_sources(module_path)
    if not sources:
        return 0.0

    classes_dir = tempfile.mkdtemp(prefix="jdepend-classes-")
    try:
        javac_cmd = ["javac", "-proc:none", "-Xlint:none", "-d", classes_dir]
        source_roots = discover_source_roots(project_path, sources)
        if source_roots:
            javac_cmd.extend(["-sourcepath", os.pathsep.join(source_roots)])
        javac_cmd.extend(sources)

        if dry_run:
            print("DRY_RUN:", " ".join(shlex.quote(part) for part in javac_cmd))
            return 0.0
        subprocess.run(javac_cmd, capture_output=True, text=True, check=False)

        class_files = []
        for root, _, filenames in os.walk(classes_dir):
            for filename in filenames:
                if filename.endswith(".class"):
                    class_files.append(os.path.join(root, filename))

        output = ""
        if class_files:
            output = run_command(["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", classes_dir], dry_run)
        if dry_run:
            return 0.0

        packages = parse_jdepend_text(output)
        if not packages:
            return aggregate_source_instability(sources)

        ce_total = float(sum(float(data.get("ce", 0)) for data in packages.values()))
        ca_total = float(sum(float(data.get("ca", 0)) for data in packages.values()))
        denom = ce_total + ca_total
        if denom <= 0.0:
            return 0.0
        return round(ce_total / denom, 6)
    finally:
        shutil.rmtree(classes_dir, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect module-level instability with JDepend")
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
    version = os.environ.get("JDEPEND_VERSION", "unknown") if not args.dry_run else "dry-run"

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path):
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module,
                    "value": compute_module_instability(project_path, module_path, args.dry_run),
                    "tool": TOOL_NAME,
                    "tool_version": version,
                    "parameters": {
                        "category": "instability",
                        "formula": "Ce/(Ca+Ce)",
                        "fallback": "source-package-dependency-when-jdepend-empty",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        "exclude_tests": True,
                    },
                    "timestamp_utc": timestamp,
                }
            )

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
