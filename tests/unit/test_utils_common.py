import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metric_output_path():
    module = load_module(REPO_ROOT / "metrics/common/utils.py")
    path = module.metric_output_path(
        "/results",
        "repo-a",
        "2026-03-01T10:00:00Z",
        "loc",
        "cloc",
        "default",
    )
    assert path.endswith("/results/repo-a-2026-03-01T10:00:00Z-loc-cloc-default.jsonl")
