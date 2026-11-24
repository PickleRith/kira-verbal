"""Offline benchmark: scripted synthetic learners played through the real assessment logic.

No database and no HTTP: a session is simulated with the same pure pieces the API uses
(`next_action`, an `Evaluator`, `validate_output`, `summarize`), so results reflect the
shipped policy, validation and scoring, and a run is reproducible.

Pieces:
* Answer bank (data/evals/answer_bank.v1.json): authored answers per lesson, objective and
  understanding state, each with a true level / misconception fixed at writing time.
* Profiles: 20 per lesson, generated deterministically from a seed. A profile gives each
  objective a state, picks phrasing variants, and may ask for a hint or ask a side
  question first. Every third profile is "held_out": report it separately and never tune
  prompts against it.
* Two policies on identical profiles:
    adaptive  the product policy (diagnostic follow-ups, one clarification)
    fixed     baseline: the open question for each objective, nothing else. Implemented by
              hiding misconception / ambiguous signals from the policy.
* Metrics compare what the system concluded with the labels of the answers the learner
  actually gave in that session (see `Metrics`).

Synthetic scripts are a limited proxy. They cannot show anything about real learners.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.domain.models import Lesson, Question
from app.domain.policy import (
    Budget,
    Finish,
    GiveHint,
    Signal,
    TurnRecord,
    next_action,
)
from app.domain.scoring import EvidenceRecord, EvidenceStatus, summarize
from app.providers.llm import EvaluationRequest, Evaluator, EvaluatorOutput
from app.services.evaluator import validate_output

PolicyName = Literal["adaptive", "fixed"]
State = Literal["strong", "partial", "misconception_resolved", "misconception_persists", "vague"]

STATE_WEIGHTS: dict[str, int] = {
    "strong": 3,
    "partial": 3,
    "misconception_resolved": 2,
    "misconception_persists": 2,
    "vague": 1,
}
TRUE_LEVEL = {"strong": 3, "partial": 2, "misconception": 1, "resolved": 3, "persists": 1}
PROFILES_PER_LESSON = 20
SEED = 20261123
MAX_STEPS = 40  # safety net; the policy's own budget ends sessions long before this


# --- data -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    id: str
    lesson_id: str
    split: Literal["dev", "held_out"]
    states: dict[str, str]  # objective -> state
    variants: dict[str, int]  # objective -> phrasing index
    hint_first: str | None  # objective where the learner asks for a hint before answering
    side_question_first: str | None  # objective where the learner first asks about the topic


@dataclass(frozen=True)
class Answer:
    text: str
    kind: Literal["answer", "hint_request", "side_question"]
    true_level: int | None = None  # None = too vague to judge
    true_tag: str | None = None


def load_bank(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_profiles(bank: dict[str, Any], *, seed: int = SEED) -> list[Profile]:
    rng = random.Random(seed)
    states, weights = list(STATE_WEIGHTS), list(STATE_WEIGHTS.values())
    profiles: list[Profile] = []
    for lesson_id, lesson in bank["lessons"].items():
        objectives = list(lesson["objectives"])
        for n in range(PROFILES_PER_LESSON):
            chosen = {o: rng.choices(states, weights)[0] for o in objectives}
            answerable = [o for o in objectives if chosen[o] in ("strong", "partial")]
            hint = rng.choice(answerable) if answerable and rng.random() < 0.15 else None
            side = rng.choice(objectives) if rng.random() < 0.15 else None
            profiles.append(
                Profile(
                    id=f"{lesson_id}-{n + 1:02d}",
                    lesson_id=lesson_id,
                    split="held_out" if n % 3 == 2 else "dev",
                    states=chosen,
                    variants={o: rng.randrange(2) for o in objectives},
                    hint_first=hint,
                    side_question_first=side if side != hint else None,
                )
            )
    return profiles


class ScriptedLearner:
    """Answers questions from the bank according to one profile."""

    def __init__(self, bank: dict[str, Any], profile: Profile) -> None:
        self._generic = bank["generic"]
        self._lesson = bank["lessons"][profile.lesson_id]
        self.profile = profile
        self._asked: dict[str, int] = {}
        self._used_hint = self._used_side = False

    def answer(self, question: Question) -> Answer:
        objective = question.objective
        entry = self._lesson["objectives"][objective]
        state, variant = self.profile.states[objective], self.profile.variants[objective]
        times = self._asked.get(question.id, 0)
        self._asked[question.id] = times + 1
        tag = entry["misconception"]

        if question.id == entry["diagnostic_question"]:
            if state == "vague":
                return Answer(entry["vague"][variant], "answer")
            if state == "misconception_persists":
                text = entry["diagnostic_persists"][variant]
                return Answer(text, "answer", TRUE_LEVEL["persists"], tag)
            # Resolved, or a learner without the misconception: answers it correctly.
            return Answer(entry["diagnostic_resolved"][variant], "answer", TRUE_LEVEL["resolved"])

        if times == 0:
            if self.profile.side_question_first == objective and not self._used_side:
                self._used_side = True
                self._asked[question.id] = 0  # the real answer is still to come
                return Answer(self._lesson["side_question"], "side_question")
            if self.profile.hint_first == objective and not self._used_hint:
                self._used_hint = True
                self._asked[question.id] = 0
                return Answer(self._generic["hint_request"], "hint_request")
        if state == "vague":
            pool = entry["vague"] if times == 0 else self._generic["vague_clarify"]
            return Answer(pool[variant], "answer")
        if state.startswith("misconception"):
            return Answer(
                entry["misconception_answers"][variant], "answer", TRUE_LEVEL["misconception"], tag
            )
        return Answer(entry[state][variant], "answer", TRUE_LEVEL[state])


# --- one simulated session --------------------------------------------------------------


@dataclass
class TurnLog:
    question_id: str
    criterion_id: str
    answer: Answer
    assisted: bool
    signal: str
    accepted_level: int | None
    accepted_tag: str | None
    rejected: int


@dataclass
class SessionResult:
    profile: Profile
    policy: PolicyName
    turns: list[TurnLog]
    finish_reason: str
    suggested: dict[str, int | None]  # criterion -> system level
    detected_tags: set[str]
    criteria_total: int


def _policy_view(history: list[TurnRecord], policy: PolicyName) -> list[TurnRecord]:
    if policy == "adaptive":
        return history
    hidden = {Signal.MISCONCEPTION, Signal.AMBIGUOUS}
    return [
        TurnRecord(r.question_id, Signal.ANSWERED) if r.signal in hidden else r for r in history
    ]


def run_session(
    lesson: Lesson,
    profile: Profile,
    bank: dict[str, Any],
    evaluate: Callable[[EvaluationRequest], EvaluatorOutput],
    policy: PolicyName,
    budget: Budget,
) -> SessionResult:
    learner = ScriptedLearner(bank, profile)
    history: list[TurnRecord] = []
    turns: list[TurnLog] = []
    records: list[EvidenceRecord] = []
    hinted: set[str] = set()
    finish = "max_steps"
    for sequence in range(1, MAX_STEPS + 1):
        action = next_action(
            lesson, _policy_view(history, policy), elapsed_seconds=0.0, budget=budget
        )
        if isinstance(action, Finish):
            finish = action.reason.value
            break
        question = lesson.question(action.question_id)
        if isinstance(action, GiveHint):
            hinted.add(question.id)
        assisted = question.id in hinted
        answer = learner.answer(question)
        output = evaluate(EvaluationRequest(lesson, question, answer.text, assisted))
        assessment = validate_output(lesson, question, answer.text, output)
        history.append(TurnRecord(question.id, assessment.signal, assessment.misconception_tag))
        accepted = [e for e in assessment.evidence if e.status is EvidenceStatus.ACCEPTED]
        for item in assessment.evidence:
            records.append(
                EvidenceRecord(
                    criterion_id=item.criterion_id,
                    level=item.proposed_level,
                    status=item.status,
                    assisted=assisted,
                    misconception_tag=item.misconception_tag,
                    sequence=sequence,
                )
            )
        criterion = next(c.id for c in lesson.criteria if c.objective == question.objective)
        turns.append(
            TurnLog(
                question_id=question.id,
                criterion_id=criterion,
                answer=answer,
                assisted=assisted,
                signal=assessment.signal.value,
                accepted_level=accepted[0].proposed_level if accepted else None,
                accepted_tag=next(
                    (e.misconception_tag for e in accepted if e.misconception_tag), None
                ),
                rejected=sum(e.status is EvidenceStatus.REJECTED for e in assessment.evidence),
            )
        )
    summary = summarize(lesson, records)
    return SessionResult(
        profile=profile,
        policy=policy,
        turns=turns,
        finish_reason=finish,
        suggested={c.criterion_id: c.suggested_level for c in summary.criteria},
        detected_tags={t for c in summary.criteria for t in c.misconception_tags},
        criteria_total=summary.criteria_total,
    )


# --- metrics ----------------------------------------------------------------------------


@dataclass
class Metrics:
    """Counts, so every reported rate can be shown with its denominator."""

    sessions: int = 0
    turns: int = 0
    # Per answer the learner gave (kind == "answer"):
    answers: int = 0
    level_judged: int = 0  # labelled level AND system accepted a level
    level_exact: int = 0
    level_within_one: int = 0
    abstained_on_judgeable: int = 0  # labelled level, system gave none
    vague_answers: int = 0
    vague_left_unknown: int = 0  # correct: no level invented
    # Misconception tags per answer:
    tag_true_positive: int = 0
    tag_false_positive: int = 0
    tag_false_negative: int = 0
    # Non-answers:
    non_answers: int = 0
    non_answers_scored: int = 0  # a hint request / side question that produced a level (bad)
    rejected_evidence: int = 0
    # Per session:
    criteria: int = 0
    criteria_with_level: int = 0
    final_judged: int = 0  # truth and system both have a final independent level
    final_within_one: int = 0
    final_unknown_expected: int = 0  # truth: no independent judgeable answer
    final_unknown_kept: int = 0
    learner_misconceptions: int = 0  # profile-level truth, asked or not
    learner_misconceptions_detected: int = 0
    learner_misconceptions_followed_up: int = 0  # a diagnostic answer was collected
    finish_reasons: dict[str, int] = field(default_factory=dict)

    def add(self, result: SessionResult, bank: dict[str, Any]) -> None:
        self.sessions += 1
        self.turns += len(result.turns)
        self.finish_reasons[result.finish_reason] = (
            self.finish_reasons.get(result.finish_reason, 0) + 1
        )
        truth_final: dict[str, int | None] = {}
        answered: set[str] = set()
        for turn in result.turns:
            self.rejected_evidence += turn.rejected
            if turn.answer.kind != "answer":
                self.non_answers += 1
                self.non_answers_scored += turn.accepted_level is not None
                continue
            self.answers += 1
            truth = turn.answer.true_level
            if truth is None:
                self.vague_answers += 1
                self.vague_left_unknown += turn.accepted_level is None
            elif turn.accepted_level is None:
                self.abstained_on_judgeable += 1
            else:
                self.level_judged += 1
                self.level_exact += turn.accepted_level == truth
                self.level_within_one += abs(turn.accepted_level - truth) <= 1
            if turn.answer.true_tag and turn.accepted_tag == turn.answer.true_tag:
                self.tag_true_positive += 1
            elif turn.answer.true_tag:
                self.tag_false_negative += 1
            if turn.accepted_tag and turn.accepted_tag != turn.answer.true_tag:
                self.tag_false_positive += 1
            if not turn.assisted:  # only independent answers set the final level
                answered.add(turn.criterion_id)
                if truth is not None:
                    truth_final[turn.criterion_id] = truth

        self.criteria += result.criteria_total
        for criterion, level in result.suggested.items():
            self.criteria_with_level += level is not None
            expected = truth_final.get(criterion)
            if expected is None:
                self.final_unknown_expected += 1
                self.final_unknown_kept += level is None
            elif level is not None:
                self.final_judged += 1
                self.final_within_one += abs(level - expected) <= 1

        lesson_bank = bank["lessons"][result.profile.lesson_id]["objectives"]
        asked = {t.question_id for t in result.turns if t.answer.kind == "answer"}
        for objective, state in result.profile.states.items():
            if not state.startswith("misconception"):
                continue
            self.learner_misconceptions += 1
            self.learner_misconceptions_detected += (
                lesson_bank[objective]["misconception"] in result.detected_tags
            )
            self.learner_misconceptions_followed_up += (
                lesson_bank[objective]["diagnostic_question"] in asked
            )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class CachingEvaluator:
    """Same answer to the same question is evaluated once, so both policies (and reruns in
    one process) share calls. Thread-safe enough for a small pool: a duplicate call is
    harmless."""

    def __init__(self, evaluator: Evaluator) -> None:
        self._evaluator = evaluator
        self._cache: dict[tuple[str, str, str, bool], EvaluatorOutput] = {}
        self.calls = 0
        self.errors = 0
        self.latencies: list[float] = []

    def __call__(self, request: EvaluationRequest) -> EvaluatorOutput:
        import time

        key = (request.lesson.id, request.question.id, request.transcript, request.assisted)
        if key not in self._cache:
            started = time.perf_counter()
            self.calls += 1
            try:
                self._cache[key] = self._evaluator.evaluate(request)
            except Exception:
                self.errors += 1
                raise
            self.latencies.append(time.perf_counter() - started)
        return self._cache[key]
