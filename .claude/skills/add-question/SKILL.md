---
name: add-question
description: Write, fix or replace KCNA/KCSA exam questions in questions/<cert>/*.yaml and validate them. Use when adding questions to a domain/topic, rewriting a flawed question, or rebalancing a bank.
---

Request: $ARGUMENTS

1. **Read the rules first:** read `docs/QUESTION_FORMAT.md`, `certs/<cert>.yaml` for the domain/topic ids and `abbr`, and the target domain file in `questions/<cert>/`, so you can match its header and `# ---- <topic> (N)` grouping.
2. **Pick ids:** a new question gets the next free id for that domain, so grep the whole `questions/<cert>/` folder for the highest `<cert>-<abbr>-NNN`. Never reuse a deleted id.
3. **Write the question:**
   - Original wording only. Never reproduce real-exam or dump content.
   - Four plausible options of similar length. Don't let the correct option be the longest.
   - No "all/none of the above" or "A and B". Quote option values YAML could misread (`yes`, `no`, `true`, `on`, numbers, a leading backtick, `*`, `&`, `[`, `{`).
   - Use a capitalized NOT and avoid double negatives.
   - Use current Kubernetes only.
   - Choose a correct letter that keeps the file's answer distribution even.
   - Write `explanation` as a folded `>` block that says why the answer is right and ideally why the distractors are wrong.
   - Give `references` with https links to official docs (kubernetes.io, cncf.io, glossary.cncf.io, project docs). Fetch each page to confirm it supports the answer.
4. **If counts changed:**
   - Update the topic counts in the YAML header comment.
   - Update the topic's entry in `KCNA_TOPIC_TARGETS` / `KCSA_TOPIC_TARGETS` in `tests/test_bank.py`.
   - The bank size is derived from those targets; if the total changed, also update `docs/EXAM_BLUEPRINTS.md` and the README's bank count.
5. **Self-check cold:** reread only the question and options, and confirm that exactly one option is defensibly correct.
6. **Validate:**
   - `docker compose run --rm --build kcx python scripts/validate_questions.py questions/<cert>`, which must print OK.
   - Then `docker compose run --rm --build kcx pytest tests/test_bank.py`.
   - Optionally `docker compose run --rm kcx python scripts/check_links.py questions/<cert>`.
7. **Report:** the ids added or changed, and the validator's coverage table if counts changed.
