from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from .jobs import OperationJob, run_streaming_command


ASSIGNMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+\s*(?:::=|::=|:=|\?=|\+=|!=|=)")
TARGET_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_. -]*)\s*::?\s*(.*)$")
SPECIAL_TARGETS = {
    ".PHONY",
    ".DEFAULT",
    ".SUFFIXES",
    ".SECONDARY",
    ".ONESHELL",
    ".DELETE_ON_ERROR",
    ".PRECIOUS",
    ".INTERMEDIATE",
}
CATEGORY_ORDER = [
    "Preparation",
    "Pipelines",
    "Software Metrics",
    "Vulnerabilities",
    "Analysis",
    "Verification",
    "Maintenance",
    "Other",
]
DISPLAY_NAME_OVERRIDES = {
    "archive": "Archive Results",
    "agreement": "Agreement Analysis",
    "case-studies": "Case Studies",
    "case-study": "Case Study",
    "clean": "Clean Workspace",
    "clean-case-study": "Clean Case Study",
    "clean-experiment": "Clean Experiment",
    "clean-src": "Clean Repositories",
    "collect-all": "Full Collection",
    "collect-cc-ck": "CK (Cyclomatic Complexity)",
    "collect-cc-lizard": "Lizard",
    "collect-cc-radon": "Radon",
    "collect-ce-ca-ck-cbo": "CK (CBO Coupling)",
    "collect-ce-ca-jdepend": "JDepend",
    "collect-churn-git": "Git Churn",
    "collect-class-count-javaparser": "JavaParser (Class Count)",
    "collect-cohesion-all": "Cohesion Suite",
    "collect-complexity-all": "Complexity Suite",
    "collect-coupling-all": "Coupling Suite",
    "collect-coverage-jacoco": "JaCoCo",
    "collect-duplication-jscpd": "JSCPD",
    "collect-lcom-ck": "CK (LCOM)",
    "collect-lcom-ckjm": "CKJM (LCOM)",
    "collect-loc-cloc": "CLOC",
    "collect-loc-scc": "SCC",
    "collect-loc-tokei": "Tokei",
    "collect-mi-halstead-java": "Halstead Java (MI)",
    "collect-normalized-loc-cloc": "CLOC (Normalized LOC)",
    "collect-package-count-javaparser": "JavaParser (Package Count)",
    "collect-paper-extras": "Paper Extras",
    "collect-size-all": "Size Suite",
    "collect-vulnerability-all": "Vulnerability Suite",
    "collect-vulnerability-codeql-java": "CodeQL",
    "collect-vulnerability-dependency-check": "Dependency-Check",
    "collect-vulnerability-pmd-security": "PMD",
    "collect-vulnerability-spotbugs-findsecbugs": "SpotBugs + FindSecBugs",
    "compute-structure-inventory": "Structure Inventory",
    "dataset": "Build Dataset",
    "experiment": "Experiment",
    "experiments": "Experiments",
    "manifest": "Build Manifest",
    "normalize": "Normalize Results",
    "normalize-vulnerability-sarif": "Normalize SARIF",
    "paper-tables": "Paper Tables",
    "prepare-java-bytecode": "Prepare Java Bytecode",
    "prepare-java-bytecode-if-enabled": "Prepare Java Bytecode (If Enabled)",
    "print-run-id": "Print Run ID",
    "report": "Generate Report",
    "validate-results": "Validate Results",
}
TOKEN_LABELS = {
    "ca": "CA",
    "cc": "CC",
    "ce": "CE",
    "ck": "CK",
    "ckjm": "CKJM",
    "cloc": "CLOC",
    "cbo": "CBO",
    "codeql": "CodeQL",
    "findsecbugs": "FindSecBugs",
    "git": "Git",
    "halstead": "Halstead",
    "jacoco": "JaCoCo",
    "javaparser": "JavaParser",
    "jscpd": "JSCPD",
    "jdepend": "JDepend",
    "lcom": "LCOM",
    "loc": "LOC",
    "mi": "MI",
    "osv": "OSV",
    "pmd": "PMD",
    "sarif": "SARIF",
    "scc": "SCC",
    "semgrep": "Semgrep",
    "spotbugs": "SpotBugs",
    "src": "SRC",
}


@dataclass(frozen=True)
class MakeTarget:
    name: str
    category: str
    dependencies: tuple[str, ...]
    description: str | None = None

    @property
    def display_name(self) -> str:
        return format_target_display_name(self.name)

    @property
    def short_description(self) -> str:
        text = (self.description or "").strip()
        if not text:
            return ""
        if len(text) <= 100:
            return text
        return text[:97].rstrip() + "..."


def discover_make_targets(makefile_path: Path) -> list[MakeTarget]:
    targets: list[MakeTarget] = []
    seen: set[str] = set()
    lines = makefile_path.read_text(encoding="utf-8").splitlines()

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or raw_line.startswith((" ", "\t")) or stripped.startswith("#"):
            continue
        if ASSIGNMENT_RE.match(raw_line):
            continue

        match = TARGET_RE.match(raw_line)
        if not match:
            continue

        raw_targets = match.group(1).split()
        dependencies = tuple(
            item for item in match.group(2).strip().split() if item and not item.startswith("#")
        )
        description = _extract_recipe_description(lines, index + 1)

        for target_name in raw_targets:
            if not _is_public_target(target_name) or target_name in seen:
                continue
            seen.add(target_name)
            targets.append(
                MakeTarget(
                    name=target_name,
                    category=categorize_target(target_name),
                    dependencies=dependencies,
                    description=description,
                )
            )

    return targets


def categorize_target(target_name: str) -> str:
    if target_name in {"case-study", "case-studies", "experiment", "experiments", "collect-all"}:
        return "Pipelines"
    if target_name.startswith("collect-vulnerability-"):
        return "Vulnerabilities"
    if target_name.startswith("collect-"):
        return "Software Metrics"
    if target_name.startswith("prepare-"):
        return "Preparation"
    if target_name in {
        "manifest",
        "normalize",
        "normalize-vulnerability-sarif",
        "dataset",
        "agreement",
        "report",
        "compute-structure-inventory",
        "paper-tables",
    }:
        return "Analysis"
    if target_name.startswith("test-") or target_name == "validate-results":
        return "Verification"
    if target_name.startswith("clean") or target_name.startswith("print-") or target_name in {
        "archive",
        "print-run-id",
    }:
        return "Maintenance"
    return "Other"


def group_targets(targets: list[MakeTarget]) -> list[tuple[str, list[MakeTarget]]]:
    grouped: dict[str, list[MakeTarget]] = {category: [] for category in CATEGORY_ORDER}
    for target in targets:
        grouped.setdefault(target.category, []).append(target)
    return [(category, grouped[category]) for category in CATEGORY_ORDER if grouped[category]]


def parse_env_overrides(raw_text: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(
                f"Invalid environment override on line {line_number}: expected KEY=VALUE."
            )
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(
                f"Invalid environment variable name on line {line_number}: {key!r}."
            )
        overrides[key] = value
    return overrides


def target_lookup(targets: list[MakeTarget]) -> dict[str, MakeTarget]:
    return {target.name: target for target in targets}


def format_target_display_name(target_name: str) -> str:
    if target_name in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[target_name]

    parts = [part for part in target_name.replace("_", "-").split("-") if part]
    if not parts:
        return target_name
    return " ".join(_format_target_token(part) for part in parts)


def run_make_target(
    job: OperationJob,
    project_root: Path,
    target_name: str,
    env_overrides: dict[str, str] | None = None,
) -> None:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
        for key, value in sorted(env_overrides.items()):
            job.append_log(f"[env] {key}={value}")
    run_streaming_command(job, ["make", target_name], cwd=project_root, env=env)


def _is_public_target(target_name: str) -> bool:
    if not target_name or target_name.startswith("."):
        return False
    if target_name in SPECIAL_TARGETS:
        return False
    if any(char in target_name for char in ("%","/")):
        return False
    return True


def _extract_recipe_description(lines: list[str], start_index: int) -> str | None:
    comments: list[str] = []

    for raw_line in lines[start_index:]:
        if raw_line.startswith((" ", "\t")):
            comment = _recipe_comment_text(raw_line)
            if comment:
                comments.append(comment)
            continue
        if not raw_line.strip():
            continue
        break

    if not comments:
        return None

    unique_comments = list(dict.fromkeys(comments))
    return " ".join(unique_comments)


def _recipe_comment_text(raw_line: str) -> str | None:
    stripped = raw_line.lstrip()
    if stripped.startswith("@#"):
        text = stripped[2:].strip()
        return text or None
    if stripped.startswith("#"):
        text = stripped[1:].strip()
        return text or None
    return None


def _format_target_token(token: str) -> str:
    lowered = token.lower()
    if lowered in TOKEN_LABELS:
        return TOKEN_LABELS[lowered]
    return token.replace(".", " ").title()
