from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import queue
import shlex
import subprocess
import threading
import uuid
from typing import Callable, Iterable


LOG_LINE_LIMIT = 4000
JobHandler = Callable[["OperationJob"], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class OperationJob:
    id: str
    kind: str
    label: str
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    error: str | None = None
    _log_lines: list[str] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def append_log(self, line: str) -> None:
        cleaned = line.rstrip("\n")
        with self._lock:
            self._log_lines.append(cleaned)
            if len(self._log_lines) > LOG_LINE_LIMIT:
                self._log_lines = self._log_lines[-LOG_LINE_LIMIT:]

    def set_running(self) -> None:
        with self._lock:
            self.status = "running"
            self.started_at = utc_now()

    def mark_success(self) -> None:
        with self._lock:
            self.status = "succeeded"
            self.finished_at = utc_now()
            if self.returncode is None:
                self.returncode = 0

    def mark_failure(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = message
            self.finished_at = utc_now()
            if self.returncode is None:
                self.returncode = 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "label": self.label,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "command": list(self.command),
                "returncode": self.returncode,
                "error": self.error,
                "log": "\n".join(self._log_lines),
            }


class OperationQueue:
    def __init__(self, history_limit: int = 50):
        self._history_limit = history_limit
        self._jobs: OrderedDict[str, OperationJob] = OrderedDict()
        self._handlers: dict[str, JobHandler] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._jobs_lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, kind: str, label: str, handler: JobHandler) -> OperationJob:
        job = OperationJob(id=uuid.uuid4().hex, kind=kind, label=label)
        with self._jobs_lock:
            self._jobs[job.id] = job
            self._handlers[job.id] = handler
        self._queue.put(job.id)
        return job

    def recent(self, limit: int = 20) -> list[dict]:
        with self._jobs_lock:
            jobs = list(self._jobs.values())[-limit:]
        return [job.snapshot() for job in reversed(jobs)]

    def get_snapshot(self, job_id: str) -> dict | None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        return job.snapshot()

    def _trim_history(self) -> None:
        with self._jobs_lock:
            while len(self._jobs) > self._history_limit:
                job_id, _ = self._jobs.popitem(last=False)
                self._handlers.pop(job_id, None)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._jobs_lock:
                job = self._jobs.get(job_id)
                handler = self._handlers.get(job_id)

            if job is None or handler is None:
                self._queue.task_done()
                continue

            job.set_running()
            try:
                handler(job)
            except Exception as exc:  # pragma: no cover - safety net
                job.append_log(f"[error] {exc}")
                job.mark_failure(str(exc))
            else:
                job.mark_success()
            finally:
                self._trim_history()
                self._queue.task_done()


def run_streaming_command(
    job: OperationJob,
    command: Iterable[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> None:
    command_list = [str(part) for part in command]
    job.command = command_list
    job.append_log(f"$ {' '.join(shlex.quote(part) for part in command_list)}")
    job.append_log(f"[cwd] {cwd}")

    process = subprocess.Popen(
        command_list,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        job.append_log(line)

    process.wait()
    job.returncode = process.returncode
    if process.returncode != 0:
        raise RuntimeError(f"Command exited with status {process.returncode}.")
