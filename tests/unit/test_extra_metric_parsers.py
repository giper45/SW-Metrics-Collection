import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jscpd_ratio_parser(tmp_path):
    module = load_module(REPO_ROOT / "metrics/duplication/java/duplication-jscpd/collect.py")
    report = tmp_path / "jscpd-report.json"
    report.write_text(
        '{"statistics":{"total":{"percentage":12.5,"duplicatedLines":10,"lines":80}}}',
        encoding="utf-8",
    )
    assert module.parse_jscpd_ratio(str(report)) == 0.125


def test_halstead_and_mi_computation_positive():
    module = load_module(REPO_ROOT / "metrics/maintainability/java/mi-halstead-java/collect.py")
    java_code = """
    package com.example;
    public class A {
        public int calc(int x) {
            if (x > 0) { return x + 1; }
            return 0;
        }
    }
    """
    halstead = module.compute_halstead_metrics(java_code)
    assert halstead["volume"] > 0
    mi = module.compute_mi(halstead["volume"], cc=2, loc=6)
    assert mi > 0


def test_checkstyle_violation_parser(tmp_path):
    module = load_module(REPO_ROOT / "metrics/quality/java/static-warnings-checkstyle/collect.py")
    report = tmp_path / "report.xml"
    report.write_text(
        """
        <checkstyle version=\"10.0\">
          <file name=\"A.java\"><error line=\"3\" message=\"x\" source=\"x\"/></file>
          <file name=\"B.java\"><error line=\"5\" message=\"y\" source=\"y\"/></file>
        </checkstyle>
        """,
        encoding="utf-8",
    )
    assert module.parse_checkstyle_violations(str(report)) == 2.0


def test_jacoco_instruction_ratio_parser(tmp_path):
    module = load_module(REPO_ROOT / "metrics/testing/java/coverage-jacoco/collect.py")
    xml_path = tmp_path / "jacoco.xml"
    xml_path.write_text(
        """
        <report name=\"demo\">
          <counter type=\"INSTRUCTION\" missed=\"20\" covered=\"80\"/>
        </report>
        """,
        encoding="utf-8",
    )
    assert module.parse_jacoco_instruction_ratio(str(xml_path)) == 0.8


def test_git_numstat_parser_ignores_tests():
    module = load_module(REPO_ROOT / "metrics/evolution/generic/churn-git/collect.py")
    raw = "10\t2\tsrc/main/java/A.java\n3\t1\tsrc/test/java/ATest.java\n"
    assert module.parse_git_numstat(raw) == 12.0


def test_churn_collect_fails_on_partial_clone_read_only_by_default(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/evolution/generic/churn-git/collect.py")

    def fake_find_git_root(project_path):
        return "/app/junit5"

    def fake_run_command_details(cmd, cwd=None, stdin_text=None, allowed_returncodes=None):
        raise module.ToolExecutionError(
            "command failed (128): git -C /app/junit5 log --numstat --format=tformat:\n"
            "stderr: fatal: Unable to create temporary file '/app/junit5/.git/objects/pack/tmp_pack_XXXXXX': Read-only file system\n"
            "fatal: fetch-pack: invalid index-pack output\n"
            "fatal: could not fetch abc from promisor remote\n"
        )

    monkeypatch.setattr(module, "find_git_root", fake_find_git_root)
    monkeypatch.setattr(module, "run_command_details", fake_run_command_details)

    with monkeypatch.context() as ctx:
        ctx.delenv("METRIC_ERROR_MODE", raising=False)
        with pytest.raises(module.ToolExecutionError) as exc:
            module.collect_project_rows(
                project="junit5",
                project_path="/app/junit5",
                tool_version="2.44.0",
                timestamp="2026-02-27T10:00:00Z",
            )
        assert "partial_clone_read_only" in str(exc.value)


def test_churn_collect_fails_in_legacy_mode_too(monkeypatch):
    module = load_module(REPO_ROOT / "metrics/evolution/generic/churn-git/collect.py")

    def fake_find_git_root(project_path):
        return "/app/junit5"

    def fake_run_command_details(cmd, cwd=None, stdin_text=None, allowed_returncodes=None):
        raise module.ToolExecutionError("command failed (128): simulated partial clone issue")

    monkeypatch.setattr(module, "find_git_root", fake_find_git_root)
    monkeypatch.setattr(module, "run_command_details", fake_run_command_details)
    monkeypatch.setenv("METRIC_ERROR_MODE", "legacy-skip")

    with pytest.raises(module.ToolExecutionError) as exc:
        module.collect_project_rows(
            project="junit5",
            project_path="/app/junit5",
            tool_version="2.44.0",
            timestamp="2026-02-27T10:00:00Z",
        )
    assert "git_log_failed" in str(exc.value)
