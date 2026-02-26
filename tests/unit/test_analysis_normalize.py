import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZE_PATH = REPO_ROOT / "analysis/normalize.py"
FIXTURE_INPUT = REPO_ROOT / "tests/fixtures/normalizer/input"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            text = raw.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def test_normalize_results_derives_cc_and_instability(tmp_path: Path):
    module = load_module(NORMALIZE_PATH, "analysis_normalize")
    output_dir = tmp_path / "results_normalized"

    summary = module.normalize_results(FIXTURE_INPUT, output_dir)
    assert summary["files"] == 2
    assert summary["derived_rows"] == 2
    assert summary["input_rows"] == 8
    assert summary["output_rows"] == 10

    sample_rows = read_jsonl(output_dir / "sample.jsonl")
    assert len(sample_rows) == 8

    cc_rows = [row for row in sample_rows if row.get("metric") == "cc" and row.get("variant") == "ckjm-normalized"]
    assert len(cc_rows) == 1
    cc_row = cc_rows[0]
    assert cc_row["component"] == "module-core"
    assert cc_row["value"] == 3.5
    assert cc_row["source_tool"] == "ckjm"
    assert cc_row["source_variant"] == "ck-raw"
    assert cc_row["source_file"] == "sample.jsonl"

    instability_rows = [row for row in sample_rows if row.get("metric") == "instability" and row.get("source_tool") == "jdepend"]
    assert len(instability_rows) == 1
    instability_row = instability_rows[0]
    assert instability_row["value"] == 0.8
    assert instability_row["variant"] == "jdepend-default-normalized"
    assert instability_row["source_file"] == "sample.jsonl"


def test_normalize_results_skips_cc_when_nom_missing_or_zero(tmp_path: Path):
    module = load_module(NORMALIZE_PATH, "analysis_normalize_nom_zero")
    output_dir = tmp_path / "results_normalized"

    source_file = FIXTURE_INPUT / "nom-zero.jsonl"
    target_file = output_dir / "nom-zero.jsonl"
    module.normalize_file(source_file, target_file, FIXTURE_INPUT)

    rows = read_jsonl(target_file)
    assert len(rows) == 2
    assert not [row for row in rows if row.get("metric") == "cc" and row.get("variant") == "ckjm-normalized"]


def test_normalize_results_backfills_legacy_schema_and_run_id(tmp_path: Path):
    module = load_module(NORMALIZE_PATH, "analysis_normalize_backfill")
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "results_normalized"
    input_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = input_dir / "legacy.jsonl"
    legacy_file.write_text(
        (
            '{"project":"repo-x","metric":"ce-ca","variant":"jdepend-default","component_type":"module","component":"module-a","submetric":"ce","value":4.0,"tool":"jdepend","tool_version":"2.9","parameters":{"dimension":"ce"},"timestamp_utc":"2026-02-24T10:45:43Z"}\n'
            '{"project":"repo-x","metric":"ce-ca","variant":"jdepend-default","component_type":"module","component":"module-a","submetric":"ca","value":1.0,"tool":"jdepend","tool_version":"2.9","parameters":{"dimension":"ca"},"timestamp_utc":"2026-02-24T10:45:43Z"}\n'
        ),
        encoding="utf-8",
    )

    summary = module.normalize_results(input_dir, output_dir)
    assert summary["files"] == 1
    assert summary["input_rows"] == 2
    assert summary["derived_rows"] == 1
    assert summary["output_rows"] == 3

    rows = read_jsonl(output_dir / "legacy.jsonl")
    run_ids = {row["run_id"] for row in rows}
    assert len(run_ids) == 1
    assert all(row["schema_version"] == "1.0" for row in rows)
    assert next(row for row in rows if row["metric"] == "instability")["run_id"] in run_ids
