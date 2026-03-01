import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numeric_helpers_use_finite_values_only():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    values = [1, "2.5", None, "nan", "not-a-number", 4]

    assert module.numeric_mean(values) == 2.5
    assert module.numeric_sum(values) == 7.5
    assert module.numeric_max(values) == 4.0


def test_safe_float_filters_invalid_values():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    assert module.safe_float("3.14") == 3.14
    assert module.safe_float("  2 ") == 2.0
    assert module.safe_float("") is None
    assert module.safe_float(None) is None
    assert module.safe_float("nan") is None
    assert module.safe_float("inf") is None


def test_numeric_percentile_linear_interpolation():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    values = [2.0, 3.0, 5.0]
    assert module.numeric_percentile(values, 95.0) == 4.8


def test_csv_roundtrip_with_required_columns(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    output = tmp_path / "rows.csv"
    rows = [
        {"a": "x", "b": 1},
        {"a": "y", "b": 2},
    ]
    module.write_csv_rows(output, rows, columns=["a", "b"])
    loaded = module.read_csv_rows(output)

    assert loaded == [{"a": "x", "b": "1"}, {"a": "y", "b": "2"}]


def test_apply_row_customiser():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    rows = [{"metric": "loc", "value": 10}]

    def add_variant(row):
        row["variant"] = "default"
        return row

    out = module.apply_row_customiser(rows, row_customiser=add_variant)
    assert out == [{"metric": "loc", "value": 10, "variant": "default"}]


def test_build_module_metric_row_default_ok():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    row = module.build_module_metric_row(
        project="repo-a",
        module="module-a",
        metric="loc",
        variant="cloc-default",
        tool="cloc",
        tool_version="1.0",
        parameters={"category": "size"},
        timestamp_utc="2026-03-01T10:00:00Z",
        value=12.0,
    )

    assert row["component_type"] == "module"
    assert row["component"] == "module-a"
    assert row["status"] == "ok"
    assert row["value"] == 12.0
    assert "skip_reason" not in row


def test_build_module_metric_rows_with_parameter_overrides():
    module = load_module(REPO_ROOT / "metrics/common/data_manager.py")
    rows = module.build_module_metric_rows(
        project="repo-a",
        module="module-a",
        variant="proxy-default",
        tool="ck",
        tool_version="1.2.3",
        timestamp_utc="2026-03-01T10:00:00Z",
        default_metric="ce-ca",
        base_parameters={"category": "coupling", "tool_output": "class.csv"},
        specs=[
            {"value": 3.0, "parameters": {"dimension": "ce"}},
            {"value": 5.0, "parameters": {"dimension": "ca"}},
            {"metric": "cbo", "value": 2.0, "parameters": {"dimension": "cbo"}},
            {"value": None, "status": "skipped", "skip_reason": "missing_input"},
        ],
    )

    assert len(rows) == 4
    assert rows[0]["metric"] == "ce-ca"
    assert rows[0]["parameters"]["category"] == "coupling"
    assert rows[0]["parameters"]["dimension"] == "ce"
    assert rows[2]["metric"] == "cbo"
    assert rows[3]["status"] == "skipped"
    assert rows[3]["value"] is None
    assert rows[3]["skip_reason"] == "missing_input"
