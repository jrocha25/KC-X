import shutil
from pathlib import Path

import pytest

from kcx import create_app, db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app(tmp_path):
    return create_app(base_dir=ROOT, db_path=tmp_path / "test.db")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_bank(app):
    return app.config["BANK"]


@pytest.fixture
def conn(app):
    c = db.connect(app.config["DB_PATH"])
    yield c
    c.close()


# An app whose KCSA cert has no questions, for "empty bank" behaviour. It copies the real certs
# and the KCNA bank; a cert with no question folder loads as [] (kcx.bank.load_bank).
@pytest.fixture
def empty_kcsa_app(tmp_path):
    base = tmp_path / "base"
    shutil.copytree(ROOT / "certs", base / "certs")
    shutil.copytree(ROOT / "questions" / "kcna", base / "questions" / "kcna")
    return create_app(base_dir=base, db_path=tmp_path / "empty.db")


@pytest.fixture
def empty_kcsa_client(empty_kcsa_app):
    return empty_kcsa_app.test_client()


@pytest.fixture
def empty_kcsa_bank(empty_kcsa_app):
    return empty_kcsa_app.config["BANK"]


@pytest.fixture
def empty_kcsa_conn(empty_kcsa_app):
    c = db.connect(empty_kcsa_app.config["DB_PATH"])
    yield c
    c.close()
