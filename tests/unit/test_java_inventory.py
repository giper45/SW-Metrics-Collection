import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_inventory_output_reads_expected_counts():
    module = load_module(REPO_ROOT / "metrics/common/java_inventory.py")
    parsed = module.parse_inventory_output(
        (
            '{"files_scanned":4,"class_count":3,"record_count":1,'
            '"interface_count":2,"enum_count":0,"package_count":2,'
            '"unnamed_package_files":1,"parse_errors":0}'
        )
    )
    assert parsed["files_scanned"] == 4
    assert parsed["class_count"] == 3
    assert parsed["package_count"] == 2


def test_parse_inventory_output_rejects_invalid_json():
    module = load_module(REPO_ROOT / "metrics/common/java_inventory.py")
    with pytest.raises(module.OutputContractError):
        module.parse_inventory_output("not-json")


def test_parse_inventory_output_rejects_negative_counts():
    module = load_module(REPO_ROOT / "metrics/common/java_inventory.py")
    with pytest.raises(module.OutputContractError):
        module.parse_inventory_output(
            (
                '{"files_scanned":1,"class_count":-1,"record_count":0,'
                '"interface_count":0,"enum_count":0,"package_count":0,'
                '"unnamed_package_files":0,"parse_errors":0}'
            )
        )
