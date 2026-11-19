# KC-X

A simple, self-hosted mock exam platform for the CNCF **KCNA** (Kubernetes and Cloud Native Associate) and **KCSA** (Kubernetes and Cloud Native Security Associate) certifications.

Clone it, run one command, and practice in your browser. Nothing leaves your machine.

> **Status:** Phases 0–6 are done. You can take a **full timed KCNA or KCSA mock exam** (60 questions, 90 minutes), drawn from a **300-question KCNA bank** or a **120-question KCSA bank**, drill **one domain at a time** (10, 20 or all questions, untimed), **retry your mistakes**, review flagged questions, see a scored result with explanations and references, and browse your history. CI (validator, tests, Docker build, link check) is in place; screenshots and the v1.0.0 tag come next. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Features (planned for v1.0)

- **Full timed exam:** 60 questions in 90 minutes, weighted by domain like the real exam. Pass mark 75%.
- **Question grid:** jump between questions, flag them for review, and change answers before submitting.
- **Result page:** the correct answer, an explanation and links to official docs for every question.
- **Domain drill:** practice one domain at a time, untimed.
- **Review mistakes:** retry the questions you got wrong last time.
- **History:** saved locally in SQLite.
- **Multi-cert:** each certification is defined by a small YAML blueprint.

## Quick start

Requires Docker with Compose.

```bash
git clone <this repo> kc-x && cd kc-x
./kcx.sh start
```

Then open <http://localhost:8080>. The server runs in the background; `./kcx.sh stop` stops it.
(Plain `docker compose up --build` works too if you prefer it.)

| Task | Command |
|---|---|
| Stop | `./kcx.sh stop` (your history is kept in the `kcx-data` volume) |
| Restart after edits (rebuilds) | `./kcx.sh restart` |
| Is it running? | `./kcx.sh status` |
| Follow server logs | `./kcx.sh logs` |
| Wipe history | `./kcx.sh reset` (asks first) |
| Validate questions | `docker compose run --rm kcx python scripts/validate_questions.py` |
| Run tests | `docker compose run --rm kcx pytest` |
| Check reference links | `docker compose run --rm kcx python scripts/check_links.py` |

After editing questions or code, run `./kcx.sh restart` so the image is rebuilt.

## Deploy (homelab)

The Dockerfile has two targets. `runtime` is the default (last) stage: the app only, no pytest or tests.
`test` adds those, and the local `compose.yaml` uses it.

- **Build:** GitLab CI (`.gitlab-ci.yml`) builds `runtime` with podman and pushes it to the private registry.
  A push to `main` that changes the image sources builds `reg.joao-rocha.com/kcx:latest`.
  A git tag (e.g. `1.0.0`) builds `:1.0.0` and moves `:latest`. The pipeline runs in the `gitlab` remote
  (`personal-projects/kc-x`), which needs the group's `REGISTRY`, `REGISTRY_USER` and `REGISTRY_PASSWORD` variables.
- **Run:** `deploy/docker-compose.yaml` is the generic compose file (named volume, port 3350).
  The live copy for the Unraid server is `docker/rockinator/kcx.yaml` in the gitops repo.
  It bind-mounts `/mnt/user/appdata/kcx/data`, which must be owned by the container user first:

  ```bash
  mkdir -p /mnt/user/appdata/kcx/data && chown 1000:1000 /mnt/user/appdata/kcx/data
  docker compose -f kcx.yaml pull && docker compose -f kcx.yaml up -d
  ```

KC-X has no authentication, and anyone who can reach it can wipe the history. Publish it on the LAN only.

## Exam coverage

| Cert | Domains (weight) | Questions in bank |
|---|---|---|
| KCNA | Kubernetes Fundamentals (44%) · Container Orchestration (28%) · Cloud Native Application Delivery (16%) · Cloud Native Architecture (12%) | 300 |
| KCSA | Overview of Cloud Native Security (14%) · Cluster Component Security (22%) · Security Fundamentals (22%) · Threat Model (16%) · Platform Security (16%) · Compliance and Security Frameworks (10%) | 120 |

Sources and details are in [docs/EXAM_BLUEPRINTS.md](docs/EXAM_BLUEPRINTS.md).

## Project layout

```
certs/          exam blueprints (domains, weights, topics, timing)
questions/      question banks: questions/<cert>/<domain>.yaml
kcx/            Flask app (bank loader, exam engine, routes, templates)
scripts/        validate_questions.py, check_links.py
tests/          pytest suite
docs/           roadmap, architecture, question format, blueprints
kcx.sh          start/stop helper (wraps docker compose)
deploy/         homelab compose file (runs the registry image)
.github/        CI workflow (validator, pytest, docker build, links)
.gitlab-ci.yml  image build and push to the private registry
```

## Documentation

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Question format & style guide](docs/QUESTION_FORMAT.md)
- [Exam blueprints & sources](docs/EXAM_BLUEPRINTS.md)
- [Contributing](CONTRIBUTING.md)

## Disclaimer

KC-X is an independent study tool. It is **not affiliated with, endorsed by, or sponsored by** the Cloud Native Computing Foundation (CNCF) or The Linux Foundation. KCNA and KCSA are their certifications.

All questions are original and written from public documentation. They are **not** real exam questions. Sharing real exam content breaks the certification NDA, and contributions of that kind will be rejected.

Passing these mock exams does not guarantee passing the real ones.

## License

[MIT](LICENSE)
