"""Age confirmation (Batch 13.2): newsletter subscriptions, customer accounts, purchases
and courses are for people aged 18 or older; free articles stay open to everyone.

People confirm with a checkbox. No date of birth is asked for or stored; newsletter
consent records include the confirmation wording as part of the evidence of consent.
"""

from __future__ import annotations

from typing import Any

FIELD = "age_confirmed"
MESSAGE = "Please confirm that you are 18 or older."
STATEMENT = "I confirm that I am 18 or older."


def age_problem(data: dict[str, Any]) -> list[str] | None:
    """The error for ``age_confirmed`` unless it is exactly ``true``."""
    return None if data.get(FIELD) is True else [MESSAGE]
