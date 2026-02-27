import csv
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "analysis/build_dataset.py"
FIXTURE_INPUT = REPO_ROOT / "tests/fixtures/build-dataset/input"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_dataset_outputs_long_and_wide(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_build_dataset")
    output_dir = tmp_path / "analysis_out"

    summary = module.build_dataset(FIXTURE_INPUT, output_dir)
    assert summary["input_rows"] == 7
    assert summary["long_rows"] == 7
    assert summary["wide_rows"] == 2

    long_rows = read_csv_rows(output_dir / "dataset_long.csv")
    assert len(long_rows) == 7
    assert {row["metric"] for row in long_rows} >= {"loc", "cc", "ce", "ca"}

    long_keys = [
        (
            row["project"],
            row["run_id"],
            row["timestamp_utc"],
            row["component"],
            row["component_type"],
            row["metric"],
            row["tool"],
            row["variant"],
            row["tool_version"],
            float(row["value"]),
        )
        for row in long_rows
    ]
    assert long_keys == sorted(long_keys)

    wide_rows = read_csv_rows(output_dir / "dataset_wide.csv")
    assert len(wide_rows) == 2

    header = list(wide_rows[0].keys())
    assert "ca__jdepend__jdepend-default" in header
    assert "ce__jdepend__jdepend-default" in header
    assert "cc__lizard__lizard-default" in header
    assert "cc__ck__ck-normalized" in header
    assert "loc__cloc__cloc-default" in header
    assert "loc__tokei__tokei-default" in header

    row_a = next(row for row in wide_rows if row["component"] == "module-a")
    assert row_a["loc__cloc__cloc-default"] == "100.0"
    assert row_a["loc__tokei__tokei-default"] == "102.0"
    assert row_a["ce__jdepend__jdepend-default"] == "4.0"
    assert row_a["ca__jdepend__jdepend-default"] == "1.0"

    row_b = next(row for row in wide_rows if row["component"] == "module-b")
    assert row_b["loc__cloc__cloc-default"] == "55.0"
    assert row_b["cc__lizard__lizard-default"] == ""


def test_build_dataset_rejects_missing_required_fields(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_build_dataset_invalid")
    input_dir = tmp_path / "results_normalized"
    input_dir.mkdir(parents=True, exist_ok=True)
    bad_file = input_dir / "bad.jsonl"
    bad_file.write_text(
        '{"schema_version":"1.0","project":"repo-x","metric":"loc","variant":"cloc-default","component_type":"module","component":"m","value":1.0,"tool":"cloc","tool_version":"1.96","parameters":{},"timestamp_utc":"2026-02-24T15:04:05Z"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        module.build_dataset(input_dir, tmp_path / "out")


def test_build_dataset_deduplicates_same_measurement_key(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_build_dataset_dedup")
    input_dir = tmp_path / "results_normalized"
    output_dir = tmp_path / "analysis_out"
    input_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        {
            "schema_version": "1.0",
            "run_id": "run-1",
            "project": "repo-x",
            "metric": "cc",
            "variant": "lizard-default",
            "component_type": "method",
            "component": "src/A.java::foo@L10",
            "status": "ok",
            "value": 3.0,
            "tool": "lizard",
            "tool_version": "1.17.10",
            "parameters": {},
            "timestamp_utc": "2026-02-26T12:00:00Z",
        },
        {
            "schema_version": "1.0",
            "run_id": "run-1",
            "project": "repo-x",
            "metric": "cc",
            "variant": "lizard-default",
            "component_type": "method",
            "component": "src/A.java::foo@L10",
            "status": "ok",
            "value": 5.0,
            "tool": "lizard",
            "tool_version": "1.17.10",
            "parameters": {},
            "timestamp_utc": "2026-02-26T12:00:00Z",
        },
        {
            "schema_version": "1.0",
            "run_id": "run-1",
            "project": "repo-x",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "file",
            "component": "src/A.java",
            "status": "ok",
            "value": 100.0,
            "tool": "cloc",
            "tool_version": "2.04",
            "parameters": {},
            "timestamp_utc": "2026-02-26T12:00:00Z",
        },
    ]

    payload = "\n".join(json.dumps(row) for row in rows) + "\n"
    (input_dir / "input.jsonl").write_text(payload, encoding="utf-8")

    summary = module.build_dataset(input_dir, output_dir)
    assert summary["input_rows"] == 3
    assert summary["long_rows_raw"] == 3
    assert summary["long_rows"] == 2
    assert summary["duplicate_measurement_groups"] == 1
    assert summary["duplicate_measurement_rows"] == 1
    assert summary["duplicate_measurement_conflicts"] == 1

    long_rows = read_csv_rows(output_dir / "dataset_long.csv")
    assert len(long_rows) == 2
    cc_row = next(row for row in long_rows if row["metric"] == "cc")
    assert cc_row["value"] == "4.0"

    duplicate_rows = read_csv_rows(output_dir / "dataset_duplicate_measurements.csv")
    assert len(duplicate_rows) == 1
    assert duplicate_rows[0]["metric"] == "cc"
    assert duplicate_rows[0]["duplicate_count"] == "2"


def test_build_dataset_ignores_runtime_telemetry_jsonl(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_build_dataset_ignore_runtime")
    input_dir = tmp_path / "results_normalized"
    output_dir = tmp_path / "analysis_out"
    input_dir.mkdir(parents=True, exist_ok=True)

    (input_dir / "metric.jsonl").write_text(
        '{"schema_version":"1.0","run_id":"run-1","project":"repo-x","metric":"loc","variant":"cloc-default","component_type":"file","component":"src/A.java","status":"ok","value":10.0,"tool":"cloc","tool_version":"1.0","parameters":{},"timestamp_utc":"2026-02-26T10:00:00Z"}\n',
        encoding="utf-8",
    )
    (input_dir / "metric-runtime-run-1.jsonl").write_text(
        '{"run_id":"run-1","metric_container":"loc-cloc:latest","duration_seconds":1.2}\n',
        encoding="utf-8",
    )

    summary = module.build_dataset(input_dir, output_dir)
    assert summary["input_rows"] == 1
