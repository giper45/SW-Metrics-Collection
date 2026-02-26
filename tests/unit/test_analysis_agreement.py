import csv
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "analysis/agreement.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_agreement_builds_pairwise_intra_metric_rows(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_agreement")
    input_csv = tmp_path / "dataset_long.csv"
    output_csv = tmp_path / "agreement.csv"

    columns = [
        "project",
        "run_id",
        "timestamp_utc",
        "component",
        "component_type",
        "metric",
        "tool",
        "variant",
        "value",
        "tool_version",
    ]
    rows = [
        # LOC on three modules and three tools => 3 agreement pairs.
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 10, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m2", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 20, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m3", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 30, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 11, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m2", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 21, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m3", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 31, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "scc", "variant": "scc-default", "value": 8, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m2", "component_type": "module", "metric": "loc", "tool": "scc", "variant": "scc-default", "value": 18, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m3", "component_type": "module", "metric": "loc", "tool": "scc", "variant": "scc-default", "value": 28, "tool_version": "1.0"},
        # CC with two tools and two shared modules => 1 pair.
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "cc", "tool": "lizard", "variant": "lizard-default", "value": 4.0, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m2", "component_type": "module", "metric": "cc", "tool": "lizard", "variant": "lizard-default", "value": 5.0, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "cc", "tool": "ckjm", "variant": "ckjm-normalized", "value": 3.0, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m2", "component_type": "module", "metric": "cc", "tool": "ckjm", "variant": "ckjm-normalized", "value": 6.0, "tool_version": "1.0"},
    ]
    write_csv(input_csv, columns, rows)

    summary = module.run_agreement(input_csv, output_csv)
    assert summary["long_rows"] == 13
    assert summary["agreement_rows"] == 4

    out_rows = read_csv(output_csv)
    assert len(out_rows) == 4
    assert {row["metric"] for row in out_rows} == {"loc", "cc"}

    loc_rows = [row for row in out_rows if row["metric"] == "loc"]
    assert len(loc_rows) == 3
    for row in loc_rows:
        assert row["n_common"] == "3"
        assert row["spearman_rho"] == "1.0"

    cc_rows = [row for row in out_rows if row["metric"] == "cc"]
    assert len(cc_rows) == 1
    assert cc_rows[0]["n_common"] == "2"


def test_read_long_csv_rejects_missing_columns(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_agreement_invalid")
    input_csv = tmp_path / "dataset_long_missing.csv"
    write_csv(
        input_csv,
        ["project", "run_id", "metric", "tool", "variant", "value"],
        [{"project": "p", "run_id": "r", "metric": "loc", "tool": "cloc", "variant": "d", "value": 1}],
    )
    with pytest.raises(ValueError):
        module.read_long_csv(input_csv)


def test_agreement_emits_insufficient_common_row_with_note(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_agreement_insufficient")
    input_csv = tmp_path / "dataset_long.csv"
    output_csv = tmp_path / "agreement.csv"

    columns = [
        "project",
        "run_id",
        "timestamp_utc",
        "component",
        "component_type",
        "metric",
        "tool",
        "variant",
        "value",
        "tool_version",
    ]
    rows = [
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 10, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-24T15:04:05Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 11, "tool_version": "1.0"},
    ]
    write_csv(input_csv, columns, rows)

    summary = module.run_agreement(input_csv, output_csv, min_common=2)
    assert summary["agreement_rows"] == 1

    out_rows = read_csv(output_csv)
    assert len(out_rows) == 1
    assert out_rows[0]["n_common"] == "1"
    assert out_rows[0]["spearman_rho"] == ""
    assert out_rows[0]["notes"] == "n_common<2"


def test_agreement_handles_duplicate_measurements_by_latest_timestamp(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_agreement_duplicates")
    input_csv = tmp_path / "dataset_long.csv"
    output_csv = tmp_path / "agreement.csv"

    columns = [
        "project",
        "run_id",
        "timestamp_utc",
        "component",
        "component_type",
        "metric",
        "tool",
        "variant",
        "value",
        "tool_version",
    ]
    rows = [
        # Duplicate measurement for cloc/m1: latest timestamp should win (value=11).
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-26T10:00:00Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 10, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-26T12:00:00Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 11, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-26T12:00:00Z", "component": "m2", "component_type": "module", "metric": "loc", "tool": "cloc", "variant": "cloc-default", "value": 20, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-26T12:00:00Z", "component": "m1", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 11, "tool_version": "1.0"},
        {"project": "repo-a", "run_id": "run-1", "timestamp_utc": "2026-02-26T12:00:00Z", "component": "m2", "component_type": "module", "metric": "loc", "tool": "tokei", "variant": "tokei-default", "value": 21, "tool_version": "1.0"},
    ]
    write_csv(input_csv, columns, rows)

    summary = module.run_agreement(input_csv, output_csv)
    assert summary["agreement_rows"] == 1
    out_rows = read_csv(output_csv)
    assert len(out_rows) == 1
    assert out_rows[0]["metric"] == "loc"
    assert out_rows[0]["n_common"] == "2"
    assert out_rows[0]["notes"] == ""
