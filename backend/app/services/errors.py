"""Service errors. Each maps to one HTTP status and error code in app/api/errors.py."""

from __future__ import annotations


class AssessmentError(Exception):
    def __init__(self, message: str, *, state_version: int | None = None) -> None:
        super().__init__(message)
        self.state_version = state_version


class MissingTokenError(AssessmentError):
    """No bearer token supplied."""


class SessionNotFoundError(AssessmentError):
    """Unknown session OR wrong token. Deliberately indistinguishable to the caller."""


class LessonNotFoundError(AssessmentError):
    """Lesson id/version is not published in the database."""


class StaleStateVersionError(AssessmentError):
    """expected_state_version does not match; the client must refetch."""


class IdempotencyMismatchError(AssessmentError):
    """client_turn_id reused with a different payload."""


class TurnInProgressError(AssessmentError):
    """The same or another turn is being evaluated right now; retry shortly."""


class ClaimLostError(AssessmentError):
    """This request's processing claim was recovered by another request (lease expired)."""


class QuestionMismatchError(AssessmentError):
    """The answer is for a question that is not the one currently asked."""


class SessionClosedError(AssessmentError):
    """Session is completed or incomplete; no more turns."""


class SessionExpiredError(AssessmentError):
    """Session deadline passed before this answer was claimed."""


class EvaluationUnavailableError(AssessmentError):
    """Evaluator failed or timed out. The turn was released; the client may retry."""
