"""Deterministic keyword evaluator for tests and the free demo.

This is deliberately simple and NOT a model of understanding: it matches phrases.
It exists so the full flow runs with no paid API and so tests are reproducible.
Known limitation: it ignores negation ("not from the roots" still matches "root").

Rules, in order:
1. Whole answer is a stop phrase            -> STOP_REQUESTED
2. Short answer asking for help/a hint      -> HELP_REQUESTED
3. Fewer than 3 words                       -> AMBIGUOUS (never scored as wrong)
4. Matches a keyword for a misconception of this question's objective -> MISCONCEPTION
5. Otherwise                                -> ANSWERED
"""

from __future__ import annotations

import re

from app.domain.policy import Signal
from app.providers.llm import EvaluationRequest, EvaluationResult

FAKE_EVALUATOR_VERSION = "fake-keyword-v1"

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

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        answer = normalize(request.transcript)
        words = answer.split()

        def result(signal: Signal, tag: str | None = None) -> EvaluationResult:
            return EvaluationResult(signal, tag, self.version)

        if answer.rstrip(".!") in STOP_PHRASES:
            return result(Signal.STOP_REQUESTED)
        if len(words) <= HELP_MAX_WORDS and HELP_PATTERN.search(answer):
            return result(Signal.HELP_REQUESTED)
        if len(words) < 3:
            return result(Signal.AMBIGUOUS)

        for misconception in request.lesson.misconceptions:
            if misconception.objective != request.question.objective:
                continue
            keywords = MISCONCEPTION_KEYWORDS.get(misconception.tag, ())
            if any(keyword in answer for keyword in keywords):
                return result(Signal.MISCONCEPTION, misconception.tag)
        return result(Signal.ANSWERED)
