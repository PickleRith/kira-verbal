"""Domain error types. The API layer maps these to HTTP status codes."""


class DomainError(Exception):
    """Base class for violations of assessment rules."""


class UnknownQuestionError(DomainError):
    """A question ID that does not exist in the pinned lesson version."""


class InvalidTurnRecordError(DomainError):
    """A turn record that is internally inconsistent with the lesson."""


class IllegalTransitionError(DomainError):
    """A session event that is not permitted from the current status."""
