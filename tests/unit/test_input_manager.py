from pathlib import Path

from input_manager import discover_module_class_files, list_source_files


def test_list_source_files_filters_out_files_without_extension(tmp_path):
    (tmp_path / "target" / "classes" / "example").mkdir(parents=True)
    (tmp_path / "target" / "classes" / "example" / "A.class").write_bytes(b"\xca\xfe\xba\xbe")
    (tmp_path / "target" / "classes" / "META-INF").mkdir(parents=True)
    (tmp_path / "target" / "classes" / "META-INF" / "LICENSE").write_text("text", encoding="utf-8")

    files = list_source_files(str(tmp_path), source_extensions={".class"}, vendor_dirs=set())
    normalized = sorted(Path(path).as_posix() for path in files)

    assert normalized == [f"{tmp_path.as_posix()}/target/classes/example/A.class"]


def test_discover_module_class_files_ignores_non_class_entries(tmp_path):
    (tmp_path / "target" / "classes" / "pkg").mkdir(parents=True)
    (tmp_path / "target" / "classes" / "pkg" / "B.class").write_bytes(b"\xca\xfe\xba\xbe")
    (tmp_path / "target" / "classes" / "META-INF").mkdir(parents=True)
    (tmp_path / "target" / "classes" / "META-INF" / "NOTICE").write_text("text", encoding="utf-8")

    class_files, inputs = discover_module_class_files(
        str(tmp_path),
        bytecode_dir_candidates=("target/classes",),
        vendor_dirs=set(),
    )

    assert inputs == [f"{tmp_path}/target/classes"]
    assert [Path(path).as_posix() for path in class_files] == [f"{tmp_path.as_posix()}/target/classes/pkg/B.class"]
