#!/usr/bin/env python3
"""Check that every question reference URL is reachable.

Usage:
    python scripts/check_links.py                 # every cert in certs/
    python scripts/check_links.py questions/kcsa  # one cert (folder name = cert id)

Exit code 0 = every URL answered with a 2xx/3xx, 1 = at least one failed.
Network flakiness is expected, so CI runs this as a non-blocking job.
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kcx.bank import BankError, load_certs, load_questions  # noqa: E402

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; kcx-link-check/1.0)"}


def check(url: str) -> str | None:
    """Return None if the URL is reachable, else a short error string."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT):
                return None
        except urllib.error.HTTPError as exc:
            # Some servers reject HEAD (403/405) or bots on HEAD only; retry with GET.
            if method == "HEAD" and exc.code in (403, 405, 400, 501):
                continue
            return f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - report any network error
            if method == "HEAD":
                continue
            return f"{type(exc).__name__}: {exc}"
    return "unreachable"


def main(argv: list[str]) -> int:
    try:
        certs = load_certs(ROOT / "certs")
    except BankError as exc:
        print(exc, file=sys.stderr)
        return 1

    targets = [Path(a) for a in argv] or [ROOT / "questions" / cid for cid in certs]
    used_by: dict[str, list[str]] = defaultdict(list)
    for qdir in targets:
        cert = certs.get(qdir.name)
        if cert is None or not qdir.is_dir():
            print(f"skip: {qdir}", file=sys.stderr)
            continue
        try:
            questions = load_questions(cert, qdir)
        except BankError as exc:
            print(exc, file=sys.stderr)
            return 1
        for q in questions:
            for ref in q.references:
                used_by[ref].append(q.id)

    urls = sorted(used_by)
    print(f"checking {len(urls)} unique URLs...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = dict(zip(urls, pool.map(check, urls)))

    failed = {u: err for u, err in results.items() if err}
    for url, err in failed.items():
        ids = ", ".join(used_by[url])
        print(f"FAIL {err:<20} {url}\n     used by: {ids}")
    print(f"\n{len(urls) - len(failed)}/{len(urls)} reachable")
    print("FAILED" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
