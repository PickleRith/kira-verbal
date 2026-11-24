"""Demo accounts: registration, sign-in, classes and a student's own check-ins.

* Passwords are hashed with scrypt (stdlib) and a per-user salt; only the hash is stored.
* Sign-in tokens are random (`kvu_` prefix), stored only as SHA-256 hashes, and expire.
* A teacher account owns one class (a workspace) with a short join code. A student joins
  a class with that code. Every check-in a student starts belongs to their class, so it
  appears in that teacher's review queue with no extra step.
* The export payload and logs never contain a student's email or name; sessions carry an
  opaque `user-…` learner id.

This is demo authentication for a prototype with synthetic data: no email verification,
password reset, SSO or school rostering. See docs/security.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthTokenRow, ReportRow, SessionRow, UserRow, WorkspaceRow
from app.domain.grading import MAX_LEVEL
from app.domain.models import Lesson
from app.schemas.accounts import (
    ClassView,
    MeView,
    RegisterRequest,
    StudentCriterionResult,
    StudentResult,
    StudentSessionItem,
    normalize_join_code,
)
from app.schemas.reports import ScoreView
from app.schemas.sessions import LessonRef, StudentSessionView
from app.services.assessment import AssessmentService, hash_secret
from app.services.errors import (
    ClassNotFoundError,
    EmailTakenError,
    InvalidCredentialsError,
    NoClassError,
    NotSignedInError,
    SessionNotFoundError,
    WrongRoleError,
)

USER_TOKEN_PREFIX = "kvu_"
TOKEN_TTL = timedelta(days=7)
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
JOIN_CODE_LENGTH = 6
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


# --- password hashing ---------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    b64 = base64.b64encode
    params = f"{_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}"
    return f"scrypt${params}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, dklen=len(expected), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email is unknown, so a wrong email takes as long as a wrong
# password and response time doesn't reveal which accounts exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _result(latest: ReportRow | None, lesson: Lesson | None) -> StudentResult | None:
    """The teacher-approved result. Nothing before approval (the suggestion is the teacher's
    to accept or change) and nothing after a rejection."""
    if latest is None or latest.status != "approved" or lesson is None:
        return None
    criteria = []
    for c in latest.criteria:
        rubric = next(x for x in lesson.criteria if x.id == c["criterion_id"])
        objective = next(o for o in lesson.objectives if o.id == rubric.objective)
        level = c["level"]
        criteria.append(
            StudentCriterionResult(
                criterion_id=rubric.id,
                objective_description=objective.description,
                level=level,
                max_level=MAX_LEVEL,
                descriptor=rubric.levels[str(level)] if level is not None else None,
            )
        )
    return StudentResult(
        score=ScoreView.from_levels({c["criterion_id"]: c["level"] for c in latest.criteria}),
        approved_at=latest.created_at,
        criteria=criteria,
    )


def _learner_id(user_id: uuid.UUID) -> str:
    return f"user-{user_id.hex[:12]}"


class AccountService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        assessment: AssessmentService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = session_factory
        self._assessment = assessment
        self._clock = clock

    @property
    def clock(self) -> Callable[[], datetime]:
        return self._clock or self._assessment.clock

    # --- register / sign in -------------------------------------------------------------

    def register(self, body: RegisterRequest) -> tuple[MeView, str, datetime]:
        now = self.clock()
        user = UserRow(
            id=uuid.uuid4(),
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            password_hash=hash_password(body.password),
            created_at=now,
        )
        try:
            with self._db.begin() as db:
                if body.role == "teacher":
                    workspace = WorkspaceRow(
                        id=uuid.uuid4(),
                        name=body.class_name or f"{body.display_name}'s class",
                        join_code=self._new_join_code(db),
                        created_at=now,
                    )
                    db.add(workspace)
                    db.flush()
                    user.workspace_id = workspace.id
                elif body.join_code:
                    user.workspace_id = self._class_by_code(db, body.join_code).id
                db.add(user)
                db.flush()
                token, expires = self._issue_token(db, user.id)
                me = self._me(db, user)
        except IntegrityError:
            raise EmailTakenError("an account with this email already exists") from None
        return me, token, expires

    def login(self, email: str, password: str) -> tuple[MeView, str, datetime]:
        with self._db.begin() as db:
            user = db.scalar(select(UserRow).where(UserRow.email == email))
            if user is None:
                verify_password(password, _DUMMY_HASH)
                raise InvalidCredentialsError("email or password is incorrect")
            if not verify_password(password, user.password_hash):
                raise InvalidCredentialsError("email or password is incorrect")
            token, expires = self._issue_token(db, user.id)
            return self._me(db, user), token, expires

    def logout(self, token: str) -> None:
        with self._db.begin() as db:
            db.execute(delete(AuthTokenRow).where(AuthTokenRow.token_sha256 == hash_secret(token)))

    def me(self, token: str) -> MeView:
        with self._db.begin() as db:
            return self._me(db, self._user(db, token))

    # --- classes --------------------------------------------------------------------------

    def join_class(self, token: str, join_code: str) -> MeView:
        with self._db.begin() as db:
            user = self._user(db, token, role="student")
            user.workspace_id = self._class_by_code(db, join_code).id
            db.flush()
            return self._me(db, user)

    def teacher_workspace(self, token: str) -> WorkspaceRow:
        """The class a signed-in teacher owns. Used by the report service for teacher routes."""
        with self._db.begin() as db:
            user = self._user(db, token, role="teacher")
            workspace = db.get(WorkspaceRow, user.workspace_id) if user.workspace_id else None
            if workspace is None:
                raise NoClassError("this teacher account has no class")
            db.expunge(workspace)
            return workspace

    def display_names(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        with self._db.begin() as db:
            rows = db.execute(
                select(UserRow.id, UserRow.display_name).where(UserRow.id.in_(user_ids))
            )
            return {user_id: name for user_id, name in rows}

    # --- a student's own check-ins ------------------------------------------------------

    def start_session(self, token: str, lesson_id: str) -> tuple[StudentSessionView, str]:
        with self._db.begin() as db:
            user = self._user(db, token, role="student")
            if user.workspace_id is None:
                raise NoClassError("join a class with your teacher's code first")
            user_id, workspace_id = user.id, user.workspace_id
        return self._assessment.create_session(
            lesson_id,
            None,
            _learner_id(user_id),
            workspace_id=workspace_id,
            learner_user_id=user_id,
        )

    def student_sessions(self, token: str) -> list[StudentSessionItem]:
        from app.services.reports import _committed_turns, _latest_report, _report_status

        with self._db.begin() as db:
            user = self._user(db, token, role="student")
            ids = list(
                db.scalars(
                    select(SessionRow.id)
                    .where(SessionRow.learner_user_id == user.id)
                    .order_by(SessionRow.created_at.desc())
                )
            )
        for session_id in ids:  # show abandoned sessions as finished
            self._assessment.apply_timers(session_id)
        review = {
            "pending": "in_progress",
            "ready_for_review": "awaiting_review",
            "approved": "reviewed",
            "rejected": "reviewed",
        }
        items: list[StudentSessionItem] = []
        with self._db.begin() as db:
            for session_id in ids:
                row = db.get(SessionRow, session_id)
                assert row is not None
                lesson = self._assessment.lessons.get(row.lesson_id, row.lesson_version)
                turns = _committed_turns(db, session_id)
                latest = _latest_report(db, row.id)
                items.append(
                    StudentSessionItem(
                        session_id=row.id,
                        lesson=LessonRef(
                            id=row.lesson_id,
                            version=row.lesson_version,
                            title=lesson.title if lesson else row.lesson_id,
                        ),
                        session_status=row.status,
                        finish_reason=row.finish_reason,  # type: ignore[arg-type]
                        created_at=row.created_at,
                        answers=sum(t.signal != "conversation" for t in turns),
                        review_status=review[_report_status(row, latest)],  # type: ignore[arg-type]
                        result=_result(latest, lesson),
                    )
                )
        return items

    def resume_session(self, token: str, session_id: uuid.UUID) -> str:
        """Issue a fresh session token for the student's own session, e.g. on another device.

        The old token stops working (only one hash is stored). Voice-worker credentials are
        separate and unaffected.
        """
        with self._db.begin() as db:
            user = self._user(db, token, role="student")
            row = db.get(SessionRow, session_id, with_for_update=True)
            if row is None or row.learner_user_id != user.id:
                raise SessionNotFoundError("session not found")
            session_token = secrets.token_urlsafe(32)
            row.access_token_sha256 = hash_secret(session_token)
        return session_token

    # --- internals ------------------------------------------------------------------------

    def _issue_token(self, db: Session, user_id: uuid.UUID) -> tuple[str, datetime]:
        now = self.clock()
        token = USER_TOKEN_PREFIX + secrets.token_urlsafe(32)
        expires = now + TOKEN_TTL
        db.add(
            AuthTokenRow(
                token_sha256=hash_secret(token), user_id=user_id, created_at=now, expires_at=expires
            )
        )
        return token, expires

    def _user(self, db: Session, token: str, *, role: str | None = None) -> UserRow:
        if not token.startswith(USER_TOKEN_PREFIX):
            raise NotSignedInError("sign in required")
        row = db.get(AuthTokenRow, hash_secret(token))
        if row is None or row.expires_at <= self.clock():
            raise NotSignedInError("your sign-in has expired; sign in again")
        user = db.get(UserRow, row.user_id)
        if user is None:
            raise NotSignedInError("sign in required")
        if role is not None and user.role != role:
            raise WrongRoleError(f"this needs a {role} account")
        return user

    def _class_by_code(self, db: Session, code: str) -> WorkspaceRow:
        workspace = db.scalar(
            select(WorkspaceRow).where(WorkspaceRow.join_code == normalize_join_code(code))
        )
        if workspace is None:
            raise ClassNotFoundError("no class has that code; check it with your teacher")
        return workspace

    def _new_join_code(self, db: Session) -> str:
        for _ in range(20):
            code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
            if db.scalar(select(WorkspaceRow.id).where(WorkspaceRow.join_code == code)) is None:
                return code
        raise RuntimeError("could not allocate a unique join code")

    def _me(self, db: Session, user: UserRow) -> MeView:
        klass = None
        if user.workspace_id is not None:
            workspace = db.get(WorkspaceRow, user.workspace_id)
            teacher = db.scalar(
                select(UserRow).where(
                    UserRow.workspace_id == user.workspace_id, UserRow.role == "teacher"
                )
            )
            is_owner = user.role == "teacher"
            students = (
                db.scalar(
                    select(func.count())
                    .select_from(UserRow)
                    .where(UserRow.workspace_id == user.workspace_id, UserRow.role == "student")
                )
                if is_owner
                else None
            )
            if workspace is not None:
                klass = ClassView(
                    id=workspace.id,
                    name=workspace.name or "Class",
                    join_code=workspace.join_code if is_owner else None,
                    teacher_name=teacher.display_name if teacher else None,
                    student_count=students,
                )
        return MeView(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,  # type: ignore[arg-type]
            created_at=user.created_at,
            class_=klass,
        )
