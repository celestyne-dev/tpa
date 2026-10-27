"""Premium reading and study experience; lesson drafts and revisions.

Revision ID: e5a7c3b91d20
Revises: d4f9a2c61e58
Create Date: 2026-10-27

Additive: new tables for lesson revisions, learner notes, highlights, bookmarks, reading
preferences and the lesson search index; new nullable/defaulted columns on
``course_lessons`` (draft working copy, lock version, live revision) and
``lesson_progress`` (saved checklist ticks, reading position).

Data steps (existing content is preserved word for word):
- every lesson block gets a stable ``uid`` and checklist items become
  ``{"id", "text"}`` objects, so highlights and ticks can point at them;
- every published lesson gets revision 1 ("migrated") holding its current live content;
- the search index is filled from published lessons of published/archived courses
  (PostgreSQL also gets a full-text GIN index);
- five lesson permissions are appended with the default grants the code defines, so a
  later RBAC sync changes nothing.

Downgrade refuses to run while learners have notes, highlights or bookmarks, or while any
lesson has unpublished draft changes (they would be lost). Otherwise it restores the
Batch 09 content format (no uids, checklist items as text).
"""

import json
import re
import secrets
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "e5a7c3b91d20"
down_revision = "d4f9a2c61e58"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
NEW_PERMISSIONS = [
    (
        "courses.view_drafts",
        "Read lesson drafts",
        "Open lesson drafts and preview unpublished lesson changes.",
    ),
    (
        "courses.edit_drafts",
        "Edit lesson drafts",
        "Change lesson text and settings in the draft (learners don't see it).",
    ),
    (
        "courses.publish_lessons",
        "Publish lessons",
        "Publish lesson changes to learners, or unpublish lessons.",
    ),
    (
        "courses.view_revisions",
        "View lesson revisions",
        "Revision history and comparisons between lesson versions.",
    ),
    (
        "courses.restore_revisions",
        "Restore lesson revisions",
        "Copy an earlier published version back into the lesson draft.",
    ),
]
_DRAFTING = ["courses.view_drafts", "courses.edit_drafts", "courses.view_revisions"]
_PUBLISHING = [key for key, _, _ in NEW_PERMISSIONS]
GRANTS = {
    "editor": _PUBLISHING,
    "administrator": _PUBLISHING,
    "editor_in_chief": _PUBLISHING,
    "content_editor": _DRAFTING,
}

PERMISSIONS = sa.table(
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
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")
LESSONS = sa.table(
    "course_lessons",
    sa.column("id", sa.Integer),
    sa.column("course_id", sa.Integer),
    sa.column("title", sa.String),
    sa.column("summary", sa.String),
    sa.column("body", JSON),
    sa.column("estimated_minutes", sa.Integer),
    sa.column("is_preview", sa.Boolean),
    sa.column("completion_required", sa.Boolean),
    sa.column("status", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("draft", JSON),
    sa.column("live_revision", sa.Integer),
    sa.column("content_published_at", sa.DateTime(timezone=True)),
)
REVISIONS = sa.table(
    "course_lesson_revisions",
    sa.column("lesson_id", sa.Integer),
    sa.column("number", sa.Integer),
    sa.column("title", sa.String),
    sa.column("summary", sa.String),
    sa.column("body", JSON),
    sa.column("estimated_minutes", sa.Integer),
    sa.column("is_preview", sa.Boolean),
    sa.column("completion_required", sa.Boolean),
    sa.column("action", sa.String),
    sa.column("note", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
SEARCH = sa.table(
    "course_lesson_search",
    sa.column("lesson_id", sa.Integer),
    sa.column("course_id", sa.Integer),
    sa.column("content", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
COURSES = sa.table("courses", sa.column("id", sa.Integer), sa.column("status", sa.String))
_SPACE = re.compile(r"\s+")


def _foreign_keys(enabled: bool) -> None:
    """SQLite rebuilds ``course_lessons``/``lesson_progress`` to add columns with
    constraints; dropping the old table must not cascade into progress, assessments or
    enrolments, so enforcement is paused meanwhile (it can only change outside a
    transaction)."""
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


def _with_ids(body):
    """Batch 09.1 content format: block uids and checklist item ids."""
    out = []
    used = set()
    for block in _loads(body) or []:
        block = dict(block)
        if not isinstance(block.get("uid"), str) or block["uid"] in used:
            block["uid"] = secrets.token_hex(5)
        used.add(block["uid"])
        if block.get("type") == "checklist":
            block["items"] = [
                item if isinstance(item, dict) else {"id": secrets.token_hex(5), "text": str(item)}
                for item in block.get("items", [])
            ]
            block.setdefault("required", False)
        out.append(block)
    return out


def _without_ids(body):
    """Batch 09 content format (for downgrade)."""
    out = []
    for block in _loads(body) or []:
        block = {k: v for k, v in dict(block).items() if k != "uid"}
        if block.get("type") == "checklist":
            block["items"] = [
                item.get("text", "") if isinstance(item, dict) else item
                for item in block.get("items", [])
            ]
            block.pop("required", None)
        out.append(block)
    return out


def _plain(body):
    """Searchable text of a lesson (same fields as services/courses/content.block_text)."""
    parts = []
    for b in body or []:
        for field in ("title", "text", "prompt", "caption", "cite"):
            if isinstance(b.get(field), str):
                parts.append(b[field])
        for item in b.get("items", []) if isinstance(b.get("items"), list) else []:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.extend(str(item.get(k, "")) for k in ("text", "label", "note", "caption"))
    return "\n".join(_SPACE.sub(" ", p).strip() for p in parts if p and p.strip())


def _add_permissions(bind) -> None:
    order = bind.execute(sa.select(sa.func.max(PERMISSIONS.c.sort_order))).scalar()
    order = -1 if order is None else order
    ids = {}
    for key, label, description in NEW_PERMISSIONS:
        existing = bind.execute(
            sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key == key)
        ).scalar()
        if existing is None:
            order += 1
            bind.execute(
                PERMISSIONS.insert().values(
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
            sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key == key)
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


def _migrate_content(bind) -> None:
    now = datetime.now(UTC)
    live_courses = {
        row.id
        for row in bind.execute(
            sa.select(COURSES.c.id).where(COURSES.c.status.in_(("published", "archived")))
        )
    }
    for row in bind.execute(sa.select(LESSONS)).fetchall():
        body = _with_ids(row.body)
        values = {"body": body}
        if row.status == "published":
            published_at = row.updated_at or now
            bind.execute(
                REVISIONS.insert().values(
                    lesson_id=row.id,
                    number=1,
                    title=row.title,
                    summary=row.summary or "",
                    body=body,
                    estimated_minutes=row.estimated_minutes,
                    is_preview=bool(row.is_preview),
                    completion_required=bool(row.completion_required),
                    action="migrated",
                    note="Content published before lesson revisions existed.",
                    created_at=published_at,
                )
            )
            values |= {"live_revision": 1, "content_published_at": published_at}
            if row.course_id in live_courses:
                bind.execute(
                    SEARCH.insert().values(
                        lesson_id=row.id,
                        course_id=row.course_id,
                        content=_plain(body),
                        updated_at=now,
                    )
                )
        bind.execute(LESSONS.update().where(LESSONS.c.id == row.id).values(**values))


def upgrade():
    op.create_table(
        "learner_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column(
            "reading",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_learner_preferences_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_preferences")),
        sa.UniqueConstraint("customer_id", name=op.f("uq_learner_preferences_customer_id")),
    )
    op.create_table(
        "course_lesson_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column(
            "body",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("is_preview", sa.Boolean(), nullable=False),
        sa.Column("completion_required", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("restored_from", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('migrated', 'published', 'restored')",
            name=op.f("ck_course_lesson_revisions_action_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_course_lesson_revisions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_course_lesson_revisions_lesson_id_course_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_lesson_revisions")),
        sa.UniqueConstraint("lesson_id", "number", name="uq_course_lesson_revisions_number"),
    )
    op.create_table(
        "course_lesson_search",
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_lesson_search_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_course_lesson_search_lesson_id_course_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lesson_id", name=op.f("pk_course_lesson_search")),
    )
    with op.batch_alter_table("course_lesson_search", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_course_lesson_search_course_id"), ["course_id"], unique=False
        )

    op.create_table(
        "learner_bookmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_learner_bookmarks_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_learner_bookmarks_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_learner_bookmarks_lesson_id_course_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_bookmarks")),
        sa.UniqueConstraint("customer_id", "lesson_id", name="uq_learner_bookmarks_lesson"),
    )
    with op.batch_alter_table("learner_bookmarks", schema=None) as batch_op:
        batch_op.create_index(
            "ix_learner_bookmarks_customer_course", ["customer_id", "course_id"], unique=False
        )

    op.create_table(
        "learner_highlights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("lesson_title", sa.String(length=200), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column(
            "anchor",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("anchor_status", sa.String(length=20), nullable=False),
        sa.Column("anchored_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "anchor_status IN ('anchored', 'orphaned')",
            name=op.f("ck_learner_highlights_anchor_status_valid"),
        ),
        sa.CheckConstraint(
            "color IN ('yellow', 'green', 'blue', 'pink')",
            name=op.f("ck_learner_highlights_color_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_learner_highlights_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_learner_highlights_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_learner_highlights_lesson_id_course_lessons"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_highlights")),
        sa.UniqueConstraint("public_id", name=op.f("uq_learner_highlights_public_id")),
    )
    with op.batch_alter_table("learner_highlights", schema=None) as batch_op:
        batch_op.create_index(
            "ix_learner_highlights_customer_course", ["customer_id", "course_id"], unique=False
        )
        batch_op.create_index("ix_learner_highlights_lesson", ["lesson_id"], unique=False)

    op.create_table(
        "learner_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("lesson_title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "anchor",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("anchor_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "anchor_status IS NULL OR anchor_status IN ('anchored', 'orphaned')",
            name=op.f("ck_learner_notes_anchor_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_learner_notes_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_learner_notes_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_learner_notes_lesson_id_course_lessons"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner_notes")),
        sa.UniqueConstraint("public_id", name=op.f("uq_learner_notes_public_id")),
    )
    with op.batch_alter_table("learner_notes", schema=None) as batch_op:
        batch_op.create_index(
            "ix_learner_notes_customer_course", ["customer_id", "course_id"], unique=False
        )
        batch_op.create_index("ix_learner_notes_lesson", ["lesson_id"], unique=False)

    _foreign_keys(False)
    try:
        with op.batch_alter_table("course_lessons", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "draft",
                    sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False)
            )
            batch_op.add_column(
                sa.Column("draft_saved_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch_op.add_column(sa.Column("draft_saved_by_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("live_revision", sa.Integer(), nullable=True))
            batch_op.add_column(
                sa.Column("content_published_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch_op.create_foreign_key(
                batch_op.f("fk_course_lessons_draft_saved_by_id_users"),
                "users",
                ["draft_saved_by_id"],
                ["id"],
                ondelete="SET NULL",
            )

        with op.batch_alter_table("lesson_progress", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "checklist",
                    sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
                    server_default="[]",
                    nullable=False,
                )
            )
            batch_op.add_column(
                sa.Column(
                    "position",
                    sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
                    nullable=True,
                )
            )
            batch_op.add_column(
                sa.Column("position_saved_at", sa.DateTime(timezone=True), nullable=True)
            )
    finally:
        _foreign_keys(True)

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_course_lesson_search_fts ON course_lesson_search "
            "USING gin (to_tsvector('english', content))"
        )
    bind = op.get_bind()
    _migrate_content(bind)
    _add_permissions(bind)


def downgrade():
    bind = op.get_bind()
    for table in ("learner_notes", "learner_highlights", "learner_bookmarks"):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError(
                f"Learners have saved study records ({table}); downgrading would delete them. "
                "Back up the database and export or remove them first."
            )
    if bind.execute(
        sa.text("SELECT COUNT(*) FROM course_lessons WHERE draft IS NOT NULL")
    ).scalar():
        raise RuntimeError(
            "Some lessons have unpublished draft changes; publish or discard them before "
            "downgrading (the previous version has no lesson drafts)."
        )
    ids = list(
        bind.execute(
            sa.select(PERMISSIONS.c.id).where(
                PERMISSIONS.c.key.in_([k for k, _, _ in NEW_PERMISSIONS])
            )
        ).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))
    for row in bind.execute(sa.select(LESSONS.c.id, LESSONS.c.body)).fetchall():
        bind.execute(
            LESSONS.update().where(LESSONS.c.id == row.id).values(body=_without_ids(row.body))
        )
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_course_lesson_search_fts")

    _foreign_keys(False)
    try:
        with op.batch_alter_table("lesson_progress", schema=None) as batch_op:
            batch_op.drop_column("position_saved_at")
            batch_op.drop_column("position")
            batch_op.drop_column("checklist")

        with op.batch_alter_table("course_lessons", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("fk_course_lessons_draft_saved_by_id_users"), type_="foreignkey"
            )
            batch_op.drop_column("content_published_at")
            batch_op.drop_column("live_revision")
            batch_op.drop_column("draft_saved_by_id")
            batch_op.drop_column("draft_saved_at")
            batch_op.drop_column("lock_version")
            batch_op.drop_column("draft")
    finally:
        _foreign_keys(True)

    with op.batch_alter_table("learner_notes", schema=None) as batch_op:
        batch_op.drop_index("ix_learner_notes_lesson")
        batch_op.drop_index("ix_learner_notes_customer_course")

    op.drop_table("learner_notes")
    with op.batch_alter_table("learner_highlights", schema=None) as batch_op:
        batch_op.drop_index("ix_learner_highlights_lesson")
        batch_op.drop_index("ix_learner_highlights_customer_course")

    op.drop_table("learner_highlights")
    with op.batch_alter_table("learner_bookmarks", schema=None) as batch_op:
        batch_op.drop_index("ix_learner_bookmarks_customer_course")

    op.drop_table("learner_bookmarks")
    with op.batch_alter_table("course_lesson_search", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_lesson_search_course_id"))

    op.drop_table("course_lesson_search")
    op.drop_table("course_lesson_revisions")
    op.drop_table("learner_preferences")
