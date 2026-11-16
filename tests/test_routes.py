import re
from datetime import timedelta

from kcx import db


def _start(client):
    resp = client.post("/exam/kcna")
    assert resp.status_code == 302
    m = re.search(r"/attempt/(\d+)/q/1$", resp.headers["Location"])
    assert m, resp.headers["Location"]
    return int(m.group(1))


def _rows(conn, aid):
    return db.get_attempt_questions(conn, aid)


def _shift_start(conn, aid, seconds_ago):
    started = db.to_iso(db.utcnow() - timedelta(seconds=seconds_ago))
    with conn:
        conn.execute("UPDATE attempts SET started_at = ? WHERE id = ?", (started, aid))


def _radio_values(html):
    return re.findall(r'name="choice" value="([A-D])"', html)


def test_full_exam_flow(client, conn, app_bank):
    aid = _start(client)
    by_id = app_bank.by_id("kcna")

    page = client.get(f"/attempt/{aid}/q/1")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "question <strong>1</strong> of 60" in html
    assert 'id="timer" data-remaining="' in html
    order = _radio_values(html)
    assert "".join(order) == _rows(conn, aid)[0]["option_order"]

    # Answer q1 correctly via Next: redirect to q2 and it's stored.
    q1 = by_id[_rows(conn, aid)[0]["question_id"]]
    resp = client.post(f"/attempt/{aid}/q/1", data={"choice": q1.answer, "go": "next"})
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/q/2")
    assert _rows(conn, aid)[0]["selected"] == q1.answer

    # Refresh keeps the answer checked and the same option order.
    html = client.get(f"/attempt/{aid}/q/1").get_data(as_text=True)
    assert f'value="{q1.answer}" checked' in html
    assert _radio_values(html) == order

    # Flag q2 without answering, jump via the grid to q10; that also saves.
    resp = client.post(f"/attempt/{aid}/q/2", data={"flag": "1", "go": "10"})
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/q/10")
    assert _rows(conn, aid)[1]["flagged"] == 1

    # Answer q10 wrong, Prev goes to q9.
    q10 = by_id[_rows(conn, aid)[9]["question_id"]]
    wrong = next(k for k in "ABCD" if k != q10.answer)
    resp = client.post(f"/attempt/{aid}/q/10", data={"choice": wrong, "go": "prev"})
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/q/9")

    # Next on the last question goes to review.
    resp = client.post(f"/attempt/{aid}/q/60", data={"go": "next"})
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/review")

    review = client.get(f"/attempt/{aid}/review").get_data(as_text=True)
    assert "Unanswered (58)" in review and "Flagged (1)" in review
    assert f'href="/attempt/{aid}/q/2"' in review

    # Result isn't available before submitting.
    resp = client.get(f"/attempt/{aid}/result")
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/review")

    resp = client.post(f"/attempt/{aid}/submit")
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/result")
    result = client.get(f"/attempt/{aid}/result").get_data(as_text=True)
    assert "FAIL" in result and "1 of 60 correct" in result
    assert q1.explanation.split()[0] in result and q1.references[0] in result
    assert "Unanswered" in result and "Wrong" in result

    # A submitted attempt can't be changed and its pages lead to the result.
    client.post(f"/attempt/{aid}/q/3", data={"choice": "A", "go": "next"})
    assert _rows(conn, aid)[2]["selected"] is None
    assert client.get(f"/attempt/{aid}/q/1").headers["Location"].endswith("/result")
    assert client.post(f"/attempt/{aid}/submit").status_code == 302  # idempotent


def test_go_submit_saves_then_scores(client, conn, app_bank):
    aid = _start(client)
    q1 = app_bank.by_id("kcna")[_rows(conn, aid)[0]["question_id"]]
    resp = client.post(f"/attempt/{aid}/q/1", data={"choice": q1.answer, "go": "submit"})
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/result")
    assert _rows(conn, aid)[0]["is_correct"] == 1


def test_expired_attempt_is_scored_on_any_request(client, conn):
    aid = _start(client)
    client.post(f"/attempt/{aid}/q/1", data={"choice": "A", "go": "next"})
    _shift_start(conn, aid, 2 * 3600)

    resp = client.get(f"/attempt/{aid}/q/1")
    assert resp.headers["Location"].endswith(f"/attempt/{aid}/result")
    attempt = db.get_attempt(conn, aid)
    assert attempt["submitted_at"] is not None and attempt["score_pct"] is not None

    resp = client.post(f"/attempt/{aid}/q/2", data={"choice": "B", "go": "next"})
    assert resp.headers["Location"].endswith("/result")
    assert _rows(conn, aid)[1]["selected"] is None
    assert client.get(f"/attempt/{aid}/result").status_code == 200


def test_expired_unsubmitted_result_page_scores(client, conn):
    aid = _start(client)
    _shift_start(conn, aid, 2 * 3600)
    resp = client.get(f"/attempt/{aid}/result")
    assert resp.status_code == 200 and "0.0%" in resp.get_data(as_text=True)


def test_answer_within_grace_is_saved_then_scored(client, conn):
    aid = _start(client)
    _shift_start(conn, aid, 90 * 60 + 2)          # deadline was ~2 s ago
    resp = client.post(f"/attempt/{aid}/q/1", data={"choice": "C", "go": "submit"})
    assert resp.headers["Location"].endswith("/result")
    row = _rows(conn, aid)[0]
    assert row["selected"] == "C" and row["is_correct"] is not None


def test_answer_after_grace_is_ignored(client, conn):
    aid = _start(client)
    _shift_start(conn, aid, 90 * 60 + 10)         # deadline was ~10 s ago
    resp = client.post(f"/attempt/{aid}/q/1", data={"choice": "C", "go": "submit"})
    assert resp.headers["Location"].endswith("/result")
    row = _rows(conn, aid)[0]
    assert row["selected"] is None and row["is_correct"] == 0


def test_removed_question_shown_on_result(client, conn):
    aid = db.create_attempt(conn, "kcna", "exam", [("kcna-kf-001", "ABCD"), ("kcna-kf-998", "ABCD")])
    html = client.get(f"/attempt/{aid}/q/2").get_data(as_text=True)
    assert "was removed" in html
    client.post(f"/attempt/{aid}/submit")
    html = client.get(f"/attempt/{aid}/result").get_data(as_text=True)
    assert "Question removed" in html and "kcna-kf-998" in html


def test_bad_requests(client, empty_kcsa_client):
    assert client.post("/exam/nope").status_code == 404
    assert empty_kcsa_client.post("/exam/kcsa").status_code == 400      # empty bank
    assert client.get("/attempt/999/q/1").status_code == 404
    aid = _start(client)
    assert client.get(f"/attempt/{aid}/q/0").status_code == 404
    assert client.get(f"/attempt/{aid}/q/61").status_code == 404
    assert client.post(f"/attempt/{aid}/q/1", data={"choice": "E"}).status_code == 400
    assert client.post(f"/attempt/{aid}/q/1", data={"go": "99"}).status_code == 400


def test_home_lists_history_and_resume(client, conn):
    html = client.get("/").get_data(as_text=True)
    assert "No attempts yet" in html and 'action="/exam/kcna"' in html

    open_id = _start(client)
    done_id = _start(client)
    client.post(f"/attempt/{done_id}/submit")
    html = client.get("/").get_data(as_text=True)
    assert f'href="/attempt/{open_id}/q/1">Resume' in html
    assert f'href="/attempt/{done_id}/result">View result' in html

    # An expired open attempt shows as scored on the home page.
    _shift_start(conn, open_id, 2 * 3600)
    html = client.get("/").get_data(as_text=True)
    assert "Resume" not in html
    assert f'href="/attempt/{open_id}/result"' in html


def test_clear_history(client, conn):
    _start(client)
    page = client.get("/history/clear")
    assert page.status_code == 200 and "delete" in page.get_data(as_text=True)
    assert db.list_attempts(conn)                               # GET alone deletes nothing
    resp = client.post("/history/clear")
    assert resp.status_code == 302
    assert db.list_attempts(conn) == []
    assert "No attempts yet" in client.get("/").get_data(as_text=True)


def test_home_shows_both_certs_ready(client, empty_kcsa_client):
    html = client.get("/").get_data(as_text=True)
    assert html.count('<span class="ok">ready</span>') == 2
    assert 'action="/exam/kcna"' in html and 'action="/exam/kcsa"' in html
    empty = empty_kcsa_client.get("/").get_data(as_text=True)
    assert empty.count('<span class="ok">ready</span>') == 1
    assert 'action="/exam/kcsa"' not in empty                  # not ready


def test_kcsa_exam_starts(client, conn):
    resp = client.post("/exam/kcsa")
    assert resp.status_code == 302
    aid = int(re.search(r"/attempt/(\d+)/q/1$", resp.headers["Location"]).group(1))
    assert db.get_attempt(conn, aid)["cert"] == "kcsa"
    html = client.get(f"/attempt/{aid}/q/1").get_data(as_text=True)
    assert "question <strong>1</strong> of 60" in html and 'id="timer"' in html


def test_history_survives_app_restart(tmp_path):
    from pathlib import Path

    from kcx import create_app

    root = Path(__file__).resolve().parent.parent
    path = tmp_path / "persist.db"
    c1 = create_app(base_dir=root, db_path=path).test_client()
    aid = _start(c1)
    c1.post(f"/attempt/{aid}/submit")
    c2 = create_app(base_dir=root, db_path=path).test_client()
    assert c2.get(f"/attempt/{aid}/result").status_code == 200


# ------------------------------------------------------------------- drill / mistakes

def _start_at(client, path, data=None):
    resp = client.post(path, data=data or {})
    assert resp.status_code == 302, resp.get_data(as_text=True)
    m = re.search(r"/attempt/(\d+)/q/1$", resp.headers["Location"])
    assert m, resp.headers["Location"]
    return int(m.group(1))


def test_drill_flow(client, conn, app_bank):
    aid = _start_at(client, "/drill/kcna", {"domain": "container-orchestration", "size": "10"})
    rows = _rows(conn, aid)
    by_id = app_bank.by_id("kcna")
    assert len(rows) == 10
    assert {by_id[r["question_id"]].domain for r in rows} == {"container-orchestration"}

    html = client.get(f"/attempt/{aid}/q/1").get_data(as_text=True)
    assert "question <strong>1</strong> of 10" in html
    assert "drill: Container Orchestration" in html
    assert 'id="timer"' not in html and "timer.js" not in html
    assert 'id="timer"' not in client.get(f"/attempt/{aid}/review").get_data(as_text=True)

    client.post(f"/attempt/{aid}/submit")
    result = client.get(f"/attempt/{aid}/result").get_data(as_text=True)
    assert "0 of 10 correct" in result and "drill: Container Orchestration" in result


def test_drill_bad_requests(client, conn):
    assert client.post("/drill/nope", data={"domain": "x", "size": "10"}).status_code == 404
    assert client.post("/drill/kcna", data={"domain": "container-orchestration", "size": "15"}).status_code == 400
    assert client.post("/drill/kcna", data={"domain": "nope", "size": "10"}).status_code == 400
    assert client.post("/drill/kcna", data={"size": "10"}).status_code == 400
    assert db.list_attempts(conn) == []


def test_drill_empty_bank_rejected(empty_kcsa_client, empty_kcsa_conn):
    resp = empty_kcsa_client.post("/drill/kcsa", data={"domain": "cn-security-overview", "size": "all"})
    assert resp.status_code == 400
    assert db.list_attempts(empty_kcsa_conn) == []


def test_home_drill_form(client, empty_kcsa_client):
    html = client.get("/").get_data(as_text=True)
    assert 'action="/drill/kcna"' in html and 'action="/drill/kcsa"' in html
    assert "Phases 4" not in html
    empty = empty_kcsa_client.get("/").get_data(as_text=True)
    assert 'action="/drill/kcsa"' not in empty                 # empty bank


def test_mistakes_flow(client, conn, app_bank):
    html = client.get("/").get_data(as_text=True)
    assert 'action="/mistakes/kcna"' not in html               # pool empty
    assert client.post("/mistakes/kcna").status_code == 400
    assert client.post("/mistakes/nope").status_code == 404

    # A 2-question exam answered wrong and blank puts both questions in the pool.
    aid = db.create_attempt(conn, "kcna", "exam", [("kcna-kf-001", "ABCD"), ("kcna-kf-002", "ABCD")])
    wrong = next(k for k in "ABCD" if k != app_bank.by_id("kcna")["kcna-kf-001"].answer)
    client.post(f"/attempt/{aid}/q/1", data={"choice": wrong, "go": "submit"})
    html = client.get("/").get_data(as_text=True)
    assert 'action="/mistakes/kcna"' in html and "Review mistakes (2)" in html

    # Answering one correctly in a mistakes session removes it from the pool.
    mid = _start_at(client, "/mistakes/kcna")
    rows = _rows(conn, mid)
    assert {r["question_id"] for r in rows} == {"kcna-kf-001", "kcna-kf-002"}
    assert 'id="timer"' not in client.get(f"/attempt/{mid}/q/1").get_data(as_text=True)
    right = app_bank.by_id("kcna")[rows[0]["question_id"]].answer
    client.post(f"/attempt/{mid}/q/1", data={"choice": right, "go": "submit"})
    assert "Review mistakes (1)" in client.get("/").get_data(as_text=True)
