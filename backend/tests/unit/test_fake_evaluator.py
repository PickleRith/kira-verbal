import pytest

from app.domain.models import Lesson
from app.domain.policy import Signal
from app.lesson_catalog import load_catalog
from app.providers.fake import FakeEvaluator
from app.providers.llm import EvaluationRequest
from app.services.evaluator import TurnAssessment, validate_output


def assess(lesson: Lesson, question_id: str, text: str) -> TurnAssessment:
    question = lesson.question(question_id)
    output = FakeEvaluator().evaluate(EvaluationRequest(lesson, question, text, assisted=False))
    assert output.evaluator_version == "fake-keyword-v2"
    return validate_output(lesson, question, text, output)


@pytest.mark.parametrize(
    ("question_id", "text", "signal", "tag"),
    [
        ("q2", "From the soil through its roots.", Signal.MISCONCEPTION, "co2_from_roots"),
        ("q2", "It comes from the air around the leaves.", Signal.ANSWERED, None),
        ("q1", "Can I get a hint?", Signal.HELP_REQUESTED, None),
        ("q1", "I don't know", Signal.HELP_REQUESTED, None),
        ("q1", "Stop.", Signal.STOP_REQUESTED, None),
        ("q1", "", Signal.AMBIGUOUS, None),
        ("q1", "yes", Signal.AMBIGUOUS, None),
        # A tag is only produced for misconceptions of the question's own objective.
        ("q4", "It takes water from the soil and roots.", Signal.ANSWERED, None),
    ],
)
def test_rules(photosynthesis: Lesson, question_id, text, signal, tag):
    result = assess(photosynthesis, question_id, text)
    assert (result.signal, result.misconception_tag) == (signal, tag)


def test_fake_evidence_passes_the_same_validator_as_the_llm(photosynthesis: Lesson):
    result = assess(photosynthesis, "q2", "  From the soil through its roots.  ")
    [item] = result.evidence
    assert item.status == "accepted" and item.proposed_level == 1
    assert item.criterion_id == "carbon_dioxide"


def test_short_answer_is_an_abstention_not_a_zero(photosynthesis: Lesson):
    [item] = assess(photosynthesis, "q1", "yes").evidence
    assert item.status == "abstained" and item.proposed_level is None


def test_long_answer_mentioning_help_is_not_a_help_request(photosynthesis: Lesson):
    text = "Sunlight helps the plant turn carbon dioxide and water into sugar and oxygen."
    assert assess(photosynthesis, "q1", text).signal is Signal.ANSWERED


def test_stop_word_inside_an_answer_is_not_a_stop_request(lessons_dir):
    loops = load_catalog(lessons_dir).get("python_loops", 1)
    text = "The loop will stop when the condition becomes false."
    assert assess(loops, "p3", text).signal is Signal.ANSWERED
