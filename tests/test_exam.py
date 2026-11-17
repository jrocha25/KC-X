import random
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from kcx import db, exam

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _qids(conn, aid):
    return [r["question_id"] for r in db.get_attempt_questions(conn, aid)]


def test_kcna_exam_shape(conn, app_bank):
    cert = app_bank.certs["kcna"]
    aid = exam.build_exam(conn, app_bank, cert, rng=random.Random(1))
    attempt = db.get_attempt(conn, aid)
    assert attempt["mode"] == "exam" and attempt["duration_sec"] == 90 * 60

    rows = db.get_attempt_questions(conn, aid)
    assert len(rows) == 60
    assert [r["position"] for r in rows] == list(range(1, 61))
    by_id = app_bank.by_id("kcna")
    per_domain = Counter(by_id[r["question_id"]].domain for r in rows)
    assert per_domain == {
        "k8s-fundamentals": 26, "container-orchestration": 17, "app-delivery": 10, "cn-architecture": 7,
    }
    assert len({r["question_id"] for r in rows}) == 60
    for r in rows:
        assert sorted(r["option_order"]) == list("ABCD")
        assert r["selected"] is None and r["flagged"] == 0


def test_exam_covers_every_topic(conn, app_bank):
    cert = app_bank.certs["kcna"]
    for seed in range(5):
        aid = exam.build_exam(conn, app_bank, cert, rng=random.Random(seed))
        by_id = app_bank.by_id("kcna")
        topics = {by_id[q].topic for q in _qids(conn, aid)}
        assert topics == {t.id for d in cert.domains for t in d.topics}
        db.delete_history(conn)


def test_consecutive_exams_do_not_repeat_and_fifth_reuses_oldest(conn, app_bank):
    cert = app_bank.certs["kcna"]
    rng = random.Random(7)
    attempts = [exam.build_exam(conn, app_bank, cert, rng=rng, now=T0 + timedelta(hours=h)) for h in range(5)]
    q1, q2, q3, q4, q5 = (set(_qids(conn, a)) for a in attempts)
    first_four = [q1, q2, q3, q4]
    # KCNA bank is 4x the exam: four exams, no repeats
    assert all(not (a & b) for i, a in enumerate(first_four) for b in first_four[i + 1:])
    assert q1 | q2 | q3 | q4 == {q.id for q in app_bank.questions["kcna"]}
    assert q5 == q1                             # least recently served come back first


def test_exam_order_is_shuffled(conn, app_bank):
    cert = app_bank.certs["kcna"]
    aid = exam.build_exam(conn, app_bank, cert, rng=random.Random(3))
    by_id = app_bank.by_id("kcna")
    domains = [by_id[q].domain for q in _qids(conn, aid)]
    assert domains != sorted(domains, key=[d.id for d in cert.domains].index)


def test_kcsa_exam_shape(conn, app_bank):
    cert = app_bank.certs["kcsa"]
    aid = exam.build_exam(conn, app_bank, cert, rng=random.Random(1))
    assert db.get_attempt(conn, aid)["duration_sec"] == 90 * 60
    qids = _qids(conn, aid)
    assert len(qids) == len(set(qids)) == 60
    by_id = app_bank.by_id("kcsa")
    assert Counter(by_id[q].domain for q in qids) == {
        "cn-security-overview": 8, "cluster-component-security": 13, "security-fundamentals": 13,
        "threat-model": 10, "platform-security": 10, "compliance-frameworks": 6,
    }


def test_empty_bank_raises(empty_kcsa_conn, empty_kcsa_bank):
    with pytest.raises(exam.ExamError, match="needs"):
        exam.build_exam(empty_kcsa_conn, empty_kcsa_bank, empty_kcsa_bank.certs["kcsa"])
    assert db.list_attempts(empty_kcsa_conn) == []


def _answer(conn, app_bank, aid, n_correct, n_wrong):
    """Answer the first n_correct questions right, the next n_wrong wrong, leave the rest blank."""
    by_id = app_bank.by_id("kcna")
    for row in db.get_attempt_questions(conn, aid):
        pos, q = row["position"], by_id[row["question_id"]]
        if pos <= n_correct:
            db.save_answer(conn, aid, pos, q.answer, False)
        elif pos <= n_correct + n_wrong:
            wrong = next(k for k in "ABCD" if k != q.answer)
            db.save_answer(conn, aid, pos, wrong, False)


def test_score_pass(conn, app_bank):
    aid = exam.build_exam(conn, app_bank, app_bank.certs["kcna"], rng=random.Random(1))
    _answer(conn, app_bank, aid, 45, 10)    # 45/60 = 75% (pass mark), 5 blank
    assert exam.score_attempt(conn, app_bank, aid, now=T0) == 75.0
    attempt = db.get_attempt(conn, aid)
    assert attempt["passed"] == 1 and attempt["submitted_at"] == db.to_iso(T0)
    marks = [r["is_correct"] for r in db.get_attempt_questions(conn, aid)]
    assert marks == [1] * 45 + [0] * 15


def test_score_fail_and_idempotent(conn, app_bank):
    aid = exam.build_exam(conn, app_bank, app_bank.certs["kcna"], rng=random.Random(1))
    _answer(conn, app_bank, aid, 44, 0)     # 73.3%
    score = exam.score_attempt(conn, app_bank, aid, now=T0)
    assert score == pytest.approx(100 * 44 / 60)
    assert db.get_attempt(conn, aid)["passed"] == 0

    # Second call: same score, submitted_at unchanged, later answers not saved.
    assert not db.save_answer(conn, aid, 60, "A", False)
    assert exam.score_attempt(conn, app_bank, aid, now=T0 + timedelta(hours=1)) == score
    assert db.get_attempt(conn, aid)["submitted_at"] == db.to_iso(T0)


def test_removed_question_scores_wrong(conn, app_bank):
    aid = db.create_attempt(conn, "kcna", "exam", [("kcna-kf-001", "ABCD"), ("kcna-kf-999", "ABCD")])
    db.save_answer(conn, aid, 1, "B", False)   # kcna-kf-001 answer is B
    db.save_answer(conn, aid, 2, "A", False)
    assert exam.score_attempt(conn, app_bank, aid) == 50.0


def test_timer_helpers(conn):
    aid = db.create_attempt(conn, "kcna", "exam", [("q1", "ABCD")], duration_sec=600, started_at=T0)
    a = db.get_attempt(conn, aid)
    assert exam.deadline(a) == T0 + timedelta(seconds=600)
    assert exam.remaining_sec(a, T0 + timedelta(seconds=100)) == 500
    assert exam.remaining_sec(a, T0 + timedelta(hours=1)) == 0
    assert not exam.is_expired(a, T0 + timedelta(seconds=599))
    assert exam.is_expired(a, T0 + timedelta(seconds=600))
    assert exam.accepts_answers(a, T0 + timedelta(seconds=600 + exam.GRACE_SEC))
    assert not exam.accepts_answers(a, T0 + timedelta(seconds=601 + exam.GRACE_SEC))

    untimed = db.get_attempt(conn, db.create_attempt(conn, "kcna", "drill", [("q1", "ABCD")]))
    assert exam.deadline(untimed) is None and exam.remaining_sec(untimed) is None
    assert not exam.is_expired(untimed) and exam.accepts_answers(untimed)


def test_finalize_if_expired(conn, app_bank):
    aid = db.create_attempt(conn, "kcna", "exam", [("kcna-kf-001", "ABCD")], duration_sec=60, started_at=T0)
    assert not exam.finalize_if_expired(conn, app_bank, db.get_attempt(conn, aid), T0 + timedelta(seconds=30))
    assert db.get_attempt(conn, aid)["submitted_at"] is None
    assert exam.finalize_if_expired(conn, app_bank, db.get_attempt(conn, aid), T0 + timedelta(seconds=61))
    assert db.get_attempt(conn, aid)["score_pct"] == 0.0


# --------------------------------------------------------------------------- drill

def test_drill_shape(conn, app_bank):
    cert = app_bank.certs["kcna"]
    aid = exam.build_drill(conn, app_bank, cert, "container-orchestration", 10, rng=random.Random(1))
    attempt = db.get_attempt(conn, aid)
    assert attempt["mode"] == "drill" and attempt["domain"] == "container-orchestration"
    assert attempt["duration_sec"] is None
    qids = _qids(conn, aid)
    by_id = app_bank.by_id("kcna")
    assert len(qids) == len(set(qids)) == 10
    assert {by_id[q].domain for q in qids} == {"container-orchestration"}


def test_drill_all_and_capped(conn, app_bank):
    cert = app_bank.certs["kcna"]
    pool = [q for q in app_bank.questions["kcna"] if q.domain == "container-orchestration"]
    aid = exam.build_drill(conn, app_bank, cert, "container-orchestration", None)
    assert sorted(_qids(conn, aid)) == sorted(q.id for q in pool)

    # Capping: every KCNA domain now has 20+ questions, so use KCSA's smallest domain.
    kcsa = app_bank.certs["kcsa"]
    small = sum(1 for q in app_bank.questions["kcsa"] if q.domain == "compliance-frameworks")
    assert small < 20
    aid = exam.build_drill(conn, app_bank, kcsa, "compliance-frameworks", 20)
    assert len(_qids(conn, aid)) == small


def test_drill_prefers_least_recently_served(conn, app_bank):
    cert = app_bank.certs["kcna"]
    rng = random.Random(2)
    a1 = exam.build_drill(conn, app_bank, cert, "container-orchestration", 10, rng=rng, now=T0)
    a2 = exam.build_drill(conn, app_bank, cert, "container-orchestration", 10, rng=rng,
                          now=T0 + timedelta(hours=1))
    assert not set(_qids(conn, a1)) & set(_qids(conn, a2))


def test_drill_errors(conn, app_bank):
    with pytest.raises(exam.ExamError, match="unknown domain"):
        exam.build_drill(conn, app_bank, app_bank.certs["kcna"], "nope", 10)
    assert db.list_attempts(conn) == []


def test_drill_empty_domain_raises(empty_kcsa_conn, empty_kcsa_bank):
    kcsa = empty_kcsa_bank.certs["kcsa"]
    with pytest.raises(exam.ExamError, match="no questions"):
        exam.build_drill(empty_kcsa_conn, empty_kcsa_bank, kcsa, kcsa.domains[0].id, 10)
    assert db.list_attempts(empty_kcsa_conn) == []


# ------------------------------------------------------------------------ mistakes

def test_mistakes_round_trip(conn, app_bank):
    cert = app_bank.certs["kcna"]
    with pytest.raises(exam.ExamError, match="empty"):
        exam.build_mistakes(conn, app_bank, cert)

    aid = exam.build_exam(conn, app_bank, cert, rng=random.Random(1))
    _answer(conn, app_bank, aid, 50, 5)     # 5 wrong, 5 blank
    exam.score_attempt(conn, app_bank, aid, now=T0)
    missed = {r["question_id"] for r in db.get_attempt_questions(conn, aid) if not r["is_correct"]}
    assert len(missed) == 10
    assert set(exam.mistakes_pool(conn, app_bank, cert)) == missed

    mid = exam.build_mistakes(conn, app_bank, cert, rng=random.Random(2), now=T0 + timedelta(hours=1))
    attempt = db.get_attempt(conn, mid)
    assert attempt["mode"] == "mistakes" and attempt["duration_sec"] is None
    assert set(_qids(conn, mid)) == missed

    # Answer all but one correctly: only that one stays in the pool.
    by_id = app_bank.by_id("kcna")
    rows = db.get_attempt_questions(conn, mid)
    for row in rows[1:]:
        db.save_answer(conn, mid, row["position"], by_id[row["question_id"]].answer, False)
    exam.score_attempt(conn, app_bank, mid, now=T0 + timedelta(hours=2))
    assert exam.mistakes_pool(conn, app_bank, cert) == [rows[0]["question_id"]]


def test_mistakes_pool_skips_removed_questions(conn, app_bank):
    cert = app_bank.certs["kcna"]
    aid = db.create_attempt(conn, "kcna", "exam", [("kcna-kf-001", "ABCD"), ("kcna-kf-999", "ABCD")])
    exam.score_attempt(conn, app_bank, aid)             # both unanswered -> wrong
    assert set(db.mistake_ids(conn, "kcna")) == {"kcna-kf-001", "kcna-kf-999"}
    assert exam.mistakes_pool(conn, app_bank, cert) == ["kcna-kf-001"]
    mid = exam.build_mistakes(conn, app_bank, cert)
    assert _qids(conn, mid) == ["kcna-kf-001"]
