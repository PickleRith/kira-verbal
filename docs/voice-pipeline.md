# Voice pipeline

Voice is an optional way to answer. It uses the **same turn API, state machine, policy and
evaluator** as text; the voice worker only moves audio and text. If anything about voice
fails, the text form on the same page keeps working.

## Topology

```mermaid
sequenceDiagram
  participant B as Browser (VoicePanel)
  participant A as Kira API
  participant L as LiveKit Cloud room
  participant W as Voice worker (app/voice/worker.py)
  B->>A: POST /v1/sessions/{id}/voice-token (session bearer token)
  A-->>B: room token (dispatches worker; metadata = session id + worker credential)
  B->>L: connect, publish microphone (WebRTC)
  L->>W: dispatch job "kira-verbal-voice"
  W->>A: GET /v1/sessions/{id} (worker credential)
  W->>L: speak intro + current question (TTS)
  B->>L: learner speaks
  L->>W: audio -> STT -> end-of-turn detected
  W->>A: POST /v1/sessions/{id}/turns {modality: "voice", final transcript}
  A-->>W: next prompt (or finished)
  W->>L: speak prompt (TTS)
  B->>A: GET /v1/sessions/{id} every 2 s while voice is on (transcript on screen)
```

## Why WebRTC for audio and HTTP for turns

WebRTC (through LiveKit) carries continuous, low-latency, two-way audio with echo cancellation
and jitter handling. A turn is a discrete, finalized event that must be authorized,
idempotent and transactional, so it stays plain HTTP to the same endpoint the text client uses.
That is why voice inherits every Day 2 guarantee (one commit per answer, stale-state rejection,
crash recovery) without new code.

## Components

| Piece | Where | Notes |
|---|---|---|
| Room token + agent dispatch | `providers/livekit_tokens.py`, `POST /v1/sessions/{id}/voice-token` | Fresh room per attempt: LiveKit dispatches from a token only when the room is created. Token TTL 10 min (join window). |
| Worker credential | `services/voice_credentials.py` | `v1.<session>.<expiry>.<HMAC>`; scoped to one session, expires at the session deadline. Gives the worker exactly the learner's own access, never more. The learner's token is not sent through LiveKit. |
| STT / TTS / turn detection | `voice/worker.py` | LiveKit Inference on the LiveKit Cloud credentials (no Deepgram or ElevenLabs keys). Defaults: `assemblyai/assemblyai-stt-3-7-realtime-agent`, `fishaudio/s2.1-pro`, `inference.TurnDetector()`. These are configurable. |
| Turn forwarding | `voice/transport.py` (`VoiceTurnBridge`) | All decisions; no LiveKit imports. Tested against the real API. |
| Browser | `frontend/components/VoicePanel.tsx` | `livekit-client` 2.25.0: connect, mic on/off, attach agent audio, show `lk.agent.state`. |

The worker runs **no LLM of its own.** It overrides `on_user_turn_completed`, sends the final
transcript to the API, speaks the reply with `session.say`, and raises `StopResponse` so the
framework never generates a reply of its own. The conversational part lives in the backend:
the API's `lead_in` can be a guarded, model-written reply such as "Sure, here's the question
again". Text and voice therefore behave identically and share the same guardrails. See
[conversation.md](conversation.md).

## VAD, STT, partial vs final

- **VAD** (voice activity detection) only says *someone is speaking*.
- **STT** turns audio into text, streaming **partial** hypotheses that change as more audio
  arrives, and a **final** transcript.
- **The turn detector** decides when the learner has finished their turn.

Only the text in `on_user_turn_completed`, which runs after the turn ends, is ever submitted.
Partial transcripts never reach the API. Empty turns (noise) are dropped without spending a
question.

## Interruptions and stale speech

- Interruptions are on by default: when the learner starts talking, the agent's speech stops.
- The agent's own speech is never submitted. The worker only sends `new_message` (the learner's
  words), and the browser's WebRTC echo cancellation keeps the speaker out of the mic.
- Turns are handled one at a time (a lock). Each learner turn bumps a generation counter. If the
  learner speaks again while an earlier answer is still being evaluated, the earlier reply is
  **not spoken**; the newer turn speaks the current prompt instead.
- If the evaluator takes more than 1.5 s, a short filler ("One moment.") plays. It is not
  added to the chat context, and it deliberately has no "thanks": the reply that follows may
  acknowledge the answer, and two thank-yous in a row sounded robotic in testing.

## Failure handling

| Situation | What the learner hears / sees |
|---|---|
| Voice not configured | Panel: "Voice isn't available on this server. You can keep answering by typing." (503 `voice_unavailable`) |
| Microphone blocked | Panel: "Microphone access was blocked…"; room disconnected; text continues |
| Learner typed meanwhile | API 409 → worker refetches → "Let's pick up from where we are. <current question>" |
| Evaluator outage | API 503 → "Sorry, I couldn't process that just now. Could you say your answer again?" |
| Network error to API | Retried with the **same** `client_turn_id` (safe); then "…You can keep going by typing" |
| Silence | After 20 s (`VOICE_USER_AWAY_SECONDS`): "Take your time. <question>", at most twice per question |
| Session finished | "That was the last question, so the assessment is finished. Your teacher will review your answers and decide your results." The browser stays connected until the agent leaves after saying it (30 s safety limit), so the line isn't cut off |
| Room disconnects | Panel shows "Resume voice"; the transcript is refreshed; nothing is lost |

## Latency

The worker logs two numbers per turn (it never logs the transcript itself):

- `backend_ms`: from end-of-turn detection to the API's reply. This includes the evaluator.
- `end_of_turn_to_first_audio_ms`: from end-of-turn detection to the first TTS audio frame
  leaving the agent.

Limitation: both start at end-of-turn **detection**, not the instant the learner stopped
talking. The turn detector's own delay, and network time to the browser, are not included.
The plan's target (speech end to first audio p95 ≤ 1.5 s, a stretch goal) has **not been
measured** yet.

## Running it

1. Create a LiveKit Cloud project. Put `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`
   in `.env`, plus a 32+ character `VOICE_WORKER_SECRET`.
2. `cd backend; pip install -e ".[voice]"`
3. Restart the API (`uvicorn app.main:app --port 8000`).
4. In another terminal, run `python -m app.voice.worker dev`.
5. Open a session in the browser → **Answer by voice**.

## Troubleshooting

- **A dialog "Microsoft Visual C++ Runtime Library: Assertion failed … livekit_ffi.dll …
  soxr … LSX_FFT_BR == NULL", then the worker exits.** On Windows, LiveKit runs jobs as
  threads by default, so two overlapping calls (for example "Resume voice" while the old call
  is still shutting down) share the native audio resampler, and it crashes. Fixed by
  `VOICE_JOB_EXECUTOR=process` (the default here): each call gets its own process. If a
  Windows Python build can't spawn processes (BrokenPipeError), set it to `thread`.

- **The agent never joins.** Is the worker running and registered with the same
  `VOICE_AGENT_NAME`? Each attempt uses a new room, so stale rooms don't block dispatch.
- **The worker gets 404 from the API.** The credential expired (session past its deadline), or
  `VOICE_WORKER_SECRET` differs between the API and the worker.
- **The worker can't reach the API.** Set `KIRA_API_URL`. On Windows use `127.0.0.1`, not
  `localhost`.

## First live run (2026-11-23)

Project `kira-verbal` on LiveKit Cloud (US East B), Windows dev machine, evaluator and
responder both on `claude-haiku-5-5`. One five-turn photosynthesis session, then three text
turns for a timing breakdown.

- **The whole path works:** dispatch, STT, turn detection, `/turns`, TTS, the closing line,
  and disconnect handling. STT transcribed all 5 turns correctly, and every intent and
  signal was correct.
- **The agent joined about 11 s late.** In dev mode no process is kept warm, and the cold
  start exceeded the 10 s initialize timeout, so only the retry worked. Fixed: 1 warm
  process in dev, a 30 s timeout, and a prewarm for slow imports. After the fix, the process
  is ready at startup (2.9 s) before any job arrives.
- **End of turn to first audio: 3.4–4.1 s** (4 measured turns). Breakdown (API
  `turn_timing` log):

  | Stage | Measured |
  |---|---|
  | Evaluator (Claude, effort medium) | 1.5–3.1 s |
  | Responder (Claude, effort low) | 1.3–1.5 s |
  | API, DB and policy | < 0.1 s |
  | TTS to first audio | ~0.3 s |

  The plan's stretch target (p95 ≤ 1.5 s) is **not met**. With an LLM judging every answer
  on the critical path, it can't be met as designed. The biggest lever is turning off the
  responder for voice (−1.3 s).
- Interruptions and silence re-prompts were not specifically exercised in this run.

## After the first runs: latency changes (2026-11-23)

A second live session, on a slow connection, measured 4.0–6.5 s from end of turn to first
audio. Two changes followed:

- `RESPONDER_SCOPE=side_turns` (new default): the reply-line model call now runs only for
  side turns and "say more" prompts, not before every question.
- Evaluator effort `low` instead of `medium` (33/33 on the labelled cases, so no measured
  loss).

Measured over the API, text, 5 turns: ordinary turns **1.8–2.4 s** (before: 2.9–4.7 s); side
turns 3.0–3.2 s. Add about 0.3 s for speech to start. **This has not been re-measured by
voice**, and it is still above the 1.5 s stretch target.

## Status

The worker was built from the LiveKit docs and checked against the installed SDKs
(`livekit-agents` 1.8.13, `livekit-api` 1.2.3, `livekit-client` 2.25.0). It imports cleanly and
its CLI runs. **No live voice conversation has been run yet,** because no LiveKit credentials
are configured. Interruption behaviour, latency and the end-to-end audio path still need a real
session.
