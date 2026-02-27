#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
SIZE_PATTERN = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)?\s*$")

SIZE_FACTORS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000 ** 2,
    "GB": 1000 ** 3,
    "TB": 1000 ** 4,
    "PB": 1000 ** 5,
    "KIB": 1024,
    "MIB": 1024 ** 2,
    "GIB": 1024 ** 3,
    "TIB": 1024 ** 4,
    "PIB": 1024 ** 5,
}


def utc_timestamp_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def parse_cpu_percent(raw: str) -> Optional[float]:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_size_bytes(raw: str) -> Optional[int]:
    match = SIZE_PATTERN.match(str(raw or ""))
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    factor = SIZE_FACTORS.get(unit)
    if factor is None:
        return None
    return int(number * factor)


def parse_memory_usage_bytes(raw: str) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    used = text.split("/", 1)[0].strip()
    return parse_size_bytes(used)


def parse_docker_stats_line(raw: str) -> Tuple[Optional[float], Optional[int]]:
    parts = [part.strip() for part in str(raw or "").split("|", 1)]
    if len(parts) != 2:
        return None, None
    cpu_percent = parse_cpu_percent(parts[0])
    memory_bytes = parse_memory_usage_bytes(parts[1])
    return cpu_percent, memory_bytes


def is_docker_run_command(command: Sequence[str]) -> bool:
    if len(command) < 2:
        return False
    return command[0] == "docker" and command[1] == "run"


def add_cidfile_option(command: Sequence[str], cidfile_path: str) -> List[str]:
    updated = list(command)
    if "--cidfile" in updated:
        return updated
    if not is_docker_run_command(updated):
        return updated
    return [updated[0], updated[1], "--cidfile", cidfile_path, *updated[2:]]


def fetch_docker_stats(container_id: str) -> Tuple[Optional[float], Optional[int]]:
    completed = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.CPUPerc}}|{{.MemUsage}}",
            container_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None, None
    return parse_docker_stats_line((completed.stdout or "").strip())


def new_cidfile_path() -> str:
    temp_dir = tempfile.gettempdir()
    return os.path.join(temp_dir, f"metric-container-{uuid.uuid4().hex}.cid")


def _append_jsonl(path: str, row: dict) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def _metric_image(command: Sequence[str]) -> str:
    if not command:
        return "unknown"
    return str(command[-1])


def _build_telemetry_row(
    command: Sequence[str],
    run_id: str,
    exit_code: int,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    cpu_samples: Sequence[float],
    memory_samples: Sequence[int],
    sample_interval_sec: float,
) -> dict:
    image = _metric_image(command)
    cpu_max = max(cpu_samples) if cpu_samples else None
    cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 6) if cpu_samples else None
    memory_max = max(memory_samples) if memory_samples else None
    metric_name = image.rsplit(":", 1)[0] if ":" in image else image
    sample_count = max(len(cpu_samples), len(memory_samples))
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "metric_container": image,
        "metric_name": metric_name,
        "timestamp_utc_start": started_at,
        "timestamp_utc_end": ended_at,
        "duration_seconds": round(duration_seconds, 6),
        "cpu_percent_avg": cpu_avg,
        "cpu_percent_max": cpu_max,
        "memory_bytes_max": memory_max,
        "samples": sample_count,
        "sample_interval_sec": sample_interval_sec,
        "status": "ok" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "command": shlex.join(command),
    }


def run_with_optional_monitoring(
    command: Sequence[str],
    run_id: str,
    results_dir: str,
    enabled: bool = False,
    sample_interval_sec: float = 0.5,
    out_path: Optional[str] = None,
) -> int:
    if not command:
        raise ValueError("missing command to execute")

    if not enabled or not is_docker_run_command(command):
        completed = subprocess.run(list(command), check=False)
        return int(completed.returncode)

    safe_interval = max(float(sample_interval_sec), 0.1)
    output_path = out_path or os.path.join(results_dir, f"metric-runtime-{run_id}.jsonl")
    cidfile_path = new_cidfile_path()

    started_at = utc_timestamp_now()
    started = time.perf_counter()
    container_id = ""
    cpu_samples: List[float] = []
    memory_samples: List[int] = []
    monitored_command = add_cidfile_option(command, cidfile_path)
    process = subprocess.Popen(monitored_command)
    try:
        while True:
            if not container_id and os.path.exists(cidfile_path):
                with open(cidfile_path, "r", encoding="utf-8") as handle:
                    container_id = handle.read().strip()

            if container_id:
                cpu_percent, memory_bytes = fetch_docker_stats(container_id)
                if cpu_percent is not None:
                    cpu_samples.append(cpu_percent)
                if memory_bytes is not None:
                    memory_samples.append(memory_bytes)

            if process.poll() is not None:
                break
            time.sleep(safe_interval)

        if container_id:
            cpu_percent, memory_bytes = fetch_docker_stats(container_id)
            if cpu_percent is not None:
                cpu_samples.append(cpu_percent)
            if memory_bytes is not None:
                memory_samples.append(memory_bytes)

        exit_code = int(process.returncode or 0)
        ended_at = utc_timestamp_now()
        duration_seconds = time.perf_counter() - started
        telemetry = _build_telemetry_row(
            command=command,
            run_id=run_id,
            exit_code=exit_code,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            cpu_samples=cpu_samples,
            memory_samples=memory_samples,
            sample_interval_sec=safe_interval,
        )
        _append_jsonl(output_path, telemetry)
        return exit_code
    finally:
        try:
            os.remove(cidfile_path)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a metric command and optionally write per-run CPU/RAM/time telemetry."
    )
    parser.add_argument("--run-id", default=(os.environ.get("METRIC_RUN_ID") or "unknown-run"))
    parser.add_argument("--results-dir", default=(os.environ.get("RESULTS_DIR") or "/results"))
    parser.add_argument(
        "--enabled",
        default=os.environ.get("METRIC_RESOURCE_TRACKING", "0"),
        help="Enable resource telemetry (1/0, true/false).",
    )
    parser.add_argument(
        "--sample-interval-sec",
        type=float,
        default=float(os.environ.get("METRIC_RESOURCE_SAMPLE_SEC", "0.5")),
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("METRIC_RESOURCE_REPORT", ""),
        help="Telemetry JSONL output path. Defaults to <results_dir>/metric-runtime-<run_id>.jsonl",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute after '--'.")
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    out_path = args.out.strip() or None
    enabled = parse_bool(args.enabled, default=False)
    return run_with_optional_monitoring(
        command=command,
        run_id=str(args.run_id),
        results_dir=str(args.results_dir),
        enabled=enabled,
        sample_interval_sec=float(args.sample_interval_sec),
        out_path=out_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
