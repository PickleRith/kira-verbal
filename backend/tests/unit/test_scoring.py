from app.domain.models import Lesson
from app.domain.scoring import EvidenceRecord, EvidenceStatus, summarize

A, AB, R = EvidenceStatus.ACCEPTED, EvidenceStatus.ABSTAINED, EvidenceStatus.REJECTED


def rec(criterion, level, status=A, *, assisted=False, tag=None, seq=1) -> EvidenceRecord:
    return EvidenceRecord(criterion, level, status, assisted, tag, seq)


def by_id(summary):
    return {c.criterion_id: c for c in summary.criteria}


def test_no_evidence_means_unknown_not_zero(photosynthesis: Lesson):
    summary = summarize(photosynthesis, [])
    assert all(c.suggested_level is None for c in summary.criteria)
    assert (summary.criteria_with_evidence, summary.criteria_total) == (0, 3)
    assert not summary.needs_review


def test_latest_independent_evidence_sets_the_suggestion(photosynthesis: Lesson):
    summary = summarize(
        photosynthesis,
        [rec("carbon_dioxide", 1, tag="co2_from_roots", seq=2), rec("carbon_dioxide", 3, seq=3)],
    )
    co2 = by_id(summary)["carbon_dioxide"]
    assert co2.suggested_level == 3
    assert co2.independent_levels == (1, 3)
    assert co2.misconception_tags == ("co2_from_roots",)
    assert co2.conflicting and summary.needs_review  # 1 then 3: a teacher should look


def test_assisted_evidence_never_sets_the_suggestion(photosynthesis: Lesson):
    summary = summarize(photosynthesis, [rec("purpose", 3, assisted=True)])
    purpose = by_id(summary)["purpose"]
    assert purpose.suggested_level is None
    assert purpose.assisted_levels == (3,)
    assert summary.criteria_with_evidence == 0


def test_correct_after_hint_leaves_independent_level_unchanged(photosynthesis: Lesson):
    summary = summarize(
        photosynthesis,
        [rec("purpose", 1, seq=1), rec("purpose", 3, assisted=True, seq=3)],
    )
    purpose = by_id(summary)["purpose"]
    assert purpose.suggested_level == 1
    assert (purpose.independent_levels, purpose.assisted_levels) == ((1,), (3,))
    assert not purpose.conflicting


def test_abstained_and_rejected_never_count(photosynthesis: Lesson):
    summary = summarize(
        photosynthesis,
        [rec("light", None, AB), rec("light", 3, R)],
    )
    light = by_id(summary)["light"]
    assert light.suggested_level is None
    assert (light.abstentions, light.rejected) == (1, 1)
    assert summary.needs_review  # rejected evidence (e.g. invented quote) is flagged


def test_coverage_counts_criteria_with_a_suggestion(photosynthesis: Lesson):
    summary = summarize(photosynthesis, [rec("purpose", 2), rec("light", 3)])
    assert (summary.criteria_with_evidence, summary.criteria_total) == (2, 3)


def test_unknown_criterion_ids_are_ignored(photosynthesis: Lesson):
    summary = summarize(photosynthesis, [rec("gravity", 3)])
    assert summary.criteria_with_evidence == 0
