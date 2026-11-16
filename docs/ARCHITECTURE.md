# Architecture

KC-X is a small server-rendered Flask app with no front-end build step. JavaScript is used only for the exam countdown.

## Components

```
browser ──HTTP──▶ gunicorn ─▶ Flask app (kcx/)
                                ├── bank.py    certs/*.yaml + questions/<cert>/*.yaml → in-memory Bank (validated at boot)
                                ├── exam.py    build attempts, save answers, score
                                ├── db.py      SQLite connection + schema.sql
                                ├── routes.py  pages / forms
                                └── templates/ Jinja2 HTML, static/style.css
                                         │
                                         ▼
                                /data/kcx.db  (Docker named volume `kcx-data`)
```

| Module | Responsibility | Status |
|---|---|---|
| `kcx/bank.py` | Load and validate certs and questions. `allocate()` (largest-remainder split) and `coverage()` | Done (Phase 0) |
| `kcx/__init__.py` | `create_app()`: loads the bank (fails fast), initializes the DB, registers routes | Done (Phase 0) |
| `kcx/db.py` / `schema.sql` | SQLite schema (WAL mode), request-scoped connection (`get_db`/`close_db`), query helpers | Done (Phase 1) |
| `kcx/exam.py` | `build_exam`, `score_attempt`, deadline helpers; `build_drill`, `build_mistakes` | Done (Phases 2, 4, 5) |
| `kcx/routes.py` | Home + history, exam/drill/mistakes start, question/review/submit, result, clear history | Done (Phases 2–5) |
| `scripts/validate_questions.py` | CLI validator and coverage report | Done (Phase 0) |
| `scripts/check_links.py` | Checks every question reference URL is reachable (non-blocking CI job) | Done (Phase 7) |
| `.github/workflows/ci.yml` | CI: validator + `pytest`, `docker build`, link check | Done (Phase 7) |

Questions are **not** stored in SQLite. YAML is the single source of truth, kept in memory, and versioned in Git.
SQLite stores only attempts and answers, which reference questions by `id`.

## Data model

See [`kcx/schema.sql`](../kcx/schema.sql).

- **`attempts`:** one row per session.
  - `mode` is `exam`, `drill` or `mistakes`.
  - `domain` is set for drills.
  - `duration_sec` is NULL when the session is untimed.
  - `submitted_at` is NULL while the session is in progress.
  - `score_pct` and `passed` are set when the attempt is submitted.
- **`attempt_questions`:** one row per served question.
  - `position` is the display order.
  - `option_order` stores the shuffled order, for example `"CABD"` means display slot 1 shows original option C. A refresh shows the same order.
  - `selected` always stores the **original** option key, so scoring is a plain comparison with `answer`.
  - `flagged` holds the review flag.
  - `is_correct` is set on submit.
- **`mistakes` (view):** `(cert, question_id)` pairs whose most recent submitted answer was wrong or blank. A later correct answer removes the question from the view, so no extra bookkeeping is needed.

## Exam generation (Phase 2)

```
counts = allocate({domain: weight}, cert.question_count)   # KCNA → 26 / 17 / 10 / 7
for each domain:
    pool = bank questions in that domain
    order pool by "least recently served" (from attempt_questions), random tie-break
    within each recency bucket, round-robin across topics so no topic is skipped when possible
    pick the first counts[domain]
shuffle the full list
for each question: option_order = random permutation of "ABCD"
INSERT attempts + attempt_questions in a single transaction
```

- If a domain has fewer questions than its count, building the exam fails with a clear message. The home page already shows `ready` only when every domain has enough questions.
- **Drill:** one domain, `size` questions (10, 20, or all), untimed. Same least-recently-served / topic round-robin
  pick as the exam. A size larger than the domain's pool is capped at the pool size; an empty pool is an error.
- **Mistakes:** every question in the `mistakes` view for the cert, shuffled, untimed. Ids no longer in the bank
  are filtered out (they are stored as wrong and could never leave the pool). The home page shows the pool size
  and hides the button when it is 0.

## Exam flow and UX (Phases 2–3)

```
Home ─▶ POST /exam/kcna    ─▶ /attempt/7/q/1 ⇄ /attempt/7/q/n ─▶ /attempt/7/review ─▶ POST submit ─▶ /attempt/7/result
     ─▶ POST /drill/kcna   (form: domain, size=10|20|all)   ─▶ same pages, untimed
     ─▶ POST /mistakes/kcna                                  ─▶ same pages, untimed
```

**Question page:**
- The question text and four radio options, shown in `option_order`.
- A **Flag for review** checkbox.
- **Prev** and **Next** buttons.
- A grid of 1…N showing which questions are answered, unanswered or flagged. Every cell is a submit
  button (`go=<n>`) styled as a link, so jumping through the grid also saves the current answer.

**Forms and saving:**
- Every button is a `POST` that saves the current answer and flag, then redirects (POST-redirect-GET).
- The exam works without JavaScript, and a refresh never loses an answer.

**Review page:**
- Lists unanswered and flagged questions before the final submit.

**Result page:**
- Score %, pass/fail against `pass_pct`, and time taken.
- Every question shows your answer, the correct answer, the explanation and the reference links.

**Home page:**
- Per cert: **Start full exam** (only when `ready`), a **Domain drill** form (domain + size 10/20/all, shown
  when any domain has questions) and **Review mistakes (N)** (hidden when the pool is empty).
- Lists past attempts (date, mode, score, pass/fail) and a **Clear history** button.

## Timer (Phase 2)

- **Deadline:** the server is authoritative. `deadline = started_at + duration_sec`.
- **Countdown:** each question page embeds the remaining seconds, and a few lines of JS count down and display them.
- **At 0:00:** the JS submits the page's form with `go=submit`. On a question page that saves the
  current answer and then scores; on the review page it posts to `/attempt/<id>/submit`.
- **Late answers:**
  - The server accepts saves until `deadline + 5 s` (`exam.GRACE_SEC`), so the auto-submit isn't
    rejected because of latency. Later saves are ignored.
  - Order on every save: store the answer (if within grace), then score if expired, then navigate.
  - On any request to an expired, unsubmitted attempt, the server scores it automatically.
  - This covers closed tabs and disabled JS.
- **Untimed attempts:** drill and mistakes attempts have `duration_sec = NULL` and no timer.

## Scoring (Phase 2)

- `is_correct = (selected == question.answer)`. Unanswered questions count as wrong.
- `score_pct = 100 * correct / total`.
- `passed = score_pct >= cert.pass_pct`. Drills and mistakes attempts also show pass/fail, for information only.
- **Idempotent:** submitting twice returns the stored result.
- **Removed questions:** if a question id from an old attempt no longer exists in the bank, the result page shows "question removed" and keeps the stored correctness.

## Configuration

| Env var | Default (Docker) | Purpose |
|---|---|---|
| `KCX_DATA_DIR` | `/app` | Folder containing `certs/` and `questions/` |
| `KCX_DB_PATH` | `/data/kcx.db` | SQLite file (on the `kcx-data` volume) |

## Adding a certification

1. Add `certs/<id>.yaml` (same shape as `kcna.yaml`, with weights summing to 100).
2. Add questions under `questions/<id>/`.
3. Rebuild with `docker compose up --build`. No code changes are needed.
