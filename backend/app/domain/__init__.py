"""Pure assessment domain: lesson types, session state machine, question policy.

Nothing in this package imports FastAPI, SQLAlchemy, Redis or provider SDKs.
That keeps the rules testable in microseconds and reusable by the text API,
the voice worker and offline benchmark scripts alike.
"""
