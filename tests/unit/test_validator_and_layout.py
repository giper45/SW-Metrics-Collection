import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_CONTAINERS = [
    "metrics/generic/normalized-collector",
    "metrics/size/generic/loc-cloc",
    "metrics/size/generic/loc-tokei",
    "metrics/size/generic/loc-scc",
    "metrics/complexity/generic/cc-lizard",
    "metrics/complexity/python/cc-radon",
    "metrics/complexity/java/cc-ck",
    "metrics/coupling/java/ce-ca-jdepend",
    "metrics/coupling/java/ce-ca-ck-cbo",
    "metrics/cohesion/java/lcom-ck",
    "metrics/cohesion/java/lcom-ckjm",
    "metrics/vulnerability/java/vulnerability-dependency-check",
    "metrics/vulnerability/java/vulnerability-codeql-java",
    "metrics/vulnerability/php/vulnerability-psalm-php",
    "metrics/vulnerability/java/vulnerability-pmd-security",
    "metrics/vulnerability/java/vulnerability-spotbugs-findsecbugs",
    "metrics/duplication/java/duplication-jscpd",
    "metrics/maintainability/java/mi-halstead-java",
    "metrics/quality/java/static-warnings-checkstyle",
    "metrics/testing/java/coverage-jacoco",
    "metrics/evolution/generic/churn-git",
]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metric_container_layout_is_complete():
    for folder in REQUIRED_CONTAINERS:
        base = REPO_ROOT / folder
        assert (base / "Dockerfile").is_file()
        assert (base / "run.sh").is_file()
        assert (base / "collect.py").is_file()
        assert (base / "README.md").is_file()


def test_validator_accepts_valid_row():
    module = load_module(
        REPO_ROOT / "metrics/validate-results/generic/jsonl-schema-validator/validate.py"
    )
    row = {
        "schema_version": "1.0",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "project": "repo-alpha",
        "metric": "loc",
        "variant": "cloc-default",
        "component_type": "module",
        "component": "module-core",
        "value": 12,
        "tool": "cloc",
        "tool_version": "1.96",
        "parameters": {},
        "timestamp_utc": "2026-02-24T15:04:05Z",
        "status": "ok",
    }
    assert module.validate_row(row) == []


def test_validator_accepts_optional_submetric():
    module = load_module(
        REPO_ROOT / "metrics/validate-results/generic/jsonl-schema-validator/validate.py"
    )
    row = {
        "schema_version": "1.0",
        "run_id": "11111111-1111-1111-1111-111111111111",
        "project": "repo-alpha",
        "metric": "cc",
        "variant": "ck-normalized",
        "component_type": "module",
        "component": "module-core",
        "submetric": "cc_proxy_mean",
        "value": 3.0,
        "tool": "ck",
        "tool_version": "0.7.0",
        "parameters": {},
        "timestamp_utc": "2026-02-24T15:04:05Z",
        "status": "ok",
    }
    assert module.validate_row(row) == []


def test_validator_rejects_invalid_row():
    module = load_module(
        REPO_ROOT / "metrics/validate-results/generic/jsonl-schema-validator/validate.py"
    )
    row = {
        "schema_version": 1,
        "run_id": 2,
        "project": "repo-alpha",
        "metric": "loc",
        "variant": "cloc-default",
        "component_type": "unknown",
        "component": "module-core",
        "value": "bad",
        "tool": "cloc",
        "tool_version": "1.96",
        "parameters": [],
        "timestamp_utc": "2026-02-24",
        "status": "ok",
    }
    errors = module.validate_row(row)
    assert any("schema_version" in error for error in errors)
    assert any("run_id" in error for error in errors)
    assert any("component_type" in error for error in errors)
    assert any("value must be number" in error for error in errors)
