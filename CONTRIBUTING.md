# Contributing

Thanks for helping. The most valuable contributions are **accurate, original questions** and fixes to existing ones.

## Ground rules

1. **No real exam content.** Never submit questions recalled from the actual KCNA or KCSA exam, or copied from exam dumps or paid practice tests. This breaks the Linux Foundation NDA and copyright, and such PRs will be closed.
2. **Every question needs a source.** Explanations must be backed by official docs, linked in `references`.
3. **Keep it current.** Write for the latest Kubernetes minor version and the current curriculum ([docs/EXAM_BLUEPRINTS.md](docs/EXAM_BLUEPRINTS.md)).

## Adding or fixing questions

1. Read [docs/QUESTION_FORMAT.md](docs/QUESTION_FORMAT.md).
2. Edit the right file under `questions/<cert>/`. Give a new question the next free id for its domain, and never reuse an old id.
3. Validate and test:
   ```bash
   docker compose run --rm --build kcx python scripts/validate_questions.py
   docker compose run --rm kcx pytest
   docker compose run --rm kcx python scripts/check_links.py   # optional, needs network
   ```
4. Answer your own question cold: read only the question and options, then check that exactly one option is defensibly correct.
5. Open a PR. Say which domain and topic it covers, and paste the validator's coverage table if counts changed.

### Reporting a wrong answer

Open an issue that includes:
- the question `id`
- what you believe is correct
- a link to official docs

## Code changes

- Follow the phase you're working on in [docs/ROADMAP.md](docs/ROADMAP.md), and tick its checkboxes in your PR.
- Keep it simple:
  - server-rendered Jinja templates
  - standard-library `sqlite3`
  - no front-end build step
  - minimal JS
- Add or update tests in `tests/`.

## PR checklist

- [ ] `scripts/validate_questions.py` prints `OK`
- [ ] `pytest` passes
- [ ] `./kcx.sh start` (or `docker compose up --build`) starts and the home page loads
- [ ] Docs updated if behaviour or formats changed
