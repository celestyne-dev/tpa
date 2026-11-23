"""Automatic certificates of completion: completion awards, certificate snapshots,
reissue lineage and issuance emails.

Revision ID: c3e9a5f17b42
Revises: f2b6d8e0a314
Create Date: 2026-11-23

Additive and backward-compatible; no existing row is changed:

- ``course_enrollments.completion_snapshot`` (nullable JSON): what the learner had met when
  the completion was awarded. Completions recorded before this release keep NULL; they are
  re-checked against the course's current requirements before a certificate is issued.
- ``course_certificates``: snapshot columns (course slug, completion date, signatory),
  ``replaces_id`` / ``reissue_reason`` for controlled reissuance, and email delivery state
  (``email_status`` NULL for existing certificates, so they are never emailed retroactively;
  ``email_claimed_at`` lets a send that died mid-way be recovered).
- The unique constraint on ``course_certificates.enrollment_id`` (one certificate per
  enrolment, ever) becomes a partial unique index: one *valid* (not revoked) certificate per
  enrolment. A revoked certificate stays as it is and a reissue is a new row with a new code.

Downgrade restores the old constraint; it fails while an enrolment has a reissued
certificate (revoked original plus its replacement), which must be resolved by hand first.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3e9a5f17b42"
down_revision = "f2b6d8e0a314"
branch_labels = None
depends_on = None

ACTIVE = sa.text("revoked_at IS NULL")


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade():
    with op.batch_alter_table("course_enrollments") as batch_op:
        batch_op.add_column(sa.Column("completion_snapshot", _json(), nullable=True))

    with op.batch_alter_table("course_certificates") as batch_op:
        batch_op.add_column(sa.Column("course_slug", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("signatory_name", sa.String(length=120), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("signatory_title", sa.String(length=120), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("replaces_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("reissue_reason", sa.String(length=300), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("email_status", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column("email_attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("email_claimed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_course_certificates_replaces_id_course_certificates"),
            "course_certificates",
            ["replaces_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint("uq_course_certificates_enrollment_id", type_="unique")
        batch_op.create_index(
            batch_op.f("ix_course_certificates_enrollment_id"), ["enrollment_id"], unique=False
        )
        batch_op.create_index(
            "uq_course_certificates_active",
            ["enrollment_id"],
            unique=True,
            postgresql_where=ACTIVE,
            sqlite_where=ACTIVE,
        )
        batch_op.create_index(
            batch_op.f("ix_course_certificates_email_status"), ["email_status"], unique=False
        )


def downgrade():
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        # SQLite rebuilds both tables to drop columns; rows that reference them stay
        # intact, so foreign-key checks pause meanwhile.
        op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("course_certificates") as batch_op:
        batch_op.drop_index(batch_op.f("ix_course_certificates_email_status"))
        batch_op.drop_index("uq_course_certificates_active")
        batch_op.drop_index(batch_op.f("ix_course_certificates_enrollment_id"))
        batch_op.create_unique_constraint("uq_course_certificates_enrollment_id", ["enrollment_id"])
        batch_op.drop_constraint(
            batch_op.f("fk_course_certificates_replaces_id_course_certificates"),
            type_="foreignkey",
        )
        for column in (
            "email_claimed_at",
            "emailed_at",
            "email_attempts",
            "email_status",
            "reissue_reason",
            "replaces_id",
            "signatory_title",
            "signatory_name",
            "completed_at",
            "course_slug",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("course_enrollments") as batch_op:
        batch_op.drop_column("completion_snapshot")
    if sqlite:
        op.execute("PRAGMA foreign_keys=ON")
