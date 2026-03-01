import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_command_stdout_reads_stdin():
    module = load_module(REPO_ROOT / "metrics/common/result_executor.py")
    out = module.run_command_stdout(
        ["python3", "-c", "import sys;print(sys.stdin.read().strip())"],
        stdin_text="hello",
    )
    assert out.strip() == "hello"


def test_run_command_details_allows_nonzero_when_configured():
    module = load_module(REPO_ROOT / "metrics/common/result_executor.py")
    out, err, code = module.run_command_details(
        ["python3", "-c", "import sys;print('warn');sys.exit(1)"],
        allowed_returncodes={0, 1},
    )
    assert out.strip() == "warn"
    assert err.strip() == ""
    assert code == 1


def test_run_command_details_raises_on_disallowed_exit():
    module = load_module(REPO_ROOT / "metrics/common/result_executor.py")
    with pytest.raises(module.ToolExecutionError) as exc:
        module.run_command_details(["python3", "-c", "import sys;sys.exit(3)"])
    assert "command failed (3)" in str(exc.value)


def test_detect_tool_version_extracts_semver():
    module = load_module(REPO_ROOT / "metrics/common/result_executor.py")
    version = module.detect_tool_version(["python3", "-c", "print('tool v1.2.3')"])
    assert version == "1.2.3"
