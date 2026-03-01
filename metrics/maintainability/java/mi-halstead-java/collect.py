#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path


from result_writer import filter_projects, generate_run_id, write_jsonl_rows
from result_executor import run_collector
from data_manager import build_module_metric_row
from error_manager import InputContractError
from utils import metric_output_path, utc_timestamp_now
from config import TEST_DIR_NAMES, VENDOR_DIRS
from input_manager import (
    add_common_cli_args,
    discover_modules,
    discover_projects,
    is_ignored_dir,
    is_test_dir,
    list_source_files)

METRIC_NAME = "maintainability-index"
VARIANT_NAME = "mi-halstead-default"
TOOL_NAME = "java-halstead-analyzer"
TOOL_VERSION = "1.0.0"

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
    re.S | re.M)

DECISION_RE = re.compile(r"\b(if|for|while|case|catch)\b|\?|&&|\|\|")


def find_java_files(module_path):
    return list_source_files(
        module_path,
        vendor_dirs=VENDOR_DIRS,
        include_tests=False,
        test_dir_names=TEST_DIR_NAMES,
        test_file_markers=(),
        source_extensions={JAVA_EXT})


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


def collect_module_metrics(module_path):
    java_files = find_java_files(module_path)
    mi_values = []
    volumes = []
    efforts = []
    ccs = []
    locs = []

    for path in java_files:
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError as exc:
            raise InputContractError(f"cannot read java source file: {path}") from exc

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


def main():
    parser = argparse.ArgumentParser(description="Collect module-level maintainability index with Java Halstead analysis")
    add_common_cli_args(parser)
    args = parser.parse_args()

    timestamp = utc_timestamp_now()
    run_id = generate_run_id()
    projects = filter_projects(discover_projects(args.app_dir, vendor_dirs=VENDOR_DIRS), app_dir=args.app_dir)
    if not projects:
        return 0

    os.makedirs(args.results_dir, exist_ok=True)
    tool_version = TOOL_VERSION

    for project, project_path in projects:
        rows = []
        for module, module_path in discover_modules(project, project_path, vendor_dirs=VENDOR_DIRS):
            value, details = collect_module_metrics(module_path)
            rows.append(
                build_module_metric_row(
                    project=project,
                    module=module,
                    metric=METRIC_NAME,
                    variant=VARIANT_NAME,
                    tool=TOOL_NAME,
                    tool_version=tool_version,
                    parameters={
                        "category": "maintainability",
                        "scope_filter": "no_tests",
                        "mi_formula": "171-5.2*ln(V)-0.23*CC-16.2*ln(LOC)",
                        "ignored_dirs": sorted(VENDOR_DIRS),
                        **details,
                    },
                    timestamp_utc=timestamp,
                    value=value,
                )
            )

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
