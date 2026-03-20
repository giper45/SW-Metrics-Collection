from pathlib import Path
import zipfile

import pytest

from webapp.services.jobs import OperationJob
from webapp.services.repositories import (
    derive_repository_name,
    import_archives,
    parse_clone_specs,
)


def test_parse_clone_specs_accepts_url_ref_and_folder():
    specs = parse_clone_specs(
        "https://github.com/google/guava.git,v33.0.0,guava\nhttps://github.com/google/gson.git"
    )

    assert len(specs) == 2
    assert specs[0].url == "https://github.com/google/guava.git"
    assert specs[0].ref == "v33.0.0"
    assert specs[0].directory_name == "guava"
    assert specs[1].directory_name == "gson"


def test_derive_repository_name_strips_dot_git():
    assert derive_repository_name("https://example.com/demo/repo.git") == "repo"


def test_import_archives_extracts_into_repository_folder(tmp_path: Path):
    src_dir = tmp_path / "src"
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("demo-repo/README.md", "hello")
        archive.writestr("demo-repo/src/Main.java", "class Main {}")

    job = OperationJob(id="1", kind="repositories", label="import")
    import_archives(job, src_dir=src_dir, archive_paths=[archive_path])

    assert (src_dir / "demo-repo" / "README.md").read_text(encoding="utf-8") == "hello"
    assert (src_dir / "demo-repo" / "src" / "Main.java").exists()


def test_import_archives_rejects_unsafe_paths(tmp_path: Path):
    src_dir = tmp_path / "src"
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "nope")

    job = OperationJob(id="1", kind="repositories", label="import")
    with pytest.raises(ValueError):
        import_archives(job, src_dir=src_dir, archive_paths=[archive_path])
