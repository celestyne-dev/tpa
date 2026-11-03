"""Lightweight error alerting from the API's own logs (no extra service or database).

The API logs every unhandled error as one line,
``Unhandled API error (request <METHOD> <path>, id <request id>)``, and returns the same
request id to the visitor in ``X-Request-ID``. ``flask monitor errors`` (run by
``tpa-error-alert.timer``) reads only the journal entries written since its previous run
(a journalctl cursor file), and emails a short summary to ``ERROR_ALERT_EMAIL`` when there
are any. The full traceback stays in the journal: ``journalctl -u <unit> | grep <id>``.

The summary contains methods, paths and request ids only: no query strings, visitor
addresses or headers, and path segments that look like tokens are redacted.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LINE = re.compile(
    r"Unhandled API error \(request (?P<method>[A-Z]{3,7}) (?P<path>\S{1,300}), "
    r"id (?P<rid>[A-Za-z0-9-]{1,64})\)"
)
# Path segments that may be secrets (download links, account tokens): long random strings.
TOKENISH = re.compile(r"^(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{20,}$")
MAX_LISTED = 10


def redact(path: str) -> str:
    return "/".join(":token" if TOKENISH.match(seg) else seg for seg in path.split("/"))


@dataclass
class ErrorSummary:
    count: int = 0
    by_route: Counter = field(default_factory=Counter)
    request_ids: list[str] = field(default_factory=list)

    def add(self, method: str, path: str, rid: str) -> None:
        self.count += 1
        self.by_route[f"{method} {redact(path)}"] += 1
        if len(self.request_ids) < MAX_LISTED:
            self.request_ids.append(rid)


def summarise(lines) -> ErrorSummary:
    summary = ErrorSummary()
    for line in lines:
        match = LINE.search(line)
        if match:
            summary.add(match["method"], match["path"], match["rid"])
    return summary


def read_journal(unit: str, cursor_file: str, first_since: str = "-15min") -> list[str]:
    """New journal lines of ``unit`` since the cursor (on the first run: ``first_since``).

    journalctl keeps the cursor file up to date itself, so every line is read once. The
    service user needs read access to the journal (group ``systemd-journal``).
    """
    args = ["journalctl", "--unit", unit, "--output", "cat", "--no-pager", "--quiet"]
    args += ["--cursor-file", cursor_file]
    if not Path(cursor_file).exists():
        args += ["--since", first_since]
    done = subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)
    if done.returncode != 0:
        raise RuntimeError((done.stderr or "journalctl failed").strip()[:300])
    return done.stdout.splitlines()


def message_text(summary: ErrorSummary, *, unit: str, tier: str, release: str) -> str:
    routes = "\n".join(f"  {n:>4} × {route}" for route, n in summary.by_route.most_common(10))
    ids = "\n".join(f"  {rid}" for rid in summary.request_ids)
    more = summary.count - len(summary.request_ids)
    return (
        f"{summary.count} unhandled API error(s) on {tier or 'an unnamed tier'} "
        f"(release {release}, unit {unit}) since the last check.\n\n"
        f"By route:\n{routes}\n\n"
        f"Request ids (each is also in the visitor's X-Request-ID header):\n{ids}\n"
        + (f"  … and {more} more\n" if more > 0 else "")
        + f"\nFull tracebacks on the server:\n  journalctl -u {unit} | grep <request id>\n"
    )
