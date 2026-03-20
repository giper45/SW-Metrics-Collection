from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path


class Config:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
    SRC_DIR = PROJECT_ROOT / "src"
    RESULTS_DIR = PROJECT_ROOT / "results"
    RESULTS_NORMALIZED_DIR = PROJECT_ROOT / "results_normalized"
    ANALYSIS_OUT_DIR = PROJECT_ROOT / "analysis_out"
    UPLOAD_TMP_DIR = PROJECT_ROOT / ".webapp_uploads"

    HOST = os.environ.get("MAVIS_WEB_HOST") or os.environ.get("MARS_WEB_HOST", "127.0.0.1")
    PORT = int(os.environ.get("MAVIS_WEB_PORT") or os.environ.get("MARS_WEB_PORT", "9999"))

    ADMIN_USERNAME = "swadmin"
    ADMIN_PASSWORD = os.environ.get("ENV_PWD")

    SECRET_KEY = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("APP_SECRET_KEY")
        or secrets.token_hex(32)
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    MAX_CONTENT_LENGTH = 512 * 1024 * 1024
    JOB_HISTORY_LIMIT = 50
