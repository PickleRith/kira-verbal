"""Create lesson_versions with an immutability trigger.

Revision ID: 0001
Revises:
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_versions",
        sa.Column("lesson_id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("version >= 1", name="ck_lesson_versions_version_positive"),
    )
    # Published versions are immutable: sessions pin (lesson_id, version), so
    # changing content in place would silently change what old sessions mean.
    op.execute(
        """
        CREATE FUNCTION reject_lesson_version_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'lesson_versions rows are immutable; publish a new version';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER lesson_versions_immutable
        BEFORE UPDATE ON lesson_versions
        FOR EACH ROW EXECUTE FUNCTION reject_lesson_version_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS lesson_versions_immutable ON lesson_versions")
    op.execute("DROP FUNCTION IF EXISTS reject_lesson_version_update()")
    op.drop_table("lesson_versions")
