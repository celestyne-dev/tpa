"""Response serialisation schemas. They define exactly which fields the API exposes."""

from marshmallow import Schema, fields


class ImageSchema(Schema):
    src = fields.String()
    alt = fields.String()
    width = fields.Integer()
    height = fields.Integer()


class TopicRefSchema(Schema):
    slug = fields.String()
    name = fields.String()


class SeoSchema(Schema):
    title = fields.String()
    description = fields.String()
    canonical_url = fields.String()
    no_index = fields.Boolean()
    og_image = fields.Nested(ImageSchema)


class TopicSchema(Schema):
    slug = fields.String()
    name = fields.String()
    description = fields.String()
    intro = fields.String()
    icon = fields.String()
    featured = fields.Boolean()
    article_count = fields.Integer()
    seo = fields.Nested(SeoSchema, allow_none=True)


class AuthorSchema(Schema):
    slug = fields.String()
    name = fields.String()


class ArticleSummarySchema(Schema):
    id = fields.String()
    slug = fields.String()
    title = fields.String()
    excerpt = fields.String()
    topic_slug = fields.String()
    topic = fields.Nested(TopicRefSchema, allow_none=True)
    secondary_topic_slugs = fields.List(fields.String(), dump_default=list)
    author = fields.Nested(AuthorSchema)
    published_at = fields.String()
    updated_at = fields.String(allow_none=True)
    featured = fields.Boolean()
    reading_time_minutes = fields.Integer()
    image = fields.Nested(ImageSchema)
    source = fields.String()


class ArticleDetailSchema(ArticleSummarySchema):
    subtitle = fields.String(allow_none=True)
    tags = fields.List(fields.String(), dump_default=list)
    body = fields.List(fields.Dict())
    canonical_url = fields.String(allow_none=True)
    seo = fields.Nested(SeoSchema, allow_none=True)


class ProductSchema(Schema):
    id = fields.String()
    slug = fields.String()
    title = fields.String()
    subtitle = fields.String()
    description = fields.String()
    format = fields.String()
    availability = fields.String()
    topic_slugs = fields.List(fields.String())
    highlights = fields.List(fields.String())
    cover_theme = fields.String()
    image = fields.Nested(ImageSchema, allow_none=True)


topic_schema = TopicSchema()
topics_schema = TopicSchema(many=True)
article_summaries_schema = ArticleSummarySchema(many=True)
article_detail_schema = ArticleDetailSchema()
products_schema = ProductSchema(many=True)
