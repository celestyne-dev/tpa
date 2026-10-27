"""Written assignments, submissions, rubrics and grading (Batch 09.2, phase 1).

Revision ID: f6b8d4a2c913
Revises: e5a7c3b91d20
Create Date: 2026-10-28

Additive only: new tables for course assignments, immutable rubric versions, learner
submissions and attempts, grades, supporting documents, grading exceptions and course
assessors. No existing table is altered, so accounts, courses, lessons, attempts,
progress and certificates are untouched. Seven ``assignments.*`` permissions are appended
with the default grants the code defines (a later RBAC sync changes nothing).

Downgrade refuses while any assignment exists (it would delete learners' work).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "f6b8d4a2c913"
down_revision = "e5a7c3b91d20"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
NEW_PERMISSIONS = [
    ("assignments.view", "View assignments", ""),
    (
        "assignments.manage",
        "Manage assignments",
        "Assignment definitions, rubrics, publishing and course assessors.",
    ),
    (
        "assignments.view_submissions",
        "View submissions",
        "Read learners' submitted work and documents (assigned courses only).",
    ),
    (
        "assignments.grade",
        "Grade submissions",
        "Score submissions and save draft grades and feedback.",
    ),
    (
        "assignments.publish_grades",
        "Publish grades",
        "Release grades and feedback to learners, request revisions, retract.",
    ),
    (
        "assignments.manage_exceptions",
        "Manage grading exceptions",
        "Deadline extensions and extra attempts for individual learners.",
    ),
    ("assignments.view_reports", "View assignment reports", ""),
]
_ALL = [key for key, _, _ in NEW_PERMISSIONS]
_GRADING = ["assignments.view", "assignments.view_submissions", "assignments.grade"]
GRANTS = {
    "administrator": _ALL,
    "editor_in_chief": _ALL,
    "editor": [k for k in _ALL if k != "assignments.manage_exceptions"],
    "content_editor": [*_GRADING, "assignments.manage"],
    "analyst": ["assignments.view", "assignments.view_reports"],
    "customer_support": ["assignments.view", "assignments.manage_exceptions"],
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
        "course_assessors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("added_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            name=op.f("fk_course_assessors_added_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_assessors_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_course_assessors_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_assessors")),
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_assessors_user"),
    )
    with op.batch_alter_table("course_assessors", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_course_assessors_user_id"), ["user_id"], unique=False)

    op.create_table(
        "course_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "prompts",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "requirements",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("passing_percent", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=True),
        sa.Column("resubmission_policy", sa.String(length=20), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_policy", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=True),
        sa.Column("required_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('written', 'project', 'case_study', 'essay', 'reflection')",
            name=op.f("ck_course_assignments_kind_valid"),
        ),
        sa.CheckConstraint(
            "late_policy IN ('block', 'allow')",
            name=op.f("ck_course_assignments_late_policy_valid"),
        ),
        sa.CheckConstraint(
            "resubmission_policy IN ('none', 'on_request', 'always')",
            name=op.f("ck_course_assignments_resubmission_policy_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_course_assignments_status_valid"),
        ),
        sa.CheckConstraint(
            "max_attempts IS NULL OR max_attempts > 0",
            name=op.f("ck_course_assignments_max_attempts_positive"),
        ),
        sa.CheckConstraint(
            "passing_percent IS NULL OR (passing_percent >= 0 AND passing_percent <= 100)",
            name=op.f("ck_course_assignments_passing_percent_range"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_assignments_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_course_assignments_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["course_lessons.id"],
            name=op.f("fk_course_assignments_lesson_id_course_lessons"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_course_assignments_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_assignments")),
        sa.UniqueConstraint("course_id", "position", name="uq_course_assignments_position"),
        sa.UniqueConstraint("public_id", name=op.f("uq_course_assignments_public_id")),
    )
    with op.batch_alter_table("course_assignments", schema=None) as batch_op:
        batch_op.create_index(
            "ix_course_assignments_course_status", ["course_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_course_assignments_lesson_id"), ["lesson_id"], unique=False
        )

    op.create_table(
        "assignment_exceptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_attempts", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "extra_attempts >= 0", name=op.f("ck_assignment_exceptions_extra_attempts_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["course_assignments.id"],
            name=op.f("fk_assignment_exceptions_assignment_id_course_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["course_enrollments.id"],
            name=op.f("fk_assignment_exceptions_enrollment_id_course_enrollments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["users.id"],
            name=op.f("fk_assignment_exceptions_granted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"],
            ["users.id"],
            name=op.f("fk_assignment_exceptions_revoked_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_exceptions")),
    )
    with op.batch_alter_table("assignment_exceptions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_assignment_exceptions_learner", ["assignment_id", "enrollment_id"], unique=False
        )

    op.create_table(
        "assignment_rubrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "criteria",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("total_points", sa.Integer(), nullable=False),
        sa.Column("passing_percent", sa.Integer(), nullable=False),
        sa.Column("feedback_required", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "passing_percent >= 0 AND passing_percent <= 100",
            name=op.f("ck_assignment_rubrics_passing_percent_range"),
        ),
        sa.CheckConstraint(
            "total_points > 0", name=op.f("ck_assignment_rubrics_total_points_positive")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["course_assignments.id"],
            name=op.f("fk_assignment_rubrics_assignment_id_course_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_assignment_rubrics_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_rubrics")),
        sa.UniqueConstraint("assignment_id", "version", name="uq_assignment_rubrics_version"),
    )
    op.create_table(
        "assignment_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'under_review', 'changes_requested', "
            "'resubmitted', 'graded', 'completed')",
            name=op.f("ck_assignment_submissions_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["course_assignments.id"],
            name=op.f("fk_assignment_submissions_assignment_id_course_assignments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_assignment_submissions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["course_enrollments.id"],
            name=op.f("fk_assignment_submissions_enrollment_id_course_enrollments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_submissions")),
        sa.UniqueConstraint(
            "assignment_id", "enrollment_id", name="uq_assignment_submissions_learner"
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_assignment_submissions_public_id")),
    )
    with op.batch_alter_table("assignment_submissions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_assignment_submissions_assignment_status", ["assignment_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_assignment_submissions_customer_id"), ["customer_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_assignment_submissions_enrollment_id"), ["enrollment_id"], unique=False
        )

    op.create_table(
        "assignment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "responses",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted')", name=op.f("ck_assignment_attempts_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["assignment_submissions.id"],
            name=op.f("fk_assignment_attempts_submission_id_assignment_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_attempts")),
        sa.UniqueConstraint("public_id", name=op.f("uq_assignment_attempts_public_id")),
        sa.UniqueConstraint(
            "submission_id", "idempotency_key", name="uq_assignment_attempts_idempotency"
        ),
        sa.UniqueConstraint("submission_id", "number", name="uq_assignment_attempts_number"),
    )
    op.create_table(
        "assignment_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["assignment_attempts.id"],
            name=op.f("fk_assignment_files_attempt_id_assignment_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_assignment_files_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_files")),
        sa.UniqueConstraint("public_id", name=op.f("uq_assignment_files_public_id")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_assignment_files_storage_key")),
    )
    with op.batch_alter_table("assignment_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_assignment_files_attempt_id"), ["attempt_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_assignment_files_customer_id"), ["customer_id"], unique=False
        )

    op.create_table(
        "assignment_grades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("rubric_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column(
            "scores",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("total_points", sa.Integer(), nullable=True),
        sa.Column("max_points", sa.Integer(), nullable=True),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("private_notes", sa.Text(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("grader_id", sa.Integer(), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_id", sa.Integer(), nullable=True),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retracted_reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('graded', 'changes_requested')",
            name=op.f("ck_assignment_grades_outcome_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retracted')",
            name=op.f("ck_assignment_grades_status_valid"),
        ),
        sa.CheckConstraint(
            "percent IS NULL OR (percent >= 0 AND percent <= 100)",
            name=op.f("ck_assignment_grades_percent_range"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["assignment_attempts.id"],
            name=op.f("fk_assignment_grades_attempt_id_assignment_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grader_id"],
            ["users.id"],
            name=op.f("fk_assignment_grades_grader_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_id"],
            ["users.id"],
            name=op.f("fk_assignment_grades_published_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["assignment_rubrics.id"],
            name=op.f("fk_assignment_grades_rubric_id_assignment_rubrics"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_grades")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_assignment_grades_attempt_id")),
    )
    with op.batch_alter_table("assignment_grades", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_assignment_grades_rubric_id"), ["rubric_id"], unique=False
        )
    _add_permissions(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM course_assignments")).scalar():
        raise RuntimeError(
            "Assignments exist; downgrading would delete them with learners' submissions, "
            "documents and grades. Back up the database and remove the assignments first."
        )
    ids = list(
        bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key.in_(_ALL))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))

    with op.batch_alter_table("assignment_grades", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assignment_grades_rubric_id"))

    op.drop_table("assignment_grades")
    with op.batch_alter_table("assignment_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assignment_files_customer_id"))
        batch_op.drop_index(batch_op.f("ix_assignment_files_attempt_id"))

    op.drop_table("assignment_files")
    op.drop_table("assignment_attempts")
    with op.batch_alter_table("assignment_submissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assignment_submissions_enrollment_id"))
        batch_op.drop_index(batch_op.f("ix_assignment_submissions_customer_id"))
        batch_op.drop_index("ix_assignment_submissions_assignment_status")

    op.drop_table("assignment_submissions")
    op.drop_table("assignment_rubrics")
    with op.batch_alter_table("assignment_exceptions", schema=None) as batch_op:
        batch_op.drop_index("ix_assignment_exceptions_learner")

    op.drop_table("assignment_exceptions")
    with op.batch_alter_table("course_assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_assignments_lesson_id"))
        batch_op.drop_index("ix_course_assignments_course_status")

    op.drop_table("course_assignments")
    with op.batch_alter_table("course_assessors", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_assessors_user_id"))

    op.drop_table("course_assessors")
