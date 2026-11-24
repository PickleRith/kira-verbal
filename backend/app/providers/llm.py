"""Evaluator interface and the Claude-backed adapter.

The orchestrator depends only on the `Evaluator` protocol, so the deterministic fake and
the LLM adapter are interchangeable. An evaluator *proposes* rubric evidence. It never
picks questions and its output is never trusted directly: `services/evaluator.py`
validates every item (criterion, exact quote, level, tag) before anything is stored as
accepted or can influence the policy or a suggested level.

AnthropicEvaluator:
* Structured output: a per-lesson JSON schema (criterion ids and tags are enums), enforced
  by the API via `output_config.format`, then parsed again with Pydantic here.
* Bounded retry: the SDK retries connection errors / 429 / 5xx (`max_retries`); this class
  re-asks once more if the reply is truncated or does not parse. Then it raises, and the
  orchestrator releases the turn (503) so the learner can resend.
* A refusal becomes "no evidence" (abstain). It is never turned into a score.
* The learner transcript is untrusted: it sits inside delimiter tags, the closing tag is
  neutralised, and no tools are offered, so an injected instruction has nothing to call.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.models import Lesson, Question
from app.providers import prompts

logger = logging.getLogger(__name__)


# --- contract shared by every evaluator ---------------------------------------------


class LearnerIntent(StrEnum):
    ANSWER = "answer"
    HELP_REQUEST = "help_request"
    STOP_REQUEST = "stop_request"
    # Not an answer attempt. These become side turns: the question is asked again and no
    # answer budget is used (up to a cap). Any evidence proposed for them is not accepted.
    SUBJECT_QUESTION = "subject_question"  # asks about the topic instead of answering
    CLARIFICATION_REQUEST = "clarification_request"  # repeat / rephrase / didn't hear
    OFF_TOPIC = "off_topic"  # unrelated to the lesson
    WELLBEING_CONCERN = "wellbeing_concern"  # upset, unsafe or being harmed


CONVERSATIONAL_INTENTS: frozenset[LearnerIntent] = frozenset(
    {
        LearnerIntent.SUBJECT_QUESTION,
        LearnerIntent.CLARIFICATION_REQUEST,
        LearnerIntent.OFF_TOPIC,
        LearnerIntent.WELLBEING_CONCERN,
    }
)


@dataclass(frozen=True)
class EvaluationRequest:
    lesson: Lesson
    question: Question
    transcript: str  # untrusted learner text
    assisted: bool


@dataclass(frozen=True)
class ProposedEvidence:
    criterion_id: str
    proposed_level: int | None
    evidence_quote: str
    misconception_tag: str | None
    reason: str
    abstain: bool


@dataclass(frozen=True)
class EvaluatorOutput:
    intent: LearnerIntent
    evidence: tuple[ProposedEvidence, ...]
    evaluator_version: str  # provider + prompt version, stored with every turn
    model: str | None = None  # the model that actually answered (None for the fake)


class Evaluator(Protocol):
    def evaluate(self, request: EvaluationRequest) -> EvaluatorOutput:
        """Propose evidence for one turn. May raise; the orchestrator treats that as
        recoverable (the turn is released and the learner can resend)."""
        ...


class EvaluatorOutputError(Exception):
    """The model's reply could not be used after the bounded retries."""


# --- Claude adapter ----------------------------------------------------------------

Effort = Literal["low", "medium", "high", "xhigh", "max"]
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def supports_server_fallback(model: str) -> bool:
    """Haiku models have no server-side fallback: a `fallbacks` list is a 400 and the
    "default" form does nothing, so it is not sent. A refusal is then handled here
    (recorded as no evidence), as for every other model."""
    return not model.startswith("claude-haiku")


class _LlmEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    proposed_level: int | None
    evidence_quote: str
    misconception_tag: str | None
    reason: str = Field(max_length=2000)
    abstain: bool


class _LlmEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_intent: LearnerIntent
    evidence: list[_LlmEvidence] = Field(max_length=8)


def output_schema(lesson: Lesson, question: Question) -> dict[str, Any]:
    """JSON schema for one request. Enums limit ids to this question's objective, which
    makes most invalid output impossible; the validator still re-checks everything."""
    criterion_ids = [c.id for c in lesson.criteria if c.objective == question.objective]
    tags = [m.tag for m in lesson.misconceptions if m.objective == question.objective]
    tag_schema: dict[str, Any] = (
        {"anyOf": [{"type": "string", "enum": tags}, {"type": "null"}]}
        if tags
        else {"type": "null"}
    )
    return {
        "type": "object",
        "properties": {
            "learner_intent": {"type": "string", "enum": [i.value for i in LearnerIntent]},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "criterion_id": {"type": "string", "enum": criterion_ids},
                        "proposed_level": {
                            "anyOf": [{"type": "integer", "enum": [0, 1, 2, 3]}, {"type": "null"}]
                        },
                        "evidence_quote": {"type": "string"},
                        "misconception_tag": tag_schema,
                        "reason": {"type": "string"},
                        "abstain": {"type": "boolean"},
                    },
                    "required": [
                        "criterion_id",
                        "proposed_level",
                        "evidence_quote",
                        "misconception_tag",
                        "reason",
                        "abstain",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["learner_intent", "evidence"],
        "additionalProperties": False,
    }


class AnthropicEvaluator:
    """Evaluator backed by the Claude Messages API (official `anthropic` SDK)."""

    def __init__(
        self,
        client: Any,  # anthropic.Anthropic, or a stub with the same .beta.messages.create
        *,
        model: str,
        effort: Effort = "medium",
        max_tokens: int = 16000,
        parse_retries: int = 1,
    ) -> None:
        self._client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.parse_retries = parse_retries
        self.version = f"anthropic:{model}:{prompts.PROMPT_VERSION}"
        # Running totals from the API's own usage report, for cost estimates in benchmarks.
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        self._usage_lock = threading.Lock()

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        with self._usage_lock:
            self.usage["requests"] += 1
            self.usage["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            self.usage["output_tokens"] += getattr(usage, "output_tokens", 0) or 0

    def build_params(self, request: EvaluationRequest) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": prompts.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompts.render_user_message(request)}],
            "output_config": {
                "effort": self.effort,
                "format": {
                    "type": "json_schema",
                    "schema": output_schema(request.lesson, request.question),
                },
            },
        }
        if supports_server_fallback(self.model):
            # Opt in to server-side refusal fallbacks (routes by refusal category).
            params["betas"] = [REFUSAL_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def evaluate(self, request: EvaluationRequest) -> EvaluatorOutput:
        params = self.build_params(request)
        last_problem = "no attempt made"
        for attempt in range(self.parse_retries + 1):
            response = self._client.beta.messages.create(**params)
            self._record_usage(response)
            served_by = getattr(response, "model", None)

            if response.stop_reason == "refusal":
                logger.warning(
                    "evaluator refusal (category=%s); recording no evidence",
                    getattr(getattr(response, "stop_details", None), "category", None),
                )
                return EvaluatorOutput(LearnerIntent.ANSWER, (), self.version, served_by)
            if response.stop_reason == "max_tokens":
                last_problem = "reply truncated at max_tokens"
                continue

            text = next((b.text for b in response.content if b.type == "text"), None)
            if text is None:
                last_problem = "reply had no text block"
                continue
            try:
                parsed = _LlmEvaluation.model_validate_json(text)
            except ValidationError as exc:
                last_problem = f"reply did not match schema: {exc.error_count()} errors"
                logger.warning("evaluator attempt %d unparseable", attempt + 1)
                continue

            return EvaluatorOutput(
                intent=parsed.learner_intent,
                evidence=tuple(
                    ProposedEvidence(
                        criterion_id=item.criterion_id,
                        proposed_level=item.proposed_level,
                        evidence_quote=item.evidence_quote,
                        misconception_tag=item.misconception_tag,
                        reason=item.reason,
                        abstain=item.abstain,
                    )
                    for item in parsed.evidence
                ),
                evaluator_version=self.version,
                model=served_by,
            )
        raise EvaluatorOutputError(last_problem)


def build_anthropic_client(*, api_key: str | None, timeout_seconds: float, max_retries: int):
    """Create the SDK client. Without an explicit key the SDK resolves credentials itself
    (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile)."""
    import anthropic  # imported lazily so fake mode never needs credentials

    kwargs: dict[str, Any] = {"timeout": timeout_seconds, "max_retries": max_retries}
    if api_key:
        kwargs["api_key"] = api_key
    return anthropic.Anthropic(**kwargs)
