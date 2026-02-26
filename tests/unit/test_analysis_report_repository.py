import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "analysis/report_repository.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_repo_report_outputs_metric_rows(tmp_path: Path):
    module = load_module(MODULE_PATH, "analysis_report_repository")

    normalized_dir = tmp_path / "results_normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / "sample.jsonl").write_text(
        (
            '{"schema_version":"1.0","run_id":"run-1","project":"repo-a","metric":"loc","variant":"cloc-default","component_type":"file","component":"src/A.java","status":"ok","value":10.0,"tool":"cloc","tool_version":"1.0","parameters":{"repo_commit":"abc","repo_dirty":false},"timestamp_utc":"2026-02-24T15:04:05Z"}\n'
            '{"schema_version":"1.0","run_id":"run-1","project":"repo-a","metric":"loc","variant":"tokei-default","component_type":"file","component":"src/A.java","status":"ok","value":12.0,"tool":"tokei","tool_version":"1.0","parameters":{"repo_commit":"abc","repo_dirty":false},"timestamp_utc":"2026-02-24T15:04:05Z"}\n'
        ),
        encoding="utf-8",
    )

    long_csv = tmp_path / "dataset_long.csv"
    long_csv.write_text(
        "project,run_id,timestamp_utc,component,component_type,metric,status,tool,variant,value,tool_version\n"
        "repo-a,run-1,2026-02-24T15:04:05Z,src/A.java,file,loc,ok,cloc,cloc-default,10.0,1.0\n"
        "repo-a,run-1,2026-02-24T15:04:05Z,src/B.java,file,loc,ok,cloc,cloc-default,20.0,1.0\n"
        "repo-a,run-1,2026-02-24T15:04:05Z,src/A.java,file,loc,ok,tokei,tokei-default,12.0,1.0\n"
        "repo-a,run-1,2026-02-24T15:04:05Z,src/B.java,file,loc,ok,tokei,tokei-default,19.0,1.0\n",
        encoding="utf-8",
    )

    rows = module.build_repo_report(normalized_dir, long_csv)
    assert len(rows) == 1
    row = rows[0]
    assert row["project"] == "repo-a"
    assert row["metric"] == "loc"
    assert row["n_tools"] == 2
    assert row["agreement_pairs"] == 1
    assert row["repo_commit"] == "abc"
