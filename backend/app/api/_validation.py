from flask import request
from marshmallow import Schema
from marshmallow import ValidationError as MarshmallowValidationError

from ..schemas.queries import is_valid_slug
from ..utils.errors import NotFoundError, ValidationError


def load_query(schema: Schema) -> dict:
    try:
        return schema.load(request.args)
    except MarshmallowValidationError as err:
        raise ValidationError(details=err.messages) from None


def load_body(schema: Schema, *, partial: bool = False) -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    try:
        return schema.load(data, partial=partial)
    except MarshmallowValidationError as err:
        raise ValidationError(details=err.messages) from None


def require_slug(slug: str, resource: str) -> str:
    if not is_valid_slug(slug):
        raise NotFoundError(f"{resource} '{slug}' was not found.")
    return slug
