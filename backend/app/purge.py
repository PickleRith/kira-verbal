"""Delete sessions older than the retention period (and everything attached to them).

    python -m app.purge              # delete sessions older than TRANSCRIPT_RETENTION_DAYS
    python -m app.purge --days 1     # override the period
    python -m app.purge --dry-run    # report what would be deleted, change nothing

Deleting a session cascades to its turns (transcripts), evidence, reports, reviews and
export events. Demo classrooms left with no sessions and older than the period go too;
classes owned by an account are kept. Accounts and lessons are never touched. Run it on a
schedule (cron / a platform job); nothing deletes data automatically while the API is
serving requests.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import SessionRow, UserRow, WorkspaceRow
from app.db.session import make_engine, make_session_factory


def purge(
    factory: sessionmaker[Session], *, older_than_days: int, now: datetime, dry_run: bool = False
) -> tuple[int, int]:
    """Return (sessions, classrooms) deleted, or that would be deleted for a dry run."""
    if older_than_days < 0:
        raise ValueError("older_than_days must not be negative")
    cutoff = now - timedelta(days=older_than_days)
    with factory.begin() as db:
        old_sessions = SessionRow.created_at < cutoff
        sessions = db.scalar(select(func.count()).select_from(SessionRow).where(old_sessions)) or 0
        if not dry_run:
            db.execute(delete(SessionRow).where(old_sessions))
        remaining = select(SessionRow.workspace_id).where(SessionRow.workspace_id.is_not(None))
        if dry_run:  # sessions are still there: ignore the ones that would be deleted
            remaining = remaining.where(SessionRow.created_at >= cutoff)
        # A class that belongs to an account is kept: it is the teacher's, not session data.
        account_classes = select(UserRow.workspace_id).where(UserRow.workspace_id.is_not(None))
        empty_old = (
            (WorkspaceRow.created_at < cutoff)
            & WorkspaceRow.id.not_in(remaining)
            & WorkspaceRow.id.not_in(account_classes)
        )
        workspaces = db.scalar(select(func.count()).select_from(WorkspaceRow).where(empty_old)) or 0
        if not dry_run:
            db.execute(delete(WorkspaceRow).where(empty_old))
    return sessions, workspaces


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=settings.transcript_retention_days)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = make_engine(settings.database_url)
    try:
        sessions, workspaces = purge(
            make_session_factory(engine),
            older_than_days=args.days,
            now=datetime.now(UTC),
            dry_run=args.dry_run,
        )
    finally:
        engine.dispose()
    verb = "would delete" if args.dry_run else "deleted"
    print(
        f"{verb} {sessions} session(s) and {workspaces} empty classroom(s) "
        f"older than {args.days} day(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
