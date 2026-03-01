import csv
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_DIR = REPO_ROOT / "metrics/generic/normalized-collector"
COLLECTOR_PATH = COLLECTOR_DIR / "collect.py"
VALIDATOR_PATH = COLLECTOR_DIR / "validator.py"
FIXTURE_APP = REPO_ROOT / "tests/fixtures/normalized-app"
COMMON_DIR = REPO_ROOT / "metrics/common"


def load_module(path: Path, module_name: str):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def with_common_pythonpath(env: dict[str, str]) -> dict[str, str]:
    merged = dict(env)
    existing = merged.get("PYTHONPATH")
    common = str(COMMON_DIR)
    merged["PYTHONPATH"] = f"{common}:{existing}" if existing else common
    return merged


def test_discover_projects_detects_git_and_source():
    module = load_module(COLLECTOR_PATH, "normalized_collect")
    projects = module.discover_projects(FIXTURE_APP)
    names = [p.name for p in projects]
    assert names == ["project-alpha", "project-beta"]


def test_parse_raw_output_cloc_shape():
    module = load_module(COLLECTOR_PATH, "normalized_collect_parse")
    stdout = json.dumps({"SUM": {"code": 7, "comment": 2, "blank": 1}})
    rows = module.parse_raw_output(
        stdout=stdout,
        metric_key="loc",
        tool_key="cloc",
        entity_type="project",
        entity_id="project-alpha",
        language="java",
        variant_key="default",
        scope_filter="no_tests",
        path_hint="project-alpha",
    )
    assert len(rows) == 4
    metric_names = [row["metric_name"] for row in rows]
    assert metric_names == ["loc_code", "loc_comment", "loc_blank", "loc_total"]


def test_collector_main_success_writes_manifest_and_csv(tmp_path: Path):
    results_dir = tmp_path / "results"

    command = (
        f"{sys.executable} -c "
        "'import json; print(json.dumps(dict(SUM=dict(code=5, comment=2, blank=1))))'"
    )

    env = os.environ.copy()
    env.update(
        {
            "APP_ROOT": str(FIXTURE_APP),
            "RESULTS_ROOT": str(results_dir),
            "METRIC_KEY": "loc",
            "TOOL_KEY": "cloc",
            "COMMAND": command,
            "TOOL_VERSION": "1.99",
            "ENTITY_TYPE": "project",
            "VARIANT_KEY": "default",
            "SCOPE_FILTER": "no_tests",
            "CONTAINER_IMAGE": "normalized-collector:test",
        }
    )

    completed = subprocess.run(
        [sys.executable, str(COLLECTOR_PATH)],
        env=with_common_pythonpath(env),
        check=False,
    )
    assert completed.returncode == 0

    manifest_paths = sorted(results_dir.glob("*/**/manifest.json"))
    data_paths = sorted(results_dir.glob("*/**/data.csv"))

    assert len(manifest_paths) == 2
    assert len(data_paths) == 2

    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "success"
        assert manifest["metric_key"] == "loc"
        assert manifest["tool_key"] == "cloc"

    for data_path in data_paths:
        with data_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 4
        assert rows[0]["entity_type"] == "project"


def test_collector_main_error_writes_empty_csv(tmp_path: Path):
    results_dir = tmp_path / "results"

    env = os.environ.copy()
    env.update(
        {
            "APP_ROOT": str(FIXTURE_APP),
            "RESULTS_ROOT": str(results_dir),
            "METRIC_KEY": "loc",
            "TOOL_KEY": "cloc",
            "COMMAND": f"{sys.executable} -c 'import sys; sys.exit(2)'",
            "TOOL_VERSION": "1.99",
            "ENTITY_TYPE": "project",
            "VARIANT_KEY": "default",
            "SCOPE_FILTER": "no_tests",
            "CONTAINER_IMAGE": "normalized-collector:test",
        }
    )

    completed = subprocess.run(
        [sys.executable, str(COLLECTOR_PATH)],
        env=with_common_pythonpath(env),
        check=False,
    )
    assert completed.returncode == 1

    manifest_paths = sorted(results_dir.glob("*/**/manifest.json"))
    data_paths = sorted(results_dir.glob("*/**/data.csv"))

    assert len(manifest_paths) == 2
    assert len(data_paths) == 2

    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "error"
        assert "error_message" in manifest

    validator = load_module(VALIDATOR_PATH, "normalized_validator")
    for data_path in data_paths:
        with data_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            all_rows = list(reader)
        assert all_rows[0] == validator.REQUIRED_COLUMNS
        assert len(all_rows) == 1
