#!/usr/bin/env python3
"""Shared Java bytecode discovery helpers."""

from __future__ import annotations

import os
from typing import Iterable

from input_manager import discover_module_class_files
from java_layout import resolve_java_module_layout


def unique_paths(paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for path in paths:
        normalized = os.path.normpath(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(path)
    return out


def candidate_bytecode_search_roots(module_path: str, project_path: str) -> list[str]:
    layout = resolve_java_module_layout(module_path, project_path)
    return unique_paths(list(layout.bytecode_search_roots))


def discover_module_class_files_with_roots(
    module_path: str,
    project_path: str,
    bytecode_dir_candidates: Iterable[str],
    *,
    vendor_dirs=None,
) -> tuple[list[str], list[str], list[str]]:
    class_files: list[str] = []
    class_seen = set()
    bytecode_inputs: list[str] = []
    search_roots = candidate_bytecode_search_roots(module_path, project_path)

    for root in search_roots:
        discovered, inputs = discover_module_class_files(
            root,
            bytecode_dir_candidates,
            vendor_dirs=vendor_dirs,
        )
        bytecode_inputs.extend(inputs)
        for path in discovered:
            normalized = os.path.normpath(path)
            if normalized in class_seen:
                continue
            class_seen.add(normalized)
            class_files.append(path)

    return class_files, unique_paths(search_roots), unique_paths(bytecode_inputs)
