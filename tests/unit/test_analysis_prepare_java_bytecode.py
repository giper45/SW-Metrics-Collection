import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "analysis/prepare_java_bytecode.py"


def load_module():
    spec = importlib.util.spec_from_file_location("analysis_prepare_java_bytecode", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_discover_tasks_recognizes_ant_repo_with_bodgeit_hint(tmp_path: Path):
    module = load_module()

    src_dir = tmp_path / "src"
    repo_dir = src_dir / "bodgeit"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "build.xml").write_text("<project default='compile'/>", encoding="utf-8")

    tasks = module._discover_tasks(src_dir, default_java=21, repos_filter=[], force=False)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.repo == "bodgeit"
    assert task.build_system == "ant"
    assert task.java_version == 8
    assert task.reason == "repo_hint=8"


def test_extract_versions_from_ant_javac_attributes():
    module = load_module()

    versions = module._extract_versions_from_text('<javac source="1.5" target="1.5" />')

    assert versions == [5, 5]


def test_build_command_for_ant_creates_bytecode_dir_before_compile(tmp_path: Path):
    module = load_module()

    task = module.BuildTask(
        repo="bodgeit",
        path=tmp_path / "bodgeit",
        build_system="ant",
        java_version=8,
        reason="repo_hint=8",
    )

    command = module._build_command(task)

    assert "cd /workspace/bodgeit" in command
    assert "mkdir -p build/WEB-INF/classes" in command
    assert command.endswith("ant compile")
