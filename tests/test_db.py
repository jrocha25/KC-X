from flask import g

from kcx import db


def test_journal_mode_is_wal(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_init_db_is_idempotent(app):
    db.init_db(app.config["DB_PATH"])
    db.init_db(app.config["DB_PATH"])


def test_create_get_and_list_attempt(conn):
    aid = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD"), ("q2", "DCBA")], duration_sec=60)
    attempt = db.get_attempt(conn, aid)
    assert attempt["cert"] == "kcna" and attempt["mode"] == "exam"
    assert attempt["duration_sec"] == 60 and attempt["submitted_at"] is None
    rows = db.get_attempt_questions(conn, aid)
    assert [(r["position"], r["question_id"], r["option_order"]) for r in rows] == [
        (1, "q1", "ABCD"), (2, "q2", "DCBA"),
    ]
    listed = db.list_attempts(conn)
    assert [a["id"] for a in listed] == [aid] and listed[0]["total"] == 2
    assert db.get_attempt(conn, aid + 1) is None


def test_list_attempts_newest_first(conn):
    first = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD")])
    second = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD")])
    assert [a["id"] for a in db.list_attempts(conn)] == [second, first]


def test_save_answer_round_trip(conn):
    aid = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD"), ("q2", "ABCD")])
    assert db.save_answer(conn, aid, 2, "C", True)
    row = db.get_attempt_questions(conn, aid)[1]
    assert row["selected"] == "C" and row["flagged"] == 1 and row["answered_at"]
    assert db.save_answer(conn, aid, 2, "C", False)
    assert db.get_attempt_questions(conn, aid)[1]["flagged"] == 0
    assert not db.save_answer(conn, aid, 9, "A", False)  # no such position


def test_save_answer_ignored_after_submit(conn):
    aid = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD")])
    with conn:
        conn.execute("UPDATE attempts SET submitted_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (aid,))
    assert not db.save_answer(conn, aid, 1, "A", True)
    row = db.get_attempt_questions(conn, aid)[0]
    assert row["selected"] is None and row["flagged"] == 0


def test_last_served_is_per_cert(conn):
    from datetime import datetime, timezone
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD"), ("q2", "ABCD")], started_at=t1)
    db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD")], started_at=t2)
    db.create_attempt(conn, "kcsa", "exam", [("s1", "ABCD")], started_at=t2)
    assert db.last_served(conn, "kcna") == {"q1": db.to_iso(t2), "q2": db.to_iso(t1)}


def test_delete_history_cascades(conn):
    db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD"), ("q2", "ABCD")])
    db.delete_history(conn)
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM attempt_questions").fetchone()[0] == 0


def test_get_db_is_cached_per_app_context_and_closed(app):
    with app.app_context():
        c1 = db.get_db()
        assert db.get_db() is c1
        assert g.db is c1
    # Teardown closed it: using it now fails.
    try:
        c1.execute("SELECT 1")
    except Exception as exc:  # sqlite3.ProgrammingError
        assert "closed" in str(exc)
    else:
        raise AssertionError("connection was not closed on teardown")
    with app.app_context():
        assert db.get_db() is not c1


def _submitted(conn, cert, marks, when):
    """A submitted attempt whose questions are marked {question_id: is_correct}."""
    aid = db.create_attempt(conn, cert, "exam", [(qid, "ABCD") for qid in marks])
    with conn:
        conn.execute("UPDATE attempts SET submitted_at = ? WHERE id = ?", (when, aid))
        for pos, ok in enumerate(marks.values(), start=1):
            conn.execute(
                "UPDATE attempt_questions SET is_correct = ? WHERE attempt_id = ? AND position = ?",
                (int(ok), aid, pos),
            )
    return aid


def test_mistakes_view(conn):
    _submitted(conn, "kcna", {"q1": False, "q2": False, "q3": True}, "2026-01-01T00:00:00+00:00")
    _submitted(conn, "kcsa", {"s1": False}, "2026-01-01T00:00:00+00:00")
    assert db.mistake_ids(conn, "kcna") == ["q1", "q2"]          # wrong or blank, per cert
    assert db.mistake_ids(conn, "kcsa") == ["s1"]

    # A later correct answer removes q1; a later wrong answer brings q3 in.
    _submitted(conn, "kcna", {"q1": True, "q3": False}, "2026-01-02T00:00:00+00:00")
    assert db.mistake_ids(conn, "kcna") == ["q2", "q3"]

    # An unsubmitted attempt (even with a correct answer saved) changes nothing.
    db.create_attempt(conn, "kcna", "mistakes", [("q2", "ABCD")])
    assert db.mistake_ids(conn, "kcna") == ["q2", "q3"]
