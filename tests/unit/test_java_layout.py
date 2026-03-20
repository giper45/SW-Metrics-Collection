import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path, name=None):
    spec = importlib.util.spec_from_file_location(name or path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_resolve_java_module_layout_uses_project_build_root_for_top_level_src_ant_repo(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/java_layout.py", "java_layout_test")
    repo_path = tmp_path / "bodgeit"
    src_path = repo_path / "src"
    src_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "build.xml").write_text("<project default='compile'/>", encoding="utf-8")

    layout = module.resolve_java_module_layout(str(src_path), str(repo_path))

    assert layout.source_input == str(src_path)
    assert layout.build_root == str(repo_path)
    assert layout.bytecode_search_roots == (str(src_path), str(repo_path))
    assert layout.is_top_level_source_module is True
    assert layout.build_root_has_build_manifest is True


def test_resolve_java_module_layout_keeps_module_build_root_for_standard_maven_module(tmp_path):
    module = load_module(REPO_ROOT / "metrics/common/java_layout.py", "java_layout_maven_test")
    module_path = tmp_path / "demo-module"
    source_root = module_path / "src" / "main" / "java"
    source_root.mkdir(parents=True, exist_ok=True)
    (module_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    layout = module.resolve_java_module_layout(str(module_path), str(tmp_path))

    assert layout.source_input == str(source_root)
    assert layout.build_root == str(module_path)
    assert layout.bytecode_search_roots == (str(module_path),)
    assert layout.is_top_level_source_module is False
