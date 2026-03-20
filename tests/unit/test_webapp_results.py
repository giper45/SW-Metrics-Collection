import json

from webapp import create_app
from webapp.services.results import build_metrics_view, build_vulnerability_view, load_result_rows


def test_results_service_builds_vulnerability_summary(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()

    (normalized_dir / "repo-sec.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "project": "repo-sec",
                "metric": "vulnerability-findings",
                "variant": "spotbugs-findsecbugs-default",
                "component_type": "module",
                "component": "service",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 2,
                "tool": "spotbugs",
                "tool_version": "1.0",
                "parameters": {
                    "summary": {
                        "total": 2,
                        "severity_critical": 0,
                        "severity_high": 1,
                        "severity_medium": 1,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "WEAK_HASH",
                            "rule_name": "Weak hash",
                            "message": "MD5 should not be used",
                            "severity": "high",
                            "source_path": "src/A.java",
                            "start_line": 10,
                            "cwe_ids": ["CWE-328"],
                            "owasp_tags": ["OWASP-A02"],
                        },
                        {
                            "rule_id": "PREDICTABLE_RANDOM",
                            "rule_name": "Predictable random",
                            "message": "Random is predictable",
                            "severity": "medium",
                            "source_path": "src/B.java",
                            "start_line": 20,
                            "cwe_ids": ["CWE-330"],
                            "owasp_tags": [],
                        },
                    ],
                },
                "timestamp_utc": "2026-03-20T09:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_vulnerability_view(rows, {"source": "normalized", "search": "", "severity": ""})

    assert view_data["summary"]["findings"] == 2
    assert view_data["summary"]["high_priority"] == 1
    assert view_data["summary"]["rules"] == 2
    assert view_data["entries"][0]["visible_findings"][0]["rule_id"] == "WEAK_HASH"


def test_results_service_enriches_vulnerability_flows_and_source_snippets(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    src_dir = tmp_path / "src"
    results_dir.mkdir()
    normalized_dir.mkdir()
    (src_dir / "repo-flow" / "src" / "main" / "java" / "com" / "example").mkdir(parents=True)
    (src_dir / "repo-flow" / "src" / "main" / "java" / "com" / "example" / "Controller.java").write_text(
        "\n".join(
            [
                "package com.example;",
                "",
                "class Controller {",
                "  String read(HttpServletRequest request) {",
                "    return request.getParameter(\"name\");",
                "  }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src_dir / "repo-flow" / "src" / "main" / "java" / "com" / "example" / "View.java").write_text(
        "\n".join(
            [
                "package com.example;",
                "",
                "class View {",
                "  void render(HttpServletResponse response, String name) throws Exception {",
                "    response.getWriter().write(name);",
                "  }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    target_file = normalized_dir / "vulnerabilities" / "jsonl" / "repo-flow.jsonl"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-flow",
                "project": "repo-flow",
                "metric": "vulnerability-findings",
                "variant": "codeql-java-security-extended",
                "component_type": "module",
                "component": "repo-flow",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 1,
                "tool": "codeql",
                "tool_version": "2.23.1",
                "parameters": {
                    "summary": {
                        "total": 1,
                        "severity_critical": 0,
                        "severity_high": 1,
                        "severity_medium": 0,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "java/xss",
                            "rule_name": "Reflected XSS",
                            "message": "Unsanitized input reaches an HTTP response",
                            "severity": "high",
                            "source_path": "src/main/java/com/example/View.java",
                            "start_line": 5,
                            "primary_location": {
                                "path": "src/main/java/com/example/View.java",
                                "start_line": 5,
                                "end_line": 5,
                                "message": "Sink location",
                            },
                            "source_location": {
                                "path": "src/main/java/com/example/Controller.java",
                                "start_line": 5,
                                "end_line": 5,
                                "message": "Source location",
                            },
                            "sink_location": {
                                "path": "src/main/java/com/example/View.java",
                                "start_line": 5,
                                "end_line": 5,
                                "message": "Sink location",
                            },
                            "flow_steps": [
                                {
                                    "path": "src/main/java/com/example/Controller.java",
                                    "start_line": 5,
                                    "end_line": 5,
                                    "message": "User-controlled input enters the program",
                                    "role": "source",
                                    "execution_order": 1,
                                },
                                {
                                    "path": "src/main/java/com/example/View.java",
                                    "start_line": 5,
                                    "end_line": 5,
                                    "message": "Unsanitized input reaches the response writer",
                                    "role": "sink",
                                    "execution_order": 2,
                                },
                            ],
                            "flow_path_count": 1,
                            "observed_features": {
                                "primary_location": True,
                                "source_location": True,
                                "sink_location": True,
                                "flow_path": True,
                                "code_snippets": True,
                            },
                            "cwe_ids": ["CWE-79"],
                            "owasp_tags": ["OWASP-A03"],
                        }
                    ],
                },
                "timestamp_utc": "2026-03-20T09:15:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_vulnerability_view(
        rows,
        {"source": "normalized", "search": "", "severity": ""},
        src_dir=src_dir,
    )

    finding = view_data["entries"][0]["visible_findings"][0]
    assert finding["observed_features"]["flow_path"] is True
    assert finding["source_location"]["path"] == "src/main/java/com/example/Controller.java"
    assert finding["sink_location"]["path"] == "src/main/java/com/example/View.java"
    assert "request.getParameter" in finding["flow_steps"][0]["snippet"]
    assert "response.getWriter().write(name);" in finding["flow_steps"][1]["snippet"]
    assert finding["feature_rows"][3]["value"] == "2 steps"


def test_results_service_builds_metric_view(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    metrics_dir = results_dir / "software-metrics" / "jsonl"
    metrics_dir.mkdir(parents=True)

    (metrics_dir / "repo-metrics.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-2",
                        "project": "repo-alpha",
                        "metric": "loc",
                        "variant": "cloc-default",
                        "component_type": "file",
                        "component": "src/Main.java",
                        "status": "ok",
                        "value": 120.0,
                        "tool": "cloc",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T10:00:00Z",
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-2",
                        "project": "repo-alpha",
                        "metric": "cc",
                        "submetric": "cc_proxy_mean",
                        "variant": "lizard-default",
                        "component_type": "module",
                        "component": "core",
                        "status": "ok",
                        "value": 4.5,
                        "tool": "lizard",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T10:00:01Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_metrics_view(rows, {"source": "raw", "metric": "", "search": ""})

    assert view_data["summary"]["rows"] == 2
    assert {group["measure"] for group in view_data["groups"]} == {"loc", "cc_proxy_mean"}
    assert view_data["rows"][0]["component"] in {"src/Main.java", "core"}


def test_results_service_reads_nested_result_directories(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    nested_raw = results_dir / "software-metrics" / "jsonl"
    nested_normalized = normalized_dir / "software-metrics" / "jsonl"
    nested_raw.mkdir(parents=True)
    nested_normalized.mkdir(parents=True)

    (nested_raw / "loc.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-3",
                "project": "repo-beta",
                "metric": "loc",
                "variant": "cloc-default",
                "component_type": "file",
                "component": "src/App.java",
                "status": "ok",
                "value": 42,
                "tool": "cloc",
                "tool_version": "1.0",
                "parameters": {},
                "timestamp_utc": "2026-03-20T11:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (nested_normalized / "cc.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-3",
                "project": "repo-beta",
                "metric": "cc",
                "variant": "lizard-default",
                "component_type": "module",
                "component": "core",
                "status": "ok",
                "value": 7,
                "tool": "lizard",
                "tool_version": "1.0",
                "parameters": {},
                "timestamp_utc": "2026-03-20T11:00:01Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)

    assert len(rows) == 2
    assert {row["_source"] for row in rows} == {"raw", "normalized"}
    assert {row["metric"] for row in rows} == {"loc", "cc"}


def test_results_routes_render_after_login(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text("clean:\n\t@echo clean\n", encoding="utf-8")
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()

    (results_dir / "vulnerabilities" / "jsonl" / "repo.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (results_dir / "vulnerabilities" / "jsonl" / "repo.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-1",
                        "project": "repo-sec",
                        "metric": "vulnerability-findings",
                        "variant": "spotbugs-findsecbugs-default",
                        "component_type": "module",
                        "component": "service",
                        "submetric": "vulnerability_total",
                        "status": "ok",
                        "value": 1,
                        "tool": "spotbugs",
                        "tool_version": "1.0",
                        "parameters": {
                            "summary": {
                                "total": 1,
                                "severity_critical": 0,
                                "severity_high": 1,
                                "severity_medium": 0,
                                "severity_low": 0,
                                "severity_info": 0,
                                "severity_unknown": 0,
                            },
                            "findings": [
                                {
                                    "rule_id": "WEAK_HASH",
                                    "rule_name": "Weak hash",
                                    "message": "MD5 should not be used",
                                    "severity": "high",
                                    "source_path": "src/A.java",
                                    "start_line": 10,
                                    "cwe_ids": ["CWE-328"],
                                    "owasp_tags": ["OWASP-A02"],
                                }
                            ],
                        },
                        "timestamp_utc": "2026-03-20T09:00:00Z",
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-1",
                        "project": "repo-sec",
                        "metric": "loc",
                        "variant": "cloc-default",
                        "component_type": "file",
                        "component": "src/A.java",
                        "status": "ok",
                        "value": 33.0,
                        "tool": "cloc",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T09:00:01Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (normalized_dir / "vulnerabilities" / "jsonl" / "repo-normalized.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (normalized_dir / "vulnerabilities" / "jsonl" / "repo-normalized.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-2",
                "project": "repo-sec",
                "metric": "vulnerability-findings",
                "variant": "codeql-java-security-extended",
                "component_type": "module",
                "component": "service",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 1,
                "tool": "codeql",
                "tool_version": "1.0",
                "parameters": {
                    "summary": {
                        "total": 1,
                        "severity_critical": 0,
                        "severity_high": 0,
                        "severity_medium": 1,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "SQL_INJECTION",
                            "rule_name": "SQL injection",
                            "message": "Unsanitized input reaches query",
                            "severity": "medium",
                            "source_path": "src/B.java",
                            "start_line": 20,
                            "cwe_ids": ["CWE-89"],
                            "owasp_tags": ["OWASP-A03"],
                        }
                    ],
                },
                "timestamp_utc": "2026-03-20T09:05:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "secret",
            "SECRET_KEY": "test-secret",
            "PROJECT_ROOT": tmp_path,
            "MAKEFILE_PATH": makefile_path,
            "SRC_DIR": tmp_path / "src",
            "RESULTS_DIR": results_dir,
            "RESULTS_NORMALIZED_DIR": normalized_dir,
            "ANALYSIS_OUT_DIR": tmp_path / "analysis_out",
            "UPLOAD_TMP_DIR": tmp_path / ".webapp_uploads",
        }
    )
    client = app.test_client()

    login_page = client.get("/login")
    html = login_page.get_data(as_text=True)
    token = html.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    client.post(
        "/login",
        data={"username": "swadmin", "password": "secret", "csrf_token": token},
        follow_redirects=True,
    )

    overview = client.get("/insights")
    vulnerabilities = client.get("/insights/vulnerabilities")
    metrics = client.get("/insights/metrics")

    assert overview.status_code == 200
    overview_html = overview.get_data(as_text=True)
    assert "Insights Hub" in overview_html
    assert "Security explorer" in overview_html
    assert "/insights/vulnerabilities?source=normalized" in overview_html
    assert "/insights/metrics?source=raw" in overview_html
    assert vulnerabilities.status_code == 200
    vulnerabilities_html = vulnerabilities.get_data(as_text=True)
    assert "SQL_INJECTION" in vulnerabilities_html
    assert "Observed Features" in vulnerabilities_html
    assert "Flow Trace" in vulnerabilities_html
    assert "N/A. This tool output does not expose a source-to-sink flow trace for this finding." in vulnerabilities_html
    assert metrics.status_code == 200
    assert "src/A.java" in metrics.get_data(as_text=True)


def test_ajax_queue_selected_targets_returns_json(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        (
            "collect-loc-cloc:\n"
            "\t@echo loc\n\n"
            "collect-vulnerability-pmd-security:\n"
            "\t@echo vuln\n"
        ),
        encoding="utf-8",
    )

    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "secret",
            "SECRET_KEY": "test-secret",
            "PROJECT_ROOT": tmp_path,
            "MAKEFILE_PATH": makefile_path,
            "SRC_DIR": tmp_path / "src",
            "RESULTS_DIR": tmp_path / "results",
            "RESULTS_NORMALIZED_DIR": tmp_path / "results_normalized",
            "ANALYSIS_OUT_DIR": tmp_path / "analysis_out",
            "UPLOAD_TMP_DIR": tmp_path / ".webapp_uploads",
        }
    )
    client = app.test_client()

    login_page = client.get("/login")
    token = login_page.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    dashboard = client.post(
        "/login",
        data={"username": "swadmin", "password": "secret", "csrf_token": token},
        follow_redirects=True,
    )
    dashboard_token = dashboard.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    response = client.post(
        "/targets/run-selected",
        data={
            "csrf_token": dashboard_token,
            "targets": ["collect-loc-cloc", "collect-vulnerability-pmd-security"],
        },
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "queued"
    assert payload["job_count"] == 2
    assert "Queued 2 target(s)" in payload["message"]


def test_ajax_queue_target_validation_error_returns_json(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text("collect-loc-cloc:\n\t@echo loc\n", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "secret",
            "SECRET_KEY": "test-secret",
            "PROJECT_ROOT": tmp_path,
            "MAKEFILE_PATH": makefile_path,
            "SRC_DIR": tmp_path / "src",
            "RESULTS_DIR": tmp_path / "results",
            "RESULTS_NORMALIZED_DIR": tmp_path / "results_normalized",
            "ANALYSIS_OUT_DIR": tmp_path / "analysis_out",
            "UPLOAD_TMP_DIR": tmp_path / ".webapp_uploads",
        }
    )
    client = app.test_client()

    login_page = client.get("/login")
    token = login_page.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    dashboard = client.post(
        "/login",
        data={"username": "swadmin", "password": "secret", "csrf_token": token},
        follow_redirects=True,
    )
    dashboard_token = dashboard.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]

    response = client.post(
        "/targets/run-selected",
        data={
            "csrf_token": dashboard_token,
            "env_overrides": "BROKEN_LINE",
            "targets": ["collect-loc-cloc"],
        },
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "expected KEY=VALUE" in payload["message"]
