"""Responder: the short conversational line spoken or shown before the next question.

The policy still decides *what* happens next (which question, hint, clarification or
re-ask). The responder only writes the sentence in front of it, so the agent can react to
what the learner actually said ("Sure, here it is again", "That's a good question, but
I'd like to hear your thinking first"). The authored question and hint text are always
added afterwards, word for word, by the orchestrator. The responder never writes them.

Every reply is checked by `services/conversation.py:check_reply` before use. If the
responder fails, times out, refuses or writes something the guard rejects, the
deterministic template from `fallback_reply` is used instead, and the turn still succeeds.
A reply can never fail a turn.

FakeResponder returns the templates and is the default (free, deterministic).
AnthropicResponder asks Claude; see `responder_prompt.py` for its instructions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.models import Lesson, Question
from app.providers import responder_prompt
from app.providers.llm import Effort, LearnerIntent

logger = logging.getLogger(__name__)

NextStep = Literal["new_question", "follow_up", "ask_for_more", "hint", "repeat_question"]

CLARIFY_LEAD_IN = "Could you say a bit more about that?"
HINT_LEAD_IN = "Here's a hint:"
SIDE_TURN_REPLIES: dict[LearnerIntent, str] = {
    LearnerIntent.SUBJECT_QUESTION: (
        "That's a good question. I can't explain it during this check-in, because I'd like "
        "to hear your own thinking. Your teacher can go over it with you afterwards."
    ),
    LearnerIntent.CLARIFICATION_REQUEST: "Sure, here's the question again.",
    LearnerIntent.OFF_TOPIC: "Let's keep our focus on {title} for now.",
    LearnerIntent.WELLBEING_CONCERN: (
        "Thank you for telling me. Please talk to your teacher or another adult you trust "
        "about this. They can help."
    ),
}
DEFAULT_SIDE_TURN_REPLY = "Let's come back to the question."


@dataclass(frozen=True)
class Exchange:
    """One earlier learner turn and what the agent said after it (for continuity)."""

    question_text: str
    learner_text: str  # untrusted
    reply: str | None


@dataclass(frozen=True)
class ResponderRequest:
    lesson: Lesson
    asked: Question  # the question the learner was responding to
    learner_text: str  # untrusted
    intent: LearnerIntent
    next_step: NextStep
    next_question: Question
    recent: tuple[Exchange, ...] = ()


class Responder(Protocol):
    version: str

    def respond(self, request: ResponderRequest) -> str | None:
        """The line to say before the next question, or None for none. May raise."""
        ...


class ResponderError(Exception):
    """The model's reply could not be used."""


def fallback_reply(request: ResponderRequest) -> str | None:
    """The deterministic line for this step. Also what FakeResponder returns."""
    if request.next_step == "ask_for_more":
        return CLARIFY_LEAD_IN
    if request.next_step == "repeat_question":
        template = SIDE_TURN_REPLIES.get(request.intent, DEFAULT_SIDE_TURN_REPLY)
        return template.format(title=request.lesson.title)
    return None  # new question, follow-up, hint: no line (the hint lead-in is added later)


class FakeResponder:
    version = "fake-template-v1"

    def respond(self, request: ResponderRequest) -> str | None:
        return fallback_reply(request)


# --- Claude adapter ----------------------------------------------------------------


class _LlmReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str


REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
    "additionalProperties": False,
}


class AnthropicResponder:
    """Responder backed by the Claude Messages API.

    One attempt only, with low effort and a short client timeout: this call sits on the
    learner's critical path, and the template fallback is always acceptable. No tools are
    offered, and the learner's words are fenced as untrusted data.
    """

    def __init__(
        self,
        client: Any,  # anthropic.Anthropic, or a stub with the same .messages.create
        *,
        model: str,
        effort: Effort = "low",
        max_tokens: int = 1024,  # thinking counts toward this, so leave headroom
    ) -> None:
        self._client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.version = f"anthropic:{model}:{responder_prompt.PROMPT_VERSION}"

    def build_params(self, request: ResponderRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": responder_prompt.SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": responder_prompt.render_user_message(request)}
            ],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": REPLY_SCHEMA},
            },
        }

    def respond(self, request: ResponderRequest) -> str | None:
        response = self._client.messages.create(**self.build_params(request))
        if response.stop_reason == "refusal":
            raise ResponderError("refusal")
        if response.stop_reason == "max_tokens":
            raise ResponderError("reply truncated at max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ResponderError("reply had no text block")
        try:
            reply = _LlmReply.model_validate_json(text).reply.strip()
        except ValidationError as exc:
            problem = f"reply did not match schema: {exc.error_count()} errors"
            raise ResponderError(problem) from None
        return reply or None
