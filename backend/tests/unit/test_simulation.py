"""The benchmark harness itself: dataset consistency, determinism, and metric bookkeeping."""

from collections import Counter

import pytest

from app.config import REPO_ROOT
from app.domain.policy import Budget
from app.evals.simulation import (
    CachingEvaluator,
    Metrics,
    ScriptedLearner,
    build_profiles,
    load_bank,
    run_session,
)
from app.lesson_catalog import load_catalog
from app.providers.fake import FakeEvaluator
from app.providers.llm import EvaluatorOutput, LearnerIntent, ProposedEvidence

BANK = load_bank(REPO_ROOT / "data" / "evals" / "answer_bank.v1.json")
BUDGET = Budget(max_turns=5, max_seconds=1e9)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(REPO_ROOT / "data" / "lessons")


def test_bank_matches_the_lessons(catalog):
    for lesson_id, entry in BANK["lessons"].items():
        lesson = catalog.latest(lesson_id)
        assert set(entry["objectives"]) == {o.id for o in lesson.objectives}
        for objective, data in entry["objectives"].items():
            assert lesson.open_question_for(objective).id == data["open_question"]
            diagnostic = lesson.diagnostic_for(data["misconception"])
            assert diagnostic is not None and diagnostic.id == data["diagnostic_question"]
            assert lesson.misconception(data["misconception"]).objective == objective
            for pool in ("strong", "partial", "misconception_answers", "vague"):
                assert len(data[pool]) == 2 and all(isinstance(t, str) and t for t in data[pool])
            for pool in ("diagnostic_resolved", "diagnostic_persists"):
                assert len(data[pool]) == 2


def test_profiles_are_deterministic_and_split():
    first, second = build_profiles(BANK), build_profiles(BANK)
    assert first == second and len(first) == 60
    assert Counter(p.split for p in first) == {"dev": 42, "held_out": 18}
    assert len({p.id for p in first}) == 60
    states = Counter(s for p in first for s in p.states.values())
    assert set(states) == {
        "strong",
        "partial",
        "misconception_resolved",
        "misconception_persists",
        "vague",
    }
    assert any(p.hint_first for p in first) and any(p.side_question_first for p in first)


def profile_with(catalog, **changes):
    base = next(p for p in build_profiles(BANK) if p.lesson_id == "photosynthesis")
    from dataclasses import replace

    return replace(base, hint_first=None, side_question_first=None, **changes)


class PerfectEvaluator:
    """Returns exactly the label of the scripted answer (looked up by text)."""

    version = "perfect"

    def __init__(self, learner_answers: dict[str, tuple[int | None, str | None]]) -> None:
        self.labels = learner_answers

    def evaluate(self, request):
        level, tag = self.labels.get(request.transcript, (None, None))
        criterion = next(
            c.id for c in request.lesson.criteria if c.objective == request.question.objective
        )
        if request.transcript.endswith("?"):
            intent = (
                LearnerIntent.HELP_REQUEST
                if "hint" in request.transcript
                else LearnerIntent.SUBJECT_QUESTION
            )
            return EvaluatorOutput(intent, (), self.version)
        item = ProposedEvidence(
            criterion,
            level,
            request.transcript if level is not None else "",
            tag,
            "",
            level is None,
        )
        return EvaluatorOutput(LearnerIntent.ANSWER, (item,), self.version)


def labels_for(lesson_id: str) -> dict[str, tuple[int | None, str | None]]:
    labels: dict[str, tuple[int | None, str | None]] = {}
    for data in BANK["lessons"][lesson_id]["objectives"].values():
        tag = data["misconception"]
        for text in data["strong"] + data["diagnostic_resolved"]:
            labels[text] = (3, None)
        for text in data["partial"]:
            labels[text] = (2, None)
        for text in data["misconception_answers"] + data["diagnostic_persists"]:
            labels[text] = (1, tag)
    return labels


def test_adaptive_follows_up_and_fixed_does_not(catalog):
    lesson = catalog.latest("photosynthesis")
    profile = profile_with(
        catalog,
        states={
            "purpose": "strong",
            "carbon_dioxide": "misconception_resolved",
            "light": "partial",
        },
    )
    evaluate = PerfectEvaluator(labels_for("photosynthesis")).evaluate

    adaptive = run_session(lesson, profile, BANK, evaluate, "adaptive", BUDGET)
    assert [t.question_id for t in adaptive.turns] == ["q1", "q2", "q3", "q4"]
    assert adaptive.suggested == {"purpose": 3, "carbon_dioxide": 3, "light": 2}
    assert adaptive.detected_tags == {"co2_from_roots"}

    fixed = run_session(lesson, profile, BANK, evaluate, "fixed", BUDGET)
    assert [t.question_id for t in fixed.turns] == ["q1", "q2", "q4"]
    assert fixed.suggested["carbon_dioxide"] == 1  # never saw the corrected answer

    a, f = Metrics(), Metrics()
    a.add(adaptive, BANK)
    f.add(fixed, BANK)
    assert (a.learner_misconceptions, a.learner_misconceptions_followed_up) == (1, 1)
    assert (f.learner_misconceptions_detected, f.learner_misconceptions_followed_up) == (1, 0)
    assert a.level_exact == a.level_judged == 4 and a.final_within_one == a.final_judged == 3


def test_hint_first_answer_is_assisted_and_final_level_stays_unknown(catalog):
    lesson = catalog.latest("photosynthesis")
    profile = profile_with(
        catalog,
        states={"purpose": "strong", "carbon_dioxide": "strong", "light": "strong"},
    )
    from dataclasses import replace

    profile = replace(profile, hint_first="purpose", side_question_first="light")
    result = run_session(
        lesson,
        profile,
        BANK,
        PerfectEvaluator(labels_for("photosynthesis")).evaluate,
        "adaptive",
        BUDGET,
    )
    kinds = [(t.question_id, t.answer.kind, t.assisted) for t in result.turns]
    assert kinds[:2] == [("q1", "hint_request", False), ("q1", "answer", True)]
    assert ("q4", "side_question", False) in kinds
    assert result.suggested["purpose"] is None  # assisted evidence never sets the level
    metrics = Metrics()
    metrics.add(result, BANK)
    assert metrics.non_answers == 2 and metrics.non_answers_scored == 0
    assert (metrics.final_unknown_expected, metrics.final_unknown_kept) == (1, 1)


def test_vague_learner_gets_one_clarification_and_stays_unknown(catalog):
    lesson = catalog.latest("fractions")
    profile = next(p for p in build_profiles(BANK) if p.lesson_id == "fractions")
    from dataclasses import replace

    profile = replace(
        profile,
        states={"part_whole": "vague", "equivalence": "strong", "comparison": "strong"},
        hint_first=None,
        side_question_first=None,
    )
    learner = ScriptedLearner(BANK, profile)
    first = learner.answer(lesson.question("f1"))
    second = learner.answer(lesson.question("f1"))
    assert first.true_level is None and second.text in BANK["generic"]["vague_clarify"]


def test_whole_benchmark_runs_with_the_fake_and_caches(catalog):
    evaluator = CachingEvaluator(FakeEvaluator())
    metrics = Metrics()
    for profile in build_profiles(BANK):
        for policy in ("adaptive", "fixed"):
            lesson = catalog.latest(profile.lesson_id)
            metrics.add(run_session(lesson, profile, BANK, evaluator, policy, BUDGET), BANK)
    assert metrics.sessions == 120 and metrics.rejected_evidence == 0
    assert evaluator.calls < metrics.turns  # shared answers were evaluated once
    assert metrics.finish_reasons.keys() <= {"objectives_exhausted", "budget"}
