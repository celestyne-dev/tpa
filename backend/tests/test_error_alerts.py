"""Lightweight error alerting: `flask monitor errors` (journal -> one summary email)."""

from __future__ import annotations

import subprocess

import pytest

from app.services import error_alerts, mail

JOURNAL = """\
[2026-11-03 10:00:01] INFO in app: started
Unhandled API error (request GET /api/v1/articles, id 3f2a9c1d0b4e5a67)
Traceback (most recent call last):
  File "x.py", line 1, in <module>
RuntimeError: boom
Unhandled API error (request POST /api/v1/downloads/Zk3qP9xLm2Rt7Vw4Yb8Nc1Hd, id 9a8b7c6d5e4f3a2b)
Unhandled API error (request GET /api/v1/articles, id 0123456789abcdef)
CSP report: script-src-elem blocked https://x.example on /about
"""


def test_summary_counts_routes_and_redacts_token_like_segments():
    s = error_alerts.summarise(JOURNAL.splitlines())
    assert s.count == 3
    assert s.by_route == {"GET /api/v1/articles": 2, "POST /api/v1/downloads/:token": 1}
    assert s.request_ids == ["3f2a9c1d0b4e5a67", "9a8b7c6d5e4f3a2b", "0123456789abcdef"]
    # Ordinary slugs and ids are kept; long mixed random strings are not.
    assert error_alerts.redact("/api/v1/articles/building-quiet-confidence") == (
        "/api/v1/articles/building-quiet-confidence"
    )
    assert error_alerts.redact("/api/v1/orders/1234") == "/api/v1/orders/1234"


def test_message_lists_at_most_ten_ids_and_how_to_find_the_traceback():
    lines = [f"Unhandled API error (request GET /x, id id{i:08d})" for i in range(14)]
    text = error_alerts.message_text(
        error_alerts.summarise(lines), unit="tpa-api.service", tier="staging", release="abc123"
    )
    assert "14 unhandled API error(s) on staging (release abc123" in text
    assert "id00000009" in text and "id00000010" not in text and "and 4 more" in text
    assert "journalctl -u tpa-api.service | grep <request id>" in text


@pytest.fixture()
def journal(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=fake_run.stdout, stderr="")

    fake_run.stdout = JOURNAL
    monkeypatch.setattr(error_alerts.subprocess, "run", fake_run)
    return fake_run, calls, str(tmp_path / "error-alert.cursor")


def _invoke(app, cursor, *extra):
    return app.test_cli_runner().invoke(
        args=["monitor", "errors", "--unit", "tpa-api-staging.service", "--cursor-file", cursor]
        + list(extra)
    )


def test_cli_emails_one_summary_and_reads_only_new_journal_lines(app, journal):
    fake_run, calls, cursor = journal
    app.config.update(MAIL_BACKEND="memory", ERROR_ALERT_EMAIL="ops@example.org")
    app.config.update(TPA_ENVIRONMENT="staging", RELEASE_ID="abc123")
    mail.MemoryBackend.outbox.clear()
    result = _invoke(app, cursor)
    assert result.exit_code == 0, result.output
    [message] = mail.MemoryBackend.outbox
    assert message.to == "ops@example.org"
    assert message.subject == "[TPA staging] 3 unhandled API error(s)"
    assert "Zk3qP9xLm2Rt7Vw4Yb8Nc1Hd" not in message.text and ":token" in message.text
    # journalctl keeps its place in the cursor file; the first run looks back 15 minutes.
    assert calls[0][:3] == ["journalctl", "--unit", "tpa-api-staging.service"]
    assert ["--cursor-file", cursor] == calls[0][calls[0].index("--cursor-file") :][:2]
    assert calls[0][-2:] == ["--since", "-15min"]
    # Later runs (cursor present) read only what is new; nothing new -> no email.
    open(cursor, "w").close()
    fake_run.stdout = "[2026-11-03 10:20:00] INFO in app: fine\n"
    result = _invoke(app, cursor)
    assert result.exit_code == 0 and "No new unhandled API errors." in result.output
    assert "--since" not in calls[1] and len(mail.MemoryBackend.outbox) == 1


def test_cli_without_a_recipient_or_mail_setup_reports_failure(app, journal):
    _fake, _calls, cursor = journal
    app.config.update(MAIL_BACKEND="memory", ERROR_ALERT_EMAIL="")
    result = _invoke(app, cursor)
    assert result.exit_code == 1 and "ERROR_ALERT_EMAIL is not set" in result.output
    app.config.update(MAIL_BACKEND="none", ERROR_ALERT_EMAIL="ops@example.org")
    result = _invoke(app, cursor)
    assert result.exit_code == 1 and "not configured" in result.output


def test_cli_reports_an_unreadable_journal(app, monkeypatch, tmp_path):
    def denied(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="No journal files found")

    monkeypatch.setattr(error_alerts.subprocess, "run", denied)
    result = _invoke(app, str(tmp_path / "c"))
    assert result.exit_code == 2 and "No journal files found" in result.output
