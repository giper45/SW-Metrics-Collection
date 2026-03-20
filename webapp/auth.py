from __future__ import annotations

import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


bp = Blueprint("auth", __name__)


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def _is_valid_csrf_token(submitted_token: str | None) -> bool:
    expected_token = session.get("_csrf_token")
    if not expected_token or not submitted_token:
        return False
    return secrets.compare_digest(expected_token, submitted_token)


def csrf_protect(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not _is_valid_csrf_token(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token.")
        return view(*args, **kwargs)

    return wrapped_view


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped_view


def _safe_redirect_target(target: str | None) -> str:
    if not target:
        return url_for("main.dashboard")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return url_for("main.dashboard")
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("main.dashboard"))

    next_url = request.args.get("next") or request.form.get("next")

    if request.method == "POST":
        if not _is_valid_csrf_token(request.form.get("csrf_token")):
            abort(400, description="Invalid CSRF token.")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        expected_username = current_app.config["ADMIN_USERNAME"]
        expected_password = current_app.config["ADMIN_PASSWORD"]

        if (
            username != expected_username
            or not secrets.compare_digest(password, expected_password)
        ):
            flash("Invalid username or password.", "danger")
        else:
            session.clear()
            session["authenticated"] = True
            session["username"] = expected_username
            session.permanent = True
            ensure_csrf_token()
            return redirect(_safe_redirect_target(next_url))

    return render_template("auth/login.html", next_url=_safe_redirect_target(next_url))


@bp.route("/logout", methods=["POST"])
@login_required
@csrf_protect
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
