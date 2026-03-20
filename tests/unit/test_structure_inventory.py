import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_structure_inventory_uses_latest_groups(tmp_path):
    module = load_module(REPO_ROOT / "analysis/structure_inventory.py")
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    loc_old = [
        {
            "schema_version": "1.0",
            "run_id": "run-old",
            "project": "repo-a",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "file",
            "component": "src/A.java",
            "status": "ok",
            "value": 10.0,
            "tool": "cloc",
            "tool_version": "1.0",
            "parameters": {},
            "timestamp_utc": "2026-03-07T10:00:00Z",
        },
        {
            "schema_version": "1.0",
            "run_id": "run-old",
            "project": "repo-a",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "file",
            "component": "src/B.java",
            "status": "ok",
            "value": 5.0,
            "tool": "cloc",
            "tool_version": "1.0",
            "parameters": {},
            "timestamp_utc": "2026-03-07T10:00:00Z",
        },
    ]
    loc_new = [
        {
            "schema_version": "1.0",
            "run_id": "run-new",
            "project": "repo-a",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "file",
            "component": "src/A.java",
            "status": "ok",
            "value": 11.0,
            "tool": "cloc",
            "tool_version": "1.0",
            "parameters": {},
            "timestamp_utc": "2026-03-08T10:00:00Z",
        },
        {
            "schema_version": "1.0",
            "run_id": "run-new",
            "project": "repo-a",
            "metric": "loc",
            "variant": "cloc-default",
            "component_type": "file",
            "component": "src/B.java",
            "status": "ok",
            "value": 6.0,
            "tool": "cloc",
            "tool_version": "1.0",
            "parameters": {},
            "timestamp_utc": "2026-03-08T10:00:00Z",
        },
    ]
    class_rows = [
        {
            "schema_version": "1.0",
            "run_id": "run-new",
            "project": "repo-a",
            "metric": "class-count",
            "variant": "javaparser-default",
            "component_type": "project",
            "component": "repo-a",
            "status": "ok",
            "value": 3.0,
            "tool": "javaparser",
            "tool_version": "3.26.3",
            "parameters": {},
            "timestamp_utc": "2026-03-08T10:00:00Z",
        }
    ]
    package_rows = [
        {
            "schema_version": "1.0",
            "run_id": "run-new",
            "project": "repo-a",
            "metric": "package-count",
            "variant": "javaparser-default",
            "component_type": "project",
            "component": "repo-a",
            "status": "ok",
            "value": 2.0,
            "tool": "javaparser",
            "tool_version": "3.26.3",
            "parameters": {},
            "timestamp_utc": "2026-03-08T10:00:00Z",
        }
    ]

    file_path = results_dir / "software-metrics" / "jsonl" / "sample.jsonl"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        for row in loc_old + loc_new + class_rows + package_rows:
            handle.write(json.dumps(row) + "\n")

    rows = module.build_structure_inventory(results_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["project"] == "repo-a"
    assert row["loc"] == 17.0
    assert row["class_count"] == 3.0
    assert row["package_count"] == 2.0
    assert row["loc_run_id"] == "run-new"
