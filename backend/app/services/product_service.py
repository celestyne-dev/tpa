from __future__ import annotations

from .content_repository import Record, get_repository


def list_products() -> list[Record]:
    """Upcoming product previews. No prices or purchase data until Batch 04."""
    return get_repository().list_products()
