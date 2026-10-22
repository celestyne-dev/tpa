"""Request validation schemas (query strings)."""

import re

from marshmallow import EXCLUDE, Schema, fields, validate

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class TopicListQuerySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    featured = fields.Boolean(load_default=None)


class ArticleListQuerySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    topic = fields.String(
        load_default=None, validate=[validate.Length(max=120), validate.Regexp(SLUG_PATTERN)]
    )
    featured = fields.Boolean(load_default=None)
    page = fields.Integer(load_default=1, validate=validate.Range(min=1, max=10_000))
    # Defaults: 12 per page, capped at 50.
    page_size = fields.Integer(load_default=12, validate=validate.Range(min=1, max=50))


def is_valid_slug(value: str) -> bool:
    return len(value) <= 120 and re.fullmatch(SLUG_PATTERN, value) is not None
