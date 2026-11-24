"""Deterministic guardrails on responder replies.

The responder's instructions already forbid feedback and teaching. These checks are the
backstop for when a model ignores them, and they decide only one thing: use the reply or
use the template. They never classify what the learner meant (the evaluator does that).

A reply is rejected if it:

* is empty, or longer than MAX_REPLY_CHARS;
* contains a link, an email-like "@", markdown, or a line break;
* gives evaluative feedback ("correct", "not quite", "great job" ...): an assessment
  that tells the learner they are right or wrong is no longer measuring what they know;
* uses an answer-key term: a content word from any criterion's top-level (level 3)
  descriptor in this lesson, unless that word already appears in the learner's own
  words, the question just asked, the next question or the lesson title. Example: on
  "Where does a plant get carbon dioxide?" a reply mentioning "stomata" or "air" is
  rejected unless the learner said it first.

The answer-key check over-blocks on purpose: a blocked reply only costs a plainer
template line, while a leaked answer would corrupt the learner's evidence. Rejections are
recorded per turn (`turns.reply_source = "fallback:<reason>"`) so the rate can be measured.
"""

from __future__ import annotations

import re

from app.domain.models import Lesson

MAX_REPLY_CHARS = 300

_WORD = re.compile(r"[a-z]+")
_LINK_OR_MARKUP = re.compile(r"https?://|www\.|@|[*#`\[\]<>]|\n")
_EVALUATIVE = re.compile(
    r"\b(correct|correctly|incorrect|wrong|exactly|right answer|not quite|almost|"
    r"well done|great job|good job|nice job|great answer|good answer|perfect|spot on|"
    r"excellent|that'?s right|that is right|you'?re right|you are right|nailed it)\b"
)

# Generic words and rubric-writing words that carry no answer content.
_STOPWORDS = frozenset(
    """
    a about above after again all also an and any are as at be because been before being
    both but by can cannot could did do does doing done each either explain explains
    explained explanation for from gives give given has have how if in into is it its
    just like mentions more most no not of on once one only or other out over own same
    says say states state such than that the their them then there these they this those
    through to too two under up very was way we were what when where which while who why
    will with without would you your describes describe names name matches correct
    correctly accurate accurately partial partially mostly omits omission make makes
    making come comes using use uses many mean means time times per must set eventually
    provide provides
    """.split()
)


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower().replace("’", "'"))}


_TERMS_CACHE: dict[tuple[str, int], frozenset[str]] = {}


def answer_key_terms(lesson: Lesson) -> frozenset[str]:
    """Content-word stems from every criterion's level-3 descriptor.

    Cached by (id, version): published versions are immutable, so this never goes stale.
    """
    key = (lesson.id, lesson.version)
    if key not in _TERMS_CACHE:
        terms: set[str] = set()
        for criterion in lesson.criteria:
            for word in _WORD.findall(criterion.levels["3"].lower()):
                if len(word) >= 3 and word not in _STOPWORDS:
                    terms.add(_stem(word))
        _TERMS_CACHE[key] = frozenset(terms)
    return _TERMS_CACHE[key]


def check_reply(reply: str, *, lesson: Lesson, allowed_context: str) -> str | None:
    """Return None if the reply may be used, else a short machine-readable reason.

    `allowed_context` is text the learner has already seen or said this turn: their own
    words, the question just asked, the next question and the lesson title.
    """
    text = reply.strip()
    if not text:
        return "empty"
    if len(text) > MAX_REPLY_CHARS:
        return "too_long"
    if _LINK_OR_MARKUP.search(text):
        return "link_or_markup"
    lowered = text.lower().replace("’", "'")
    if _EVALUATIVE.search(lowered):
        return "evaluative"
    leaked = (_stems(lowered) & answer_key_terms(lesson)) - _stems(allowed_context)
    if leaked:
        return "answer_key_term"
    return None
