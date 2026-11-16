# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Style

- Before starting any non-trivial task, ask clarifying questions until you are ~95% confident you understand what I want.
- Do not guess at ambiguous requirements — ask instead of assuming.
- Only proceed without asking if the task is trivial or fully unambiguous.
- Always update readme.md, claude.md or other documentation at the end of tasks, if needed.
- at the end of a plan, always commit and push.
- when creating new questions, always make sure that they follow the same structure and style of the KCNA/KCSA.

## Commands (Docker only — Flask is not installed on the host)

The image copies code, questions and tests at build time (no bind mount), so pass `--build` after any edit or you will test stale files.

- Run app: `./kcx.sh start|stop|restart|status|logs|reset` (detached, rebuilds on start; `reset` wipes attempt history)
  or `docker compose up --build` → http://localhost:8080 (`docker compose down -v` wipes attempt history)
- Validate questions: `docker compose run --rm --build kcx python scripts/validate_questions.py [questions/kcna]`
- Tests: `docker compose run --rm --build kcx pytest` (single test: append `tests/test_bank.py::test_bank_matches_blueprint`)
- Link check (network): `docker compose run --rm kcx python scripts/check_links.py [questions/kcsa]`

## Question banks

- YAML in `questions/<cert>/<domain>.yaml` is the single source of truth (never stored in SQLite). The app refuses to start if any question is invalid. The full spec is in `docs/QUESTION_FORMAT.md`; use `/add-question` when writing questions.
- Ids are `<cert>-<abbr>-NNN` (abbr from `certs/<cert>.yaml`). Never renumber or reuse an id, because attempt history references ids. Retire a question by deleting it.
- `tests/test_bank.py` pins the exact per-topic counts (`KCNA_TOPIC_TARGETS` / `KCSA_TOPIC_TARGETS`); the bank size (KCNA 180 = 3x the exam, KCSA 120 = 2x) is derived from them. Growing a bank is allowed, but update the targets together with the topic counts in the YAML header and `docs/EXAM_BLUEPRINTS.md`.
- Tests also fail if any answer letter holds more than 40% of answers, or if the correct option is strictly the longest in more than 35% of questions.
- Never write content recalled from the real exam or from dumps (LF NDA). Every question cites official https docs. Use current Kubernetes only: PSA (not PSP), containerd/CRI-O, EndpointSlices, Gateway API.
- A new cert needs only `certs/<id>.yaml` plus a `questions/<id>/` folder, with no code changes. Domain weights must sum to 100. On curriculum changes, also update `docs/EXAM_BLUEPRINTS.md` and `last_verified`.

## Architecture rules

- Keep it simple: Jinja templates, stdlib `sqlite3` (no ORM), no front-end build step. Every form is POST-redirect-GET, and the app must work without JS.
- DB helpers in `kcx/db.py` take `conn` as the first argument so they work outside a Flask app context.
- The server is the authority on exam deadlines (`exam.GRACE_SEC`). `option_order` stores the shuffle, and `selected` stores the original option key.
- SQLite runs in WAL mode because gunicorn runs 2 workers.

## Conventions

- No formatter or linter is configured; match the surrounding style (`from __future__ import annotations`, `X | None` hints, frozen dataclasses, `# ---- section` dividers, ~120-char lines).
- Commit directly to `main`. When finishing a roadmap item, tick its checkbox in `docs/ROADMAP.md`.
