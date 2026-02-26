import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "analysis/build_manifest.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_manifest_tracks_missing_expected_variant(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_build_manifest")
    run_id = "11111111-1111-4111-8111-111111111111"
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "sample.jsonl").write_text(
        (
            '{"schema_version":"1.0","run_id":"11111111-1111-4111-8111-111111111111","project":"repo-a","metric":"loc","variant":"cloc-default","component_type":"file","component":"src/A.java","status":"ok","value":10.0,"tool":"cloc","tool_version":"1.0","parameters":{"repo_commit":"abc","repo_dirty":false},"timestamp_utc":"2026-02-24T15:04:05Z"}\n'
            '{"schema_version":"1.0","run_id":"11111111-1111-4111-8111-111111111111","project":"repo-a","metric":"loc","variant":"tokei-default","component_type":"file","component":"src/A.java","status":"ok","value":12.0,"tool":"tokei","tool_version":"1.0","parameters":{"repo_commit":"abc","repo_dirty":false},"timestamp_utc":"2026-02-24T15:04:05Z"}\n'
        ),
        encoding="utf-8",
    )

    expected = {
        ("loc", "cloc", "cloc-default"),
        ("loc", "tokei", "tokei-default"),
        ("loc", "scc", "scc-default"),
    }
    manifest = module.build_manifest(
        results_dir=results_dir,
        run_id=run_id,
        expected_variants=expected,
        preferred_component_type="file",
        language="java",
    )

    assert manifest["run_id"] == run_id
    assert manifest["projects"] == ["repo-a"]
    assert manifest["component_type_primary"] == "file"
    assert manifest["status"] == "partial"
    assert "loc|scc|scc-default" in manifest["missing_variants"]
