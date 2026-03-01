import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module_with_stub_lizard(path):
    fake = types.ModuleType("lizard")
    fake.__version__ = "test"
    fake.analyze = lambda _sources: []
    previous = sys.modules.get("lizard")
    sys.modules["lizard"] = fake
    try:
        module = load_module(path)
    finally:
        if previous is None:
            sys.modules.pop("lizard", None)
        else:
            sys.modules["lizard"] = previous
    return module


def test_collect_module_complexities_returns_empty_on_no_sources():
    module = load_module_with_stub_lizard(REPO_ROOT / "metrics/complexity/generic/cc-lizard/collect.py")
    assert module._collect_module_complexities([]) == []


def test_collect_module_complexities_parses_numeric_values(monkeypatch):
    module = load_module_with_stub_lizard(REPO_ROOT / "metrics/complexity/generic/cc-lizard/collect.py")

    class Fn:
        def __init__(self, cc):
            self.cyclomatic_complexity = cc

    class FileInfo:
        def __init__(self, values):
            self.function_list = [Fn(v) for v in values]

    monkeypatch.setattr(
        module.lizard,
        "analyze",
        lambda _sources: [FileInfo([2, "3", "bad"]), FileInfo([5])],
    )

    values = module._collect_module_complexities(["/tmp/A.java"])
    assert values == [2.0, 3.0, 5.0]
