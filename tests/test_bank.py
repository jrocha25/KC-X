from pathlib import Path

import pytest
import yaml

from kcx import create_app
from kcx.bank import BankError, allocate, coverage, load_bank, load_cert, load_questions

ROOT = Path(__file__).resolve().parent.parent

# Planned KCNA bank: exactly 3x the per-exam allocation, 78/51/30/21 (see docs/EXAM_BLUEPRINTS.md).
KCNA_TOPIC_TARGETS = {
    "k8s-fundamentals": {"core-concepts": 27, "administration": 17, "scheduling": 16, "containerization": 18},
    "container-orchestration": {"networking": 15, "security": 14, "troubleshooting": 10, "storage": 12},
    "app-delivery": {"application-delivery": 20, "debugging": 10},
    "cn-architecture": {"observability": 9, "ecosystem-principles": 8, "community-collaboration": 4},
}

# Planned KCSA bank: exactly 2x the per-exam allocation (16/26/26/20/20/12).
KCSA_TOPIC_TARGETS = {
    "cn-security-overview": {
        "four-cs": 3, "cloud-provider-infra": 2, "controls-frameworks": 2, "isolation-techniques": 3,
        "artifact-image-security": 3, "workload-code-security": 3,
    },
    "cluster-component-security": {
        "api-server": 4, "controller-manager": 2, "scheduler": 2, "kubelet": 3, "container-runtime": 2,
        "kube-proxy": 2, "pod": 2, "etcd": 3, "container-networking": 2, "client-security": 2, "storage": 2,
    },
    "security-fundamentals": {
        "pod-security-standards": 3, "pod-security-admission": 3, "authentication": 4, "authorization": 4,
        "secrets": 4, "isolation-segmentation": 2, "audit-logging": 3, "network-policy": 3,
    },
    "threat-model": {
        "trust-boundaries": 3, "persistence": 3, "denial-of-service": 3, "malicious-code": 3,
        "network-attacker": 2, "sensitive-data": 3, "privilege-escalation": 3,
    },
    "platform-security": {
        "supply-chain": 4, "image-repository": 3, "observability": 2, "service-mesh": 3, "pki": 3,
        "connectivity": 2, "admission-control": 3,
    },
    "compliance-frameworks": {
        "compliance-frameworks": 3, "threat-modelling": 3, "supply-chain-compliance": 3, "automation-tooling": 3,
    },
}

CERTS = ["kcna", "kcsa"]


@pytest.fixture(scope="module")
def bank():
    return load_bank(ROOT)


def test_certs_load(bank):
    assert set(bank.certs) == {"kcna", "kcsa"}
    for cert in bank.certs.values():
        assert sum(d.weight for d in cert.domains) == 100


def test_allocate_kcna_split():
    assert allocate({"a": 44, "b": 28, "c": 16, "d": 12}, 60) == {"a": 26, "b": 17, "c": 10, "d": 7}


def test_allocate_always_sums_to_total():
    for total in range(1, 130):
        assert sum(allocate({"a": 14, "b": 22, "c": 22, "d": 16, "e": 16, "f": 10}, total).values()) == total


@pytest.mark.parametrize("cert_id, targets", [("kcna", KCNA_TOPIC_TARGETS), ("kcsa", KCSA_TOPIC_TARGETS)])
def test_bank_matches_blueprint(bank, cert_id, targets):
    cert = bank.certs[cert_id]
    questions = bank.questions[cert_id]
    # The bank size follows the planned targets (KCNA 180, KCSA 120).
    assert len(questions) == sum(sum(topics.values()) for topics in targets.values())
    assert coverage(cert, questions) == targets


def test_allocate_kcsa_split():
    assert allocate({"a": 14, "b": 22, "c": 22, "d": 16, "e": 16, "f": 10}, 60) == {
        "a": 8, "b": 13, "c": 13, "d": 10, "e": 10, "f": 6,
    }


@pytest.mark.parametrize("cert_id", CERTS)
def test_bank_supports_two_exams_without_repeats(bank, cert_id):
    cert = bank.certs[cert_id]
    per_exam = allocate({d.id: d.weight for d in cert.domains}, cert.question_count)
    cov = coverage(cert, bank.questions[cert_id])
    for domain_id, n in per_exam.items():
        assert sum(cov[domain_id].values()) >= 2 * n


@pytest.mark.parametrize("cert_id", CERTS)
def test_answer_keys_are_not_lopsided(bank, cert_id):
    # Guard against an author habitually putting the right answer in one slot.
    counts = {k: 0 for k in "ABCD"}
    for q in bank.questions[cert_id]:
        counts[q.answer] += 1
    assert max(counts.values()) <= 0.4 * len(bank.questions[cert_id])


@pytest.mark.parametrize("cert_id", CERTS)
def test_correct_answer_is_not_usually_the_longest(bank, cert_id):
    # "Pick the longest option" must not be a winning strategy (chance is ~25%).
    qs = bank.questions[cert_id]
    longest = sum(
        1 for q in qs
        if all(len(q.options[q.answer]) > len(v) for k, v in q.options.items() if k != q.answer)
    )
    assert longest <= 0.35 * len(qs)


def test_invalid_question_is_rejected(tmp_path):
    cert = load_cert(ROOT / "certs" / "kcna.yaml")
    bad = [{
        "id": "kcna-kf-999", "domain": "k8s-fundamentals", "topic": "nope", "difficulty": "easy",
        "question": "Q?", "options": {"A": "x", "B": "y", "C": "All of the above", "D": "x"},
        "answer": "E", "explanation": "e", "references": ["http://insecure"],
    }]
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(BankError) as exc:
        load_questions(cert, tmp_path)
    msg = str(exc.value)
    for fragment in ("unknown topic", "distinct", "positional", "answer must be", "https"):
        assert fragment in msg


def test_home_page_renders(tmp_path):
    app = create_app(base_dir=ROOT, db_path=tmp_path / "test.db")
    resp = app.test_client().get("/")
    assert resp.status_code == 200
    assert b"KCNA" in resp.data and b"KCSA" in resp.data
    assert (tmp_path / "test.db").exists()
