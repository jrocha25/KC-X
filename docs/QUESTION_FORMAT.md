# Question format

Questions are YAML files under `questions/<cert-id>/`. Use one file per domain, for example `questions/kcna/k8s-fundamentals.yaml`.
Each file is a list of questions.

The app loads every `*.yaml` in the folder at startup. It **refuses to start** if any question is invalid, and prints every error it found.

## Schema

```yaml
- id: kcna-kf-001                 # <cert>-<domain abbr>-<3 digits>; unique; never reused
  domain: k8s-fundamentals        # a domain id from certs/<cert>.yaml
  topic: core-concepts            # a topic id under that domain
  difficulty: easy                # easy | medium | hard
  question: Which Kubernetes control plane component stores the entire state of the cluster?
  options:                        # exactly A, B, C, D; all distinct, non-empty strings
    A: kube-scheduler
    B: etcd
    C: kube-controller-manager
    D: kubelet
  answer: B                       # the key of the correct option
  explanation: >                  # why the answer is right (and ideally why the others are wrong)
    etcd is a consistent, highly-available key-value store that Kubernetes uses as the
    backing store for all cluster data.
  references:                     # one or more https URLs to official docs
    - https://kubernetes.io/docs/concepts/overview/components/
```

### Field rules

| Field | Rule |
|---|---|
| `id` | Must match `<cert>-<abbr>-NNN`. The `abbr` comes from the domain in `certs/<cert>.yaml` (`kf`, `co`, `ad`, `ca` for KCNA; `ov`, `cc`, `sf`, `tm`, `ps`, `cf` for KCSA). Never renumber or reuse an id, because attempt history refers to questions by id. Retire a question by deleting it. |
| `domain`, `topic` | Must exist in the cert config. |
| `difficulty` | `easy` is recall of one fact. `medium` applies a concept or tells similar things apart. `hard` is a multi-step scenario, an edge case, or a subtle default. |
| `options` | Exactly four. They are **shuffled** when shown, so never write "all of the above", "none of the above", or "A and B" (the validator rejects the first two). Quote values that YAML could misread: `yes`, `no`, `true`, `on`, numbers, or text starting with `` ` ``, `*`, `&`, `[`, `{`. |
| `answer` | One of `A`–`D`. Keep correct answers spread evenly across letters within a file. A test fails if any letter holds more than 40% of the answers. |
| `explanation` | Required. Shown on the result page. |
| `references` | At least one `https://` URL. Prefer kubernetes.io, cncf.io, glossary.cncf.io, and official project docs. |

## Style guide

The goal is to feel like the real exam: short and precise, with one clearly correct answer.

- **Mix of question types (KCNA):**
  - About 75% are short concept questions ("Which component…", "What does X do?").
  - About 15% are short scenarios ("A Pod is Pending with event …. What is the most likely cause?").
  - About 10% are recognition questions (a kubectl command, a manifest field, an `apiVersion`).
- **Stay at the cert's level (KCNA scope).** KCNA is an associate exam, so test concepts from the curriculum topics,
  everyday kubectl basics (get, describe, logs, exec, apply, scale, rollout, port-forward, debug) and well-known CNCF
  projects at a "what is it for" level. Leave out:
  - CKA/CKAD procedures (kubeadm upgrades, etcdctl, kubelet flags)
  - niche kubectl flags or JSON paths
  - exact edge-case defaults or version-policy numbers
  - KCSA-depth security, such as PSA audit/warn modes, OIDC token flow or posture-scanning tools

  A few `hard` stretch questions are fine.
- **Distractors are plausible.** Use real component names, real flags and real objects used in the wrong place. Avoid joke answers.
- **Options are about the same length.** The correct answer should not be noticeably the longest. A test fails if it is strictly the longest in more than 35% of questions; chance is about 25%.
- **Use current Kubernetes only:**
  - Pod Security Admission, not PodSecurityPolicy.
  - containerd/CRI-O, not dockershim.
  - EndpointSlices.
  - Gateway API alongside Ingress.
- **No trick wording.** Avoid double negatives. If you write NOT, capitalize it.
- **Write original wording.** Never paste questions from exam dumps or other practice sites.

Good:
> A Pod is stuck in ImagePullBackOff. Which is the most likely cause?

Bad:
> Which of these is not something that wouldn't cause ImagePullBackOff? (double negative)
> (D) All of the above (positional)

## Checking your work

```bash
docker compose run --rm kcx python scripts/validate_questions.py questions/kcna
docker compose run --rm kcx pytest
```

The validator prints a coverage table:
- per domain and per topic, how many questions there are compared with the exam split
- the difficulty mix

`tests/test_bank.py` pins the planned topic split of each bank. If you intentionally change a bank's size, update `KCNA_TOPIC_TARGETS` or `KCSA_TOPIC_TARGETS` there too.

To check that every reference URL still resolves (needs network access; CI runs it as a non-blocking job):

```bash
docker compose run --rm kcx python scripts/check_links.py questions/kcsa
```
