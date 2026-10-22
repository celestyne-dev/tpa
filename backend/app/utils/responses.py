"""Consistent JSON response envelopes.

Success:  {"data": ..., "meta": {...}}
Error:    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any


def success(data: Any, meta: dict[str, Any] | None = None, status: int = 200):
    body: dict[str, Any] = {"data": data}
    if meta:
        body["meta"] = meta
    return body, status


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}
