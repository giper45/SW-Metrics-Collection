from __future__ import annotations

from functools import partial
from pathlib import Path
import uuid

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .auth import csrf_protect, login_required
from .services.makefile import (
    discover_make_targets,
    group_targets,
    parse_env_overrides,
    run_make_target,
    target_lookup,
)
from .services.results import (
    build_insights_overview,
    build_metrics_view,
    build_vulnerability_view,
    format_number,
    load_result_rows,
    metric_badge,
    severity_badge,
    source_label,
    tool_badge,
    tool_label,
)
from .services.repositories import (
    clean_repositories,
    clone_repositories,
    delete_repository,
    import_archives,
    list_repositories,
    parse_clone_specs,
    sanitize_repository_name,
)


bp = Blueprint("main", __name__)

STATUS_CLASSES = {
    "queued": "secondary",
    "running": "warning",
    "succeeded": "success",
    "failed": "danger",
}
QUICK_ACTION_NAMES = ("collect-all", "case-study", "experiment")
WORKFLOW_STEPS = (
    ("Prepare", "Preparation", ("prepare-java-bytecode",)),
    ("Software Metrics", "Software Metrics", ("collect-size-all", "collect-complexity-all", "collect-coupling-all", "collect-cohesion-all", "collect-paper-extras")),
    ("Vulnerability Metrics", "Vulnerabilities", ("collect-vulnerability-all",)),
    ("Normalize", "Analysis", ("normalize",)),
    ("Analyze", "Analysis", ("agreement", "dataset")),
    ("Report", "Analysis", ("report",)),
)


def _queue():
    return current_app.extensions["operation_queue"]


def _all_targets():
    return discover_make_targets(current_app.config["MAKEFILE_PATH"])


def _result_rows():
    return load_result_rows(
        current_app.config["RESULTS_DIR"],
        current_app.config["RESULTS_NORMALIZED_DIR"],
    )


def _wants_json_response() -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and (
        request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def _queue_success_response(message: str, *, job_ids: list[str]) -> tuple:
    if _wants_json_response():
        return (
            jsonify(
                {
                    "status": "queued",
                    "message": message,
                    "job_ids": job_ids,
                    "job_count": len(job_ids),
                    "job_detail_url": url_for("main.job_detail", job_id=job_ids[0]) if job_ids else "",
                    "jobs_url": url_for("main.job_list"),
                }
            ),
            200,
        )
    flash(message, "success")
    return redirect(url_for("main.job_detail", job_id=job_ids[0]))


def _queue_error_response(message: str, status_code: int = 400):
    if _wants_json_response():
        return jsonify({"status": "error", "message": message}), status_code
    flash(message, "danger")
    return redirect(url_for("main.dashboard"))


def _job_summary(jobs: list[dict]) -> dict[str, int | str | bool]:
    counts = {status: 0 for status in STATUS_CLASSES}
    for job in jobs:
        status = str(job.get("status", "")).strip()
        if status in counts:
            counts[status] += 1
    active = counts["queued"] + counts["running"]
    return {
        **counts,
        "active": active,
        "has_active": active > 0,
        "pulse_label": "Active" if active > 0 else "Idle",
    }


def _workflow_items(targets: list) -> list[dict]:
    lookup = target_lookup(targets)
    items: list[dict] = []
    for label, category, target_names in WORKFLOW_STEPS:
        resolved_targets = [lookup[name] for name in target_names if name in lookup]
        items.append(
            {
                "label": label,
                "category": category,
                "targets": resolved_targets,
            }
        )
    return items


def _queue_target_message(targets: list) -> str:
    labels = [target.display_name for target in targets]
    if not labels:
        return "Queued command."
    if len(labels) == 1:
        return f"Queued {labels[0]}."
    if len(labels) <= 3:
        return f"Queued {len(labels)} commands: {', '.join(labels)}."
    preview = ", ".join(labels[:3])
    return f"Queued {len(labels)} commands: {preview}, +{len(labels) - 3} more."


def _preparation_targets(targets: list) -> list:
    return [target for target in targets if target.category == "Preparation"]


def _quick_actions(targets: list) -> list:
    lookup = target_lookup(targets)
    return [lookup[name] for name in QUICK_ACTION_NAMES if name in lookup]


def _advanced_sections(targets: list) -> list[tuple[str, list]]:
    quick_action_names = {target.name for target in _quick_actions(targets)}
    sections = []
    for category, items in group_targets(targets):
        if category == "Preparation":
            continue
        filtered = [target for target in items if target.name not in quick_action_names]
        if filtered:
            sections.append((category, filtered))
    return sections


@bp.route("/")
@login_required
def dashboard():
    jobs = _queue().recent(limit=10)
    targets = _all_targets()
    summary = _job_summary(jobs)
    refresh_seconds = 5 if summary["has_active"] else None
    return render_template(
        "dashboard/index.html",
        grouped_targets=group_targets(targets),
        preparation_targets=_preparation_targets(targets),
        quick_actions=_quick_actions(targets),
        advanced_sections=_advanced_sections(targets),
        workflow_items=_workflow_items(targets),
        jobs=jobs,
        job_summary=summary,
        repositories=list_repositories(current_app.config["SRC_DIR"]),
        refresh_seconds=refresh_seconds,
        status_classes=STATUS_CLASSES,
    )


@bp.route("/insights")
@login_required
def insights_overview():
    rows = _result_rows()
    overview = build_insights_overview(rows)
    return render_template(
        "insights/index.html",
        overview=overview,
        source_label=source_label,
        format_number=format_number,
    )


@bp.route("/insights/vulnerabilities")
@login_required
def insights_vulnerabilities():
    rows = _result_rows()
    view_data = build_vulnerability_view(
        rows,
        {
            "source": request.args.get("source", ""),
            "project": request.args.get("project", ""),
            "tool": request.args.get("tool", ""),
            "run_id": request.args.get("run_id", ""),
            "component": request.args.get("component", ""),
            "severity": request.args.get("severity", ""),
            "search": request.args.get("search", ""),
        },
        src_dir=current_app.config["SRC_DIR"],
    )
    return render_template(
        "insights/vulnerabilities.html",
        view_data=view_data,
        severity_badge=severity_badge,
        source_label=source_label,
        tool_badge=tool_badge,
        tool_label=tool_label,
        format_number=format_number,
        severity_order=("critical", "high", "medium", "low", "info", "unknown"),
    )


@bp.route("/insights/metrics")
@login_required
def insights_metrics():
    rows = _result_rows()
    view_data = build_metrics_view(
        rows,
        {
            "source": request.args.get("source", ""),
            "project": request.args.get("project", ""),
            "metric": request.args.get("metric", ""),
            "tool": request.args.get("tool", ""),
            "component_type": request.args.get("component_type", ""),
            "run_id": request.args.get("run_id", ""),
            "status": request.args.get("status", ""),
            "search": request.args.get("search", ""),
        },
    )
    return render_template(
        "insights/metrics.html",
        view_data=view_data,
        metric_badge=metric_badge,
        source_label=source_label,
        tool_badge=tool_badge,
        tool_label=tool_label,
        format_number=format_number,
    )


@bp.route("/jobs")
@login_required
def job_list():
    return render_template(
        "dashboard/jobs.html",
        jobs=_queue().recent(limit=current_app.config["JOB_HISTORY_LIMIT"]),
        status_classes=STATUS_CLASSES,
    )


@bp.route("/jobs/<job_id>")
@login_required
def job_detail(job_id: str):
    job = _queue().get_snapshot(job_id)
    if not job:
        abort(404)
    refresh_seconds = 3 if job["status"] in {"queued", "running"} else None
    return render_template(
        "dashboard/job_detail.html",
        job=job,
        refresh_seconds=refresh_seconds,
        status_classes=STATUS_CLASSES,
    )


@bp.route("/targets/run", methods=["POST"])
@login_required
@csrf_protect
def run_target():
    target_name = request.form.get("target", "").strip()
    available_targets = target_lookup(_all_targets())
    target = available_targets.get(target_name)
    if target is None:
        return _queue_error_response("Unknown Makefile target.", status_code=400)

    try:
        env_overrides = parse_env_overrides(request.form.get("env_overrides", ""))
    except ValueError as exc:
        return _queue_error_response(str(exc), status_code=400)

    job = _queue().enqueue(
        kind="make",
        label=f"Run {target.display_name}",
        handler=partial(
            run_make_target,
            project_root=current_app.config["PROJECT_ROOT"],
            target_name=target_name,
            env_overrides=env_overrides,
        ),
    )
    return _queue_success_response(
        _queue_target_message([target]),
        job_ids=[job.id],
    )


@bp.route("/targets/run-selected", methods=["POST"])
@login_required
@csrf_protect
def run_selected_targets():
    available_targets = target_lookup(_all_targets())
    selected_names = [name.strip() for name in request.form.getlist("targets") if name.strip()]
    if not selected_names:
        return _queue_error_response("Choose at least one target to queue.", status_code=400)

    invalid = [name for name in selected_names if name not in available_targets]
    if invalid:
        return _queue_error_response("Unknown Makefile target.", status_code=400)

    try:
        env_overrides = parse_env_overrides(request.form.get("env_overrides", ""))
    except ValueError as exc:
        return _queue_error_response(str(exc), status_code=400)

    queued_jobs = []
    selected_targets = [available_targets[target_name] for target_name in selected_names]
    for target_name in selected_names:
        target = available_targets[target_name]
        job = _queue().enqueue(
            kind="make",
            label=f"Run {target.display_name}",
            handler=partial(
                run_make_target,
                project_root=current_app.config["PROJECT_ROOT"],
                target_name=target_name,
                env_overrides=env_overrides,
            ),
        )
        queued_jobs.append(job)

    return _queue_success_response(
        _queue_target_message(selected_targets),
        job_ids=[job.id for job in queued_jobs],
    )


@bp.route("/repositories/clone", methods=["POST"])
@login_required
@csrf_protect
def clone_repositories_route():
    try:
        clone_specs = parse_clone_specs(request.form.get("clone_specs", ""))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.dashboard"))

    replace_existing = request.form.get("replace_existing") == "1"
    job = _queue().enqueue(
        kind="repositories",
        label=f"Clone {len(clone_specs)} repositories",
        handler=partial(
            clone_repositories,
            src_dir=current_app.config["SRC_DIR"],
            specs=clone_specs,
            replace_existing=replace_existing,
        ),
    )
    flash("Repository clone batch queued.", "success")
    return redirect(url_for("main.job_detail", job_id=job.id))


@bp.route("/repositories/upload", methods=["POST"])
@login_required
@csrf_protect
def upload_archives_route():
    uploaded_files = [item for item in request.files.getlist("zip_files") if item.filename]
    if not uploaded_files:
        flash("Choose at least one .zip archive to upload.", "danger")
        return redirect(url_for("main.dashboard"))

    upload_tmp_dir = current_app.config["UPLOAD_TMP_DIR"]
    request_upload_dir = upload_tmp_dir / uuid.uuid4().hex
    request_upload_dir.mkdir(parents=True, exist_ok=True)
    archive_paths: list[Path] = []
    for uploaded_file in uploaded_files:
        safe_name = Path(uploaded_file.filename).name
        archive_path = request_upload_dir / safe_name
        uploaded_file.save(archive_path)
        archive_paths.append(archive_path)

    replace_existing = request.form.get("replace_existing") == "1"
    job = _queue().enqueue(
        kind="repositories",
        label=f"Import {len(archive_paths)} archive(s)",
        handler=partial(
            import_archives,
            src_dir=current_app.config["SRC_DIR"],
            archive_paths=archive_paths,
            replace_existing=replace_existing,
        ),
    )
    flash("Zip import queued.", "success")
    return redirect(url_for("main.job_detail", job_id=job.id))


@bp.route("/repositories/clean", methods=["POST"])
@login_required
@csrf_protect
def clean_repositories_route():
    job = _queue().enqueue(
        kind="repositories",
        label="Clean repository folder",
        handler=partial(
            clean_repositories,
            src_dir=current_app.config["SRC_DIR"],
        ),
    )
    flash("Repository clean-up queued.", "success")
    return redirect(url_for("main.job_detail", job_id=job.id))


@bp.route("/repositories/<repository_name>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_repository_route(repository_name: str):
    try:
        safe_name = sanitize_repository_name(repository_name)
    except ValueError:
        abort(400, description="Invalid repository name.")

    job = _queue().enqueue(
        kind="repositories",
        label=f"Delete repository {safe_name}",
        handler=partial(
            delete_repository,
            src_dir=current_app.config["SRC_DIR"],
            repository_name=safe_name,
        ),
    )
    flash(f"Delete job queued for '{safe_name}'.", "success")
    return redirect(url_for("main.job_detail", job_id=job.id))


@bp.route("/healthz")
def healthz():
    return {"status": "ok"}
