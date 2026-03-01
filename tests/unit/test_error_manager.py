import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_error_mode_defaults_to_fail_fast(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/error_manager.py")
    monkeypatch.delenv("METRIC_ERROR_MODE", raising=False)
    assert module.error_mode() == module.ERROR_MODE_FAIL_FAST
    assert module.is_fail_fast_mode() is True


def test_error_fallback_or_raise_raises_in_fail_fast(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/error_manager.py")
    monkeypatch.setenv("METRIC_ERROR_MODE", module.ERROR_MODE_FAIL_FAST)
    with pytest.raises(module.ErrorPolicyViolation):
        module.error_fallback_or_raise("tool_failed", category="tool", context="module=a")


def test_error_mode_ignores_legacy_skip_env(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/error_manager.py")
    monkeypatch.setenv("METRIC_ERROR_MODE", module.ERROR_MODE_LEGACY_SKIP)
    assert module.error_mode() == module.ERROR_MODE_FAIL_FAST
    with pytest.raises(module.ErrorPolicyViolation):
        module.error_fallback_or_raise("tool_failed", category="tool", context="module=a")


def test_error_fallback_or_raise_uses_typed_categories(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/common/error_manager.py")
    monkeypatch.setenv("METRIC_ERROR_MODE", module.ERROR_MODE_FAIL_FAST)
    with pytest.raises(module.InputContractError):
        module.error_fallback_or_raise("missing_input", category="input")
    with pytest.raises(module.OutputContractError):
        module.error_fallback_or_raise("invalid_output", category="output")
