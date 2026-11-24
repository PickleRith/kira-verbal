"""Teacher workspaces, reports (revisioned), reviews and export events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23

Reports, reviews and export events are append-only: a trigger rejects UPDATE and DELETE,
so the audit trail cannot be rewritten in place. A teacher decision creates a NEW report
revision plus a review row linking the revision it was based on to the one it produced.
(Deleting a whole session still cascades, which is the documented retention path.)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
TRIGGERS = {
    "reports": "reject_report_change",
    "reviews": "reject_report_child_change",
    "export_events": "reject_report_child_change",
}


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("teacher_token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.add_column(
        "sessions",
        sa.Column("workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
    )
    op.create_index("ix_sessions_workspace_id", "sessions", ["workspace_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "session_id", sa.Uuid, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("criteria", postgresql.JSONB, nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("session_id", "revision", name="uq_reports_session_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_reports_revision"),
        sa.CheckConstraint(
            "status IN ('ready_for_review','approved','rejected')", name="ck_reports_status"
        ),
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "report_id", sa.Uuid, sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "result_report_id",
            sa.Uuid,
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("approved_levels", postgresql.JSONB),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject')", name="ck_reviews_decision"),
    )
    op.create_table(
        "export_events",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid,
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # one export per approved revision
        ),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )

    # Two functions because PL/pgSQL resolves OLD.<column> even in an untaken branch.
    # A DELETE is allowed only when the owning session is already gone, i.e. the row is
    # being removed by the cascade from deleting a whole session (the retention path).
    op.execute(
        """
        CREATE FUNCTION reject_report_change() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               AND NOT EXISTS (SELECT 1 FROM sessions WHERE id = OLD.session_id) THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION '% rows are append-only; record a new revision instead',
                TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_report_child_change() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND NOT EXISTS (
                SELECT 1 FROM reports r JOIN sessions s ON s.id = r.session_id
                WHERE r.id = OLD.report_id
            ) THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION '% rows are append-only; record a new revision instead',
                TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table, function in TRIGGERS.items():
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {function}();
            """
        )


def downgrade() -> None:
    for table in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_report_child_change()")
    op.execute("DROP FUNCTION IF EXISTS reject_report_change()")
    op.drop_table("export_events")
    op.drop_table("reviews")
    op.drop_table("reports")
    op.drop_index("ix_sessions_workspace_id", table_name="sessions")
    op.drop_column("sessions", "workspace_id")
    op.drop_table("workspaces")
