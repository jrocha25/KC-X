"""SQLite helpers. Schema lives in schema.sql.

Query helpers take a connection as their first argument, so exam.py and tests can use
them without a Flask app context. Routes get a request-scoped connection from get_db().
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """One timestamp format everywhere, so string ordering matches time ordering."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create the database file and apply schema.sql (idempotent)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        # WAL lets the two gunicorn workers read while one writes. The mode is stored
        # in the file, so setting it once at startup is enough.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------- request-scoped connection

def get_db() -> sqlite3.Connection:
    """One connection per app context (i.e. per request), closed by close_db on teardown."""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# ---------------------------------------------------------------------- query helpers

def create_attempt(
    conn: sqlite3.Connection,
    cert: str,
    mode: str,
    items: list[tuple[str, str]],
    duration_sec: int | None = None,
    domain: str | None = None,
    started_at: datetime | None = None,
) -> int:
    """Insert an attempt and its questions in one transaction.

    `items` is the display order: [(question_id, option_order), ...].
    """
    started = to_iso(started_at or utcnow())
    with conn:
        cur = conn.execute(
            "INSERT INTO attempts (cert, mode, domain, started_at, duration_sec) VALUES (?, ?, ?, ?, ?)",
            (cert, mode, domain, started, duration_sec),
        )
        attempt_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO attempt_questions (attempt_id, position, question_id, option_order) VALUES (?, ?, ?, ?)",
            [(attempt_id, pos, qid, order) for pos, (qid, order) in enumerate(items, start=1)],
        )
    return attempt_id


def get_attempt(conn: sqlite3.Connection, attempt_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()


def get_attempt_questions(conn: sqlite3.Connection, attempt_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM attempt_questions WHERE attempt_id = ? ORDER BY position", (attempt_id,)
    ).fetchall()


def save_answer(
    conn: sqlite3.Connection,
    attempt_id: int,
    position: int,
    selected: str | None,
    flagged: bool,
    now: datetime | None = None,
) -> bool:
    """Store the answer and flag for one question. Does nothing once the attempt is submitted.

    Returns True if a row was updated.
    """
    answered_at = to_iso(now or utcnow()) if selected else None
    with conn:
        cur = conn.execute(
            """
            UPDATE attempt_questions
               SET selected = ?, flagged = ?, answered_at = COALESCE(?, answered_at)
             WHERE attempt_id = ? AND position = ?
               AND EXISTS (SELECT 1 FROM attempts WHERE id = ? AND submitted_at IS NULL)
            """,
            (selected, int(bool(flagged)), answered_at, attempt_id, position, attempt_id),
        )
    return cur.rowcount > 0


def list_attempts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All attempts, newest first, with their question counts."""
    return conn.execute(
        """
        SELECT a.*, COUNT(aq.position) AS total
          FROM attempts a
          LEFT JOIN attempt_questions aq ON aq.attempt_id = a.id
         GROUP BY a.id
         ORDER BY a.started_at DESC, a.id DESC
        """
    ).fetchall()


def last_served(conn: sqlite3.Connection, cert: str) -> dict[str, str]:
    """{question_id: ISO timestamp of the most recent attempt that served it} for one cert."""
    rows = conn.execute(
        """
        SELECT aq.question_id, MAX(a.started_at) AS last
          FROM attempt_questions aq
          JOIN attempts a ON a.id = aq.attempt_id
         WHERE a.cert = ?
         GROUP BY aq.question_id
        """,
        (cert,),
    ).fetchall()
    return {r["question_id"]: r["last"] for r in rows}


def mistake_ids(conn: sqlite3.Connection, cert: str) -> list[str]:
    """Question ids in the `mistakes` view for one cert (latest submitted answer wrong or blank)."""
    rows = conn.execute(
        "SELECT question_id FROM mistakes WHERE cert = ? ORDER BY question_id", (cert,)
    ).fetchall()
    return [r["question_id"] for r in rows]


def delete_history(conn: sqlite3.Connection) -> None:
    """Delete every attempt; attempt_questions rows go with them (ON DELETE CASCADE)."""
    with conn:
        conn.execute("DELETE FROM attempts")
