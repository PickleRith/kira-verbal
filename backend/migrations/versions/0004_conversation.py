"""Conversation layer: side turns, stored lead-ins, reply provenance.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The line said before the current question. Stored so a refetch (resume, the voice
    # worker after a conflict) shows exactly what the turn response showed.
    op.add_column("sessions", sa.Column("current_lead_in", sa.Text))
    op.drop_constraint("ck_sessions_purpose", "sessions", type_="check")
    op.create_check_constraint(
        "ck_sessions_purpose",
        "sessions",
        "current_purpose IS NULL OR current_purpose IN "
        "('open','diagnostic','clarify','hint','respond')",
    )
    # What the evaluator thought the learner meant, and who wrote the reply
    # ("fake-template-v1", "anthropic:<model>:responder-v1", "fallback:<reason>").
    op.add_column("turns", sa.Column("intent", sa.String(32)))
    op.add_column("turns", sa.Column("reply_source", sa.String(160)))


def downgrade() -> None:
    op.drop_column("turns", "reply_source")
    op.drop_column("turns", "intent")
    op.execute("UPDATE sessions SET current_purpose = 'clarify' WHERE current_purpose = 'respond'")
    op.drop_constraint("ck_sessions_purpose", "sessions", type_="check")
    op.create_check_constraint(
        "ck_sessions_purpose",
        "sessions",
        "current_purpose IS NULL OR current_purpose IN ('open','diagnostic','clarify','hint')",
    )
    op.drop_column("sessions", "current_lead_in")
