"""KC-X: local mock exam platform for CNCF KCNA / KCSA practice."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from . import config
from .bank import load_bank
from .db import close_db, init_db


def create_app(base_dir: Path | None = None, db_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    base_dir = base_dir or config.BASE_DIR
    db_path = db_path or config.DB_PATH

    # Fail fast: an invalid question bank stops the server with a readable error list.
    app.config["BANK"] = load_bank(base_dir)
    app.config["DB_PATH"] = db_path
    init_db(db_path)
    app.teardown_appcontext(close_db)

    from .routes import bp
    app.register_blueprint(bp)
    return app
