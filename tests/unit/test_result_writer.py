import importlib.util
import json
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_jsonl_rows_injects_schema_and_run_id(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    output = tmp_path / "rows.jsonl"

    rows = [
        {
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
        }
    ]
    module.write_jsonl_rows(str(output), rows, run_id="11111111-1111-1111-1111-111111111111")

    line = output.read_text(encoding="utf-8").strip()
    assert line.startswith('{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111"')
    parsed = json.loads(line)
    assert parsed["schema_version"] == "1.0"
    assert parsed["run_id"] == "11111111-1111-1111-1111-111111111111"


def test_write_jsonl_rows_rejects_missing_required_field(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    output = tmp_path / "rows.jsonl"
    rows = [
        {
            "project": "repo-alpha",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "module",
            # "component" missing
            "value": 12,
            "tool": "cloc",
            "tool_version": "1.96",
            "parameters": {},
            "timestamp_utc": "2026-02-24T15:04:05Z",
        }
    ]
    with pytest.raises(ValueError):
        module.write_jsonl_rows(str(output), rows, run_id="11111111-1111-1111-1111-111111111111")


def test_write_jsonl_rows_accepts_submetric_optional(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    output = tmp_path / "rows.jsonl"
    rows = [
        {
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
        }
    ]
    module.write_jsonl_rows(str(output), rows, run_id="11111111-1111-1111-1111-111111111111")
    parsed = json.loads(output.read_text(encoding="utf-8").strip())
    assert parsed["submetric"] == "cc_proxy_mean"


def test_generate_run_id_uses_env_override(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    monkeypatch.setenv("METRIC_RUN_ID", "fixed-run-id")
    assert module.generate_run_id() == "fixed-run-id"


def test_write_jsonl_rows_keeps_canonical_key_order(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    output = tmp_path / "rows.jsonl"
    rows = [
        {
            "project": "repo-alpha",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "module",
            "component": "module-core",
            "value": 12.0,
            "tool": "cloc",
            "tool_version": "1.96",
            "parameters": {"mode": "code"},
            "timestamp_utc": "2026-02-24T15:04:05Z",
            "submetric": "loc_code",
        }
    ]
    module.write_jsonl_rows(str(output), rows, run_id="11111111-1111-1111-1111-111111111111")
    raw_line = output.read_text(encoding="utf-8").strip()
    expected_prefix = (
        '{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111",'
        '"project":"repo-alpha","metric":"loc","variant":"cloc-default","component_type":"module",'
        '"component":"module-core","submetric":"loc_code","status":"ok","value":12.0,'
    )
    assert raw_line.startswith(expected_prefix)


def test_write_jsonl_rows_accepts_skipped_with_null_value(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    output = tmp_path / "rows.jsonl"
    rows = [
        {
            "project": "repo-alpha",
            "metric": "cc",
            "variant": "radon-default",
            "component_type": "project",
            "component": "repo-alpha",
            "status": "skipped",
            "skip_reason": "no_python_sources",
            "value": None,
            "tool": "radon",
            "tool_version": "6.0.1",
            "parameters": {},
            "timestamp_utc": "2026-02-24T15:04:05Z",
        }
    ]

    module.write_jsonl_rows(str(output), rows, run_id="11111111-1111-1111-1111-111111111111")
    parsed = json.loads(output.read_text(encoding="utf-8").strip())
    assert parsed["status"] == "skipped"
    assert parsed["value"] is None


def test_generate_run_id_default_is_uuid4(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    monkeypatch.delenv("METRIC_RUN_ID", raising=False)
    monkeypatch.delenv("RUN_ID", raising=False)
    run_id = module.generate_run_id()
    parsed = uuid.UUID(run_id)
    assert parsed.version == 4


def test_generate_run_id_uses_run_id_alias(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/result_writer.py")
    monkeypatch.delenv("METRIC_RUN_ID", raising=False)
    monkeypatch.setenv("RUN_ID", "alias-run-id")
    assert module.generate_run_id() == "alias-run-id"


def test_run_collector_maps_runtime_and_value_errors():
    module = load_module(REPO_ROOT / "metrics/common/result_executor.py")

    def raise_runtime():
        raise RuntimeError("tool failed")

    def raise_value():
        raise ValueError("output invalid")

    assert module.run_collector(raise_runtime) == module.EXIT_TOOL_ERROR
    assert module.run_collector(raise_value) == module.EXIT_OUTPUT_ERROR
