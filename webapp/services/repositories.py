from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import shutil
import shlex
import subprocess
import zipfile

from .jobs import OperationJob


@dataclass(frozen=True)
class CloneSpec:
    url: str
    ref: str | None = None
    directory_name: str | None = None


def list_repositories(src_dir: Path) -> list[Path]:
    if not src_dir.exists():
        return []
    return sorted(
        [
            entry
            for entry in src_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        ],
        key=lambda entry: entry.name.lower(),
    )


def parse_clone_specs(raw_text: str) -> list[CloneSpec]:
    specs: list[CloneSpec] = []
    reader = csv.reader(io.StringIO(raw_text))
    for line_number, row in enumerate(reader, start=1):
        cleaned = [item.strip() for item in row if item.strip()]
        if not cleaned or cleaned[0].startswith("#"):
            continue
        if len(cleaned) > 3:
            raise ValueError(
                f"Invalid repository row on line {line_number}: use url[,ref][,folder]."
            )

        url = cleaned[0]
        ref = cleaned[1] if len(cleaned) >= 2 else None
        directory_name = cleaned[2] if len(cleaned) == 3 else derive_repository_name(url)
        specs.append(CloneSpec(url=url, ref=ref, directory_name=directory_name))

    if not specs:
        raise ValueError("Add at least one repository definition.")
    return specs


def derive_repository_name(url: str) -> str:
    candidate = url.rstrip("/").rsplit("/", 1)[-1]
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    return sanitize_repository_name(candidate or "repository")


def sanitize_repository_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    if not normalized:
        raise ValueError("Repository name cannot be empty.")
    return normalized


def clone_repositories(
    job: OperationJob,
    src_dir: Path,
    specs: list[CloneSpec],
    replace_existing: bool = False,
) -> None:
    src_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        destination = _repository_path(src_dir, spec.directory_name or derive_repository_name(spec.url))
        if destination.exists():
            if not replace_existing:
                raise FileExistsError(
                    f"Repository folder already exists: {destination.name}. Enable overwrite to replace it."
                )
            job.append_log(f"[cleanup] Removing existing folder {destination.name}")
            shutil.rmtree(destination)

        command = ["git", "clone", "--depth", "1"]
        if spec.ref:
            command.extend(["--branch", spec.ref, "--single-branch"])
        command.extend([spec.url, str(destination)])

        job.append_log(f"[clone] {spec.url} -> {destination.name}")
        _run_command(job, command, cwd=src_dir.parent)


def clean_repositories(job: OperationJob, src_dir: Path) -> None:
    repositories = list_repositories(src_dir)
    if not repositories:
        job.append_log("[info] No repositories to clean.")
        return

    for repository in repositories:
        job.append_log(f"[delete] {repository.name}")
        shutil.rmtree(repository)


def delete_repository(job: OperationJob, src_dir: Path, repository_name: str) -> None:
    repository_path = _repository_path(src_dir, repository_name)
    if not repository_path.exists():
        raise FileNotFoundError(f"Repository folder does not exist: {repository_name}")
    job.append_log(f"[delete] {repository_path.name}")
    shutil.rmtree(repository_path)


def import_archives(
    job: OperationJob,
    src_dir: Path,
    archive_paths: list[Path],
    replace_existing: bool = False,
) -> None:
    src_dir.mkdir(parents=True, exist_ok=True)
    for archive_path in archive_paths:
        try:
            _extract_archive(job, archive_path, src_dir, replace_existing=replace_existing)
        finally:
            archive_path.unlink(missing_ok=True)
            try:
                archive_path.parent.rmdir()
            except OSError:
                pass


def _extract_archive(
    job: OperationJob,
    archive_path: Path,
    src_dir: Path,
    replace_existing: bool = False,
) -> None:
    if archive_path.suffix.lower() != ".zip":
        raise ValueError(f"Unsupported archive format: {archive_path.name}")

    with zipfile.ZipFile(archive_path) as archive:
        members = [item for item in archive.infolist() if item.filename]
        if not members:
            raise ValueError(f"Archive is empty: {archive_path.name}")

        archive_root = _single_archive_root(members)
        repository_name = sanitize_repository_name(
            archive_root or archive_path.stem
        )
        destination = _repository_path(src_dir, repository_name)

        if destination.exists():
            if not replace_existing:
                raise FileExistsError(
                    f"Repository folder already exists: {destination.name}. Enable overwrite to replace it."
                )
            job.append_log(f"[cleanup] Removing existing folder {destination.name}")
            shutil.rmtree(destination)

        job.append_log(f"[extract] {archive_path.name} -> {destination.name}")
        destination.mkdir(parents=True, exist_ok=False)

        try:
            for member in members:
                member_parts = _member_parts(member.filename)
                if not member_parts or member_parts[0] == "__MACOSX":
                    continue
                if archive_root and member_parts[0] == archive_root:
                    member_parts = member_parts[1:]
                if not member_parts:
                    continue

                target_path = _safe_destination(destination, member_parts)
                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise


def _run_command(job: OperationJob, command: list[str], cwd: Path) -> None:
    job.append_log(f"$ {' '.join(shlex.quote(part) for part in command)}")
    job.append_log(f"[cwd] {cwd}")
    process = subprocess.Popen(
        command,
        cwd=cwd,
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


def _repository_path(src_dir: Path, repository_name: str) -> Path:
    sanitized = sanitize_repository_name(repository_name)
    path = (src_dir / sanitized).resolve()
    src_root = src_dir.resolve()
    if path.parent != src_root:
        raise ValueError("Repository path escapes the source directory.")
    return path


def _safe_destination(destination: Path, member_parts: list[str]) -> Path:
    target = (destination / Path(*member_parts)).resolve()
    destination_root = destination.resolve()
    if target != destination_root and destination_root not in target.parents:
        raise ValueError("Archive contains an unsafe path.")
    return target


def _single_archive_root(members: list[zipfile.ZipInfo]) -> str | None:
    roots: set[str] = set()
    for member in members:
        parts = _member_parts(member.filename)
        if parts and parts[0] != "__MACOSX":
            roots.add(parts[0])
        if len(roots) > 1:
            return None
    return next(iter(roots)) if roots else None


def _member_parts(member_name: str) -> list[str]:
    return [part for part in PurePosixPath(member_name).parts if part not in {"", "."}]
