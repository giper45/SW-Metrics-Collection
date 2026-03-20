import csv
import io
import json

from webapp import create_app
from webapp.services.results import (
    build_metrics_view,
    build_vulnerability_view,
    export_metric_rows_csv,
    export_metrics_vulnerability_matrix_csv,
    export_vulnerability_findings_csv,
    load_result_rows,
)


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
    assert view_data["summary"]["tool_names"] == ["spotbugs"]
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
    assert finding["primary_location"]["language_label"] == "Java"
    assert finding["flow_steps"][0]["language_label"] == "Java"
    assert "request.getParameter" in finding["flow_steps"][0]["snippet"]
    assert "response.getWriter().write(name);" in finding["flow_steps"][1]["snippet"]
    assert "color:" in str(finding["flow_steps"][0]["snippet_html"])
    assert finding["feature_rows"][3]["value"] == "2 steps"


def test_results_service_auto_source_prefers_matching_raw_vulnerability_rows(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    raw_dir = results_dir / "vulnerabilities" / "jsonl"
    normalized_vuln_dir = normalized_dir / "vulnerabilities" / "jsonl"
    raw_dir.mkdir(parents=True)
    normalized_vuln_dir.mkdir(parents=True)

    (raw_dir / "mutillidae.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-raw",
                "project": "mutillidae",
                "metric": "vulnerability-findings",
                "variant": "psalm-php-taint-analysis",
                "component_type": "module",
                "component": "src",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 2,
                "tool": "psalm",
                "tool_version": "6.16.1",
                "parameters": {
                    "summary": {
                        "total": 2,
                        "severity_critical": 0,
                        "severity_high": 2,
                        "severity_medium": 0,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [],
                },
                "timestamp_utc": "2026-03-20T12:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (normalized_vuln_dir / "repo-sec.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-normalized",
                "project": "repo-sec",
                "metric": "vulnerability-findings",
                "variant": "codeql-java-security-extended",
                "component_type": "module",
                "component": "service",
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
                    "findings": [],
                },
                "timestamp_utc": "2026-03-20T12:05:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_vulnerability_view(
        rows,
        {"project": "mutillidae", "tool": "psalm", "source": "", "search": "", "severity": ""},
    )

    assert view_data["filters"]["source"] == "raw"
    assert view_data["summary"]["findings"] == 2
    assert view_data["entries"][0]["row"]["project"] == "mutillidae"


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
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-2",
                        "project": "repo-alpha",
                        "metric": "class-count",
                        "variant": "javaparser-default",
                        "component_type": "module",
                        "component": "core",
                        "status": "ok",
                        "value": 12.0,
                        "tool": "javaparser",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T10:00:02Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_metrics_view(rows, {"source": "raw", "metric": "", "search": ""})

    assert view_data["summary"]["rows"] == 3
    assert view_data["summary"]["tool_names"] == ["cloc", "javaparser", "lizard"]
    assert view_data["summary"]["collector_scopes"] == 2
    assert view_data["summary"]["scope_names"] == ["generic", "java"]
    assert {group["measure"] for group in view_data["groups"]} == {"loc", "cc_proxy_mean", "class-count"}
    assert {group["collector_scope"] for group in view_data["groups"]} == {"generic", "java"}
    assert any(group["tool_names"] == ["cloc"] for group in view_data["groups"])
    assert any(scope["key"] == "java" for scope in view_data["summary"]["scope_breakdown"])
    assert view_data["rows"][0]["component"] in {"src/Main.java", "core"}


def test_results_service_auto_source_prefers_matching_raw_metric_rows(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    raw_dir = results_dir / "software-metrics" / "jsonl"
    normalized_metrics_dir = normalized_dir / "software-metrics" / "jsonl"
    raw_dir.mkdir(parents=True)
    normalized_metrics_dir.mkdir(parents=True)

    (raw_dir / "mutillidae.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-raw",
                "project": "mutillidae",
                "metric": "loc",
                "variant": "cloc-default",
                "component_type": "file",
                "component": "src/index.php",
                "status": "ok",
                "value": 12,
                "tool": "cloc",
                "tool_version": "1.0",
                "parameters": {},
                "timestamp_utc": "2026-03-20T12:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (normalized_metrics_dir / "repo-sec.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-normalized",
                "project": "repo-sec",
                "metric": "class-count",
                "variant": "javaparser-default",
                "component_type": "module",
                "component": "service",
                "status": "ok",
                "value": 8,
                "tool": "javaparser",
                "tool_version": "1.0",
                "parameters": {},
                "timestamp_utc": "2026-03-20T12:05:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_metrics_view(rows, {"project": "mutillidae", "source": "", "search": ""})

    assert view_data["filters"]["source"] == "raw"
    assert view_data["summary"]["rows"] == 1
    assert view_data["rows"][0]["project"] == "mutillidae"


def test_results_service_filters_metrics_by_collector_scope(tmp_path):
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
                        "metric": "class-count",
                        "variant": "javaparser-default",
                        "component_type": "module",
                        "component": "core",
                        "status": "ok",
                        "value": 12.0,
                        "tool": "javaparser",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T10:00:02Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    view_data = build_metrics_view(rows, {"source": "raw", "collector_scope": "java", "search": ""})

    assert view_data["summary"]["rows"] == 1
    assert view_data["rows"][0]["tool"] == "javaparser"
    assert view_data["rows"][0]["_collector_scope"] == "java"
    assert view_data["options"]["collector_scopes"] == [
        {"key": "generic", "label": "Generic", "badge": "secondary"},
        {"key": "java", "label": "Java", "badge": "warning"},
    ]


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


def test_results_service_exports_vulnerability_findings_csv_with_cves(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    vuln_dir = normalized_dir / "vulnerabilities" / "jsonl"
    vuln_dir.mkdir(parents=True)

    (vuln_dir / "repo-cves.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-cves",
                "project": "repo-cves",
                "metric": "vulnerability-findings",
                "variant": "dependency-check-default",
                "component_type": "module",
                "component": "service",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 1,
                "tool": "dependency-check",
                "tool_version": "12.2.0",
                "parameters": {
                    "summary": {
                        "total": 1,
                        "severity_critical": 1,
                        "severity_high": 0,
                        "severity_medium": 0,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "CVE-2021-44228",
                            "rule_name": "Log4Shell",
                            "message": "Vulnerable dependency found",
                            "severity": "critical",
                            "source_path": "pom.xml",
                            "start_line": 12,
                            "package_name": "org.apache.logging.log4j:log4j-core",
                            "package_version": "2.14.1",
                            "cwe_ids": ["CWE-502"],
                        }
                    ],
                },
                "timestamp_utc": "2026-03-20T13:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    csv_text = export_vulnerability_findings_csv(rows, {"source": "normalized", "project": "repo-cves"})
    exported_rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(exported_rows) == 1
    assert exported_rows[0]["project"] == "repo-cves"
    assert exported_rows[0]["tool"] == "dependency-check"
    assert exported_rows[0]["cve_ids"] == "CVE-2021-44228"
    assert exported_rows[0]["cve_primary"] == "CVE-2021-44228"
    assert exported_rows[0]["package_name"] == "org.apache.logging.log4j:log4j-core"


def test_results_service_exports_metrics_vulnerability_matrix_csv(tmp_path):
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    metrics_dir = results_dir / "software-metrics" / "jsonl"
    vulnerabilities_dir = results_dir / "vulnerabilities" / "jsonl"
    metrics_dir.mkdir(parents=True)
    vulnerabilities_dir.mkdir(parents=True)

    (metrics_dir / "repo-alpha.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-metrics-1",
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
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "run_id": "run-metrics-2",
                        "project": "repo-alpha",
                        "metric": "class-count",
                        "variant": "javaparser-default",
                        "component_type": "module",
                        "component": "core",
                        "status": "ok",
                        "value": 12.0,
                        "tool": "javaparser",
                        "tool_version": "1.0",
                        "parameters": {},
                        "timestamp_utc": "2026-03-20T10:00:02Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (vulnerabilities_dir / "repo-alpha.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-vuln-1",
                "project": "repo-alpha",
                "metric": "vulnerability-findings",
                "variant": "dependency-check-default",
                "component_type": "module",
                "component": "core",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 1,
                "tool": "dependency-check",
                "tool_version": "12.2.0",
                "parameters": {
                    "summary": {
                        "total": 1,
                        "severity_critical": 1,
                        "severity_high": 0,
                        "severity_medium": 0,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "CVE-2021-44228",
                            "rule_name": "Log4Shell",
                            "message": "Vulnerable dependency found",
                            "severity": "critical",
                            "source_path": "pom.xml",
                            "start_line": 12,
                            "cwe_ids": ["CWE-502"],
                        }
                    ],
                },
                "timestamp_utc": "2026-03-20T10:05:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_result_rows(results_dir, normalized_dir)
    csv_text = export_metrics_vulnerability_matrix_csv(
        rows,
        {"source": "raw", "project": "repo-alpha", "component_type": "module"},
    )
    exported_rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(exported_rows) == 1
    assert exported_rows[0]["project"] == "repo-alpha"
    assert exported_rows[0]["component"] == "core"
    assert exported_rows[0]["vulnerability_findings_total"] == "1"
    assert exported_rows[0]["vulnerability_cve_ids"] == "CVE-2021-44228"
    assert exported_rows[0]["metric_cc__cc_proxy_mean__lizard"] == "4.5"
    assert exported_rows[0]["metric_class_count__class_count__javaparser"] == "12.0"


def test_results_routes_render_after_login(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text("clean:\n\t@echo clean\n", encoding="utf-8")
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    src_dir = tmp_path / "src"
    results_dir.mkdir()
    normalized_dir.mkdir()
    (src_dir / "repo-sec" / "src").mkdir(parents=True, exist_ok=True)
    (src_dir / "repo-sec" / "src" / "A.java").write_text(
        "\n".join(
            [
                "class A {",
                "  String read(String user) {",
                "    return user;",
                "  }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src_dir / "repo-sec" / "src" / "B.java").write_text(
        "\n".join(
            [
                "class B {",
                "  void query(String sql) {",
                "    System.out.println(sql);",
                "  }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

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
                                    "primary_location": {
                                        "path": "src/B.java",
                                        "start_line": 3,
                                        "end_line": 3,
                                        "message": "Sink location",
                                    },
                                    "source_location": {
                                        "path": "src/A.java",
                                        "start_line": 2,
                                        "end_line": 2,
                                        "message": "Source location",
                                    },
                                    "sink_location": {
                                        "path": "src/B.java",
                                        "start_line": 3,
                                        "end_line": 3,
                                        "message": "Sink location",
                                    },
                                    "flow_steps": [
                                        {
                                            "path": "src/A.java",
                                            "start_line": 2,
                                            "end_line": 2,
                                            "message": "User input enters the method",
                                            "role": "source",
                                            "execution_order": 1,
                                        },
                                        {
                                            "path": "src/B.java",
                                            "start_line": 3,
                                            "end_line": 3,
                                            "message": "User input reaches the sink",
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
            "SRC_DIR": src_dir,
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
    vulnerabilities_raw = client.get("/insights/vulnerabilities?source=raw")
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
    assert "CodeQL" in vulnerabilities_html
    assert "Observed Features" in vulnerabilities_html
    assert "Flow Trace" in vulnerabilities_html
    assert 'data-flow-jump="' in vulnerabilities_html
    assert "Scroll inside this panel to inspect long traces." in vulnerabilities_html
    assert "Export Findings CSV" in vulnerabilities_html
    assert "/insights/vulnerabilities/export.csv?source=normalized" in vulnerabilities_html
    assert "Source" in vulnerabilities_html
    assert "Sink" in vulnerabilities_html
    assert vulnerabilities_raw.status_code == 200
    assert "N/A. This tool output does not expose a source-to-sink flow trace for this finding." in vulnerabilities_raw.get_data(as_text=True)
    assert metrics.status_code == 200
    metrics_html = metrics.get_data(as_text=True)
    assert "src/A.java" in metrics_html
    assert "CLOC" in metrics_html
    assert "Collector scope" in metrics_html
    assert "Generic" in metrics_html
    assert "Export Metrics + Vulnerabilities CSV" in metrics_html
    assert "/insights/metrics/export.csv?source=raw" in metrics_html
    assert "/insights/metrics/export-matrix.csv?source=raw" in metrics_html


def test_results_export_routes_return_csv_after_login(tmp_path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text("clean:\n\t@echo clean\n", encoding="utf-8")
    results_dir = tmp_path / "results"
    normalized_dir = tmp_path / "results_normalized"
    results_dir.mkdir()
    normalized_dir.mkdir()
    (results_dir / "software-metrics" / "jsonl").mkdir(parents=True, exist_ok=True)
    (results_dir / "vulnerabilities" / "jsonl").mkdir(parents=True, exist_ok=True)

    (results_dir / "software-metrics" / "jsonl" / "repo-export.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-metrics",
                "project": "repo-export",
                "metric": "class-count",
                "variant": "javaparser-default",
                "component_type": "module",
                "component": "core",
                "status": "ok",
                "value": 8,
                "tool": "javaparser",
                "tool_version": "1.0",
                "parameters": {},
                "timestamp_utc": "2026-03-20T14:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (results_dir / "vulnerabilities" / "jsonl" / "repo-export.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-vulns",
                "project": "repo-export",
                "metric": "vulnerability-findings",
                "variant": "dependency-check-default",
                "component_type": "module",
                "component": "core",
                "submetric": "vulnerability_total",
                "status": "ok",
                "value": 1,
                "tool": "dependency-check",
                "tool_version": "12.2.0",
                "parameters": {
                    "summary": {
                        "total": 1,
                        "severity_critical": 1,
                        "severity_high": 0,
                        "severity_medium": 0,
                        "severity_low": 0,
                        "severity_info": 0,
                        "severity_unknown": 0,
                    },
                    "findings": [
                        {
                            "rule_id": "CVE-2021-44228",
                            "rule_name": "Log4Shell",
                            "message": "Vulnerable dependency found",
                            "severity": "critical",
                            "source_path": "pom.xml",
                            "start_line": 12,
                            "cwe_ids": ["CWE-502"],
                        }
                    ],
                },
                "timestamp_utc": "2026-03-20T14:01:00Z",
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
    token = login_page.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    client.post(
        "/login",
        data={"username": "swadmin", "password": "secret", "csrf_token": token},
        follow_redirects=True,
    )

    vulnerabilities_export = client.get("/insights/vulnerabilities/export.csv?source=raw&project=repo-export")
    metrics_export = client.get("/insights/metrics/export.csv?source=raw&project=repo-export")
    matrix_export = client.get("/insights/metrics/export-matrix.csv?source=raw&project=repo-export")

    assert vulnerabilities_export.status_code == 200
    assert 'attachment; filename="vulnerability-findings-export.csv"' in vulnerabilities_export.headers["Content-Disposition"]
    assert "CVE-2021-44228" in vulnerabilities_export.get_data(as_text=True)
    assert metrics_export.status_code == 200
    assert 'attachment; filename="software-metrics-export.csv"' in metrics_export.headers["Content-Disposition"]
    assert "class-count" in metrics_export.get_data(as_text=True)
    assert matrix_export.status_code == 200
    assert 'attachment; filename="metrics-vulnerabilities-matrix-export.csv"' in matrix_export.headers["Content-Disposition"]
    matrix_body = matrix_export.get_data(as_text=True)
    assert "vulnerability_cve_ids" in matrix_body
    assert "CVE-2021-44228" in matrix_body


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
    assert payload["message"] == "Queued 2 commands: CLOC, PMD."


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
