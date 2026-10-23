"""One pass of the email worker (``flask newsletter worker``).

Order matters: start due schedules, freeze and queue campaign audiences, expand
automation triggers and due steps, then send what the rate limit allows and close
finished campaigns. Each stage commits on its own, so an interruption at any point is
safe to resume.
"""

from __future__ import annotations

import time
from typing import Any

from flask import current_app

from ...extensions import db
from . import automations, campaigns, queue

_last_inactive_check = {"at": 0.0}


def run_cycle(*, worker: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    stages = (
        ("scheduled_started", campaigns.start_due_scheduled),
        ("campaigns_prepared", campaigns.prepare_sending),
        ("trigger_events", automations.process_events),
        ("automation_messages", automations.process_due),
    )
    for name, func in stages:
        try:
            result[name] = func()
            db.session.commit()
        except Exception:  # one failing stage must not stop the others
            db.session.rollback()
            current_app.logger.exception("Email worker stage %s failed", name)
            result[name] = "error"
    if time.monotonic() - _last_inactive_check["at"] > 3600:
        try:
            result["reengagement_enrolled"] = automations.process_inactive()
            _last_inactive_check["at"] = time.monotonic()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Re-engagement check failed")
    try:
        result["delivery"] = queue.run_once(worker)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Email delivery pass failed")
        result["delivery"] = "error"
    try:
        result["campaigns_finished"] = campaigns.finish_completed()
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Finishing campaigns failed")
    return result
