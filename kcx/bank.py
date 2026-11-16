"""Load and validate cert blueprints (certs/*.yaml) and question banks (questions/<cert>/*.yaml).

This module is fully implemented in Phase 0 because both the app and
scripts/validate_questions.py depend on it. See docs/QUESTION_FORMAT.md for the schema.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

OPTION_KEYS = ("A", "B", "C", "D")
DIFFICULTIES = ("easy", "medium", "hard")
REQUIRED_FIELDS = (
    "id", "domain", "topic", "difficulty", "question",
    "options", "answer", "explanation", "references",
)
# Options are shuffled at exam time, so positional phrasing is forbidden.
FORBIDDEN_OPTION_PHRASES = ("all of the above", "none of the above")


class BankError(Exception):
    """Raised when certs or questions fail validation. `errors` holds every problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s):\n" + "\n".join(errors))


@dataclass(frozen=True)
class Topic:
    id: str
    name: str


@dataclass(frozen=True)
class Domain:
    id: str
    abbr: str
    name: str
    weight: int
    topics: tuple[Topic, ...]

    @property
    def topic_ids(self) -> set[str]:
        return {t.id for t in self.topics}


@dataclass(frozen=True)
class Cert:
    id: str
    name: str
    duration_min: int
    question_count: int
    pass_pct: int
    domains: tuple[Domain, ...]
    last_verified: str = ""

    def domain(self, domain_id: str) -> Domain | None:
        return next((d for d in self.domains if d.id == domain_id), None)


@dataclass(frozen=True)
class Question:
    id: str
    cert: str
    domain: str
    topic: str
    difficulty: str
    question: str
    options: dict[str, str]
    answer: str
    explanation: str
    references: tuple[str, ...]
    source_file: str = ""


@dataclass
class Bank:
    certs: dict[str, Cert] = field(default_factory=dict)
    questions: dict[str, list[Question]] = field(default_factory=dict)  # cert id -> questions

    def by_id(self, cert_id: str) -> dict[str, Question]:
        return {q.id: q for q in self.questions.get(cert_id, [])}


# --------------------------------------------------------------------------- certs

def load_cert(path: Path) -> Cert:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    where = path.name

    for key in ("id", "name", "duration_min", "question_count", "pass_pct", "domains"):
        if key not in data:
            errors.append(f"{where}: missing '{key}'")
    if errors:
        raise BankError(errors)

    domains: list[Domain] = []
    seen_ids: set[str] = set()
    seen_abbr: set[str] = set()
    for raw in data["domains"]:
        did, abbr = raw.get("id"), raw.get("abbr")
        if not did or not abbr:
            errors.append(f"{where}: domain missing id/abbr: {raw!r}")
            continue
        if did in seen_ids:
            errors.append(f"{where}: duplicate domain id '{did}'")
        if abbr in seen_abbr:
            errors.append(f"{where}: duplicate domain abbr '{abbr}'")
        seen_ids.add(did)
        seen_abbr.add(abbr)
        topics = tuple(Topic(t["id"], t["name"]) for t in raw.get("topics", []))
        if not topics:
            errors.append(f"{where}: domain '{did}' has no topics")
        if len({t.id for t in topics}) != len(topics):
            errors.append(f"{where}: domain '{did}' has duplicate topic ids")
        domains.append(Domain(did, abbr, raw["name"], int(raw["weight"]), topics))

    total = sum(d.weight for d in domains)
    if total != 100:
        errors.append(f"{where}: domain weights sum to {total}, expected 100")
    if errors:
        raise BankError(errors)

    return Cert(
        id=data["id"],
        name=data["name"],
        duration_min=int(data["duration_min"]),
        question_count=int(data["question_count"]),
        pass_pct=int(data["pass_pct"]),
        domains=tuple(domains),
        last_verified=str(data.get("last_verified", "")),
    )


def load_certs(certs_dir: Path) -> dict[str, Cert]:
    certs: dict[str, Cert] = {}
    errors: list[str] = []
    for path in sorted(certs_dir.glob("*.yaml")):
        try:
            cert = load_cert(path)
        except BankError as exc:
            errors.extend(exc.errors)
            continue
        if cert.id in certs:
            errors.append(f"{path.name}: duplicate cert id '{cert.id}'")
        certs[cert.id] = cert
    if errors:
        raise BankError(errors)
    return certs


# ----------------------------------------------------------------------- questions

def _validate_question(raw: object, cert: Cert, where: str) -> tuple[Question | None, list[str]]:
    if not isinstance(raw, dict):
        return None, [f"{where}: entry is not a mapping"]
    qid = raw.get("id", "<no id>")
    loc = f"{where}:{qid}"
    errors: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        return None, [f"{loc}: missing field(s) {', '.join(missing)}"]

    domain = cert.domain(raw["domain"])
    if domain is None:
        errors.append(f"{loc}: unknown domain '{raw['domain']}' for cert '{cert.id}'")
    else:
        if raw["topic"] not in domain.topic_ids:
            errors.append(f"{loc}: unknown topic '{raw['topic']}' in domain '{domain.id}'")
        if not re.fullmatch(rf"{cert.id}-{domain.abbr}-\d{{3}}", str(qid)):
            errors.append(f"{loc}: id must match '{cert.id}-{domain.abbr}-NNN'")

    if raw["difficulty"] not in DIFFICULTIES:
        errors.append(f"{loc}: difficulty must be one of {DIFFICULTIES}")

    for key in ("question", "explanation"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            errors.append(f"{loc}: '{key}' must be a non-empty string")

    options = raw["options"]
    if not isinstance(options, dict) or tuple(sorted(options)) != OPTION_KEYS:
        errors.append(f"{loc}: options must have exactly the keys A, B, C, D")
        options = {}
    else:
        # YAML turns bare yes/no/true/numbers into non-strings; require explicit strings.
        for k, v in options.items():
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{loc}: option {k} must be a non-empty string (quote it in YAML)")
        texts = [str(v).strip().lower() for v in options.values()]
        if len(set(texts)) != len(texts):
            errors.append(f"{loc}: options must be distinct")
        for k, v in options.items():
            low = str(v).lower()
            if any(p in low for p in FORBIDDEN_OPTION_PHRASES):
                errors.append(f"{loc}: option {k} uses positional phrasing ('{v}'); options are shuffled")

    if raw["answer"] not in OPTION_KEYS:
        errors.append(f"{loc}: answer must be one of A, B, C, D")

    refs = raw["references"]
    if not isinstance(refs, list) or not refs:
        errors.append(f"{loc}: references must be a non-empty list")
        refs = []
    for ref in refs:
        if not isinstance(ref, str) or not ref.startswith("https://"):
            errors.append(f"{loc}: reference must be an https URL: {ref!r}")

    if errors:
        return None, errors
    return Question(
        id=str(qid),
        cert=cert.id,
        domain=raw["domain"],
        topic=raw["topic"],
        difficulty=raw["difficulty"],
        question=raw["question"].strip(),
        options={k: options[k].strip() for k in OPTION_KEYS},
        answer=raw["answer"],
        explanation=raw["explanation"].strip(),
        references=tuple(refs),
        source_file=where,
    ), []


def load_questions(cert: Cert, questions_dir: Path) -> list[Question]:
    """Load every *.yaml file under questions_dir for `cert`. Raises BankError on any problem."""
    questions: list[Question] = []
    errors: list[str] = []
    seen: dict[str, str] = {}

    for path in sorted(questions_dir.glob("*.yaml")):
        try:
            entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            errors.append(f"{path.name}: invalid YAML: {exc}")
            continue
        if not isinstance(entries, list):
            errors.append(f"{path.name}: top level must be a list of questions")
            continue
        for raw in entries:
            q, errs = _validate_question(raw, cert, path.name)
            errors.extend(errs)
            if q is None:
                continue
            if q.id in seen:
                errors.append(f"{path.name}:{q.id}: duplicate id (also in {seen[q.id]})")
                continue
            seen[q.id] = path.name
            questions.append(q)

    if errors:
        raise BankError(errors)
    return questions


def load_bank(base_dir: Path) -> Bank:
    """Load certs/ and questions/<cert>/ under base_dir. A cert with no question folder gets []."""
    certs = load_certs(base_dir / "certs")
    bank = Bank(certs=certs)
    errors: list[str] = []
    for cert_id, cert in certs.items():
        qdir = base_dir / "questions" / cert_id
        if not qdir.is_dir():
            bank.questions[cert_id] = []
            continue
        try:
            bank.questions[cert_id] = load_questions(cert, qdir)
        except BankError as exc:
            errors.extend(f"{cert_id}/{e}" for e in exc.errors)
    if errors:
        raise BankError(errors)
    return bank


# ------------------------------------------------------------------------ helpers

def allocate(weights: dict[str, int], total: int) -> dict[str, int]:
    """Split `total` across keys proportionally to `weights` using largest-remainder rounding.

    >>> allocate({"a": 44, "b": 28, "c": 16, "d": 12}, 60)
    {'a': 26, 'b': 17, 'c': 10, 'd': 7}
    """
    wsum = sum(weights.values())
    exact = {k: w * total / wsum for k, w in weights.items()}
    counts = {k: math.floor(v) for k, v in exact.items()}
    leftover = total - sum(counts.values())
    # Ties broken by original order (dicts preserve insertion order; sort is stable).
    for k in sorted(exact, key=lambda k: exact[k] - counts[k], reverse=True)[:leftover]:
        counts[k] += 1
    return counts


def coverage(cert: Cert, questions: list[Question]) -> dict[str, dict[str, int]]:
    """Return {domain_id: {topic_id: count}} including zero entries for every configured topic."""
    cov = {d.id: {t.id: 0 for t in d.topics} for d in cert.domains}
    for q in questions:
        cov[q.domain][q.topic] += 1
    return cov
