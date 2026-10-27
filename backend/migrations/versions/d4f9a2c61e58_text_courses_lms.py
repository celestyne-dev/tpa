"""Text-based courses and learning management.

Revision ID: d4f9a2c61e58
Revises: c3e8d1f20b47
Create Date: 2026-10-27

Additive only: new tables for course categories, courses (+ topics), modules, lessons,
assessments, questions, enrolments, lesson progress, attempts and certificates. Existing
tables are not altered.

Permissions: the placeholder "courses.manage" (never available) is replaced in the code
catalogue by ten granular course permissions appended at the end; permissions after the
old placeholder move up one place so the stored order matches the catalogue. Grants are
added to the built-in roles and templates exactly as the code defines them, so a later
RBAC sync changes nothing.

Downgrade refuses to run while any course exists (it would delete learner records).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "d4f9a2c61e58"
down_revision = "c3e8d1f20b47"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
NEW_PERMISSIONS = [
    ("courses.view", "View courses", ""),
    ("courses.create", "Create courses", ""),
    (
        "courses.edit",
        "Edit course details",
        "Descriptions, outcomes, pricing link, access rules, SEO and covers.",
    ),
    ("courses.publish", "Publish courses", "Publish, schedule and unpublish courses and lessons."),
    ("courses.archive", "Archive courses", ""),
    (
        "courses.manage_curriculum",
        "Manage course curriculum",
        "Modules, lessons, lesson content, order and worksheets.",
    ),
    (
        "courses.manage_assessments",
        "Manage assessments",
        "Quizzes, reflections, questions and answer keys.",
    ),
    (
        "courses.view_enrollments",
        "View enrolments and progress",
        "Learners, progress, assessment results and certificates.",
    ),
    (
        "courses.manage_enrollments",
        "Manage enrolments and certificates",
        "Enrol or remove learners, revoke or correct certificates.",
    ),
    ("courses.view_reports", "View course reports", ""),
]
_AUTHORING = [
    "courses.view",
    "courses.create",
    "courses.edit",
    "courses.manage_curriculum",
    "courses.manage_assessments",
]
_PUBLISHING = [*_AUTHORING, "courses.publish", "courses.archive"]
GRANTS = {
    "editor": _PUBLISHING,
    "analyst": ["courses.view", "courses.view_reports"],
    "administrator": [key for key, _, _ in NEW_PERMISSIONS],
    "editor_in_chief": [*_PUBLISHING, "courses.view_reports"],
    "content_editor": _AUTHORING,
    "customer_support": ["courses.view", "courses.view_enrollments", "courses.manage_enrollments"],
    "marketing_manager": ["courses.view", "courses.view_reports"],
    "product_manager": ["courses.view"],
    "website_manager": ["courses.view"],
}
PLACEHOLDER = "courses.manage"


def _permissions():
    return sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.String),
        sa.column("group", sa.String),
        sa.column("module", sa.String),
        sa.column("is_available", sa.Boolean),
        sa.column("is_sensitive", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )


ROLES = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
LINKS = sa.table(
    "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
)


def _add_permissions() -> None:
    bind = op.get_bind()
    permissions = _permissions()
    synced = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == NEW_PERMISSIONS[0][0])
    ).scalar()
    placeholder = bind.execute(
        sa.select(permissions.c.sort_order).where(permissions.c.key == PLACEHOLDER)
    ).scalar()
    if placeholder is not None and synced is None:
        # (Skipped when the new code's RBAC sync already ran: the order is then correct.)
        bind.execute(
            permissions.update()
            .where(permissions.c.sort_order > placeholder, permissions.c.key != PLACEHOLDER)
            .values(sort_order=permissions.c.sort_order - 1)
        )
    order = bind.execute(
        sa.select(sa.func.max(permissions.c.sort_order)).where(permissions.c.key != PLACEHOLDER)
    ).scalar()
    order = -1 if order is None else order
    ids = {}
    for key, label, description in NEW_PERMISSIONS:
        existing = bind.execute(
            sa.select(permissions.c.id).where(permissions.c.key == key)
        ).scalar()
        order += 1
        if existing is None:
            bind.execute(
                permissions.insert().values(
                    key=key,
                    label=label,
                    description=description,
                    group=GROUP,
                    module="courses",
                    is_available=True,
                    is_sensitive=False,
                    sort_order=order,
                )
            )
        ids[key] = bind.execute(
            sa.select(permissions.c.id).where(permissions.c.key == key)
        ).scalar()
    for role_name, keys in GRANTS.items():
        role_id = bind.execute(sa.select(ROLES.c.id).where(ROLES.c.name == role_name)).scalar()
        if role_id is None:
            continue  # created with these grants by the next RBAC sync
        for key in keys:
            linked = bind.execute(
                sa.select(LINKS.c.role_id).where(
                    LINKS.c.role_id == role_id, LINKS.c.permission_id == ids[key]
                )
            ).scalar()
            if linked is None:
                bind.execute(LINKS.insert().values(role_id=role_id, permission_id=ids[key]))


def _remove_permissions() -> None:
    bind = op.get_bind()
    permissions = _permissions()
    keys = [key for key, _, _ in NEW_PERMISSIONS]
    ids = list(
        bind.execute(sa.select(permissions.c.id).where(permissions.c.key.in_(keys))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(permissions.delete().where(permissions.c.id.in_(ids)))
    placeholder = bind.execute(
        sa.select(permissions.c.sort_order).where(permissions.c.key == PLACEHOLDER)
    ).scalar()
    if placeholder is not None:
        bind.execute(
            permissions.update()
            .where(permissions.c.sort_order >= placeholder, permissions.c.key != PLACEHOLDER)
            .values(sort_order=permissions.c.sort_order + 1)
        )


def upgrade():
    op.create_table(
        "course_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_course_categories_slug")),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column(
            "description",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "outcomes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "prerequisites",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "audience",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("cover_media_id", sa.Integer(), nullable=True),
        sa.Column("social_image_id", sa.Integer(), nullable=True),
        sa.Column("access_type", sa.String(length=10), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("enrollment_open", sa.Boolean(), nullable=False),
        sa.Column("access_days", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("certificate_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("featured_order", sa.Integer(), nullable=False),
        sa.Column("seo_title", sa.String(length=200), nullable=True),
        sa.Column("meta_description", sa.String(length=320), nullable=True),
        sa.Column("noindex", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "access_type IN ('free', 'premium')", name=op.f("ck_courses_access_type_valid")
        ),
        sa.CheckConstraint(
            "availability IN ('available', 'coming_soon')",
            name=op.f("ck_courses_availability_valid"),
        ),
        sa.CheckConstraint(
            "level IN ('beginner', 'intermediate', 'advanced', 'all_levels')",
            name=op.f("ck_courses_level_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'archived')",
            name=op.f("ck_courses_status_valid"),
        ),
        sa.CheckConstraint(
            "access_days IS NULL OR access_days > 0", name=op.f("ck_courses_access_days_positive")
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name=op.f("ck_courses_estimated_minutes_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name=op.f("fk_courses_author_id_authors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["course_categories.id"],
            name=op.f("fk_courses_category_id_course_categories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cover_media_id"],
            ["media_assets.id"],
            name=op.f("fk_courses_cover_media_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_courses_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_courses_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["social_image_id"],
            ["media_assets.id"],
            name=op.f("fk_courses_social_image_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_courses_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("product_id", name=op.f("uq_courses_product_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_courses_public_id")),
        sa.UniqueConstraint("slug", name=op.f("uq_courses_slug")),
    )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_courses_author_id"), ["author_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_courses_category_id"), ["category_id"], unique=False)
        batch_op.create_index("ix_courses_status_featured", ["status", "is_featured"], unique=False)

    op.create_table(
        "course_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column(
            "objectives",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_modules_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_modules")),
        sa.UniqueConstraint("course_id", "position", name="uq_course_modules_position"),
    )
    op.create_table(
        "course_topics",
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_topics_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_course_topics_topic_id_topics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("course_id", "topic_id", name=op.f("pk_course_topics")),
    )
    with op.batch_alter_table("course_topics", schema=None) as batch_op:
        batch_op.create_index("ix_course_topics_topic_id", ["topic_id"], unique=False)

    op.create_table(
        "course_lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column(
            "body",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_preview", sa.Boolean(), nullable=False),
        sa.Column("completion_required", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_course_lessons_status_valid")
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name=op.f("ck_course_lessons_estimated_minutes_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_lessons_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name=op.f("fk_course_lessons_module_id_course_modules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_course_lessons_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_lessons")),
        sa.UniqueConstraint("course_id", "slug", name="uq_course_lessons_slug"),
        sa.UniqueConstraint("module_id", "position", name="uq_course_lessons_position"),
    )
    with op.batch_alter_table("course_lessons", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_course_lessons_course_id"), ["course_id"], unique=False
        )

    op.create_table(
        "course_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("passing_score", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("show_answers", sa.String(length=20), nullable=False),
        sa.Column("required_for_completion", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('quiz', 'reflection', 'self_assessment')",
            name=op.f("ck_course_assessments_kind_valid"),
        ),
        sa.CheckConstraint(
            "show_answers IN ('after_submit', 'after_pass', 'never')",
            name=op.f("ck_course_assessments_show_answers_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_course_assessments_status_valid")
        ),
        sa.CheckConstraint(
            "max_attempts IS NULL OR max_attempts > 0",
            name=op.f("ck_course_assessments_max_attempts_positive"),
        ),
        sa.CheckConstraint(
            "passing_score IS NULL OR (passing_score >= 0 AND passing_score <= 100)",
            name=op.f("ck_course_assessments_passing_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_assessments_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_course_assessments_lesson_id_course_lessons"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_assessments")),
        sa.UniqueConstraint("course_id", "position", name="uq_course_assessments_position"),
    )
    with op.batch_alter_table("course_assessments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_course_assessments_lesson_id"), ["lesson_id"], unique=False
        )

    op.create_table(
        "course_enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("entitlement_id", sa.Integer(), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_lesson_id", sa.Integer(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=300), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "source IN ('free', 'purchase', 'manual')",
            name=op.f("ck_course_enrollments_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')", name=op.f("ck_course_enrollments_status_valid")
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name=op.f("ck_course_enrollments_progress_range"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_enrollments_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_course_enrollments_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            ["entitlements.id"],
            name=op.f("fk_course_enrollments_entitlement_id_entitlements"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["users.id"],
            name=op.f("fk_course_enrollments_granted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_course_enrollments_last_lesson_id_course_lessons"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_enrollments")),
        sa.UniqueConstraint("customer_id", "course_id", name="uq_course_enrollments_learner"),
    )
    with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
        batch_op.create_index(
            "ix_course_enrollments_course_status", ["course_id", "status"], unique=False
        )

    op.create_table(
        "assessment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "answers",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "results",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["course_assessments.id"],
            name=op.f("fk_assessment_attempts_assessment_id_course_assessments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["course_enrollments.id"],
            name=op.f("fk_assessment_attempts_enrollment_id_course_enrollments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_attempts")),
        sa.UniqueConstraint(
            "assessment_id", "enrollment_id", "attempt_number", name="uq_assessment_attempts_number"
        ),
    )
    with op.batch_alter_table("assessment_attempts", schema=None) as batch_op:
        batch_op.create_index("ix_assessment_attempts_enrollment", ["enrollment_id"], unique=False)

    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("prompt", sa.String(length=1000), nullable=False),
        sa.Column("help_text", sa.String(length=500), nullable=False),
        sa.Column(
            "options",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "correct",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.Column(
            "settings",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('single_choice', 'multiple_select', 'true_false', 'short_text', 'rating')",
            name=op.f("ck_assessment_questions_kind_valid"),
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_assessment_questions_points_non_negative")),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["course_assessments.id"],
            name=op.f("fk_assessment_questions_assessment_id_course_assessments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_questions")),
        sa.UniqueConstraint("assessment_id", "position", name="uq_assessment_questions_position"),
    )
    op.create_table(
        "course_certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("recipient_name", sa.String(length=160), nullable=False),
        sa.Column("course_title", sa.String(length=200), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=300), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction_note", sa.Text(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_certificates_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_course_certificates_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["course_enrollments.id"],
            name=op.f("fk_course_certificates_enrollment_id_course_enrollments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_course_certificates_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_certificates")),
        sa.UniqueConstraint("code", name=op.f("uq_course_certificates_code")),
        sa.UniqueConstraint("enrollment_id", name=op.f("uq_course_certificates_enrollment_id")),
    )
    with op.batch_alter_table("course_certificates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_course_certificates_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_course_certificates_customer_id"), ["customer_id"], unique=False
        )

    op.create_table(
        "lesson_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "responses",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["course_enrollments.id"],
            name=op.f("fk_lesson_progress_enrollment_id_course_enrollments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_lesson_progress_lesson_id_course_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_progress")),
        sa.UniqueConstraint("enrollment_id", "lesson_id", name="uq_lesson_progress_lesson"),
    )
    with op.batch_alter_table("lesson_progress", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_lesson_progress_lesson_id"), ["lesson_id"], unique=False
        )

    _add_permissions()


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM courses")).scalar():
        raise RuntimeError(
            "Courses exist; downgrading would delete them with their enrolments, progress and "
            "certificates. Back up the database and remove the courses first."
        )
    _remove_permissions()
    with op.batch_alter_table("lesson_progress", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_lesson_progress_lesson_id"))

    op.drop_table("lesson_progress")
    with op.batch_alter_table("course_certificates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_certificates_customer_id"))
        batch_op.drop_index(batch_op.f("ix_course_certificates_course_id"))

    op.drop_table("course_certificates")
    op.drop_table("assessment_questions")
    with op.batch_alter_table("assessment_attempts", schema=None) as batch_op:
        batch_op.drop_index("ix_assessment_attempts_enrollment")

    op.drop_table("assessment_attempts")
    with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
        batch_op.drop_index("ix_course_enrollments_course_status")

    op.drop_table("course_enrollments")
    with op.batch_alter_table("course_assessments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_assessments_lesson_id"))

    op.drop_table("course_assessments")
    with op.batch_alter_table("course_lessons", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_lessons_course_id"))

    op.drop_table("course_lessons")
    with op.batch_alter_table("course_topics", schema=None) as batch_op:
        batch_op.drop_index("ix_course_topics_topic_id")

    op.drop_table("course_topics")
    op.drop_table("course_modules")
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_index("ix_courses_status_featured")
        batch_op.drop_index(batch_op.f("ix_courses_category_id"))
        batch_op.drop_index(batch_op.f("ix_courses_author_id"))

    op.drop_table("courses")
    op.drop_table("course_categories")
