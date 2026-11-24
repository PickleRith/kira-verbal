"""Demo accounts: users, sign-in tokens, classes with join codes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-23

* users: a student or a teacher. Passwords are stored only as scrypt hashes. A teacher owns
  one class (a workspace); a student belongs to at most one class, joined with its code.
* auth_tokens: sign-in tokens, stored only as SHA-256 hashes, with an expiry.
* workspaces gain a display name and a join code, and the old per-browser teacher token
  becomes optional (account classes have none; demo classrooms keep theirs).
* sessions gain learner_user_id: which student account took the check-in (NULL for demo
  learners launched by a teacher and for anonymous sessions).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("name", sa.Text))
    op.add_column("workspaces", sa.Column("join_code", sa.String(12)))
    op.create_unique_constraint("uq_workspaces_join_code", "workspaces", ["join_code"])
    op.alter_column("workspaces", "teacher_token_sha256", nullable=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column(
            "workspace_id", sa.Uuid, sa.ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("role IN ('student','teacher')", name="ck_users_role"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
    )
    # One teacher per class.
    op.create_index(
        "uq_users_teacher_workspace",
        "users",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("role = 'teacher'"),
    )
    op.create_table(
        "auth_tokens",
        sa.Column("token_sha256", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
    )
    op.add_column(
        "sessions",
        sa.Column("learner_user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_sessions_learner_user_id", "sessions", ["learner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_learner_user_id", table_name="sessions")
    op.drop_column("sessions", "learner_user_id")
    op.drop_table("auth_tokens")
    op.drop_index("uq_users_teacher_workspace", table_name="users")
    op.drop_table("users")
    op.execute("DELETE FROM workspaces WHERE teacher_token_sha256 IS NULL")
    op.alter_column("workspaces", "teacher_token_sha256", nullable=False)
    op.drop_constraint("uq_workspaces_join_code", "workspaces", type_="unique")
    op.drop_column("workspaces", "join_code")
    op.drop_column("workspaces", "name")
