# API

Base URL (local): `http://127.0.0.1:8000`. Interactive schema: `/docs`, raw OpenAPI: `/openapi.json`.
All bodies are JSON. Unknown request fields are rejected (422).

## Authorization (demo)

`POST /v1/sessions` returns a `session_token` once. Every other session call needs
`Authorization: Bearer <session_token>`. Only a SHA-256 hash is stored.

- Missing token → `401 missing_token`.
- Wrong token **or** unknown session → `404 session_not_found` (deliberately identical, so a
  caller cannot probe which session IDs exist).

This isolates synthetic demo sessions from each other. It is not school authentication.

## Endpoints

| Method / path | Purpose | Success |
|---|---|---|
| `GET /health` | Process is up (no dependency checks) | 200 |
| `GET /ready` | Postgres, Redis and lessons OK | 200 / 503 |
| `GET /v1/lessons` | Latest published version of each lesson | 200 |
| `POST /v1/sessions` | Create a session; returns token and first prompt | 201 |
| `GET /v1/sessions/{id}` | Current state, prompt and transcript (resume) | 200 |
| `POST /v1/sessions/{id}/turns` | Submit one finalized answer | 200 |
| `POST /v1/sessions/{id}/finish` | Learner exits early → `incomplete` (idempotent) | 200 |
| `POST /v1/sessions/{id}/voice-token` | LiveKit room token that dispatches the voice worker; 503 `voice_unavailable` if not configured, 409 if the session is closed | 200 |

The voice worker authenticates with a per-session credential (`v1.<session>.<expiry>.<hmac>`)
in the same `Authorization: Bearer` header. It is accepted only for its own session and only
until the session deadline. See [voice-pipeline.md](voice-pipeline.md).

Student responses never include evaluator output (signals, misconception tags, levels).
A test asserts this.

## Example: create

```http
POST /v1/sessions
{"lesson_id": "photosynthesis"}
```
```json
{
  "id": "6f1c…",
  "lesson": {"id": "photosynthesis", "version": 1, "title": "Photosynthesis"},
  "status": "awaiting_answer",
  "state_version": 1,
  "prompt": {"question_id": "q1", "text": "Explain photosynthesis in your own words.",
             "purpose": "open", "lead_in": null, "hint": null},
  "finish_reason": null,
  "transcript": [],
  "deadline_at": "2026-11-23T23:06:00Z",
  "session_token": "…"
}
```
`lesson_version` may be given to pin a specific version; omitted means latest.

## Example: submit a turn

```http
POST /v1/sessions/{id}/turns
Authorization: Bearer …
{"client_turn_id": "b6f0…", "expected_state_version": 3, "transcript": "From the soil through its roots.",
 "modality": "text", "question_id": "q2"}
```
```json
{"state_version": 5, "status": "awaiting_answer",
 "prompt": {"question_id": "q3", "text": "How do leaves exchange gases with the air?",
            "purpose": "diagnostic", "lead_in": null, "hint": null},
 "finish_reason": null}
```
Each accepted turn advances `state_version` by 2 (claim, then commit). Clients should
treat it as opaque and always echo the latest value they were given.

`prompt.purpose` is `open`, `diagnostic` (approved follow-up), `clarify` (one request for
more detail after an unclear answer), `hint`, or `respond` (the same question again after
a turn that was not an answer, such as a question about the topic or "say that again"; see
[conversation.md](conversation.md)). Whenever `lead_in` is set, show or speak it before
`text`. It is the agent's reply to the last turn, followed by the authored hint if there is
one. `text` is always the authored question, word for word. `GET` returns the same
`lead_in` as the turn response did. Each transcript entry has a `reply`, which is what the
agent said after that turn. When the session finishes, `prompt` is `null` and `finish_reason` is
one of `objectives_exhausted`, `budget`, `learner_request`, `timeout`, `learner_exit`.

Limits: `transcript` ≤ 2000 characters (may be empty; an empty answer gets a clarification,
never a zero). `client_turn_id` matches `^[A-Za-z0-9_-]{1,64}$`.

## Errors

Body: `{"error": "<code>", "message": "…", "state_version": <int|null>}`.

| Status | `error` | Meaning | Client should |
|---|---|---|---|
| 401 | `missing_token` | No bearer token | Send the token |
| 404 | `session_not_found` | Unknown session or wrong token | Stop |
| 404 | `lesson_not_found` | Lesson not published | Run seed / pick another |
| 409 | `stale_state_version` | Session moved on | Refetch, show latest prompt |
| 409 | `question_mismatch` | Answer is for a different question | Refetch |
| 409 | `idempotency_mismatch` | Same `client_turn_id`, different payload | New id after refetch |
| 409 | `turn_in_progress` | Still processing (`Retry-After: 1`) | Retry the same request |
| 409 | `claim_lost` | Processing lease expired and was recovered | Refetch, resend same id |
| 409 | `session_closed` | Session completed/incomplete | Show finished state |
| 409 | `session_expired` | Deadline passed | Show finished state |
| 422 | (FastAPI) | Invalid body | Fix input |
| 503 | `evaluation_unavailable` | Evaluator failed/timed out (`Retry-After: 1`); answer released | Refetch, resend same id with new version |

Rate limiting (429) is planned for Day 6.

## Idempotency

- The key is `(session, client_turn_id)`. Generate a new id per answer; reuse it for retries
  of that answer.
- Retrying with an identical payload after success returns the **stored** response, byte for
  byte, without re-running the evaluator, even though `state_version` has since moved on.
  (Lookup happens before the version check for exactly this reason.)
- Same id with a different payload → `409 idempotency_mismatch`.
- If an attempt fails (`503`, `claim_lost`), that attempt is marked `failed` and the same id
  can be reused with the new `expected_state_version`.

## Transaction design (why it is safe)

```text
T0 refresh  lock session row; recover expired processing lease; time out idle sessions
T1 claim    lock session row; idempotency lookup; check status/version/deadline/question;
            insert turn(processing); session -> evaluating; state_version++; lease = now+60 s
--          evaluator call: no transaction, no lock, 45 s timeout
--          plan next action from a snapshot; responder writes the lead-in (5 s timeout,
            guarded, template fallback); still no lock
T2 commit   lock session + turn; verify claim unchanged; policy picks next action (if it
            differs from the plan, the template lead-in is used);
            turn -> committed + cached response; session -> awaiting_answer|completed; state_version++
```

- **No transaction is held during the evaluator call.** A slow model would otherwise hold row
  locks and connections for seconds.
- **The row lock serializes claims; `state_version` rejects stale clients; partial unique
  indexes** (`status <> 'failed'`) make two live copies of one turn impossible even if code
  is wrong.
- **Crash between T1 and T2:** the claim stays `processing` until its lease expires; the next
  request for the session marks it `failed` and returns the session to `awaiting_answer`. If the
  original request somehow resumes, T2 sees its claim is gone and aborts (`claim_lost`).
- **Accepted cost:** after a crash the evaluator may run twice for one answer. A turn can never
  commit twice. See [ADR 0001](adr/0001-database-idempotency.md).
