"""Content-Security-Policy violation reports: ``POST /api/v1/csp-report``.

Browsers send these while the policy runs in report-only mode (deploy/nginx). Each
report is reduced to the directive, the blocked origin and the page path (no query
strings, cookies or visitor details) and logged, so the policy can be reviewed on
staging before it is enforced. Nothing is stored; always 204; rate limited.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from flask import current_app, request
from flask_restful import Resource

from ..extensions import limiter

MAX_BODY = 8 * 1024


def _origin_only(value: object) -> str:
    """'inline', 'eval', 'data' etc. as sent; URLs reduced to scheme://host."""
    text = str(value or "")[:200]
    parts = urlsplit(text)
    if parts.scheme in ("http", "https") and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return text.split(":", 1)[0] if ":" in text else text


def summarise(payload: object) -> list[dict[str, str]]:
    """The useful fields of a report-uri (csp-report) or Reporting API body."""
    reports = payload if isinstance(payload, list) else [payload]
    out = []
    for item in reports[:10]:
        if not isinstance(item, dict):
            continue
        body = item.get("csp-report") or item.get("body") or {}
        if not isinstance(body, dict):
            continue
        directive = (
            body.get("effective-directive")
            or body.get("effectiveDirective")
            or body.get("violated-directive", "")
        )
        page = body.get("document-uri") or body.get("documentURL") or ""
        out.append(
            {
                "directive": str(directive)[:80],
                "blocked": _origin_only(body.get("blocked-uri") or body.get("blockedURL")),
                "page": urlsplit(str(page)).path[:200],
            }
        )
    return out


class CspReportResource(Resource):
    method_decorators = {"post": [limiter.limit("30 per minute")]}

    def post(self):
        raw = request.get_data(cache=False)[: MAX_BODY + 1]
        if len(raw) <= MAX_BODY:
            try:
                for report in summarise(json.loads(raw or b"null")):
                    current_app.logger.warning(
                        "CSP report: %s blocked %s on %s",
                        report["directive"],
                        report["blocked"],
                        report["page"],
                    )
            except (ValueError, UnicodeDecodeError):
                pass
        return "", 204, {"Cache-Control": "no-store"}


PUBLIC_SECURITY_ROUTES = [(CspReportResource, "/csp-report")]
