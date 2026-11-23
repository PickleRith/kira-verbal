"""Deterministic keyword evaluator for tests and the free demo.

This is deliberately simple and NOT a model of understanding: it matches phrases.
It exists so the full flow runs with no paid API and so tests are reproducible.
Its output goes through the same validator as the LLM's.

Known limitations: it ignores negation ("not from the roots" still matches "root"), and
the level it proposes for an ordinary answer (2) is a placeholder, not a judgment. Its
evaluator_version ("fake-keyword-v2") marks every such row so it is never mistaken for
real evaluation.

Rules, in order:
1. Whole answer is a stop phrase            -> intent stop_request
2. Short answer asking for help/a hint      -> intent help_request
3. Fewer than 3 words                       -> abstain (-> AMBIGUOUS, never scored as wrong)
4. Keyword for a misconception of this question's objective -> level 1 + tag
5. Otherwise                                -> placeholder level 2
"""

from __future__ import annotations

import re

from app.providers.llm import (
    EvaluationRequest,
    EvaluatorOutput,
    LearnerIntent,
    ProposedEvidence,
)

FAKE_EVALUATOR_VERSION = "fake-keyword-v2"

STOP_PHRASES = frozenset(
    {"stop", "quit", "i want to stop", "i want to finish", "i'm done", "im done", "end"}
)
HELP_PATTERN = re.compile(r"\b(hint|help)\b|\bi (don'?t|do not) know\b|\bnot sure\b")
HELP_MAX_WORDS = 8

# Keywords per misconception tag, matched as substrings of the normalized answer.
MISCONCEPTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food_from_soil": ("food from the soil", "food from soil", "eats soil", "food from the ground"),
    "co2_from_roots": ("root", "soil"),
    "light_is_food": (
        "eats light",
        "eats sunlight",
        "light is food",
        "sunlight is food",
        "light is its food",
        "sunlight is its food",
    ),
    "unequal_parts_ok": (
        "any size",
        "different sizes",
        "don't have to be equal",
        "doesn't matter how big",
    ),
    "add_to_top_and_bottom": (
        "add 1",
        "add one",
        "added 1",
        "added one",
        "same number to the top and bottom",
    ),
    "bigger_denominator_bigger_fraction": (
        "1/5 is bigger",
        "1/5 is larger",
        "1/8 is bigger",
        "1/8 is more",
        "bigger denominator",
    ),
    "body_runs_once": ("only once", "one time", "runs once"),
    "range_includes_stop": (
        "1, 2, 3, 4, 5",
        "1 2 3 4 5",
        "including 5",
        "1 to 5",
        "last value is 3",
    ),
    "while_stops_itself": (
        "stops by itself",
        "stops on its own",
        "eventually stops",
        "after a while",
    ),
}


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


class FakeEvaluator:
    version = FAKE_EVALUATOR_VERSION

    def evaluate(self, request: EvaluationRequest) -> EvaluatorOutput:
        answer = normalize(request.transcript)
        words = answer.split()
        criterion_id = next(
            c.id for c in request.lesson.criteria if c.objective == request.question.objective
        )

        def output(
            intent: LearnerIntent = LearnerIntent.ANSWER, *items: ProposedEvidence
        ) -> EvaluatorOutput:
            return EvaluatorOutput(intent, items, self.version, None)

        def item(level: int | None, tag: str | None, reason: str) -> ProposedEvidence:
            return ProposedEvidence(
                criterion_id=criterion_id,
                proposed_level=level,
                evidence_quote=request.transcript.strip() if level is not None else "",
                misconception_tag=tag,
                reason=reason,
                abstain=level is None,
            )

        if answer.rstrip(".!") in STOP_PHRASES:
            return output(LearnerIntent.STOP_REQUEST)
        if len(words) <= HELP_MAX_WORDS and HELP_PATTERN.search(answer):
            return output(LearnerIntent.HELP_REQUEST)
        if len(words) < 3:
            return output(LearnerIntent.ANSWER, item(None, None, "Too short to judge."))

        for misconception in request.lesson.misconceptions:
            if misconception.objective != request.question.objective:
                continue
            keywords = MISCONCEPTION_KEYWORDS.get(misconception.tag, ())
            if any(keyword in answer for keyword in keywords):
                return output(
                    LearnerIntent.ANSWER,
                    item(1, misconception.tag, f"Keyword fake matched '{misconception.tag}'."),
                )
        return output(
            LearnerIntent.ANSWER,
            item(2, None, "Keyword fake: placeholder level, not a judgment of correctness."),
        )
