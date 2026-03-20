#!/usr/bin/env python3
"""Shared Java project/module layout resolution helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from input_manager import choose_first_existing_dir

JAVA_BUILD_MANIFESTS = (
    "build.xml",
    "pom.xml",
    "mvnw",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradlew",
)

TOP_LEVEL_SOURCE_MODULE_HINTS = (
    "src",
    "source",
    "src/main/java",
    "main/java",
)
JAVA_SOURCE_INPUT_CANDIDATES = ("main/java", "src/main/java")


@dataclass(frozen=True)
class JavaModuleLayout:
    project_path: str
    module_path: str
    module_relative_path: str
    source_input: str | None
    build_root: str
    bytecode_search_roots: tuple[str, ...]
    module_has_build_manifest: bool
    build_root_has_build_manifest: bool
    is_top_level_source_module: bool


def _norm(path: str) -> str:
    return os.path.normpath(str(path))


def _has_build_manifest(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, name)) for name in JAVA_BUILD_MANIFESTS)


def _unique_paths(paths: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen = set()
    for path in paths:
        normalized = _norm(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(path)
    return tuple(out)


def resolve_java_module_layout(module_path: str, project_path: str) -> JavaModuleLayout:
    module_norm = _norm(module_path)
    project_norm = _norm(project_path)
    try:
        module_relative_path = os.path.relpath(module_norm, project_norm).replace("\\", "/")
    except ValueError:
        module_relative_path = os.path.basename(module_norm).lower()

    module_has_build_manifest = _has_build_manifest(module_norm)
    project_has_build_manifest = _has_build_manifest(project_norm)
    is_top_level_source_module = module_relative_path in TOP_LEVEL_SOURCE_MODULE_HINTS

    build_root = module_norm
    if not module_has_build_manifest and project_has_build_manifest and is_top_level_source_module:
        build_root = project_norm

    return JavaModuleLayout(
        project_path=project_norm,
        module_path=module_norm,
        module_relative_path=module_relative_path,
        source_input=choose_first_existing_dir(
            module_norm,
            JAVA_SOURCE_INPUT_CANDIDATES,
            fallback=module_norm if is_top_level_source_module else None,
        ),
        build_root=build_root,
        bytecode_search_roots=_unique_paths([module_norm, build_root]),
        module_has_build_manifest=module_has_build_manifest,
        build_root_has_build_manifest=_has_build_manifest(build_root),
        is_top_level_source_module=is_top_level_source_module,
    )
