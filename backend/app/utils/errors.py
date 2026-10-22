"""API exceptions and JSON error handlers.

Handlers never include stack traces or internal exception text in responses.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from ..extensions import db
from .responses import error_body

logger = logging.getLogger(__name__)


class APIError(Exception):
    status_code = 400
    code = "bad_request"
    message = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: Any = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details


class NotFoundError(APIError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class ValidationError(APIError):
    status_code = 400
    code = "validation_error"
    message = "One or more parameters are invalid."


class AuthenticationError(APIError):
    status_code = 401
    code = "authentication_failed"
    message = "Authentication is required."


class ForbiddenError(APIError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action."


class ConflictError(APIError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "too_many_requests",
}

_HTTP_MESSAGES = {
    404: "The requested resource was not found.",
    429: "Too many requests. Please wait a moment and try again.",
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify(error_body(err.code, err.message, err.details)), err.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        status = err.code or 500
        code = _HTTP_CODES.get(status, "http_error")
        message = _HTTP_MESSAGES.get(status) or err.description
        return jsonify(error_body(code, message or "Request failed.")), status

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(err: IntegrityError):
        db.session.rollback()
        logger.warning("Integrity error: %s", err.__class__.__name__)
        return jsonify(
            error_body("conflict", "The change conflicts with existing data (duplicate or in use).")
        ), 409

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        db.session.rollback()
        logger.exception("Unhandled API error", exc_info=err)
        return jsonify(error_body("internal_error", "An unexpected error occurred.")), 500
