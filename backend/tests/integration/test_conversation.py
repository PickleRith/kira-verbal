"""Conversation layer end to end against real Postgres (fake evaluator, scripted responders)."""

from __future__ import annotations

import dataclasses
import threading

import pytest
from sqlalchemy import Engine, select
from test_assessment_service import GOOD_Q1, ROOTS_Q2, Learner  # same folder (pytest rootdir)

from app.db.models import EvidenceRow, TurnRow
from app.providers.llm import LearnerIntent
from app.providers.responder import SIDE_TURN_REPLIES, ResponderRequest
from app.services.assessment import AssessmentService

pytestmark = pytest.mark.integration

SUBJECT_TEMPLATE = SIDE_TURN_REPLIES[LearnerIntent.SUBJECT_QUESTION]


class ScriptedResponder:
    """Returns a fixed reply (or raises / blocks) and records every request."""

    version = "scripted-v1"

    def __init__(self, reply: str | None = None, *, error: Exception | None = None) -> None:
        self.reply, self.error = reply, error
        self.requests: list[ResponderRequest] = []
        self.gate: threading.Event | None = None

    def respond(self, request: ResponderRequest) -> str | None:
        self.requests.append(request)
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.error is not None:
            raise self.error
        return self.reply


def turn_rows(engine: Engine, session_id) -> list[TurnRow]:
    with engine.connect() as c:
        return list(
            c.execute(
                select(TurnRow.intent, TurnRow.signal, TurnRow.reply_source, TurnRow.assisted)
                .where(TurnRow.session_id == session_id)
                .order_by(TurnRow.sequence)
            ).all()
        )


def test_subject_question_re_asks_without_using_the_answer_budget(
    service: AssessmentService, seeded_engine: Engine
):
    learner = Learner(service)
    r = learner.say("What are stomata?")
    assert (r.prompt.question_id, r.prompt.purpose) == ("q1", "respond")
    assert r.prompt.lead_in == SUBJECT_TEMPLATE
    assert r.prompt.text == "Explain photosynthesis in your own words."  # verbatim

    # Four side turns are free (default allowance), so all five answers still happen.
    for _ in range(3):
        learner.say("Can you repeat that?")
    for text in (GOOD_Q1, ROOTS_Q2):
        learner.say(text)
    assert learner.question_id == "q3"  # the roots diagnostic was still earned

    rows = turn_rows(seeded_engine, learner.id)
    assert [row.intent for row in rows[:4]] == [
        "subject_question",
        "clarification_request",
        "clarification_request",
        "clarification_request",
    ]
    assert {row.signal for row in rows[:4]} == {"conversation"}
    with seeded_engine.connect() as c:
        statuses = c.execute(
            select(EvidenceRow.validation_status)
            .join(TurnRow, TurnRow.id == EvidenceRow.turn_id)
            .where(TurnRow.session_id == learner.id, TurnRow.signal == "conversation")
        ).all()
    assert all(s == "rejected" for (s,) in statuses)  # never scored


def test_refetch_shows_the_same_lead_in_and_the_transcript_shows_replies(
    service: AssessmentService,
):
    learner = Learner(service)
    sent = learner.say("What are stomata?")
    view = service.get_session(learner.id, learner.token)
    assert view.prompt == sent.prompt  # resume / voice resync see exactly what was said
    [entry] = view.transcript
    assert (entry.answer, entry.reply) == ("What are stomata?", SUBJECT_TEMPLATE)


def test_model_reply_is_used_when_it_passes_the_guard(
    service: AssessmentService, seeded_engine: Engine
):
    service.responder = ScriptedResponder("Thanks for sharing that. Let's keep going.")
    learner = Learner(service)
    r = learner.say(GOOD_Q1)
    assert r.prompt.lead_in == "Thanks for sharing that. Let's keep going."
    assert r.prompt.text == "Where does a plant get carbon dioxide?"
    assert turn_rows(seeded_engine, learner.id)[0].reply_source == "scripted-v1"


@pytest.mark.parametrize(
    ("reply", "source"),
    [
        ("Good question! Stomata are tiny holes in the leaves.", "fallback:answer_key_term"),
        ("Correct! Nice one.", "fallback:evaluative"),
        ("x" * 400, "fallback:too_long"),
    ],
)
def test_unsafe_model_reply_falls_back_to_the_template(
    service: AssessmentService, seeded_engine: Engine, reply, source
):
    service.responder = ScriptedResponder(reply)
    learner = Learner(service)
    r = learner.say("What are stomata?")
    assert r.prompt.lead_in == SUBJECT_TEMPLATE
    assert turn_rows(seeded_engine, learner.id)[0].reply_source == source


def test_responder_failure_never_fails_the_turn(service: AssessmentService, seeded_engine):
    service.responder = ScriptedResponder(error=RuntimeError("provider down"))
    learner = Learner(service)
    r = learner.say("I don't know")  # hint
    assert r.prompt.purpose == "hint" and r.prompt.lead_in.startswith("Here's a hint:")
    assert turn_rows(seeded_engine, learner.id)[0].reply_source == "fallback:error"


def test_slow_responder_times_out_to_the_template(service: AssessmentService, seeded_engine):
    service.config = dataclasses.replace(service.config, responder_timeout_seconds=0.2)
    slow = ScriptedResponder("Sure, here it is again.")
    slow.gate = threading.Event()  # never set: blocks until its own 5 s wait expires
    service.responder = slow
    learner = Learner(service)
    r = learner.say("Can you repeat that?")
    slow.gate.set()
    assert r.prompt.lead_in == SIDE_TURN_REPLIES[LearnerIntent.CLARIFICATION_REQUEST]
    assert turn_rows(seeded_engine, learner.id)[0].reply_source == "fallback:error"


def test_hint_stays_through_a_side_turn_and_the_answer_is_assisted(
    service: AssessmentService, seeded_engine: Engine
):
    learner = Learner(service)
    hinted = learner.say("Can I have a hint?")
    assert hinted.prompt.hint
    r = learner.say("What do you mean?")
    assert r.prompt.purpose == "respond" and r.prompt.hint == hinted.prompt.hint
    learner.say(GOOD_Q1)
    assert [row.assisted for row in turn_rows(seeded_engine, learner.id)] == [False, True, True]


def test_hint_reply_keeps_the_authored_hint_word_for_word(service: AssessmentService):
    service.responder = ScriptedResponder("No problem.")
    learner = Learner(service)
    r = learner.say("Can I have a hint?")
    assert r.prompt.lead_in == f"No problem. Here's a hint: {r.prompt.hint}"


def test_wellbeing_concern_is_recorded_and_answered_with_care(
    service: AssessmentService, seeded_engine: Engine
):
    learner = Learner(service)
    r = learner.say("I'm scared to go home today")
    assert "adult you trust" in r.prompt.lead_in
    assert turn_rows(seeded_engine, learner.id)[0].intent == "wellbeing_concern"


def test_retry_replays_the_reply_without_asking_the_responder_again(
    service: AssessmentService,
):
    responder = ScriptedResponder("Sure, here it is again.")
    service.responder = responder
    learner = Learner(service)
    turn = learner.turn("Can you repeat that?", cid="same-id")
    first = learner.submit(turn)
    again = service.submit_turn(learner.id, learner.token, turn)
    assert again == first
    assert len(responder.requests) == 1


def test_responder_sees_the_learner_and_recent_exchanges_but_no_rubric(
    service: AssessmentService,
):
    responder = ScriptedResponder(None)
    service.responder = responder
    learner = Learner(service)
    learner.say(GOOD_Q1)
    learner.say("Why do plants need air?")
    request = responder.requests[-1]
    assert request.learner_text == "Why do plants need air?"
    assert request.intent is LearnerIntent.SUBJECT_QUESTION
    assert request.next_step == "repeat_question"
    assert [e.learner_text for e in request.recent] == [GOOD_Q1]
