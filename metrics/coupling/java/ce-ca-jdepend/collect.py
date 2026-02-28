#!/usr/bin/env python3
import argparse
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

from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector

METRIC_NAME = "ce-ca"
VARIANT_NAME = "jdepend-default"
TOOL_NAME = "jdepend"
TOOL_JAR = "/opt/tools/jdepend.jar"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}
BYTECODE_DIR_CANDIDATES = (
    "target/classes",
    "build/classes/java/main",
    "build/classes/kotlin/main",
    "build/classes",
    "out/production",
)

PACKAGE_RE = re.compile(r"^(?:-+\s*)?Package:?\s+(.+)$")
CA_RE = re.compile(r"\bCa:\s*([0-9]+)")
CE_RE = re.compile(r"\bCe:\s*([0-9]+)")
I_RE = re.compile(r"\bI:\s*([0-9]*\.?[0-9]+)")


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


def _env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def allow_local_compile_fallback():
    return _env_flag("JDEPEND_ENABLE_LOCAL_COMPILE_FALLBACK", default=True)


def fallback_java_release():
    raw = str(os.environ.get("JDEPEND_FALLBACK_JAVA_RELEASE", "8")).strip()
    return raw if raw.isdigit() and int(raw) > 0 else "8"


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


def discover_class_files(base_dir):
    class_files = []
    for root, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(filenames):
            if filename.endswith(".class") and not filename.startswith("."):
                class_files.append(os.path.join(root, filename))
    return class_files


def discover_module_class_files(module_path):
    class_files = []
    seen = set()
    inputs = []
    for rel_dir in BYTECODE_DIR_CANDIDATES:
        candidate_dir = os.path.join(module_path, rel_dir)
        if not os.path.isdir(candidate_dir):
            continue
        inputs.append(candidate_dir)
        for class_file in discover_class_files(candidate_dir):
            if class_file in seen:
                continue
            seen.add(class_file)
            class_files.append(class_file)
    return class_files, inputs


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
            packages[current] = {"ca": 0, "ce": 0, "i": 0.0}
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


def compile_module_sources(sources, dry_run):
    classes_dir = tempfile.mkdtemp(prefix="jdepend-classes-")
    release = fallback_java_release()
    cmd = ["javac", "--release", release, "-proc:none", "-Xlint:none", "-d", classes_dir]
    cmd.extend(sources)
    if dry_run:
        print("DRY_RUN:", " ".join(shlex.quote(part) for part in cmd))
        return {
            "ok": True,
            "classes_dir": classes_dir,
            "class_files": [],
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "release": release,
        }
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return {
            "ok": False,
            "classes_dir": classes_dir,
            "class_files": [],
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "exit_code": int(completed.returncode),
            "release": release,
        }
    return {
        "ok": True,
        "classes_dir": classes_dir,
        "class_files": discover_class_files(classes_dir),
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "exit_code": int(completed.returncode),
        "release": release,
    }


def aggregate_ce_ca(module_path, dry_run):
    sources = find_java_sources(module_path)
    prebuilt_class_files, prebuilt_inputs = discover_module_class_files(module_path)
    cleanup_dir = None
    class_files = list(prebuilt_class_files)
    jdepend_inputs = list(prebuilt_inputs)
    bytecode_mode = "prebuilt"
    compile_exit_code = None
    compile_release = None

    try:
        if dry_run:
            if class_files:
                print(
                    "DRY_RUN:",
                    " ".join(
                        shlex.quote(part)
                        for part in ["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", *jdepend_inputs]
                    ),
                )
            elif sources and allow_local_compile_fallback():
                compiled = compile_module_sources(sources, dry_run=True)
                cleanup_dir = compiled["classes_dir"]
                compile_release = compiled.get("release")
                print(
                    "DRY_RUN:",
                    " ".join(
                        shlex.quote(part)
                        for part in ["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", compiled["classes_dir"]]
                    ),
                )
            return {
                "status": "ok",
                "ce": 0.0,
                "ca": 0.0,
                "class_files_found": len(class_files),
                "java_sources_found": len(sources),
                "bytecode_inputs": jdepend_inputs,
                "bytecode_mode": bytecode_mode if class_files else "dry-run",
                "compile_exit_code": compile_exit_code,
                "compile_release": compile_release,
            }

        if not class_files:
            if not sources:
                return {
                    "status": "ok",
                    "ce": 0.0,
                    "ca": 0.0,
                    "class_files_found": 0,
                    "java_sources_found": 0,
                    "bytecode_inputs": [],
                    "bytecode_mode": "not-applicable",
                    "compile_exit_code": compile_exit_code,
                    "compile_release": compile_release,
                }

        prebuilt_skip_reason = None
        if class_files:
            try:
                output = run_command(["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", *jdepend_inputs], dry_run=False)
                packages = parse_jdepend_text(output)
                if packages:
                    ce_total = float(sum(item.get("ce", 0) for item in packages.values()))
                    ca_total = float(sum(item.get("ca", 0) for item in packages.values()))
                    return {
                        "status": "ok",
                        "ce": ce_total,
                        "ca": ca_total,
                        "class_files_found": len(class_files),
                        "java_sources_found": len(sources),
                        "bytecode_inputs": jdepend_inputs,
                        "bytecode_mode": bytecode_mode,
                        "compile_exit_code": compile_exit_code,
                        "compile_release": compile_release,
                    }
                prebuilt_skip_reason = "jdepend_empty_output"
            except RuntimeError:
                prebuilt_skip_reason = "jdepend_execution_failed"

        if sources and allow_local_compile_fallback():
            compiled = compile_module_sources(sources, dry_run=False)
            cleanup_dir = compiled["classes_dir"]
            compile_exit_code = compiled["exit_code"]
            compile_release = compiled.get("release")
            if not compiled["ok"]:
                skip_reason = "missing_bytecode_compile_failed"
                if prebuilt_skip_reason:
                    skip_reason = f"{prebuilt_skip_reason}_compile_failed"
                return {
                    "status": "skipped",
                    "skip_reason": skip_reason,
                    "ce": None,
                    "ca": None,
                    "class_files_found": len(class_files),
                    "java_sources_found": len(sources),
                    "bytecode_inputs": jdepend_inputs,
                    "bytecode_mode": "missing" if not class_files else "prebuilt",
                    "compile_exit_code": compile_exit_code,
                    "compile_release": compile_release,
                }
            compiled_class_files = list(compiled.get("class_files", []))
            if not compiled_class_files:
                return {
                    "status": "skipped",
                    "skip_reason": "missing_bytecode_compile_empty",
                    "ce": None,
                    "ca": None,
                    "class_files_found": len(class_files),
                    "java_sources_found": len(sources),
                    "bytecode_inputs": jdepend_inputs,
                    "bytecode_mode": "missing" if not class_files else "prebuilt",
                    "compile_exit_code": compile_exit_code,
                    "compile_release": compile_release,
                }
            try:
                local_inputs = [compiled["classes_dir"]]
                output = run_command(["java", "-cp", TOOL_JAR, "jdepend.textui.JDepend", *local_inputs], dry_run=False)
            except RuntimeError:
                return {
                    "status": "skipped",
                    "skip_reason": "jdepend_execution_failed",
                    "ce": None,
                    "ca": None,
                    "class_files_found": len(compiled_class_files),
                    "java_sources_found": len(sources),
                    "bytecode_inputs": local_inputs,
                    "bytecode_mode": "local-compile",
                    "compile_exit_code": compile_exit_code,
                    "compile_release": compile_release,
                }
            packages = parse_jdepend_text(output)
            if packages:
                ce_total = float(sum(item.get("ce", 0) for item in packages.values()))
                ca_total = float(sum(item.get("ca", 0) for item in packages.values()))
                return {
                    "status": "ok",
                    "ce": ce_total,
                    "ca": ca_total,
                    "class_files_found": len(compiled_class_files),
                    "java_sources_found": len(sources),
                    "bytecode_inputs": local_inputs,
                    "bytecode_mode": "local-compile",
                    "compile_exit_code": compile_exit_code,
                    "compile_release": compile_release,
                }
            return {
                "status": "skipped",
                "skip_reason": "jdepend_empty_output",
                "ce": None,
                "ca": None,
                "class_files_found": len(compiled_class_files),
                "java_sources_found": len(sources),
                "bytecode_inputs": local_inputs,
                "bytecode_mode": "local-compile",
                "compile_exit_code": compile_exit_code,
                "compile_release": compile_release,
            }

        if prebuilt_skip_reason:
            return {
                "status": "skipped",
                "skip_reason": prebuilt_skip_reason,
                "ce": None,
                "ca": None,
                "class_files_found": len(class_files),
                "java_sources_found": len(sources),
                "bytecode_inputs": jdepend_inputs,
                "bytecode_mode": "prebuilt",
                "compile_exit_code": compile_exit_code,
                "compile_release": compile_release,
            }

        return {
            "status": "skipped",
            "skip_reason": "missing_bytecode",
            "ce": None,
            "ca": None,
            "class_files_found": 0,
            "java_sources_found": len(sources),
            "bytecode_inputs": list(prebuilt_inputs),
            "bytecode_mode": "missing",
            "compile_exit_code": compile_exit_code,
            "compile_release": compile_release,
        }
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def build_dimension_row(project, module, dimension, module_stats, timestamp, version):
    status = str(module_stats.get("status", "ok"))
    row = {
        "project": project,
        "metric": METRIC_NAME,
        "variant": VARIANT_NAME,
        "component_type": "module",
        "component": module,
        "value": float(module_stats[dimension]) if status == "ok" else None,
        "tool": TOOL_NAME,
        "tool_version": version,
        "parameters": {
            "category": "coupling",
            "dimension": dimension,
            "metric_source": "jdepend-bytecode",
            "bytecode_mode": module_stats.get("bytecode_mode", "unknown"),
            "bytecode_inputs": list(module_stats.get("bytecode_inputs", [])),
            "class_files_found": int(module_stats.get("class_files_found", 0)),
            "java_sources_found": int(module_stats.get("java_sources_found", 0)),
            "compile_exit_code": module_stats.get("compile_exit_code"),
            "compile_release": module_stats.get("compile_release"),
            "ignored_dirs": sorted(VENDOR_DIRS),
            "exclude_tests": True,
        },
        "timestamp_utc": timestamp,
    }
    if status == "skipped":
        row["status"] = "skipped"
        row["skip_reason"] = str(module_stats.get("skip_reason", "invalid_module_input"))
    return row


def main():
    parser = argparse.ArgumentParser(description="Collect module-level Ce/Ca with JDepend")
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
            module_stats = aggregate_ce_ca(module_path, args.dry_run)
            rows.append(build_dimension_row(project, module, "ce", module_stats, timestamp, version))
            rows.append(build_dimension_row(project, module, "ca", module_stats, timestamp, version))

        target = output_path(args.results_dir, project, timestamp)
        if args.dry_run:
            print("DRY_RUN: would write", len(rows), "rows to", target)
            continue
        write_jsonl_rows(target, rows, run_id=run_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_collector(main))
