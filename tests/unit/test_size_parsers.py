import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cloc_parser_extracts_sum_code():
    module = load_module(REPO_ROOT / "metrics/size/generic/loc-cloc/collect.py")
    payload = {"header": {}, "SUM": {"blank": 1, "comment": 2, "code": 7}}
    assert module.parse_cloc_json(json.dumps(payload)) == 7


def test_tokei_parser_prefers_total_code():
    module = load_module(REPO_ROOT / "metrics/size/generic/loc-tokei/collect.py")
    payload = {"Total": {"code": 11, "comments": 2}}
    assert module.parse_tokei_json(json.dumps(payload)) == 11


def test_scc_parser_supports_totals_dict():
    module = load_module(REPO_ROOT / "metrics/size/generic/loc-scc/collect.py")
    payload = {"totals": {"Code": 13, "Lines": 20}}
    assert module.parse_scc_json(payload) == 13
