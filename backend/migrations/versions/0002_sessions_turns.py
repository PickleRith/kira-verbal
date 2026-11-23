"""Create sessions and turns.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("synthetic_learner_id", sa.String(64), nullable=False),
        sa.Column("lesson_id", sa.String(64), nullable=False),
        sa.Column("lesson_version", sa.Integer, nullable=False),
        sa.Column("access_token_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("current_question_id", sa.String(64)),
        sa.Column("current_purpose", sa.String(16)),
        sa.Column("current_hint_index", sa.Integer),
        sa.Column("finish_reason", sa.String(32)),
        sa.Column("lease_expires_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.Column("deadline_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id", "lesson_version"],
            ["lesson_versions.lesson_id", "lesson_versions.version"],
            name="fk_sessions_lesson_version",
        ),
        sa.CheckConstraint(
            "status IN ('created','awaiting_answer','evaluating','completed','incomplete')",
            name="ck_sessions_status",
        ),
        sa.CheckConstraint(
            "current_purpose IS NULL OR current_purpose IN ('open','diagnostic','clarify','hint')",
            name="ck_sessions_purpose",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_sessions_state_version"),
    )

    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_turn_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("transcript", sa.Text, nullable=False),
        sa.Column("modality", sa.String(8), nullable=False),
        sa.Column("assisted", sa.Boolean, nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("signal", sa.String(32)),
        sa.Column("misconception_tag", sa.String(64)),
        sa.Column("evaluator_version", sa.String(64)),
        sa.Column("response", postgresql.JSONB),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("committed_at", TZ),
        sa.CheckConstraint("status IN ('processing','committed','failed')", name="ck_turns_status"),
        sa.CheckConstraint("modality IN ('text','voice')", name="ck_turns_modality"),
        sa.CheckConstraint("sequence >= 1", name="ck_turns_sequence"),
        sa.CheckConstraint(
            "status <> 'committed' OR (signal IS NOT NULL AND response IS NOT NULL)",
            name="ck_turns_committed_complete",
        ),
    )
    # Partial unique indexes: a failed attempt does not block a retry with the same
    # client_turn_id, but two live (processing/committed) copies of a turn are impossible.
    op.create_index(
        "uq_turns_live_client_turn_id",
        "turns",
        ["session_id", "client_turn_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
    )
    op.create_index(
        "uq_turns_live_sequence",
        "turns",
        ["session_id", "sequence"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_turns_live_sequence", table_name="turns")
    op.drop_index("uq_turns_live_client_turn_id", table_name="turns")
    op.drop_table("turns")
    op.drop_table("sessions")
