#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
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

METRIC_NAME = "maintainability-index"
VARIANT_NAME = "mi-halstead-default"
TOOL_NAME = "java-halstead-analyzer"
TOOL_VERSION = "1.0.0"

VENDOR_DIRS = {"node_modules", "target", "build", ".venv", "venv", ".git"}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing"}
JAVA_EXT = ".java"

JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
    "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
    "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native",
    "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void", "volatile", "while",
}

SYMBOL_OPERATORS = {
    "&&", "||", "==", "!=", "<=", ">=", "<<", ">>", ">>>", "++", "--", "+=", "-=", "*=", "/=", "%=", "&=",
    "|=", "^=", "->", "::", "+", "-", "*", "/", "%", "&", "|", "^", "~", "!", "=", "<", ">", "?", ":", ".",
    "(", ")", "{", "}", "[", "]", ";", ",",
}

TOKEN_RE = re.compile(
    r"//.*?$|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\b[A-Za-z_]\w*\b|\b\d+(?:\.\d+)?\b|&&|\|\||==|!=|<=|>=|>>>=|>>>|>>|<<|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|->|::|[+\-*/%&|^~!=<>?:;,.(){}\[\]]",
    re.S | re.M,
)

DECISION_RE = re.compile(r"\b(if|for|while|case|catch)\b|\?|&&|\|\|")


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


def find_java_files(module_path):
    files = []
    for root, dirnames, filenames in os.walk(module_path):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d) and not is_test_dir(d))
        for filename in sorted(filenames):
            if filename.startswith(".") or not filename.endswith(JAVA_EXT):
                continue
            files.append(os.path.join(root, filename))
    return files


def strip_comments_for_loc(text):
    result = []
    i = 0
    in_block = False
    while i < len(text):
        if not in_block and i + 1 < len(text) and text[i : i + 2] == "//":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if not in_block and i + 1 < len(text) and text[i : i + 2] == "/*":
            in_block = True
            i += 2
            continue
        if in_block and i + 1 < len(text) and text[i : i + 2] == "*/":
            in_block = False
            i += 2
            continue
        if not in_block:
            result.append(text[i])
        i += 1
    return "".join(result)


def compute_loc(text):
    stripped = strip_comments_for_loc(text)
    return sum(1 for line in stripped.splitlines() if line.strip())


def tokenize_java(text):
    operators = []
    operands = []
    for token in TOKEN_RE.findall(text):
        if token.startswith("//") or token.startswith("/*"):
            continue
        if token.startswith('"') or token.startswith("'"):
            operands.append(token)
            continue
        if token[0].isdigit():
            operands.append(token)
            continue
        if token in SYMBOL_OPERATORS:
            operators.append(token)
            continue
        if token in JAVA_KEYWORDS:
            operators.append(token)
            continue
        if re.match(r"^[A-Za-z_]\w*$", token):
            operands.append(token)
    return operators, operands


def compute_halstead_metrics(text):
    operators, operands = tokenize_java(text)
    n1 = len(set(operators))
    n2 = len(set(operands))
    n = n1 + n2
    n1_total = len(operators)
    n2_total = len(operands)
    n_total = n1_total + n2_total

    if n <= 1 or n_total == 0:
        return {
            "n1": n1,
            "n2": n2,
            "N1": n1_total,
            "N2": n2_total,
            "volume": 0.0,
            "difficulty": 0.0,
            "effort": 0.0,
        }

    volume = n_total * math.log2(n)
    difficulty = 0.0
    if n2 > 0:
        difficulty = (n1 / 2.0) * (n2_total / float(n2))
    effort = difficulty * volume

    return {
        "n1": n1,
        "n2": n2,
        "N1": n1_total,
        "N2": n2_total,
        "volume": float(volume),
        "difficulty": float(difficulty),
        "effort": float(effort),
    }


def compute_file_cc(text):
    # Approximate cyclomatic complexity based on decision tokens.
    decisions = len(DECISION_RE.findall(text))
    return 1 + decisions if text.strip() else 0


def compute_mi(halstead_volume, cc, loc):
    if halstead_volume <= 0 or loc <= 0:
        return 0.0
    raw = (171.0 - 5.2 * math.log(halstead_volume) - 0.23 * cc - 16.2 * math.log(loc)) * 100.0 / 171.0
    if raw < 0:
        return 0.0
    if raw > 100:
        return 100.0
    return float(raw)


def mean(values):
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def collect_module_metrics(module_path, dry_run):
    java_files = find_java_files(module_path)
    if dry_run:
        preview = java_files[:8]
        suffix = " ..." if len(java_files) > 8 else ""
        print("DRY_RUN: analyze", " ".join(preview) + suffix)
        return 0.0, {
            "file_count": len(java_files),
            "halstead_volume_mean": 0.0,
            "halstead_effort_mean": 0.0,
            "cc_mean": 0.0,
            "loc_mean": 0.0,
        }

    mi_values = []
    volumes = []
    efforts = []
    ccs = []
    locs = []

    for path in java_files:
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue

        loc = compute_loc(text)
        cc = compute_file_cc(text)
        halstead = compute_halstead_metrics(text)
        mi = compute_mi(halstead["volume"], cc, loc)

        volumes.append(halstead["volume"])
        efforts.append(halstead["effort"])
        ccs.append(float(cc))
        locs.append(float(loc))
        mi_values.append(mi)

    return round(mean(mi_values), 6), {
        "file_count": len(java_files),
        "halstead_volume_mean": round(mean(volumes), 6),
        "halstead_effort_mean": round(mean(efforts), 6),
        "cc_mean": round(mean(ccs), 6),
        "loc_mean": round(mean(locs), 6),
    }


def output_path(results_dir, project, timestamp):
    return os.path.join(results_dir, f"{project}-{timestamp}-{METRIC_NAME}-{TOOL_NAME}-{VARIANT_NAME}.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Collect module-level maintainability index with Java Halstead analysis")
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
    tool_version = "dry-run" if args.dry_run else TOOL_VERSION

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path):
            value, details = collect_module_metrics(module_path, args.dry_run)
            rows.append(
                {
                    "project": project,
                    "metric": METRIC_NAME,
                    "variant": VARIANT_NAME,
                    "component_type": "module",
                    "component": module,
                    "value": value,
                    "tool": TOOL_NAME,
                    "tool_version": tool_version,
                    "parameters": {
                        "category": "maintainability",
                        "scope_filter": "no_tests",
                        "mi_formula": "171-5.2*ln(V)-0.23*CC-16.2*ln(LOC)",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        **details,
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
