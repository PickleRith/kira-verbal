"""Create evidence (validated evaluator output per turn).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Turn evaluator_version can now hold "anthropic:<model>:<prompt version>".
    op.alter_column("turns", "evaluator_version", type_=sa.String(128))

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "session_id", sa.Uuid, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "turn_id", sa.Uuid, sa.ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("criterion_id", sa.String(64), nullable=False),
        sa.Column("objective", sa.String(64)),
        sa.Column("proposed_level", sa.Integer),
        sa.Column("evidence_quote", sa.Text, nullable=False),
        sa.Column("misconception_tag", sa.String(64)),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("assisted", sa.Boolean, nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("evaluator_version", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "validation_status IN ('accepted','abstained','rejected')", name="ck_evidence_status"
        ),
        sa.CheckConstraint(
            "proposed_level IS NULL OR proposed_level BETWEEN 0 AND 3", name="ck_evidence_level"
        ),
        sa.CheckConstraint(
            "validation_status <> 'accepted' OR proposed_level IS NOT NULL",
            name="ck_evidence_accepted_has_level",
        ),
        sa.CheckConstraint(
            "(validation_status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_evidence_rejection_reason",
        ),
    )
    op.create_index("ix_evidence_session", "evidence", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_session", table_name="evidence")
    op.drop_table("evidence")
    op.alter_column("turns", "evaluator_version", type_=sa.String(64))
