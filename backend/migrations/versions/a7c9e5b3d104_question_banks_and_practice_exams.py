"""Question banks, practice exams and started (timed) assessment attempts (Batch 09.2,
phase 2).

Revision ID: a7c9e5b3d104
Revises: f6b8d4a2c913
Create Date: 2026-10-29

- New tables ``question_banks`` and ``bank_questions``.
- ``course_assessments`` gains ``practice``, ``time_limit_minutes``, ``selection``,
  ``shuffle_questions`` and ``shuffle_options``. Existing assessments get the defaults
  (not practice, untimed, no draws, no shuffling), so they behave exactly as before and
  completion requirements are unchanged.
- ``assessment_attempts`` gains ``status``, ``started_at``, ``deadline_at``, ``snapshot``
  and ``lock_version``; ``submitted_at`` becomes nullable (in-progress attempts). Every
  existing attempt becomes ``status = 'submitted'`` with its answers, scores, results and
  submission time untouched, so pass states, progress and certificates are preserved.
- Two ``question_banks.*`` permissions are appended with the grants the code defines.

Downgrade refuses while any question bank, in-progress or expired attempt, practice exam,
timed or drawn assessment exists, since that data could not be represented afterwards.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "a7c9e5b3d104"
down_revision = "f6b8d4a2c913"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
NEW_PERMISSIONS = [
    (
        "question_banks.view",
        "View question banks",
        "List banks and their questions, without answer keys.",
    ),
    (
        "question_banks.manage",
        "Manage question banks",
        "Create and edit banks and questions, including answer keys.",
    ),
]
_ALL = [key for key, _, _ in NEW_PERMISSIONS]
GRANTS = {
    "administrator": _ALL,
    "editor_in_chief": _ALL,
    "editor": _ALL,
    "content_editor": _ALL,
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


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def _foreign_keys(enabled: bool) -> None:
    """SQLite rebuilds ``course_assessments`` (referenced by questions and attempts) to
    add constrained columns; dropping the old table must not cascade into learners'
    attempts, so enforcement is paused meanwhile (it can only change outside a
    transaction)."""
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


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


def upgrade():
    op.create_table(
        "question_banks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'archived')", name=op.f("ck_question_banks_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_question_banks_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_banks")),
        sa.UniqueConstraint("public_id", name=op.f("uq_question_banks_public_id")),
    )
    op.create_table(
        "bank_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("bank_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("prompt", sa.String(length=1000), nullable=False),
        sa.Column("help_text", sa.String(length=500), nullable=False),
        sa.Column("options", _json(), nullable=False),
        sa.Column("correct", _json(), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.Column("settings", _json(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("tags", _json(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('single_choice', 'multiple_select', 'true_false', 'short_text', 'rating')",
            name=op.f("ck_bank_questions_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')", name=op.f("ck_bank_questions_status_valid")
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_bank_questions_points_non_negative")),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["question_banks.id"],
            name=op.f("fk_bank_questions_bank_id_question_banks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_questions")),
        sa.UniqueConstraint("public_id", name=op.f("uq_bank_questions_public_id")),
    )
    with op.batch_alter_table("bank_questions", schema=None) as batch_op:
        batch_op.create_index("ix_bank_questions_bank_status", ["bank_id", "status"], unique=False)

    _foreign_keys(False)
    try:
        with op.batch_alter_table("course_assessments", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("practice", sa.Boolean(), server_default=sa.false(), nullable=False)
            )
            batch_op.add_column(sa.Column("time_limit_minutes", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("selection", _json(), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "shuffle_questions", sa.Boolean(), server_default=sa.false(), nullable=False
                )
            )
            batch_op.add_column(
                sa.Column(
                    "shuffle_options", sa.Boolean(), server_default=sa.false(), nullable=False
                )
            )
            batch_op.create_check_constraint(
                batch_op.f("ck_course_assessments_time_limit_range"),
                "time_limit_minutes IS NULL OR "
                "(time_limit_minutes > 0 AND time_limit_minutes <= 600)",
            )

        with op.batch_alter_table("assessment_attempts", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "status", sa.String(length=20), server_default="submitted", nullable=False
                )
            )
            batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("snapshot", _json(), nullable=True))
            batch_op.add_column(
                sa.Column("lock_version", sa.Integer(), server_default="1", nullable=False)
            )
            batch_op.alter_column(
                "submitted_at", existing_type=sa.DateTime(timezone=True), nullable=True
            )
            batch_op.create_check_constraint(
                batch_op.f("ck_assessment_attempts_status_valid"),
                "status IN ('in_progress', 'submitted', 'expired')",
            )
    finally:
        _foreign_keys(True)

    _add_permissions(op.get_bind())


def downgrade():
    bind = op.get_bind()
    checks = (
        ("SELECT COUNT(*) FROM question_banks", "Question banks exist"),
        (
            "SELECT COUNT(*) FROM assessment_attempts WHERE status <> 'submitted'",
            "Started or expired assessment attempts exist",
        ),
        (
            "SELECT COUNT(*) FROM course_assessments WHERE practice = :t "
            "OR time_limit_minutes IS NOT NULL OR selection IS NOT NULL "
            "OR shuffle_questions = :t OR shuffle_options = :t",
            "Practice, timed, drawn or shuffled assessments exist",
        ),
    )
    for sql, problem in checks:
        if bind.execute(sa.text(sql), {"t": True} if ":t" in sql else {}).scalar():
            raise RuntimeError(
                f"{problem}; downgrading would lose them or learners' attempts. Back up the "
                "database and remove them first."
            )
    ids = list(
        bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key.in_(_ALL))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))

    _foreign_keys(False)
    try:
        with op.batch_alter_table("assessment_attempts", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("ck_assessment_attempts_status_valid"), type_="check"
            )
            batch_op.alter_column(
                "submitted_at", existing_type=sa.DateTime(timezone=True), nullable=False
            )
            batch_op.drop_column("lock_version")
            batch_op.drop_column("snapshot")
            batch_op.drop_column("deadline_at")
            batch_op.drop_column("started_at")
            batch_op.drop_column("status")

        with op.batch_alter_table("course_assessments", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("ck_course_assessments_time_limit_range"), type_="check"
            )
            batch_op.drop_column("shuffle_options")
            batch_op.drop_column("shuffle_questions")
            batch_op.drop_column("selection")
            batch_op.drop_column("time_limit_minutes")
            batch_op.drop_column("practice")
    finally:
        _foreign_keys(True)

    with op.batch_alter_table("bank_questions", schema=None) as batch_op:
        batch_op.drop_index("ix_bank_questions_bank_status")

    op.drop_table("bank_questions")
    op.drop_table("question_banks")
