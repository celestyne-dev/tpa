"""Content repository abstraction.

Services depend on the ``ContentRepository`` protocol, not on where content
lives. Batch 01 uses ``LocalContentRepository`` (JSON sample data); Batch 02
adds a SQLAlchemy-backed implementation with the same interface, so API
resources and services do not change.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from flask import current_app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

Record = dict[str, Any]


class ContentRepository(Protocol):
    def list_topics(self) -> list[Record]: ...

    def list_articles(self) -> list[Record]: ...

    def list_products(self) -> list[Record]: ...


@cache
def _load(name: str) -> tuple[Record, ...]:
    with (DATA_DIR / f"{name}.json").open(encoding="utf-8") as fh:
        return tuple(json.load(fh))


class LocalContentRepository:
    """Read-only repository backed by bundled JSON sample files."""

    def list_topics(self) -> list[Record]:
        return deepcopy(list(_load("topics")))

    def list_articles(self) -> list[Record]:
        return deepcopy(list(_load("articles")))

    def list_products(self) -> list[Record]:
        return deepcopy(list(_load("products")))


def get_repository() -> ContentRepository:
    """Return the repository configured on the app (overridable in tests)."""
    return current_app.extensions.setdefault("tpa_content_repository", LocalContentRepository())
