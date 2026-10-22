"""Admin request validation. Unknown fields are rejected (no mass assignment)."""

from __future__ import annotations

from datetime import UTC

from marshmallow import RAISE, Schema, ValidationError, fields, pre_load, validate

from ..utils.validation import SLUG_RE, is_https_url, plain_text_problem


def _plain(value: str) -> None:
    if value and (problem := plain_text_problem(value)):
        raise ValidationError(problem)


def _https(value: str) -> None:
    if value and not is_https_url(value):
        raise ValidationError("Enter a full https:// URL.")


def _http_or_https(value: str) -> None:
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValidationError("Enter a full http(s):// URL.")


def _slug(value: str) -> None:
    if value and not SLUG_RE.match(value):
        raise ValidationError("Use lowercase letters, numbers and hyphens.")


def Text(max_len: int, *, required: bool = False, allow_none: bool = False, min_len: int = 0):  # noqa: N802
    return fields.String(
        required=required,
        allow_none=allow_none,
        validate=[validate.Length(min=min_len, max=max_len), _plain],
    )


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE

    @pre_load
    def _blank_to_none(self, data, **_kwargs):
        if not isinstance(data, dict):
            return data
        out = {}
        for key, value in data.items():
            field = self.fields.get(key)
            if isinstance(value, str):
                value = value.strip()
                if value == "" and field is not None and field.allow_none:
                    value = None
            out[key] = value
        return out


class LoginSchema(StrictSchema):
    email = fields.String(required=True, validate=validate.Length(min=3, max=254))
    password = fields.String(required=True, validate=validate.Length(min=1, max=256))


class ChangePasswordSchema(StrictSchema):
    current_password = fields.String(required=True, validate=validate.Length(max=256))
    new_password = fields.String(required=True, validate=validate.Length(max=256))


class PageQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    page = fields.Integer(load_default=1, validate=validate.Range(min=1, max=100_000))
    page_size = fields.Integer(load_default=20, validate=validate.Range(min=1, max=100))


class MediaQuerySchema(PageQuerySchema):
    q = fields.String(load_default=None, validate=validate.Length(max=100))
    type = fields.String(
        load_default=None,
        validate=validate.OneOf(
            ["image/jpeg", "image/png", "image/webp", "image/avif", "image/gif", "image/svg+xml"]
        ),
    )
    usage = fields.String(
        load_default=None, validate=validate.OneOf(["used", "unused", "missing_alt"])
    )
    status = fields.String(
        load_default="active", validate=validate.OneOf(["active", "archived", "all"])
    )
    sort = fields.String(
        load_default="newest", validate=validate.OneOf(["newest", "oldest", "filename", "size"])
    )
    uploaded_from = fields.AwareDateTime(load_default=None, default_timezone=UTC)
    uploaded_to = fields.AwareDateTime(load_default=None, default_timezone=UTC)
    page_size = fields.Integer(load_default=30, validate=validate.Range(min=1, max=100))


class MediaUpdateSchema(StrictSchema):
    alt_text = fields.String(allow_none=True, validate=validate.Length(max=300))
    title = fields.String(allow_none=True, validate=validate.Length(max=200))
    caption = fields.String(allow_none=True, validate=validate.Length(max=500))
    credit = fields.String(allow_none=True, validate=validate.Length(max=200))
    source_url = fields.String(allow_none=True, validate=validate.Length(max=500))
    filename = fields.String(validate=validate.Length(min=1, max=120))
    focal_x = fields.Float(validate=validate.Range(min=0, max=1))
    focal_y = fields.Float(validate=validate.Range(min=0, max=1))


class ArticleQuerySchema(PageQuerySchema):
    q = fields.String(load_default=None, validate=validate.Length(max=100))
    status = fields.String(
        load_default=None, validate=validate.OneOf(["draft", "scheduled", "published", "archived"])
    )
    topic_id = fields.Integer(load_default=None)
    author_id = fields.Integer(load_default=None)
    featured = fields.Boolean(load_default=None)
    review_status = fields.String(
        load_default=None, validate=validate.OneOf(["none", "submitted", "approved"])
    )
    has_pending = fields.Boolean(load_default=None)
    mine = fields.Boolean(load_default=None)


class ArticleWriteSchema(StrictSchema):
    title = Text(200, required=True, min_len=1)
    slug = fields.String(allow_none=True, validate=[validate.Length(max=200), _slug])
    subtitle = Text(300, allow_none=True)
    excerpt = Text(500, allow_none=False)
    body = fields.List(fields.Dict(), validate=validate.Length(max=300))
    author_id = fields.Integer(allow_none=True)
    primary_topic_id = fields.Integer(allow_none=True)
    secondary_topic_ids = fields.List(fields.Integer(), validate=validate.Length(max=10))
    tag_ids = fields.List(fields.Integer(), validate=validate.Length(max=20))
    featured = fields.Boolean()
    featured_image_id = fields.Integer(allow_none=True)
    social_image_id = fields.Integer(allow_none=True)
    seo_title = Text(200, allow_none=True)
    meta_description = Text(320, allow_none=True)
    social_title = Text(200, allow_none=True)
    social_description = Text(320, allow_none=True)
    canonical_url = fields.String(allow_none=True, validate=[validate.Length(max=500), _https])
    noindex = fields.Boolean()
    original_url = fields.String(
        allow_none=True, validate=[validate.Length(max=500), _http_or_https]
    )
    original_slug = Text(200, allow_none=True)


class ArticleSaveSchema(ArticleWriteSchema):
    """PATCH payload: content fields plus save metadata (never stored as content)."""

    lock_version = fields.Integer(allow_none=True, validate=validate.Range(min=1))
    mode = fields.String(load_default="save", validate=validate.OneOf(["save", "autosave"]))
    change_summary = Text(200, allow_none=True)


class LockSchema(StrictSchema):
    lock_version = fields.Integer(allow_none=True, load_default=None)


class RevisionCompareSchema(Schema):
    class Meta:
        unknown = "exclude"

    from_id = fields.Integer(required=True, data_key="from")
    to_id = fields.Integer(required=True, data_key="to")


class SlugCheckSchema(Schema):
    class Meta:
        unknown = "exclude"

    slug = fields.String(required=True, validate=validate.Length(min=1, max=200))
    exclude = fields.Integer(load_default=None)


class RedirectWriteSchema(StrictSchema):
    source_path = fields.String(required=True, validate=validate.Length(min=1, max=500))
    destination = fields.String(required=True, validate=validate.Length(min=1, max=1000))
    status_code = fields.Integer(load_default=301)
    is_active = fields.Boolean(load_default=True)
    note = fields.String(allow_none=True, validate=validate.Length(max=300))


class RedirectQuerySchema(PageQuerySchema):
    q = fields.String(load_default=None, validate=validate.Length(max=100))
    active = fields.Boolean(load_default=None)
    origin = fields.String(
        load_default=None, validate=validate.OneOf(["manual", "slug_change", "import"])
    )
    page_size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=200))


class RedirectImportSchema(StrictSchema):
    csv = fields.String(required=True, validate=validate.Length(min=1, max=2_000_000))
    dry_run = fields.Boolean(load_default=False)


class JobQuerySchema(PageQuerySchema):
    status = fields.String(
        load_default=None,
        validate=validate.OneOf(["pending", "running", "succeeded", "failed", "cancelled"]),
    )


class PublishSchema(StrictSchema):
    published_at = fields.AwareDateTime(allow_none=True, load_default=None)


class ReassignSchema(StrictSchema):
    target_id = fields.Integer(required=True)


class TopicWriteSchema(StrictSchema):
    name = Text(120, required=True, min_len=1)
    slug = fields.String(allow_none=True, validate=[validate.Length(max=120), _slug])
    description = Text(500)
    intro = Text(2000)
    icon = fields.String(validate=validate.Length(max=40))
    featured = fields.Boolean()
    display_order = fields.Integer(validate=validate.Range(min=0, max=10_000))
    status = fields.String(validate=validate.OneOf(["active", "hidden", "archived"]))
    featured_image_id = fields.Integer(allow_none=True)
    seo_title = Text(200, allow_none=True)
    seo_description = Text(320, allow_none=True)


class AuthorWriteSchema(StrictSchema):
    display_name = Text(120, required=True, min_len=1)
    slug = fields.String(allow_none=True, validate=[validate.Length(max=120), _slug])
    bio = Text(2000)
    status = fields.String(validate=validate.OneOf(["active", "archived"]))
    profile_image_id = fields.Integer(allow_none=True)
    is_person = fields.Boolean()


class TagWriteSchema(StrictSchema):
    name = Text(80, required=True, min_len=1)
    slug = fields.String(allow_none=True, validate=[validate.Length(max=100), _slug])
    description = Text(300)


class PageWriteSchema(StrictSchema):
    title = Text(200, required=True, min_len=1)
    status = fields.String(validate=validate.OneOf(["draft", "published", "archived"]))
    seo_title = Text(200, allow_none=True)
    meta_description = Text(320, allow_none=True)
    noindex = fields.Boolean()


class SectionWriteSchema(StrictSchema):
    variant = fields.String(validate=validate.Length(max=40))
    content = fields.Dict()
    is_visible = fields.Boolean()


class SectionCreateSchema(StrictSchema):
    key = fields.String(required=True, validate=validate.Length(min=1, max=60))
    section_type = fields.String(required=True, validate=validate.Length(max=40))
    variant = fields.String(validate=validate.Length(max=40))
    content = fields.Dict()
    is_visible = fields.Boolean()


class ReorderSchema(StrictSchema):
    order = fields.List(fields.Integer(), required=True, validate=validate.Length(max=100))


class SettingsWriteSchema(StrictSchema):
    values = fields.Dict(required=True)


class NavigationWriteSchema(StrictSchema):
    items = fields.List(fields.Dict(), required=True)


class UserCreateSchema(StrictSchema):
    email = fields.String(required=True, validate=validate.Length(max=254))
    display_name = Text(120, required=True, min_len=1)
    password = fields.String(required=True, validate=validate.Length(max=256))
    roles = fields.List(fields.String(), required=True, validate=validate.Length(max=10))


class UserUpdateSchema(StrictSchema):
    display_name = Text(120, min_len=1)
    status = fields.String(validate=validate.OneOf(["active", "disabled"]))
    roles = fields.List(fields.String(), validate=validate.Length(max=10))


class ResetPasswordSchema(StrictSchema):
    password = fields.String(required=True, validate=validate.Length(max=256))


class AuditQuerySchema(PageQuerySchema):
    action = fields.String(load_default=None, validate=validate.Length(max=80))
    resource_type = fields.String(load_default=None, validate=validate.Length(max=50))
    actor_id = fields.Integer(load_default=None)


class UserQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    q = fields.String(load_default=None, validate=validate.Length(max=100))
    status = fields.String(load_default=None, validate=validate.OneOf(["active", "disabled"]))
    role = fields.String(load_default=None, validate=validate.Length(max=50))


class InvitationCreateSchema(StrictSchema):
    email = fields.String(required=True, validate=validate.Length(max=254))
    display_name = Text(120, allow_none=True)
    roles = fields.List(fields.String(), required=True, validate=validate.Length(min=1, max=10))


class RoleWriteSchema(StrictSchema):
    label = Text(80, required=True, min_len=1)
    description = Text(255, allow_none=True)
    permissions = fields.List(
        fields.String(validate=validate.Length(max=80)), validate=validate.Length(max=200)
    )
    is_active = fields.Boolean()


class RoleQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    include_inactive = fields.Boolean(load_default=True)


class InvitationQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    status = fields.String(
        load_default=None, validate=validate.OneOf(["pending", "accepted", "expired", "revoked"])
    )


class TokenSchema(StrictSchema):
    token = fields.String(required=True, validate=validate.Length(min=1, max=200))


class AcceptInvitationSchema(StrictSchema):
    token = fields.String(required=True, validate=validate.Length(min=1, max=200))
    password = fields.String(required=True, validate=validate.Length(max=256))
    display_name = fields.String(allow_none=True, validate=validate.Length(max=120))


class CompleteResetSchema(StrictSchema):
    token = fields.String(required=True, validate=validate.Length(min=1, max=200))
    password = fields.String(required=True, validate=validate.Length(max=256))


# ---- Batch 04: page builder, shared sections, CTAs, announcements ----------------------------


class PageCreateSchema(StrictSchema):
    title = Text(200, required=True, min_len=1)
    slug = fields.String(allow_none=True, validate=validate.Length(max=120))
    template = fields.String(load_default="standard", validate=validate.Length(max=40))
    parent_id = fields.Integer(allow_none=True, load_default=None)


class PageQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    status = fields.String(
        load_default=None, validate=validate.OneOf(["draft", "published", "archived"])
    )
    q = fields.String(load_default=None, validate=validate.Length(max=100))


class PageDraftSchema(StrictSchema):
    lock_version = fields.Integer(required=True, allow_none=True)
    page = fields.Dict(load_default=None)
    sections = fields.List(fields.Dict(), validate=validate.Length(max=60))


class PagePreviewSchema(StrictSchema):
    page = fields.Dict(load_default=None)
    sections = fields.List(fields.Dict(), validate=validate.Length(max=60))


class PageScheduleSchema(StrictSchema):
    scheduled_at = fields.AwareDateTime(required=True, default_timezone=UTC)
    lock_version = fields.Integer(required=True, allow_none=True)


class PageSlugCheckSchema(Schema):
    class Meta:
        unknown = "exclude"

    slug = fields.String(required=True, validate=validate.Length(min=1, max=120))
    parent_id = fields.Integer(load_default=None, allow_none=True)
    exclude = fields.Integer(load_default=None, allow_none=True)


class ShareSectionSchema(StrictSchema):
    name = Text(120, required=True, min_len=1)


class SharedSectionSchema(StrictSchema):
    name = fields.String(validate=validate.Length(max=200))
    description = fields.String(allow_none=True, validate=validate.Length(max=400))
    section_type = fields.String(validate=validate.Length(max=40))
    variant = fields.String(allow_none=True, validate=validate.Length(max=40))
    content = fields.Dict()
    design = fields.Dict(allow_none=True)
    lock_version = fields.Integer(allow_none=True)
    propagate = fields.Boolean(load_default=True)


class CtaSchema(StrictSchema):
    name = fields.String(validate=validate.Length(max=200))
    label = fields.String(validate=validate.Length(max=100))
    url = fields.String(validate=validate.Length(max=500))
    style = fields.String(validate=validate.Length(max=20))
    description = fields.String(allow_none=True, validate=validate.Length(max=400))


class AnnouncementSchema(StrictSchema):
    name = fields.String(validate=validate.Length(max=200))
    message = fields.String(validate=validate.Length(max=400))
    cta_label = fields.String(allow_none=True, validate=validate.Length(max=100))
    cta_url = fields.String(allow_none=True, validate=validate.Length(max=500))
    variant = fields.String(validate=validate.Length(max=20))
    target = fields.String(validate=validate.Length(max=20))
    target_paths = fields.List(fields.String(validate=validate.Length(max=400)))
    starts_at = fields.AwareDateTime(allow_none=True, default_timezone=UTC)
    ends_at = fields.AwareDateTime(allow_none=True, default_timezone=UTC)
    is_enabled = fields.Boolean()
    is_dismissible = fields.Boolean()


class SettingsQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    groups = fields.String(load_default=None, validate=validate.Length(max=200))


class LinkOptionsQuerySchema(Schema):
    class Meta:
        unknown = "exclude"

    q = fields.String(load_default="", validate=validate.Length(max=100))
