from __future__ import annotations

from flask import Flask

from .auth import bp as auth_bp
from .auth import ensure_csrf_token
from .config import Config
from .services.jobs import OperationQueue
from .views import bp as main_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    if not app.config.get("ADMIN_PASSWORD"):
        raise RuntimeError("ENV_PWD must be set before starting the web application.")

    app.config["SRC_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["RESULTS_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["RESULTS_NORMALIZED_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["ANALYSIS_OUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_TMP_DIR"].mkdir(parents=True, exist_ok=True)

    app.extensions["operation_queue"] = OperationQueue(
        history_limit=app.config["JOB_HISTORY_LIMIT"]
    )

    @app.context_processor
    def inject_template_globals() -> dict:
        return {
            "admin_username": app.config["ADMIN_USERNAME"],
            "csrf_token": ensure_csrf_token(),
        }

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    return app
