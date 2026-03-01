#!/usr/bin/env python3
import csv
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JAVA_FIXTURE = REPO_ROOT / "tests/fixtures/java-multi-repo"
JAVA_COUPLING_FIXTURE = REPO_ROOT / "tests/fixtures/java-coupling-repo"
PYTHON_FIXTURE = REPO_ROOT / "tests/fixtures/python-multi-repo"
NORMALIZED_FIXTURE = REPO_ROOT / "tests/fixtures/normalized-app"
JAVA_EXTENDED_FIXTURE = REPO_ROOT / "tests/fixtures/java-extended-repo"
TIMESTAMP = "2026-02-24T15:04:05Z"

JAVA_MULTI_COMPONENTS = {
    ("repo-alpha", "module-core"),
    ("repo-alpha", "module-utils"),
    ("repo-beta", "service-api"),
    ("repo-beta", "service-impl"),
}
JAVA_COUPLING_COMPONENTS = {("repo-coupling", "module-coupled")}
JAVA_EXTENDED_COMPONENTS = {
    ("repo-gamma", "module-coverage"),
    ("repo-gamma", "module-dup"),
    ("repo-gamma", "module-style"),
}
PYTHON_COMPONENTS = {("repo-py", "pkg-a"), ("repo-py", "pkg-b")}
CHURN_COMPONENTS = {("repo-churn", "module-core")}

EXPECTED_LOC = {
    ("repo-alpha", "module-core"): 31.0,
    ("repo-alpha", "module-utils"): 15.0,
    ("repo-beta", "service-api"): 4.0,
    ("repo-beta", "service-impl"): 23.0,
}
EXPECTED_CC_LIZARD = {
    ("repo-alpha", "module-core"): 3.0,
    ("repo-alpha", "module-utils"): 2.0,
    ("repo-beta", "service-api"): 0.0,
    ("repo-beta", "service-impl"): 3.5,
}
EXPECTED_CC_RADON = {
    ("repo-py", "pkg-a"): 4.0,
    ("repo-py", "pkg-b"): 3.0,
}

CONTAINERS = [
    {
        "name": "loc-cloc",
        "context": REPO_ROOT / "metrics/size/generic/loc-cloc",
        "image": "loc-cloc:test",
        "fixture": JAVA_FIXTURE,
        "metric": "loc",
        "variant": "cloc-default",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "loc-tokei",
        "context": REPO_ROOT / "metrics/size/generic/loc-tokei",
        "image": "loc-tokei:test",
        "fixture": JAVA_FIXTURE,
        "metric": "loc",
        "variant": "tokei-default",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "loc-scc",
        "context": REPO_ROOT / "metrics/size/generic/loc-scc",
        "image": "loc-scc:test",
        "fixture": JAVA_FIXTURE,
        "metric": "loc",
        "variant": "scc-default",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "cc-lizard",
        "context": REPO_ROOT / "metrics/complexity/generic/cc-lizard",
        "image": "cc-lizard:test",
        "fixture": JAVA_FIXTURE,
        "metric": "cc",
        "variant": "lizard-default",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "cc-radon",
        "context": REPO_ROOT / "metrics/complexity/python/cc-radon",
        "image": "cc-radon:test",
        "fixture": PYTHON_FIXTURE,
        "metric": "cc",
        "variant": "radon-default",
        "expected_components": PYTHON_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "cc-ck-wmc",
        "context": REPO_ROOT / "metrics/complexity/java/cc-ck",
        "image": "cc-ck:test",
        "fixture": JAVA_FIXTURE,
        "metric": "wmc",
        "variant": "ck-raw",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "ce-ca-jdepend",
        "context": REPO_ROOT / "metrics/coupling/java/ce-ca-jdepend",
        "image": "ce-ca-jdepend:test",
        "fixture": JAVA_COUPLING_FIXTURE,
        "metric": "ce-ca",
        "variant": "jdepend-default",
        "expected_components": JAVA_COUPLING_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "ce-ca-ck-cbo",
        "context": REPO_ROOT / "metrics/coupling/java/ce-ca-ck-cbo",
        "image": "ce-ca-ck-cbo:test",
        "fixture": JAVA_COUPLING_FIXTURE,
        "metric": "ce-ca",
        "variant": "ck-ce-ca-proxy",
        "expected_components": JAVA_COUPLING_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "lcom-ck",
        "context": REPO_ROOT / "metrics/cohesion/java/lcom-ck",
        "image": "lcom-ck:test",
        "fixture": JAVA_FIXTURE,
        "metric": "lcom",
        "variant": "ck-default",
        "expected_components": JAVA_MULTI_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "duplication-jscpd",
        "context": REPO_ROOT / "metrics/duplication/java/duplication-jscpd",
        "image": "duplication-jscpd:test",
        "fixture": JAVA_EXTENDED_FIXTURE,
        "metric": "duplication-rate",
        "variant": "jscpd-default",
        "expected_components": JAVA_EXTENDED_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "mi-halstead-java",
        "context": REPO_ROOT / "metrics/maintainability/java/mi-halstead-java",
        "image": "mi-halstead-java:test",
        "fixture": JAVA_EXTENDED_FIXTURE,
        "metric": "maintainability-index",
        "variant": "mi-halstead-default",
        "expected_components": JAVA_EXTENDED_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "static-warnings-checkstyle",
        "context": REPO_ROOT / "metrics/quality/java/static-warnings-checkstyle",
        "image": "static-warnings-checkstyle:test",
        "fixture": JAVA_EXTENDED_FIXTURE,
        "metric": "static-warnings",
        "variant": "checkstyle-default",
        "expected_components": JAVA_EXTENDED_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "coverage-jacoco",
        "context": REPO_ROOT / "metrics/testing/java/coverage-jacoco",
        "image": "coverage-jacoco:test",
        "fixture": JAVA_EXTENDED_FIXTURE,
        "metric": "test-coverage",
        "variant": "jacoco-default",
        "expected_components": JAVA_EXTENDED_COMPONENTS,
        "require_positive_any": True,
    },
    {
        "name": "churn-git",
        "context": REPO_ROOT / "metrics/evolution/generic/churn-git",
        "image": "churn-git:test",
        "fixture": "__DYNAMIC_CHURN_FIXTURE__",
        "metric": "code-churn",
        "variant": "git-default",
        "expected_components": CHURN_COMPONENTS,
        "require_positive_any": True,
    },
]

NORMALIZED_CONTAINERS = [
    {
        "name": "normalized-loc-cloc",
        "context": REPO_ROOT / "metrics/generic/normalized-collector",
        "image": "normalized-collector:test",
        "fixture": NORMALIZED_FIXTURE,
        "metric": "loc",
        "tool": "cloc",
        "env": {
            "METRIC_KEY": "loc",
            "TOOL_KEY": "cloc",
            "COMMAND": "cloc --json --quiet --skip-uniqueness {project_path}",
            "TOOL_VERSION_COMMAND": "cloc --version",
            "ENTITY_TYPE": "project",
            "VARIANT_KEY": "default",
            "SCOPE_FILTER": "no_tests",
            "CONTAINER_IMAGE": "normalized-collector:test",
        },
    }
]


def run(cmd):
    subprocess.check_call(cmd)


def ensure_docker():
    try:
        subprocess.check_output(["docker", "version"], stderr=subprocess.STDOUT)
    except Exception as exc:
        raise RuntimeError(f"Docker is required for integration tests: {exc}") from exc


def docker_build(image, context):
    run(
        [
            "docker",
            "build",
            "--build-context",
            f"repo_common={REPO_ROOT / 'metrics/common'}",
            "-t",
            image,
            str(context),
        ]
    )


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def module_key(row):
    return row["project"], row["component"]


def assert_close(actual, expected, tolerance, label):
    if abs(actual - expected) > tolerance:
        raise AssertionError(
            f"{label}: expected {expected:.6f}, got {actual:.6f}, tolerance {tolerance:.6f}"
        )


def assert_in_range(value, lower, upper, label):
    if value < lower or value > upper:
        raise AssertionError(f"{label}: expected [{lower}, {upper}], got {value}")


def validate_schema(row):
    required = {
        "schema_version",
        "run_id",
        "project",
        "metric",
        "variant",
        "component_type",
        "component",
        "value",
        "tool",
        "tool_version",
        "parameters",
        "timestamp_utc",
    }
    missing = required - set(row.keys())
    if missing:
        raise AssertionError(f"missing keys: {sorted(missing)}")
    if row["component_type"] != "module":
        raise AssertionError(f"component_type must be module, got {row['component_type']}")
    if row["schema_version"] != "1.0":
        raise AssertionError(f"schema_version must be 1.0, got {row['schema_version']}")
    if not isinstance(row["run_id"], str) or not row["run_id"]:
        raise AssertionError("run_id must be non-empty string")
    if not isinstance(row["parameters"], dict):
        raise AssertionError(f"parameters must be object, got {type(row['parameters'])}")

    status = str(row.get("status", "ok"))
    if status not in {"ok", "skipped"}:
        raise AssertionError(f"status must be ok|skipped, got {status}")
    value = row["value"]
    if status == "skipped":
        if value is not None:
            raise AssertionError(f"value must be null when skipped, got {value}")
        if "skip_reason" in row and not isinstance(row.get("skip_reason"), str):
            raise AssertionError("skip_reason must be string when present")
    else:
        if not isinstance(value, (int, float)):
            raise AssertionError(f"value must be numeric, got {type(value)}")
        if not math.isfinite(float(value)):
            raise AssertionError(f"value must be finite, got {value}")
    if row["timestamp_utc"] != TIMESTAMP:
        raise AssertionError(f"unexpected timestamp_utc: {row['timestamp_utc']}")


def resolve_fixture(case, dynamic_churn_fixture):
    if case["fixture"] == "__DYNAMIC_CHURN_FIXTURE__":
        return dynamic_churn_fixture
    return case["fixture"]


def map_single_row_per_component(rows, label):
    mapped = {}
    for row in rows:
        if str(row.get("status", "ok")) == "skipped":
            continue
        key = module_key(row)
        if key in mapped:
            raise AssertionError(f"duplicate row for component in {label}: {key}")
        mapped[key] = float(row["value"])
    return mapped


def map_ce_ca_rows(rows):
    mapped = {}
    for row in rows:
        if str(row.get("status", "ok")) == "skipped":
            continue
        key = module_key(row)
        dimension = str(row.get("parameters", {}).get("dimension", "")).lower()
        if dimension not in {"ce", "ca"}:
            raise AssertionError(f"invalid dimension in ce-ca row: {dimension}")
        mapped.setdefault(key, {})
        if dimension in mapped[key]:
            raise AssertionError(f"duplicate ce/ca row for component {key} and dimension {dimension}")
        mapped[key][dimension] = float(row["value"])

    for key, values in mapped.items():
        if set(values.keys()) != {"ce", "ca"}:
            raise AssertionError(f"missing ce/ca pair for {key}: found {sorted(values.keys())}")
    return mapped


def map_rows_by_submetric(rows, label):
    mapped = {}
    for row in rows:
        key = module_key(row)
        submetric = str(row.get("submetric", "")).strip()
        if not submetric:
            raise AssertionError(f"missing submetric in {label} row for {key}")
        mapped.setdefault(key, {})
        if submetric in mapped[key]:
            raise AssertionError(f"duplicate submetric row for {label} at {key} and {submetric}")
        mapped[key][submetric] = float(row["value"])
    return mapped


def assert_expected_components(rows, expected_components, label):
    observed = {module_key(row) for row in rows}
    if observed != expected_components:
        raise AssertionError(
            f"{label}: component mismatch. expected={sorted(expected_components)} observed={sorted(observed)}"
        )


def run_container_case(case, results_dir, dynamic_churn_fixture):
    docker_build(case["image"], case["context"])
    fixture = resolve_fixture(case, dynamic_churn_fixture)
    run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            f"METRIC_TIMESTAMP_UTC={TIMESTAMP}",
            "-v",
            f"{fixture}:/app:ro",
            "-v",
            f"{results_dir}:/results",
            case["image"],
        ]
    )

    files = sorted(results_dir.glob(f"*-{case['metric']}-{case['variant']}.jsonl"))
    if not files:
        raise AssertionError(f"no output file produced for {case['name']}")

    selected_rows = []
    variant_rows = []
    for file_path in files:
        for row in read_jsonl(file_path):
            validate_schema(row)
            if row["variant"] != case["variant"]:
                continue
            variant_rows.append(row)
            if row["metric"] == case["metric"]:
                selected_rows.append(row)

    if not selected_rows:
        raise AssertionError(f"no matching rows found for {case['name']}")

    expected_components = case.get("expected_components")
    if expected_components:
        assert_expected_components(selected_rows, expected_components, case["name"])

    if case.get("require_positive_any"):
        values = [float(row["value"]) for row in selected_rows]
        if not any(value > 0 for value in values):
            raise AssertionError(
                f"all values are <= 0 for {case['name']} (metric={case['metric']}, variant={case['variant']})"
            )

    return variant_rows


def validate_numeric_oracles(rows_by_name):
    # LOC: fixed oracle values + cross-tool agreement.
    loc_cloc = map_single_row_per_component(rows_by_name["loc-cloc"], "loc-cloc")
    loc_tokei = map_single_row_per_component(rows_by_name["loc-tokei"], "loc-tokei")
    loc_scc = map_single_row_per_component(rows_by_name["loc-scc"], "loc-scc")

    for key, expected in EXPECTED_LOC.items():
        assert_close(loc_cloc[key], expected, 0.001, f"loc-cloc {key}")

    for key in EXPECTED_LOC:
        max_delta = max(
            abs(loc_cloc[key] - loc_tokei[key]),
            abs(loc_cloc[key] - loc_scc[key]),
            abs(loc_tokei[key] - loc_scc[key]),
        )
        if max_delta > 2.0:
            raise AssertionError(f"loc cross-tool mismatch too large at {key}: delta={max_delta}")

    # CC: deterministic fixture values for lizard/radon + CK raw sanity.
    cc_lizard = map_single_row_per_component(rows_by_name["cc-lizard"], "cc-lizard")
    cc_radon = map_single_row_per_component(rows_by_name["cc-radon"], "cc-radon")
    ck_rows = rows_by_name["cc-ck-wmc"]
    ck_wmc = map_single_row_per_component(
        [row for row in ck_rows if row["metric"] == "wmc"],
        "cc-ck-wmc",
    )
    ck_nom = map_single_row_per_component(
        [row for row in ck_rows if row["metric"] == "nom"],
        "cc-ck-nom",
    )

    for key, expected in EXPECTED_CC_LIZARD.items():
        assert_close(cc_lizard[key], expected, 0.001, f"cc-lizard {key}")
    for key, expected in EXPECTED_CC_RADON.items():
        assert_close(cc_radon[key], expected, 0.001, f"cc-radon {key}")
    for key in ck_wmc:
        if key not in ck_nom:
            raise AssertionError(f"missing NOM row for CK component {key}")
        wmc_value = ck_wmc[key]
        nom_value = ck_nom[key]
        assert_in_range(wmc_value, 0.0, 10000.0, f"cc-ck wmc {key}")
        assert_in_range(nom_value, 0.0, 10000.0, f"cc-ck nom {key}")
        if nom_value > 0.0:
            cc_proxy = wmc_value / nom_value
            assert_in_range(cc_proxy, 0.0, 100.0, f"cc-ck proxy {key}")

    # Coupling + instability: strict Ce/Ca pairing and derived relation checks.
    ce_ca = map_ce_ca_rows(rows_by_name["ce-ca-jdepend"])
    for key, values in ce_ca.items():
        assert_in_range(values["ce"], 0.0, 1000.0, f"jdepend ce {key}")
        assert_in_range(values["ca"], 0.0, 1000.0, f"jdepend ca {key}")
        if values["ce"] <= 0.0 or values["ca"] <= 0.0:
            raise AssertionError(f"jdepend ce/ca should both be positive for fixture {key}")

    # Cohesion.
    lcom = map_single_row_per_component(rows_by_name["lcom-ck"], "lcom-ck")
    if not any(value > 0 for value in lcom.values()):
        raise AssertionError("lcom-ck must have at least one positive module value")
    for key, value in lcom.items():
        assert_in_range(value, 0.0, 1000.0, f"lcom-ck {key}")

    # Duplication, coverage and instability-like ratios.
    duplication = map_single_row_per_component(rows_by_name["duplication-jscpd"], "duplication-jscpd")
    for key, value in duplication.items():
        assert_in_range(value, 0.0, 1.0, f"duplication ratio {key}")
    if duplication[("repo-gamma", "module-dup")] <= 0.1:
        raise AssertionError("module-dup should show non-trivial duplication (> 0.1)")
    if duplication[("repo-gamma", "module-coverage")] > 0.05:
        raise AssertionError("module-coverage should stay near zero duplication")
    if duplication[("repo-gamma", "module-style")] > 0.05:
        raise AssertionError("module-style should stay near zero duplication")

    coverage = map_single_row_per_component(rows_by_name["coverage-jacoco"], "coverage-jacoco")
    for key, value in coverage.items():
        assert_in_range(value, 0.0, 1.0, f"coverage ratio {key}")
    if coverage[("repo-gamma", "module-coverage")] <= 0.4:
        raise AssertionError("module-coverage expected to have coverage > 0.4")
    if coverage[("repo-gamma", "module-dup")] > 0.01:
        raise AssertionError("module-dup should have ~0 coverage (no tests)")
    if coverage[("repo-gamma", "module-style")] > 0.01:
        raise AssertionError("module-style should have ~0 coverage (no tests)")

    # Maintainability index.
    mi = map_single_row_per_component(rows_by_name["mi-halstead-java"], "mi-halstead-java")
    for key, value in mi.items():
        assert_in_range(value, 0.0, 100.0, f"mi-halstead {key}")
    if mi[("repo-gamma", "module-style")] <= mi[("repo-gamma", "module-dup")]:
        raise AssertionError("module-style MI should be greater than module-dup on fixture")

    # Static warnings.
    warnings = map_single_row_per_component(
        rows_by_name["static-warnings-checkstyle"], "static-warnings-checkstyle"
    )
    for key, value in warnings.items():
        assert_in_range(value, 0.0, 100000.0, f"static warnings {key}")
    if warnings[("repo-gamma", "module-style")] < 1.0:
        raise AssertionError("module-style should produce checkstyle violations")
    if warnings[("repo-gamma", "module-dup")] != 0.0:
        raise AssertionError("module-dup should not produce style violations in fixture")
    if warnings[("repo-gamma", "module-coverage")] != 0.0:
        raise AssertionError("module-coverage should not produce style violations in fixture")

    # Churn.
    churn = map_single_row_per_component(rows_by_name["churn-git"], "churn-git")
    churn_value = churn[("repo-churn", "module-core")]
    if churn_value < 3.0:
        raise AssertionError(f"churn should be meaningfully positive on dynamic git fixture, got {churn_value}")

    # CBO proxy sanity.
    ce_ca_ck = map_single_row_per_component(rows_by_name["ce-ca-ck-cbo"], "ce-ca-ck-cbo")
    for key, value in ce_ca_ck.items():
        assert_in_range(value, 0.0, 1000.0, f"ce-ca-ck-cbo {key}")
    if ce_ca_ck[("repo-coupling", "module-coupled")] <= 0.0:
        raise AssertionError("ck-cbo coupling proxy should be > 0 for coupling fixture")


def run_normalized_case(case, results_dir):
    docker_build(case["image"], case["context"])

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-e",
        f"METRIC_TIMESTAMP_UTC={TIMESTAMP}",
        "-v",
        f"{case['fixture']}:/app:ro",
        "-v",
        f"{results_dir}:/results",
    ]
    for key, value in case.get("env", {}).items():
        docker_cmd.extend(["-e", f"{key}={value}"])
    docker_cmd.append(case["image"])

    run(docker_cmd)

    manifest_paths = sorted(results_dir.glob(f"*/**/{case['metric']}/{case['tool']}/manifest.json"))
    csv_paths = sorted(results_dir.glob(f"*/**/{case['metric']}/{case['tool']}/data.csv"))

    if not manifest_paths or not csv_paths:
        raise AssertionError(f"normalized output not produced for {case['name']}")

    for manifest_path in manifest_paths:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("status") != "success":
            raise AssertionError(f"normalized collector failed: {manifest_path}")
        if payload.get("metric_key") != case["metric"]:
            raise AssertionError(f"invalid metric_key in {manifest_path}")
        if payload.get("tool_key") != case["tool"]:
            raise AssertionError(f"invalid tool_key in {manifest_path}")

    required_header = [
        "entity_type",
        "entity_id",
        "metric_name",
        "metric_value",
        "unit",
        "language",
        "tool_key",
        "variant_key",
        "scope_filter",
        "path_hint",
    ]
    for csv_path in csv_paths:
        with open(csv_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
        if not rows:
            raise AssertionError(f"empty csv file: {csv_path}")
        if rows[0] != required_header:
            raise AssertionError(f"invalid csv header in {csv_path}")


def run_validator(results_dir):
    validator_context = REPO_ROOT / "metrics/validate-results/generic/jsonl-schema-validator"
    docker_build("jsonl-schema-validator:test", validator_context)
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{results_dir}:/results",
            "jsonl-schema-validator:test",
        ]
    )


def create_dynamic_churn_fixture(base_dir):
    fixture_root = base_dir / "churn-app"
    project_root = fixture_root / "repo-churn"
    module_root = project_root / "module-core"
    src_dir = module_root / "src/main/java/com/example/churn"
    test_dir = module_root / "src/test/java/com/example/churn"

    src_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    file_path = src_dir / "ChurnOps.java"
    file_path.write_text(
        """
package com.example.churn;

public class ChurnOps {
    public int add(int left, int right) {
        return left + right;
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    run(["git", "init", str(project_root)])
    run(["git", "-C", str(project_root), "config", "user.name", "Metric Bot"])
    run(["git", "-C", str(project_root), "config", "user.email", "metric-bot@example.com"])
    run(["git", "-C", str(project_root), "add", "."])
    run(["git", "-C", str(project_root), "commit", "-m", "initial commit"])

    file_path.write_text(
        """
package com.example.churn;

public class ChurnOps {
    public int add(int left, int right) {
        int result = left + right;
        if (result > 100) {
            return 100;
        }
        return result;
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    run(["git", "-C", str(project_root), "add", "."])
    run(["git", "-C", str(project_root), "commit", "-m", "modify implementation"])

    test_file = test_dir / "ChurnOpsTest.java"
    test_file.write_text(
        """
package com.example.churn;

public class ChurnOpsTest {
    public void placeholder() {}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    run(["git", "-C", str(project_root), "add", "."])
    run(["git", "-C", str(project_root), "commit", "-m", "add tests"])

    return fixture_root


def main():
    ensure_docker()

    results_dir = Path(tempfile.mkdtemp(prefix="metric-matrix-results-"))
    dynamic_fixture_dir = Path(tempfile.mkdtemp(prefix="metric-matrix-fixtures-"))
    try:
        dynamic_churn_fixture = create_dynamic_churn_fixture(dynamic_fixture_dir)
        rows_by_name = {}
        for case in CONTAINERS:
            rows_by_name[case["name"]] = run_container_case(case, results_dir, dynamic_churn_fixture)

        validate_numeric_oracles(rows_by_name)
        run_validator(results_dir)

        for case in NORMALIZED_CONTAINERS:
            run_normalized_case(case, results_dir)

        print("All Docker matrix tests passed with numeric/invariant checks.")
        return 0
    finally:
        shutil.rmtree(results_dir, ignore_errors=True)
        shutil.rmtree(dynamic_fixture_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
