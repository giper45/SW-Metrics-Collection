import sys
from pathlib import Path

from analysis import metric_runtime_monitor as module


def test_parse_cpu_percent_accepts_percent_strings():
    assert module.parse_cpu_percent("12.5%") == 12.5
    assert module.parse_cpu_percent("0.0") == 0.0
    assert module.parse_cpu_percent("not-a-number") is None


def test_parse_memory_usage_bytes_uses_used_side():
    value = module.parse_memory_usage_bytes("12.5MiB / 8GiB")
    assert value == int(12.5 * 1024 * 1024)


def test_add_cidfile_option_injects_after_docker_run():
    command = ["docker", "run", "--rm", "loc-cloc:latest"]
    updated = module.add_cidfile_option(command, "/tmp/container.cid")
    assert updated[0:4] == ["docker", "run", "--cidfile", "/tmp/container.cid"]
    assert updated[-2:] == ["--rm", "loc-cloc:latest"]


def test_parse_docker_stats_line_handles_expected_format():
    cpu_percent, memory_bytes = module.parse_docker_stats_line("3.4%|18.0MiB / 8GiB")
    assert cpu_percent == 3.4
    assert memory_bytes == int(18.0 * 1024 * 1024)


def test_new_cidfile_path_points_to_nonexistent_file():
    first = Path(module.new_cidfile_path())
    second = Path(module.new_cidfile_path())
    assert first != second
    assert not first.exists()
    assert not second.exists()


def test_run_without_monitoring_returns_child_exit_code(tmp_path: Path):
    report_path = tmp_path / "telemetry.jsonl"
    code = module.run_with_optional_monitoring(
        command=[sys.executable, "-c", "import sys; sys.exit(7)"],
        run_id="run-123",
        results_dir=str(tmp_path),
        enabled=False,
        out_path=str(report_path),
    )
    assert code == 7
    assert not report_path.exists()
