#!/usr/bin/env python3
"""Validate question banks and print a coverage report.

Usage:
    python scripts/validate_questions.py                 # every cert in certs/
    python scripts/validate_questions.py questions/kcna  # one cert (folder name = cert id)

Exit code 0 = valid, 1 = validation errors.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kcx.bank import BankError, allocate, coverage, load_certs, load_questions  # noqa: E402


def report(cert, questions) -> None:
    per_exam = allocate({d.id: d.weight for d in cert.domains}, cert.question_count)
    cov = coverage(cert, questions)
    print(f"\n{cert.name}: {len(questions)} questions")
    if not questions:
        print("  (bank not written yet)")
        return
    print(f"  {'domain / topic':<52}{'bank':>6}{'per exam':>10}{'2x exam':>9}")
    for d in cert.domains:
        total = sum(cov[d.id].values())
        flag = "" if total >= 2 * per_exam[d.id] else "  <- below 2x"
        print(f"  {d.name + f' ({d.weight}%)':<52}{total:>6}{per_exam[d.id]:>10}{2 * per_exam[d.id]:>9}{flag}")
        for t in d.topics:
            print(f"    - {t.name:<48}{cov[d.id][t.id]:>6}")
    diff = Counter(q.difficulty for q in questions)
    if questions:
        mix = ", ".join(f"{k} {diff[k]} ({100 * diff[k] / len(questions):.0f}%)" for k in ("easy", "medium", "hard"))
        print(f"  difficulty: {mix}")


def main(argv: list[str]) -> int:
    try:
        certs = load_certs(ROOT / "certs")
    except BankError as exc:
        print(exc, file=sys.stderr)
        return 1

    targets = [Path(a) for a in argv] or [ROOT / "questions" / cid for cid in certs]
    failed = False
    for qdir in targets:
        cert = certs.get(qdir.name)
        if cert is None:
            print(f"error: no certs/{qdir.name}.yaml for folder {qdir}", file=sys.stderr)
            failed = True
            continue
        if not qdir.is_dir():
            print(f"\n{cert.name}: no question folder ({qdir})")
            continue
        try:
            questions = load_questions(cert, qdir)
        except BankError as exc:
            print(f"\n{cert.name}: INVALID", file=sys.stderr)
            print(exc, file=sys.stderr)
            failed = True
            continue
        report(cert, questions)

    print("\nFAILED" if failed else "\nOK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
