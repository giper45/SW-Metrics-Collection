#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

BYTECODE_DIR_CANDIDATES = (
    "target/classes",
    "build/classes/java/main",
    "build/classes/kotlin/main",
    "build/classes",
    "out/production",
)

DEFAULT_JAVA_VERSION = 21

REPO_VERSION_HINTS = {
    "Java": 21,
    "gson": 21,
    "junit5": 25,
}


@dataclass
class BuildTask:
    repo: str
    path: Path
    build_system: str
    java_version: int
    reason: str


def _to_int_version(raw: str) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("1."):
        text = text[2:]
    if not text.isdigit():
        return None
    parsed = int(text)
    if parsed <= 0:
        return None
    return parsed


def _extract_versions_from_text(text: str) -> List[int]:
    versions: List[int] = []
    for pattern in (
        r"maven\.compiler\.release>\s*([0-9]+)\s*<",
        r"maven\.compiler\.source>\s*([0-9]+(?:\.[0-9]+)?)\s*<",
        r"maven\.compiler\.target>\s*([0-9]+(?:\.[0-9]+)?)\s*<",
        r"<release>\s*([0-9]+)\s*</release>",
        r"JavaLanguageVersion\.of\(\s*([0-9]+)\s*\)",
        r"VERSION_([0-9]+)",
        r"\bJDK\s*([0-9]+(?:\.[0-9]+)?)\b",
    ):
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            parsed = _to_int_version(match)
            if parsed is not None:
                versions.append(parsed)
    return versions


def _has_class_files(repo_path: Path) -> bool:
    for rel_dir in BYTECODE_DIR_CANDIDATES:
        candidate = repo_path / rel_dir
        if not candidate.is_dir():
            continue
        if any(candidate.rglob("*.class")):
            return True
    return False


def _run(cmd: Sequence[str], *, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def _detect_build_system(repo_path: Path) -> Optional[str]:
    if (repo_path / "gradlew").is_file() or (repo_path / "build.gradle").is_file() or (repo_path / "build.gradle.kts").is_file():
        return "gradle"
    if (repo_path / "mvnw").is_file() or (repo_path / "pom.xml").is_file():
        return "maven"
    return None


def _scan_repo_versions(repo_path: Path) -> List[int]:
    versions: List[int] = []
    candidates = [
        repo_path / "pom.xml",
        repo_path / "build.gradle",
        repo_path / "build.gradle.kts",
        repo_path / "gradle.properties",
        repo_path / "README.md",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        versions.extend(_extract_versions_from_text(text))
    return versions


def _detect_java_version(repo_name: str, repo_path: Path, build_system: str, default_java: int) -> Tuple[int, str]:
    hint = REPO_VERSION_HINTS.get(repo_name)
    if hint:
        return int(hint), f"repo_hint={hint}"

    versions = _scan_repo_versions(repo_path)
    if versions:
        detected = max(versions)
        # Build runtime should be modern enough for current Maven/Gradle wrappers.
        detected = max(detected, 17)
        return detected, f"detected_max={detected}"

    return int(default_java), f"default={default_java}"


def _ensure_builder_image(builder_dir: Path, java_version: int) -> str:
    image = f"java-builder:jdk{java_version}"
    inspect = _run(["docker", "image", "inspect", image])
    if inspect.returncode == 0:
        return image

    build = _run(
        [
            "docker",
            "build",
            "-t",
            image,
            "--build-arg",
            f"JAVA_VERSION={java_version}",
            str(builder_dir),
        ]
    )
    if build.returncode != 0:
        raise RuntimeError(
            f"failed to build {image}\nstdout:\n{build.stdout}\nstderr:\n{build.stderr}"
        )
    return image


def _build_command(task: BuildTask) -> str:
    if task.build_system == "maven":
        maven_bin = "./mvnw" if (task.path / "mvnw").is_file() else "mvn"
        return (
            f"cd /workspace/{task.repo} && "
            f"chmod +x ./mvnw >/dev/null 2>&1 || true && "
            f"{maven_bin} --batch-mode -q "
            "-DskipTests -Dmaven.test.skip=true -DskipITs "
            "-Dcheckstyle.skip=true -Dspotbugs.skip=true -Dpmd.skip=true "
            "-Denforcer.skip=true -Dlicense.skip=true -Drat.skip=true "
            "-Djacoco.skip=true -Drevapi.skip=true "
            "compile"
        )

    gradle_bin = "./gradlew" if (task.path / "gradlew").is_file() else "gradle"
    return (
        f"cd /workspace/{task.repo} && "
        f"chmod +x ./gradlew >/dev/null 2>&1 || true && "
        f"{gradle_bin} --no-daemon classes -x test"
    )


def _run_build(task: BuildTask, image: str, src_dir: Path) -> subprocess.CompletedProcess:
    uid = os.getuid()
    gid = os.getgid()
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{uid}:{gid}",
        "-e",
        "HOME=/tmp",
        "-e",
        "GRADLE_USER_HOME=/tmp/.gradle",
        "-v",
        f"{src_dir}:/workspace",
        image,
        "bash",
        "-lc",
        _build_command(task),
    ]
    return _run(docker_cmd)


def _discover_tasks(src_dir: Path, default_java: int, repos_filter: List[str], force: bool) -> List[BuildTask]:
    wanted = set(repos_filter or [])
    tasks: List[BuildTask] = []
    for repo_path in sorted(path for path in src_dir.iterdir() if path.is_dir()):
        repo = repo_path.name
        if wanted and repo not in wanted:
            continue

        build_system = _detect_build_system(repo_path)
        if not build_system:
            continue
        if not force and _has_class_files(repo_path):
            continue

        version, reason = _detect_java_version(repo, repo_path, build_system, default_java)
        tasks.append(
            BuildTask(
                repo=repo,
                path=repo_path,
                build_system=build_system,
                java_version=version,
                reason=reason,
            )
        )
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Java bytecode in src/ using versioned java-builder Docker images.")
    parser.add_argument("--src-dir", default="src", help="Path to repository roots (default: src)")
    parser.add_argument(
        "--builder-dir",
        default="metrics/java-builder",
        help="Path to java-builder Docker context",
    )
    parser.add_argument("--default-java", type=int, default=DEFAULT_JAVA_VERSION, help="Default JDK version (default: 21)")
    parser.add_argument("--repo", action="append", default=[], help="Build only the given repo name (repeatable)")
    parser.add_argument("--force", action="store_true", help="Build even when .class files already exist")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any repo build fails")
    parser.add_argument("--dry-run", action="store_true", help="Print planned tasks without executing Docker")
    args = parser.parse_args()

    src_dir = Path(args.src_dir).resolve()
    builder_dir = Path(args.builder_dir).resolve()
    if not src_dir.is_dir():
        raise SystemExit(f"src-dir not found: {src_dir}")
    if not builder_dir.is_dir():
        raise SystemExit(f"builder-dir not found: {builder_dir}")

    tasks = _discover_tasks(
        src_dir=src_dir,
        default_java=int(args.default_java),
        repos_filter=list(args.repo),
        force=bool(args.force),
    )

    if not tasks:
        print("java-bytecode: nothing to build (all repos already have class files or no Java build files found)")
        return 0

    print(f"java-bytecode: tasks={len(tasks)} src={src_dir}")
    for task in tasks:
        print(f"  - {task.repo}: {task.build_system} jdk={task.java_version} ({task.reason})")

    if args.dry_run:
        return 0

    images: Dict[int, str] = {}
    failures: List[str] = []

    for task in tasks:
        try:
            if task.java_version not in images:
                images[task.java_version] = _ensure_builder_image(builder_dir, task.java_version)
            image = images[task.java_version]
        except RuntimeError as exc:
            failures.append(f"{task.repo}: {exc}")
            continue

        print(f"[build] {task.repo} ({task.build_system}, jdk={task.java_version})")
        completed = _run_build(task, image=image, src_dir=src_dir)
        if completed.returncode == 0:
            print(f"[ok] {task.repo}")
            continue

        failures.append(
            f"{task.repo}: exit={completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
        print(f"[fail] {task.repo} exit={completed.returncode}")

    if failures:
        print(f"java-bytecode: failures={len(failures)}")
        for item in failures:
            print(f"---\n{item}")
        if args.strict:
            return 1
    else:
        print("java-bytecode: all builds succeeded")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
