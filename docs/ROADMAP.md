# Roadmap

KC-X is built in small phases. Each phase ends with something you can run and check.

**Principles:**
- Simple and practical over pretty.
- Server-rendered pages.
- Everything runs with `docker compose up`.

Design details live in [ARCHITECTURE.md](ARCHITECTURE.md). Question rules are in [QUESTION_FORMAT.md](QUESTION_FORMAT.md).

| Phase | Goal | Status |
|---|---|---|
| 0 | Foundation: docs, skeleton, Docker, blueprints, 120 KCNA questions | ✅ Done |
| 1 | Data layer | ✅ Done |
| 2 | Full timed exam | ✅ Done |
| 3 | Results & history | ✅ Done |
| 4 | Domain drill | ✅ Done |
| 5 | Review mistakes | ✅ Done |
| 6 | KCSA question bank | ✅ Done |
| 7 | Quality & release v1.0 | 🟨 In progress |

---

## Phase 0: Foundation ✅
- [x] Docs: README, ROADMAP, ARCHITECTURE, QUESTION_FORMAT, EXAM_BLUEPRINTS, CONTRIBUTING, MIT license
- [x] `Dockerfile` (non-root, writable `/data`) and `compose.yaml` (named volume `kcx-data`)
- [x] `certs/kcna.yaml` and `certs/kcsa.yaml`, taken from the official LF pages
- [x] `kcx/bank.py`: loader and validator, `allocate()`, `coverage()`
- [x] `scripts/validate_questions.py` coverage report
- [x] 120 KCNA questions (52/34/20/14), validated, with every reference URL checked
- [x] Home page lists the certs, their blueprints and the question counts in the bank
- [x] `tests/test_bank.py`

**Acceptance:**
- `docker compose up --build` shows the home page.
- `validate_questions.py` prints `OK`.
- `pytest` passes.

## Phase 1: Data layer ✅
- [x] `db.get_db()` stores the connection on `flask.g`, and `close_db` runs on teardown
- [x] Small query helpers: `create_attempt`, `get_attempt`, `get_attempt_questions`, `save_answer`, `list_attempts`
- [x] Turn on `PRAGMA journal_mode=WAL` (gunicorn runs 2 workers)
- [x] Unit tests against a temp DB

**Acceptance:** helper tests pass, and the DB file survives `docker compose down && docker compose up`.

## Phase 2: Full timed exam ✅
- [x] `exam.build_exam()`: weighted per-domain sampling (`allocate`), least-recently-served first, topic round-robin, shuffled questions and options, saved in one transaction
- [x] `POST /exam/<cert>` starts an attempt
- [x] `GET/POST /attempt/<id>/q/<n>`: question page, radio options, flag checkbox, Prev/Next, question grid
- [x] `GET /attempt/<id>/review`: lists unanswered and flagged questions, with a Submit button
- [x] Server-side deadline, a JS countdown (display only), auto-submit at 0:00, auto-score on any request after the deadline
- [x] `exam.score_attempt()`, idempotent

**Acceptance:**
- A KCNA exam has exactly 60 questions split 26/17/10/7 across the domains.
- Refreshing the page keeps answers, flags, and the order of questions and options.
- Closing the tab past the deadline and reopening it shows a scored result.
- The exam is fully usable with JS disabled, apart from the live countdown.

## Phase 3: Results & history ✅
- [x] `GET /attempt/<id>/result` shows:
  - score %, pass/fail, and time used
  - every question with your answer, the correct answer, the explanation and the references
- [x] Past-attempts table on the home page (date, cert, mode, score, pass/fail), with links to results
- [x] Resume link for an unfinished attempt
- [x] `POST /history/clear`, with a confirm step

**Acceptance:** after submitting, every question shows its explanation, and old results stay viewable after a restart.

## Phase 4: Domain drill ✅
- [x] Form on the home page: pick domain and size (10, 20 or all) per cert; `POST /drill/<cert>`
- [x] `exam.build_drill()`: untimed (`duration_sec NULL`), reuses the same question, review and result pages
- [x] A size larger than the domain's pool is capped at the pool size (e.g. Cloud Native Architecture, 20 → 14)

**Acceptance:** a "Container Orchestration, 10" drill serves 10 questions, all from that domain, with no timer shown.

## Phase 5: Review mistakes ✅
- [x] `exam.build_mistakes()` builds an attempt from the `mistakes` view (latest submitted answer wrong or blank); `POST /mistakes/<cert>`
- [x] Questions no longer in the bank are left out of the pool, so it can always be emptied
- [x] The home page shows how many questions each cert currently has in the mistakes pool, and hides the button when the pool is empty

**Acceptance:**
- A question answered wrong in an exam appears in the pool.
- Answering it correctly in a mistakes session removes it from the pool.

## Phase 6: KCSA question bank ✅
- [x] Re-check the KCSA blueprint against the LF page, then update `last_verified` (unchanged on 2026-11-13)
- [x] Write 120 KCSA questions at twice the per-exam split: 16/26/26/20/20/12
- [x] Add `KCSA_TOPIC_TARGETS` to the tests; answer-key and longest-option checks now run for every cert

**Acceptance:**
- The validator reports `OK`.
- The home page shows KCSA as `ready`.
- A full KCSA exam can be taken.

## Phase 7: Quality & release
- [x] GitHub Actions: run the validator, `pytest` and `docker build` on each PR (`.github/workflows/ci.yml`)
- [x] Route tests with the Flask test client, covering the whole exam flow (`tests/test_routes.py`)
- [x] A CI job that checks reference URLs, allowed to fail without blocking (`scripts/check_links.py`)
- [x] Homelab deploy: slim `runtime` image target, GitLab CI pushes it to the private registry (`.gitlab-ci.yml`), compose in `deploy/` and gitops
- [x] Grow the KCNA bank to 180 questions, three times the per-exam split: 78/51/30/21
- [x] Grow the KCNA bank to 240 questions, four times the per-exam split: 104/68/40/28
- [ ] README screenshots
- [ ] Tag `v1.0.0`

## Backlog (not scheduled)
- Per-domain score breakdown on the result page
- Score trend over time, as a chart on the history page
- Practice mode with instant feedback after each question
- Multi-select questions
- Local profiles (several people on one install)
- Export and import history as JSON
- Keyboard shortcuts (1–4 to answer, F to flag, ←/→ to navigate)
