# Architecture

Status: Day 4 + conversation layer. Components marked *(planned)* do not exist in code yet.

## Diagram

```mermaid
flowchart TD
  UI[Next.js student UI] --> API[FastAPI REST API]
  UI <-->|WebRTC| RTC[LiveKit room]
  RTC <--> W[Python voice worker: STT/TTS via LiveKit Inference, no LLM]
  W -->|same /turns endpoint| API
  API --> O[Assessment orchestrator]
  O --> P[Question policy and lesson rubric]
  O --> E[Evaluator: keyword fake or Claude adapter]
  E --> V[Deterministic evidence validator]
  V --> S[Scoring: suggested levels, unknowns, conflicts]
  O --> RS[Responder: Claude or templates] --> G[Reply guardrails]
  O --> DB[(PostgreSQL durable records)]
  API --> DB
  API -.-> R[(Redis: readiness only so far)]
  API --> X[Mock Kira export adapter - planned]
```

## Component responsibilities

| Component | Code | Responsibility |
|---|---|---|
| Lesson schema | `backend/app/domain/models.py` | Defines a valid lesson; rejects broken references, missing rubric levels, ambiguous diagnostics |
| Lesson catalog | `backend/app/lesson_catalog.py` | Loads `data/lessons/*.json` at startup and for seeding |
| Lesson store | `backend/app/services/lessons.py` | Reads published versions from Postgres (runtime source of truth), caches forever |
| State machine | `backend/app/domain/state.py` | The only legal session status transitions |
| Question policy | `backend/app/domain/policy.py` | Pure function: (lesson, history, time, budget) → next action |
| Evaluator interface + Claude adapter | `backend/app/providers/llm.py` | `Evaluator` protocol (turn → intent + proposed evidence); `AnthropicEvaluator` with structured output and bounded retry |
| Evaluator prompt | `backend/app/providers/prompts.py` | Versioned prompt; untrusted transcript boundary |
| Fake evaluator | `backend/app/providers/fake.py` | Deterministic keyword rules; free and reproducible |
| Evidence validator | `backend/app/services/evaluator.py` | Accept / abstain / reject each item; derive the policy signal from accepted evidence only |
| Scoring | `backend/app/domain/scoring.py` | Suggested level per criterion; unknown, assisted, conflicts, coverage |
| Orchestrator | `backend/app/services/assessment.py` | Sessions, the claim/evaluate/commit turn algorithm, recovery, deadlines |
| Repositories | `backend/app/repositories/` | SQL for lessons, sessions, turns |
| API | `backend/app/api/` | Routes, bearer-token dependency, error → HTTP mapping |
| Student UI | `frontend/components/StudentSession.tsx` | Intro, transcript, answer form, hint/finish, retry and resume |
| Voice panel | `frontend/components/VoicePanel.tsx` | Join the LiveKit room, mic control, agent state; text stays available |
| Voice token + worker credential | `providers/livekit_tokens.py`, `services/voice_credentials.py` | Room token that dispatches the worker; per-session HMAC credential for the worker |
| Voice worker | `backend/app/voice/` | `worker.py` (LiveKit), `transport.py` (turn forwarding, testable), `client.py` (HTTP) |
| Responder | `backend/app/providers/responder.py`, `responder_prompt.py` | The short line said before each question; Claude (`claude-haiku-5-5`) or templates |
| Reply guardrails | `backend/app/services/conversation.py` | Length, no feedback, no answer-key terms; template otherwise. See [conversation.md](conversation.md) |

## Dependency direction

```text
api ──► services ──► domain
          │  └─────► providers (Evaluator protocol)
          └────────► repositories ──► db
```

`domain/` imports nothing from FastAPI, SQLAlchemy, Redis or provider SDKs.

## Request flow: one text turn

1. `StudentSession.send()` builds a `TurnInput` with a `client_turn_id` (kept in storage until
   confirmed) and the latest `state_version`, then calls `api.submitTurn()` (`frontend/lib/api.ts`).
2. `POST /v1/sessions/{id}/turns` → `api/sessions.py:submit_turn` → Pydantic validates the body;
   `api/deps.py:session_token` extracts the bearer token.
3. `AssessmentService.submit_turn`: refresh (T0), claim (T1), evaluator call outside any
   transaction, commit (T2). Details in [api.md](api.md#transaction-design-why-it-is-safe).
4. `services/evaluator.py:validate_output` checks every proposed evidence item against the
   lesson and the stored transcript; the signal comes from accepted items only. Evidence rows
   (accepted, abstained and rejected) are inserted in T2 with the turn.
5. The policy (`domain/policy.py:next_action`) picks the next question from committed history.
6. The student-facing `TurnResponse` is stored on the turn row and returned. The UI then
   refetches the session to render the transcript.

## Key decisions and tradeoffs

- **Lesson versions are immutable** (frozen models, hash check, DB trigger). Sessions pin
  `(lesson_id, version)` by foreign key.
- **Deterministic policy, conversational surface.** The policy picks every question, and the
  authored wording is always used. A responder model writes only the short line in front
  of it, behind deterministic guardrails. Side turns (questions, "say that again", off topic)
  re-ask the question without using the answer budget, up to a cap.
- **The LLM proposes, code disposes.** The evaluator's output is validated before it can affect
  the policy or a score; see [assessment-policy.md](assessment-policy.md).
- **Budget counts learner turns** (default 5), including hint requests and clarifications.
- **Idempotency and concurrency in Postgres**, not Redis. See
  [ADR 0001](adr/0001-database-idempotency.md).
- **Learner "stop" vs "finish early".** Saying a stop phrase ends the session as `completed`
  with `finish_reason = learner_request` (the state machine only allows evaluating →
  completed for a policy finish). Pressing "Finish early" makes it `incomplete` /
  `learner_exit`. Reports (Day 5) must show uncovered objectives as unknown either way.
- **Demo auth is a per-session bearer token**, not real accounts.
