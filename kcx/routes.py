"""HTTP routes. Every form is a plain POST followed by a redirect, so the app works without JS."""
from __future__ import annotations

import sqlite3

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from . import db, exam
from .bank import OPTION_KEYS, Bank, allocate

bp = Blueprint("kcx", __name__)


def _bank() -> Bank:
    return current_app.config["BANK"]


def _load(attempt_id: int) -> tuple[sqlite3.Connection, sqlite3.Row]:
    conn = db.get_db()
    attempt = db.get_attempt(conn, attempt_id)
    if attempt is None:
        abort(404)
    return conn, attempt


def _to_result(attempt_id: int):
    return redirect(url_for("kcx.result", attempt_id=attempt_id))


def _to_question(attempt_id: int, n: int):
    return redirect(url_for("kcx.question", attempt_id=attempt_id, n=n))


# ------------------------------------------------------------------- template filters

@bp.app_template_filter("when")
def _fmt_when(iso: str | None) -> str:
    return db.from_iso(iso).strftime("%Y-%m-%d %H:%M UTC") if iso else ""


@bp.app_template_filter("clock")
def _fmt_clock(seconds: int | float | None) -> str:
    if seconds is None:
        return ""
    s = max(0, int(seconds))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ------------------------------------------------------------------------------ home

@bp.get("/")
def home():
    bank = _bank()
    conn = db.get_db()

    # Expired attempts left open (closed tab, no JS) get scored before they are listed.
    attempts = db.list_attempts(conn)
    open_rows = [a for a in attempts if a["submitted_at"] is None]
    if any([exam.finalize_if_expired(conn, bank, a) for a in open_rows]):
        attempts = db.list_attempts(conn)

    certs = []
    for cert in bank.certs.values():
        questions = bank.questions.get(cert.id, [])
        per_exam = allocate({d.id: d.weight for d in cert.domains}, cert.question_count)
        have = {d.id: sum(1 for q in questions if q.domain == d.id) for d in cert.domains}
        certs.append({
            "cert": cert,
            "count": len(questions),
            "ready": all(have[d] >= n for d, n in per_exam.items()),
            "per_exam": per_exam,
            "have": have,
            "drill_domains": [d for d in cert.domains if have[d.id]],
            "mistakes": len(exam.mistakes_pool(conn, bank, cert)),
        })
    return render_template("home.html", certs=certs, attempts=attempts, cert_names={
        c.id: c.name for c in bank.certs.values()
    })


# ------------------------------------------------------------------------ start exam

DRILL_SIZES = {"10": 10, "20": 20, "all": None}


def _start(cert_id: str, build):
    """Look up the cert (404 if unknown), build the attempt (400 on ExamError), go to q/1."""
    bank = _bank()
    cert = bank.certs.get(cert_id)
    if cert is None:
        abort(404)
    try:
        attempt_id = build(db.get_db(), bank, cert)
    except exam.ExamError as exc:
        abort(400, description=str(exc))
    return _to_question(attempt_id, 1)


@bp.post("/exam/<cert_id>")
def start_exam(cert_id: str):
    return _start(cert_id, exam.build_exam)


@bp.post("/drill/<cert_id>")
def start_drill(cert_id: str):
    size_key = request.form.get("size", "10")
    if size_key not in DRILL_SIZES:
        abort(400, description="invalid drill size")
    domain_id = request.form.get("domain", "")
    return _start(
        cert_id,
        lambda conn, bank, cert: exam.build_drill(conn, bank, cert, domain_id, DRILL_SIZES[size_key]),
    )


@bp.post("/mistakes/<cert_id>")
def start_mistakes(cert_id: str):
    return _start(cert_id, exam.build_mistakes)


# -------------------------------------------------------------------------- questions

@bp.get("/attempt/<int:attempt_id>/q/<int:n>")
def question(attempt_id: int, n: int):
    bank = _bank()
    conn, attempt = _load(attempt_id)
    if exam.finalize_if_expired(conn, bank, attempt):
        return _to_result(attempt_id)
    rows = db.get_attempt_questions(conn, attempt_id)
    if not 1 <= n <= len(rows):
        abort(404)
    row = rows[n - 1]
    q = bank.by_id(attempt["cert"]).get(row["question_id"])
    options = [(key, q.options[key]) for key in row["option_order"]] if q else []
    return render_template(
        "question.html",
        attempt=attempt,
        rows=rows,
        n=n,
        row=row,
        q=q,
        options=options,
        remaining=exam.remaining_sec(attempt),
        cert=bank.certs.get(attempt["cert"]),
    )


@bp.post("/attempt/<int:attempt_id>/q/<int:n>")
def save_question(attempt_id: int, n: int):
    bank = _bank()
    conn, attempt = _load(attempt_id)
    rows = db.get_attempt_questions(conn, attempt_id)
    if not 1 <= n <= len(rows):
        abort(404)
    choice = request.form.get("choice") or None
    if choice is not None and choice not in OPTION_KEYS:
        abort(400, description="invalid choice")

    now = db.utcnow()
    # 1. Save (allowed until deadline + grace). 2. Score if the time is up. 3. Navigate.
    if exam.accepts_answers(attempt, now):
        db.save_answer(conn, attempt_id, n, choice, "flag" in request.form, now)
    if exam.finalize_if_expired(conn, bank, attempt, now):
        return _to_result(attempt_id)

    go = request.form.get("go", "next")
    total = len(rows)
    if go == "prev":
        return _to_question(attempt_id, max(1, n - 1))
    if go == "next":
        if n == total:
            return redirect(url_for("kcx.review", attempt_id=attempt_id))
        return _to_question(attempt_id, n + 1)
    if go == "review":
        return redirect(url_for("kcx.review", attempt_id=attempt_id))
    if go == "submit":
        exam.score_attempt(conn, bank, attempt_id, now)
        return _to_result(attempt_id)
    if go.isdigit() and 1 <= int(go) <= total:
        return _to_question(attempt_id, int(go))
    abort(400, description="invalid navigation")


# ---------------------------------------------------------------------- review/submit

@bp.get("/attempt/<int:attempt_id>/review")
def review(attempt_id: int):
    bank = _bank()
    conn, attempt = _load(attempt_id)
    if exam.finalize_if_expired(conn, bank, attempt):
        return _to_result(attempt_id)
    rows = db.get_attempt_questions(conn, attempt_id)
    return render_template(
        "review.html",
        attempt=attempt,
        rows=rows,
        unanswered=[r for r in rows if r["selected"] is None],
        flagged=[r for r in rows if r["flagged"]],
        remaining=exam.remaining_sec(attempt),
        cert=bank.certs.get(attempt["cert"]),
    )


@bp.post("/attempt/<int:attempt_id>/submit")
def submit(attempt_id: int):
    conn, _ = _load(attempt_id)
    exam.score_attempt(conn, _bank(), attempt_id)
    return _to_result(attempt_id)


# ----------------------------------------------------------------------------- result

@bp.get("/attempt/<int:attempt_id>/result")
def result(attempt_id: int):
    bank = _bank()
    conn, attempt = _load(attempt_id)
    if attempt["submitted_at"] is None:
        if not exam.finalize_if_expired(conn, bank, attempt):
            return redirect(url_for("kcx.review", attempt_id=attempt_id))
        attempt = db.get_attempt(conn, attempt_id)

    by_id = bank.by_id(attempt["cert"])
    items = []
    for row in db.get_attempt_questions(conn, attempt_id):
        q = by_id.get(row["question_id"])
        options = [(key, q.options[key]) for key in row["option_order"]] if q else []
        items.append({"row": row, "q": q, "options": options})

    used = (db.from_iso(attempt["submitted_at"]) - db.from_iso(attempt["started_at"])).total_seconds()
    if attempt["duration_sec"] is not None:
        used = min(used, attempt["duration_sec"])
    return render_template(
        "result.html",
        attempt=attempt,
        items=items,
        correct=sum(1 for i in items if i["row"]["is_correct"]),
        time_used=used,
        cert=bank.certs.get(attempt["cert"]),
    )


# ---------------------------------------------------------------------------- history

@bp.get("/history/clear")
def confirm_clear():
    return render_template("confirm_clear.html", count=len(db.list_attempts(db.get_db())))


@bp.post("/history/clear")
def clear_history():
    db.delete_history(db.get_db())
    return redirect(url_for("kcx.home"))
