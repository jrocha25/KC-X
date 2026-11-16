"""Exam engine: build attempts, track the deadline, score.

Algorithm reference: docs/ARCHITECTURE.md ("Exam generation", "Scoring", "Timer").
Three attempt modes: build_exam (timed), build_drill and build_mistakes (both untimed).
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

from . import db
from .bank import Bank, Cert, Question, allocate

# Saves are accepted this long after the deadline, so the JS auto-submit at 0:00
# (which posts the current page's answer) is not rejected by network latency.
GRACE_SEC = 5


class ExamError(ValueError):
    """An attempt can't be built, e.g. the bank has too few questions for a domain."""


# ------------------------------------------------------------------------- building

def _pick(pool: list[Question], n: int, served: dict[str, str], rng: random.Random) -> list[Question]:
    """Choose n questions: least recently served first, round-robin across topics.

    Never-served questions sort first ("" < any timestamp). Within one recency bucket,
    each question gets a rank inside its topic, so the first pick of every topic comes
    before the second pick of any topic. The initial shuffle breaks remaining ties.
    """
    pool = list(pool)
    rng.shuffle(pool)
    seen: Counter[tuple[str, str]] = Counter()
    rank: dict[str, int] = {}
    for q in sorted(pool, key=lambda q: served.get(q.id, "")):  # stable: keeps the shuffle
        key = (served.get(q.id, ""), q.topic)
        rank[q.id] = seen[key]
        seen[key] += 1
    pool.sort(key=lambda q: (served.get(q.id, ""), rank[q.id]))
    return pool[:n]


def _option_order(rng: random.Random) -> str:
    return "".join(rng.sample("ABCD", 4))


def build_exam(
    conn: sqlite3.Connection,
    bank: Bank,
    cert: Cert,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> int:
    """Create a full timed attempt and return its id. Everything is stored up front, so a
    refresh or a server restart resumes the same questions in the same order."""
    rng = rng or random.Random()
    counts = allocate({d.id: d.weight for d in cert.domains}, cert.question_count)
    questions = bank.questions.get(cert.id, [])
    served = db.last_served(conn, cert.id)

    chosen: list[Question] = []
    for domain in cert.domains:
        pool = [q for q in questions if q.domain == domain.id]
        need = counts[domain.id]
        if len(pool) < need:
            raise ExamError(
                f"{cert.name}: domain '{domain.name}' needs {need} questions, the bank has {len(pool)}"
            )
        chosen.extend(_pick(pool, need, served, rng))

    rng.shuffle(chosen)
    return db.create_attempt(
        conn, cert.id, "exam", _items(chosen, rng), duration_sec=cert.duration_min * 60, started_at=now
    )


def _items(questions: list[Question], rng: random.Random) -> list[tuple[str, str]]:
    return [(q.id, _option_order(rng)) for q in questions]


def build_drill(
    conn: sqlite3.Connection,
    bank: Bank,
    cert: Cert,
    domain_id: str,
    size: int | None,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> int:
    """Create an untimed attempt from one domain and return its id.

    `size` None means every question in the domain. A size larger than the domain's pool
    is capped at the pool size, so a 20-question drill of a 14-question domain serves 14.
    """
    rng = rng or random.Random()
    domain = cert.domain(domain_id)
    if domain is None:
        raise ExamError(f"{cert.name}: unknown domain '{domain_id}'")
    pool = [q for q in bank.questions.get(cert.id, []) if q.domain == domain.id]
    if not pool:
        raise ExamError(f"{cert.name}: domain '{domain.name}' has no questions in the bank")

    n = len(pool) if size is None else min(size, len(pool))
    chosen = _pick(pool, n, db.last_served(conn, cert.id), rng)
    rng.shuffle(chosen)
    return db.create_attempt(conn, cert.id, "drill", _items(chosen, rng), domain=domain.id, started_at=now)


def mistakes_pool(conn: sqlite3.Connection, bank: Bank, cert: Cert) -> list[str]:
    """Question ids in the mistakes pool that still exist in the bank.

    Removed questions are stored as wrong and could never be answered correctly again,
    so they are left out; otherwise the pool would never empty.
    """
    by_id = bank.by_id(cert.id)
    return [qid for qid in db.mistake_ids(conn, cert.id) if qid in by_id]


def build_mistakes(
    conn: sqlite3.Connection,
    bank: Bank,
    cert: Cert,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> int:
    """Create an untimed attempt from every question in the cert's mistakes pool."""
    rng = rng or random.Random()
    by_id = bank.by_id(cert.id)
    chosen = [by_id[qid] for qid in mistakes_pool(conn, bank, cert)]
    if not chosen:
        raise ExamError(f"{cert.name}: the mistakes pool is empty")
    rng.shuffle(chosen)
    return db.create_attempt(conn, cert.id, "mistakes", _items(chosen, rng), started_at=now)


# ---------------------------------------------------------------------------- timer

def deadline(attempt: sqlite3.Row) -> datetime | None:
    if attempt["duration_sec"] is None:
        return None
    return db.from_iso(attempt["started_at"]) + timedelta(seconds=attempt["duration_sec"])


def remaining_sec(attempt: sqlite3.Row, now: datetime | None = None) -> int | None:
    end = deadline(attempt)
    if end is None:
        return None
    # Rounded up, so the JS countdown never reaches 0:00 before the real deadline.
    return max(0, math.ceil((end - (now or db.utcnow())).total_seconds()))


def is_expired(attempt: sqlite3.Row, now: datetime | None = None) -> bool:
    end = deadline(attempt)
    return end is not None and (now or db.utcnow()) >= end


def accepts_answers(attempt: sqlite3.Row, now: datetime | None = None) -> bool:
    """True while answers may be saved: not submitted, and not past deadline + grace."""
    if attempt["submitted_at"] is not None:
        return False
    end = deadline(attempt)
    return end is None or (now or db.utcnow()) <= end + timedelta(seconds=GRACE_SEC)


# -------------------------------------------------------------------------- scoring

def score_attempt(
    conn: sqlite3.Connection, bank: Bank, attempt_id: int, now: datetime | None = None
) -> float:
    """Score and submit an attempt. Unanswered questions, and questions no longer in the
    bank, count as wrong. Idempotent: an already submitted attempt keeps its stored score.

    The first statement claims the attempt (submitted_at IS NULL -> now) and takes the
    write lock, so two gunicorn workers can't both score it.
    """
    with conn:
        claimed = conn.execute(
            "UPDATE attempts SET submitted_at = ? WHERE id = ? AND submitted_at IS NULL",
            (db.to_iso(now or db.utcnow()), attempt_id),
        ).rowcount
        attempt = db.get_attempt(conn, attempt_id)
        if attempt is None:
            raise ExamError(f"attempt {attempt_id} does not exist")
        if not claimed:
            return attempt["score_pct"]

        cert = bank.certs.get(attempt["cert"])
        by_id = bank.by_id(attempt["cert"])
        rows = db.get_attempt_questions(conn, attempt_id)
        correct = 0
        for row in rows:
            q = by_id.get(row["question_id"])
            ok = q is not None and row["selected"] == q.answer
            correct += ok
            conn.execute(
                "UPDATE attempt_questions SET is_correct = ? WHERE attempt_id = ? AND position = ?",
                (int(ok), attempt_id, row["position"]),
            )
        score = 100 * correct / len(rows) if rows else 0.0
        passed = cert is not None and score >= cert.pass_pct
        conn.execute(
            "UPDATE attempts SET score_pct = ?, passed = ? WHERE id = ?",
            (score, int(passed), attempt_id),
        )
    return score


def finalize_if_expired(
    conn: sqlite3.Connection, bank: Bank, attempt: sqlite3.Row, now: datetime | None = None
) -> bool:
    """Score an unsubmitted attempt whose deadline has passed. Returns True if it is (now) submitted."""
    if attempt["submitted_at"] is not None:
        return True
    if is_expired(attempt, now):
        score_attempt(conn, bank, attempt["id"], now)
        return True
    return False
