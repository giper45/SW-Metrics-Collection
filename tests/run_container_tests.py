#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
FIXTURE_APP = os.path.join(SCRIPT_DIR, "fixtures", "java-known-project")
METRIC_DIR = os.path.join(REPO_ROOT, "metrics", "java", "cyclomatic-complexity-lizard")
IMAGE_TAG = "sw-metrics-java-cyclomatic-test:latest"
OUTPUT_FILE = "cyclomatic-complexity-package.jsonl"


def run(cmd):
    subprocess.check_call(cmd)


def ensure_docker_available():
    try:
        subprocess.check_output(["docker", "version"], stderr=subprocess.STDOUT)
    except Exception as exc:
        print("ERROR: Docker is required to run container tests.")
        print(f"Details: {exc}")
        return False
    return True


def build_image():
    run(
        [
            "docker",
            "build",
            "--build-context",
            f"repo_common={os.path.join(REPO_ROOT, 'metrics', 'common')}",
            "-t",
            IMAGE_TAG,
            METRIC_DIR,
        ]
    )


def run_container(app_dir, results_dir):
    env = ["-e", "PROJECT_NAME=known-project", "-e", "METRIC_TIMESTAMP=2026-01-01T00:00:00Z"]
    cmd = [
        "docker",
        "run",
        "--rm",
        *env,
        "-v",
        f"{app_dir}:/app:ro",
        "-v",
        f"{results_dir}:/results",
        IMAGE_TAG,
    ]
    run(cmd)


def read_jsonl(path):
    lines = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                lines.append(json.loads(stripped))
    return lines


def assert_equals(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected} actual={actual}")


def test_happy_path():
    results_dir = tempfile.mkdtemp(prefix="container-metric-results-")
    try:
        run_container(FIXTURE_APP, results_dir)
        output_path = os.path.join(results_dir, OUTPUT_FILE)
        if not os.path.isfile(output_path):
            raise AssertionError(f"Missing output file: {output_path}")

        rows = read_jsonl(output_path)
        assert_equals(len(rows), 2, "Unexpected package row count")
        assert_equals(
            [row["component"] for row in rows],
            ["com.acme.core", "com.acme.util"],
            "Component ordering should be deterministic",
        )

        by_component = {row["component"]: row for row in rows}

        core = by_component.get("com.acme.core")
        util = by_component.get("com.acme.util")
        if core is None or util is None:
            raise AssertionError(f"Expected packages not found. Components={sorted(by_component.keys())}")

        assert_equals(core["value"], 4, "com.acme.core CC mismatch")
        assert_equals(util["value"], 4, "com.acme.util CC mismatch")

        for row in rows:
            assert_equals(row["project"], "known-project", "project mismatch")
            assert_equals(row["metric"], "cyclomatic_complexity", "metric mismatch")
            assert_equals(row["tool"], "lizard", "tool mismatch")
            assert_equals(row["aggregation_level"], "package", "aggregation mismatch")
            assert_equals(row["timestamp"], "2026-01-01T00:00:00Z", "timestamp mismatch")
            for field in (
                "project",
                "component",
                "metric",
                "value",
                "tool",
                "tool_version",
                "aggregation_level",
                "timestamp",
            ):
                if field not in row:
                    raise AssertionError(f"Missing field '{field}' in row {row}")
    finally:
        shutil.rmtree(results_dir, ignore_errors=True)


def test_empty_app_dir():
    app_dir = tempfile.mkdtemp(prefix="container-empty-app-")
    results_dir = tempfile.mkdtemp(prefix="container-empty-results-")
    try:
        run_container(app_dir, results_dir)
        output_path = os.path.join(results_dir, OUTPUT_FILE)
        if not os.path.isfile(output_path):
            raise AssertionError(f"Missing output file for empty app dir: {output_path}")

        rows = read_jsonl(output_path)
        assert_equals(rows, [], "Expected no rows for empty app dir")
    finally:
        shutil.rmtree(app_dir, ignore_errors=True)
        shutil.rmtree(results_dir, ignore_errors=True)


def main():
    if not ensure_docker_available():
        return 2

    build_image()
    test_happy_path()
    test_empty_app_dir()
    print("Container metric tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
