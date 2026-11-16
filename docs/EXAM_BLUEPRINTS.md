# Exam blueprints

KC-X mirrors the **structure** of the real exams: domains, weights, question counts and timing.
It never reproduces real exam questions. Those are covered by the Linux Foundation candidate NDA.

The machine-readable versions live in [`certs/`](../certs). The app and the validator read only those files.
This page explains where the numbers come from.

_Last verified: **2026-11-13**_

## Sources

| Fact | Source | Status |
|---|---|---|
| KCNA domains, weights, topics, 90 min | [LF KCNA certification page](https://training.linuxfoundation.org/certification/kubernetes-cloud-native-associate/) | Official |
| KCNA curriculum change (exams on/after 2025-11-24) | [LF KCNA program changes](https://training.linuxfoundation.org/kcna-program-changes/) | Official |
| KCSA domains, weights, competencies, 90 min | [LF KCSA certification page](https://training.linuxfoundation.org/certification/kubernetes-and-cloud-native-security-associate-kcsa/) | Official |
| Curriculum PDFs | [cncf/curriculum](https://github.com/cncf/curriculum) | Official |
| 60 questions, 75% pass mark (both exams) | Widely reported by study guides; not stated on the LF cert pages | Secondary |

When the LF updates a curriculum:
1. Update `certs/<cert>.yaml`.
2. Update this page and its `last_verified` date.
3. Run `scripts/validate_questions.py` to see which domains need new questions.

## KCNA: Kubernetes and Cloud Native Associate

- **Format:** online, proctored, multiple choice with one correct answer.
- **Length:** 60 questions in 90 minutes.
- **Pass mark:** 75%.

The official page lists each domain's competencies as topic headings only. Every KC-X question maps to exactly one of these topics.

| Domain | Weight | Topics | Per exam | Bank target |
|---|---:|---|---:|---:|
| Kubernetes Fundamentals | 44% | Kubernetes Core Concepts · Administration · Scheduling · Containerization | 26 | 78 |
| Container Orchestration | 28% | Networking · Security · Troubleshooting · Storage | 17 | 51 |
| Cloud Native Application Delivery | 16% | Application Delivery · Debugging | 10 | 30 |
| Cloud Native Architecture | 12% | Observability · Cloud Native Ecosystem and Principles · Cloud Native Community and Collaboration | 7 | 21 |
| **Total** | 100% | | **60** | **180** |

**How the counts are worked out:**
- **Per exam:** the `weight × 60` split, rounded with the largest-remainder method (`kcx.bank.allocate`).
- **Bank target:** three times the per-exam count, so three full mock exams can run without repeating a question. (KCSA uses twice the per-exam count.)

**Planned topic split of the 180-question bank:**

| Domain | Topic | Questions |
|---|---|---:|
| Kubernetes Fundamentals | Core Concepts | 27 |
| | Administration | 17 |
| | Scheduling | 16 |
| | Containerization | 18 |
| Container Orchestration | Networking | 15 |
| | Security | 14 |
| | Troubleshooting | 10 |
| | Storage | 12 |
| Application Delivery | Application Delivery | 20 |
| | Debugging | 10 |
| Cloud Native Architecture | Observability | 9 |
| | Ecosystem and Principles | 8 |
| | Community and Collaboration | 4 |

**Difficulty target:** about 40% easy, 45% medium, 15% hard.

## KCSA: Kubernetes and Cloud Native Security Associate

- **Format:** online, proctored, multiple choice.
- **Length:** 60 questions in 90 minutes.
- **Pass mark:** 75%.
- **Question bank:** 120 questions, twice the per-exam split (Phase 6 of the [roadmap](ROADMAP.md)).

| Domain | Weight | Per exam | Bank target |
|---|---:|---:|---:|
| Overview of Cloud Native Security | 14% | 8 | 16 |
| Kubernetes Cluster Component Security | 22% | 13 | 26 |
| Kubernetes Security Fundamentals | 22% | 13 | 26 |
| Kubernetes Threat Model | 16% | 10 | 20 |
| Platform Security | 16% | 10 | 20 |
| Compliance and Security Frameworks | 10% | 6 | 12 |
| **Total** | 100% | **60** | **120** |

Each domain's competencies are copied verbatim into [`certs/kcsa.yaml`](../certs/kcsa.yaml) as topics. Some examples:
- **Kubernetes Cluster Component Security:** API Server, Controller Manager, Scheduler, Kubelet, Container Runtime, KubeProxy, Pod, Etcd, Container Networking, Client Security, Storage.
- **Kubernetes Threat Model:** Trust Boundaries and Data Flow, Persistence, Denial of Service, Malicious Code Execution, Attacker on the Network, Access to Sensitive Data, Privilege Escalation.

**Planned topic split of the 120-question bank** (every topic has at least 2; heavier where the exam leans):

| Domain | Topic | Questions |
|---|---|---:|
| Overview of Cloud Native Security | The 4Cs of Cloud Native Security | 3 |
| | Cloud Provider and Infrastructure Security | 2 |
| | Controls and Frameworks | 2 |
| | Isolation Techniques | 3 |
| | Artifact Repository and Image Security | 3 |
| | Workload and Application Code Security | 3 |
| Kubernetes Cluster Component Security | API Server | 4 |
| | Controller Manager · Scheduler | 2 each |
| | Kubelet | 3 |
| | Container Runtime · KubeProxy · Pod | 2 each |
| | Etcd | 3 |
| | Container Networking · Client Security · Storage | 2 each |
| Kubernetes Security Fundamentals | Pod Security Standards · Pod Security Admissions | 3 each |
| | Authentication · Authorization · Secrets | 4 each |
| | Isolation and Segmentation | 2 |
| | Audit Logging · Network Policy | 3 each |
| Kubernetes Threat Model | Trust Boundaries and Data Flow · Persistence · Denial of Service · Malicious Code Execution | 3 each |
| | Attacker on the Network | 2 |
| | Access to Sensitive Data · Privilege Escalation | 3 each |
| Platform Security | Supply Chain Security | 4 |
| | Image Repository | 3 |
| | Observability | 2 |
| | Service Mesh · PKI | 3 each |
| | Connectivity | 2 |
| | Admission Control | 3 |
| Compliance and Security Frameworks | Compliance · Threat Modelling · Supply Chain Compliance · Automation and Tooling | 3 each |

**Difficulty target:** about 40% easy, 45% medium, 15% hard (the bank is 38 / 48 / 15).

The current Kubernetes docs no longer describe the 4Cs model by name. Questions on that topic cite the
[v1.28 security overview page](https://github.com/kubernetes/website/blob/release-1.28/content/en/docs/concepts/security/overview.md)
in the kubernetes/website repo, the last release that still contains it.
