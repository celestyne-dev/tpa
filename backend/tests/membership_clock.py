"""Controlled time for membership and payment tests (tests only).

The fake Paystack in ``conftest.py`` reports fixed dates: first charge 23 Oct 2026, next
payment and renewal 23 Nov 2026. The services decide what is "now" through their own
module-level ``_now()`` helpers, so a test that mixes the fake's dates with the real clock
starts failing once the calendar passes those dates. ``Clock`` pins every one of those
helpers to a single test-controlled instant instead.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest

# The fake's fixed timeline, a few minutes after each charge.
FIRST_PAYMENT = datetime(2026, 10, 23, 10, 5, tzinfo=UTC)
RENEWAL = datetime(2026, 11, 23, 10, 5, tzinfo=UTC)

CLOCK_MODULES = (
    "app.services.memberships.admin",
    "app.services.memberships.billing",
    "app.services.memberships.compliance",
    "app.services.memberships.lifecycle",
    "app.services.memberships.plans",
    "app.services.memberships.reports",
    "app.services.commerce.checkout",
    "app.services.commerce.customers",
    "app.services.commerce.entitlements",
    "app.services.commerce.payments",
)


class Clock:
    """One instant shared by the membership and payment services."""

    def __init__(self, monkeypatch, when):
        self.now = when
        for name in CLOCK_MODULES:
            monkeypatch.setattr(importlib.import_module(name), "_now", lambda: self.now)

    def set(self, when):
        self.now = when


@pytest.fixture()
def clock(monkeypatch):
    return Clock(monkeypatch, FIRST_PAYMENT)


def paystack_time(when: datetime) -> str:
    """``when`` in the fake Paystack's timestamp format."""
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
