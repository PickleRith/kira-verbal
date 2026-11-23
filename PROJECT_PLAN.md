# Kira Verbal — Engineering project plan

> Independent portfolio prototype proposing an oral-assessment activity for Kira Learning 2.0. Not affiliated with Kira; no private API access or integration is assumed. Use synthetic learners and adult testers only.

## 0. How to use this document in VS Code

1. Create a folder `kira-verbal`, open it in VS Code, and save this file as `PROJECT_PLAN.md` at its root.
2. Open Markdown Preview with Ctrl+Shift+V (Windows/Linux) or Cmd+Shift+V (macOS).
3. Complete milestones in order. Check `[x]` only when the acceptance tests pass and you can explain the code without AI assistance.
4. Commit each milestone separately. Keep `docs/engineering-journal.md` with decisions, bugs, fixes, and actual benchmark results.
5. Give Codex or Cursor one milestone at a time; review diffs, run tests, and explain the changes before proceeding.

**Definition of done:** a teacher can select a lesson, launch an adaptive voice assessment, inspect transcript-backed rubric evidence, approve or revise a proposed mastery update, and export a versioned result. The app works in a public synthetic-data demo and has reproducible tests and documentation.

## 1. Product scope

### Problem and hypothesis
Written answers alone may not demonstrate conceptual understanding. A short oral conversation can supply additional evidence, but must not be treated as proof of cheating, ability, or overall mastery. The hypothesis is that adaptive, rubric-grounded questions reveal actionable misconceptions with less teacher effort than manually conducting oral assessments. This is a hypothesis, not a validated outcome.

### User journey
1. Teacher selects a lesson, rubric, and synthetic learner; previews questions.
2. Learner enters a session, chooses voice or text, and receives a clear explanation of the assessment.
3. Agent asks an open question, then follows up based on the response; tracks hints and interruptions.
4. Independent evaluator maps transcript evidence to rubric criteria and flags uncertainty.
5. Teacher reviews evidence, edits suggested rubric levels and approves or rejects the report.
6. Approved evidence can be exported through a mock Kira adapter. No actual gradebook is changed.

### MVP / non-goals
- [ ] Three lessons: photosynthesis, fractions, and Python loops; 2–4 objectives each.
- [ ] Five-question maximum, 3–5 minute target, text fallback, optional voice.
- [ ] Adaptive follow-up, hint tracking, transcript, rubric evidence, teacher review and JSON export.
- [ ] Synthetic demo data, provider-independent backend interfaces, automated tests.
- [ ] Explicitly exclude real student accounts, school SSO, automated high-stakes grading, cheating detection, emotion/accent scoring, biometrics, phone calls, custom model training, and real Kira integration.

## 2. Architecture

```mermaid
flowchart TD
  UI[Next.js student and teacher UI] --> API[FastAPI REST API]
  UI <-->|WebRTC| RTC[LiveKit room]
  RTC <--> W[Python voice worker]
  W --> API
  API --> O[Assessment orchestrator]
  O --> P[Question policy and lesson rubric]
  O --> E[Independent evidence evaluator]
  E --> L[LLM provider adapter]
  O --> R[(Redis session coordination)]
  O --> DB[(PostgreSQL durable records)]
  API --> DB
  API --> X[Mock Kira export adapter]
  W --> STT[Speech recognition]
  W --> TTS[Speech synthesis]
```

**Key design:** the backend owns assessment state. The voice worker transports speech and invokes the same turn endpoint as the text client. The LLM proposes rubric evidence; deterministic code validates evidence, controls question selection and computes suggested rubric levels. Teachers own final decisions. Start with a deterministic fake evaluator and text flow, then enable real providers.

### Stack decisions
| Layer | Choice | Why |
|---|---|---|
| UI | Next.js + TypeScript + Tailwind | Two clear experiences; typed API client |
| API | FastAPI + Pydantic | Typed contracts and generated OpenAPI |
| Persistence | PostgreSQL + SQLAlchemy + Alembic | Durable audit trail, constraints, migrations |
| Coordination | Redis | Short-lived locks and session coordination; not source of truth |
| Audio | LiveKit Agents/WebRTC | Browser streaming, interruption handling |
| STT / TTS | Deepgram / ElevenLabs | Familiar replaceable providers; text-only mode avoids cost |
| Evaluator | Configurable LLM structured output | Evidence extraction; not sole grading authority |
| Testing | pytest, Vitest, Playwright | Domain, API, UI and end-to-end checks |
| Local infra | Docker Compose | Reproducible Postgres and Redis |

Use current official provider quickstarts and lock dependency versions after validating compatibility. Do not invent SDK methods. No vector database is required for three curated lessons; introduce retrieval only when corpus size justifies it.

## 3. Repository map

```text
kira-verbal/
  PROJECT_PLAN.md
  README.md
  .env.example
  .gitignore
  compose.yaml
  Makefile                         # optional convenience commands
  frontend/
    app/
      page.tsx                     # landing / demo role selector
      student/[sessionId]/page.tsx # assessment experience
      teacher/page.tsx              # sessions and lessons
      teacher/[sessionId]/page.tsx  # evidence review
    components/                    # voice controls, transcript, rubric cards
    lib/api.ts                     # typed HTTP client
    lib/types.ts                   # generated or synchronized API types
    tests/
  backend/
    pyproject.toml
    alembic.ini
    migrations/
    app/
      main.py                      # app factory, routes, health
      config.py                    # environment configuration
      api/                         # REST handlers; no domain logic
      schemas/                     # Pydantic request/response contracts
      domain/
        state.py                   # state machine and legal transitions
        policy.py                  # deterministic next-question selection
        scoring.py                 # rubric aggregation and abstention
        models.py                  # domain types
      services/
        assessment.py              # orchestrates a turn
        evaluator.py               # evidence validation and evaluation
        reports.py                 # report construction and review
      repositories/                # database read/write boundaries
      db/                          # SQLAlchemy models and sessions
      providers/
        llm.py                     # evaluator interface + real adapter
        fake.py                    # predictable test/demo implementation
        kira_mock.py               # proposed integration export
      voice/
        worker.py                  # LiveKit agent entrypoint
        transport.py               # audio lifecycle / turn forwarding
      seed.py                      # synthetic data import
    tests/
      unit/
      integration/
  data/
    lessons/                       # versioned lesson JSON
    evals/                         # synthetic labeled conversations
  scripts/                         # seeding and benchmark runners
  docs/
    architecture.md
    api.md
    data-model.md
    assessment-policy.md
    voice-pipeline.md
    evaluation.md
    privacy-and-safety.md
    deployment.md
    engineering-journal.md
    adr/                           # architectural decision records
```

### Code reading order
- [ ] `main.py` → routes: explain where a request enters and how it is validated.
- [ ] `schemas/` → `domain/state.py`: explain the difference between API shape and business state.
- [ ] `services/assessment.py` → `domain/policy.py`: trace a complete turn and next question.
- [ ] `services/evaluator.py` → `domain/scoring.py`: explain why invalid evidence cannot affect a score.
- [ ] `repositories/` → `db/`: explain transaction boundaries and uniqueness constraints.
- [ ] `voice/worker.py` → API: explain why voice and text share the same logic.
- [ ] `frontend/lib/api.ts` → student and teacher pages: explain how state is displayed and errors handled.
- [ ] `tests/`: locate the tests protecting every major invariant.

## 4. Data model and contracts

| Entity | Essential fields / constraints |
|---|---|
| Lesson | id, version, title, objectives, question graph; immutable version after publication |
| Rubric criterion | id, lesson_version, objective, descriptors for levels 0–3 |
| Session | id, synthetic_learner_id, lesson_version, status, state_version, created_at, deadline |
| Turn | id, session_id, client_turn_id, sequence, question_id, transcript, hint_level, modality; unique(session_id, client_turn_id) |
| Evidence | id, turn_id, criterion_id, exact quote, proposed_level or null, reason, evaluator_version, validation_status |
| Report | id, session_id, revision, suggested_levels, gaps, status; unique(session_id, revision) |
| Review | id, report_id, reviewer_id, approved_levels, decision, reason, timestamp |
| Export event | id, report_id, schema_version, idempotency_key, payload; unique(idempotency_key) |

Use UUIDs, UTC timestamps, foreign keys and database constraints. A session pins a lesson and rubric version; evaluations pin prompt/model versions. Avoid storing raw audio in MVP. Keep transcripts only for a configured retention period; document deletion behavior.

### Example lesson fixture
```json
{
  "id": "photosynthesis",
  "version": 1,
  "title": "Photosynthesis",
  "objectives": ["purpose", "light", "carbon_dioxide"],
  "questions": [
    {"id":"q1","objective":"purpose","prompt":"Explain photosynthesis in your own words."},
    {"id":"q2","objective":"carbon_dioxide","prompt":"Where does a plant get carbon dioxide?"},
    {"id":"q3","objective":"carbon_dioxide","prompt":"How do leaves exchange gases with the air?"}
  ]
}
```
Expand fixtures with full rubric descriptors, question difficulty, permitted hints and misconception tags. Validate at startup and in tests.

### REST API (proposed)
| Method / path | Purpose |
|---|---|
| GET /health | Process health |
| GET /ready | Dependency readiness |
| GET /v1/lessons | Curated lessons and versions |
| POST /v1/sessions | Create session; return ID and initial question |
| GET /v1/sessions/{id} | Resume current state and transcript |
| POST /v1/sessions/{id}/turns | Submit one finalized text/voice turn |
| POST /v1/sessions/{id}/finish | Complete or mark incomplete |
| POST /v1/sessions/{id}/voice-token | Short-lived room-scoped credential |
| GET /v1/sessions/{id}/report | Fetch report; pending status allowed |
| POST /v1/reports/{id}/review | Teacher approve/revise/reject with revision check |
| POST /v1/reports/{id}/export | Idempotent export of approved revision |

Example turn request:
```json
{"client_turn_id":"demo-turn-001","expected_state_version":2,"transcript":"From the soil through its roots.","modality":"voice","question_id":"q2"}
```
Example result (illustrative):
```json
{"state_version":3,"status":"awaiting_answer","next_question":{"id":"q3","prompt":"How do leaves exchange gases with the air?"},"hint_level":0}
```
Keep teacher-only evaluation results out of the student response. Return 409 on stale version, 422 on invalid input, 429 on rate limit. Retrying the same client turn ID with identical payload returns the stored response; a mismatched payload conflicts. Authorize every session and report operation; public demo roles are isolated synthetic sessions, not real school authorization.

## 5. Core assessment logic

```mermaid
stateDiagram-v2
  [*] --> created
  created --> awaiting_answer: start
  awaiting_answer --> evaluating: finalized turn
  evaluating --> awaiting_answer: validated result and next question
  evaluating --> completed: budget met
  evaluating --> awaiting_answer: recoverable error / retry
  awaiting_answer --> incomplete: timeout or exit
  evaluating --> incomplete: terminal failure
  completed --> [*]
  incomplete --> [*]
```
Report lifecycle is separate: pending → ready_for_review → approved/rejected; a revision creates a new report version. Only approved versions export.

### Turn algorithm
```text
validate authorization, turn size and session deadline
look up existing idempotency key before checking state version
claim turn using a durable transaction and unique constraint
persist finalized transcript; mark evaluating
call evaluator outside database transaction with timeout
validate structured output and exact quote against stored transcript
select next permitted question using deterministic policy
atomically persist evidence, resulting state and cached response
return next question or completion status
```
Use a recoverable lease for abandoned processing claims. Redis lock is optional optimization with token-safe release and bounded TTL; database state version and unique constraints are correctness guarantees. Never hold a DB transaction open during a network model call. Duplicate external inference may occur after a crash, but duplicate committed turn/evidence events must not. Test this explicitly.

### Question policy
1. Ask an unassisted open question for an uncovered objective.
2. If evidence suggests a misconception, ask one approved diagnostic follow-up.
3. If evidence is missing or ambiguous, request clarification or switch to text.
4. If learner asks for help, deliver a permitted hint, mark the resulting turn assisted.
5. Move to next uncovered objective; stop on question/time budget or learner request.

Track diagnostic questions separately from instructional hints. A follow-up that reveals an answer counts as assistance. No invented question IDs or unbounded loops. Do not penalize silence, speech recognition uncertainty, accent, grammar, disability, or refusal.

### Evaluator contract
```json
{
  "criterion_id":"carbon_dioxide",
  "proposed_level":1,
  "evidence_quote":"From the soil through its roots.",
  "misconception_tag":"co2_from_roots",
  "reason":"Response attributes carbon dioxide uptake to roots.",
  "abstain":false
}
```
Validate allowed criterion IDs, exact normalized substring, valid level, applicable question and allowed misconception tags. Prompt treats student transcript as untrusted data and cannot invoke tools or change rules. Missing/invalid evidence → abstain, not zero. Model confidence is not calibrated probability; do not display it as such.

Rubric levels: 0 = explicit incorrect evidence, 1 = partial understanding or material misconception, 2 = mostly correct with omission, 3 = accurate explanation matching criterion. Unknown = insufficient evidence. Store independent and assisted evidence separately. Suggested level uses the latest valid independent evidence per criterion; conflicting evidence triggers review. Report coverage (# criteria with evidence / # criteria) separately. Avoid percentages that imply calibrated mastery. Teacher can revise any suggestion, with reason.

## 6. Seven-day implementation checklist

### Day 1 — Scaffold and domain (4–6 hours)
- [ ] Initialize Git and project folders; add README, .gitignore, .env.example.
- [ ] Set up Next.js, FastAPI, Postgres, Redis and migrations.
- [ ] Implement lesson schema, fixture validation and seed data.
- [ ] Implement state machine and policy as pure functions with unit tests.
- [ ] Add health and readiness routes and basic CI.
- [ ] Document local setup and architecture diagram.
**Acceptance:** clean clone can start dependencies; health works; tests reject illegal transitions and question IDs.
**Explain:** Why are domain functions independent of FastAPI and SQLAlchemy? Why version lesson data?

### Day 2 — End-to-end text assessment (5–7 hours)
- [ ] Create sessions and durable turn records.
- [ ] Add fake evaluator, orchestrator and deterministic question policy.
- [ ] Implement text student UI, loading state, resume and finish.
- [ ] Implement unique turn IDs, optimistic state versions and recovery behavior.
- [ ] Test duplicate/concurrent submissions and stale versions.
- [ ] Document API examples and transaction decisions.
**Acceptance:** complete a photosynthesis assessment from the browser without any paid API; duplicate requests do not advance twice.
**Explain:** Trace a turn from React to Postgres; explain why a Redis lock alone is insufficient.

### Day 3 — Real evaluation (5–7 hours)
- [ ] Implement LLM adapter with structured output, timeout and bounded retry.
- [ ] Write versioned evaluator prompt with rubric context and untrusted transcript boundary.
- [ ] Validate exact quotes and criterion IDs; implement abstention.
- [ ] Add separate independent/assisted evidence; persist evaluator metadata.
- [ ] Add fixtures for incorrect, partial, correct, ambiguous and adversarial answers.
- [ ] Document scoring policy and limitations.
**Acceptance:** invalid quote never becomes accepted evidence; outage degrades gracefully; teacher sees unknown instead of fabricated score.
**Explain:** Why separate interviewer and evaluator? How does prompt injection differ from an ordinary incorrect answer?

### Day 4 — Streaming voice (5–7 hours)
- [ ] Configure LiveKit room and short-lived server-issued token.
- [ ] Implement Python worker using official SDK quickstart for chosen version.
- [ ] Connect STT and TTS providers; send only finalized student turns to shared endpoint.
- [ ] Implement interruption handling, silence timeout, mic controls and text fallback.
- [ ] Ensure assistant speech does not enter student transcript; ignore stale audio generation after barge-in.
- [ ] Measure speech-end to first audible reply with trace timestamps.
- [ ] Document audio lifecycle and troubleshooting.
**Acceptance:** two-way voice conversation completes the same flow as text; interruption stops speech; provider failure allows text continuation.
**Explain:** WebRTC vs HTTP; VAD vs STT; partial vs final transcripts; how cancellation prevents stale speech.

### Day 5 — Teacher dashboard and export (5–7 hours)
- [ ] Add report creation, pending/ready states and evidence links.
- [ ] Display objective-level rubric suggestions, unknowns, misconceptions and hint history.
- [ ] Add review/edit/approve/reject with audit trail and revision check.
- [ ] Implement mock Kira export schema and download.
- [ ] Restrict teacher routes; isolate synthetic demo sessions.
- [ ] Test approval requirement, duplicate export and stale review revisions.
**Acceptance:** teacher can review exact transcript evidence, revise a level and export only approved results.
**Explain:** Why is export a separate boundary? How is a review auditable?

### Day 6 — Evaluation, security and reliability (5–7 hours)
- [ ] Create 50–100 synthetic conversations, manually label a held-out subset before tuning.
- [ ] Implement reproducible evaluation script and baseline comparison.
- [ ] Test malformed provider output, network failures, prompt injection and interrupted sessions.
- [ ] Check authorization, rate limits, input sizes, secrets, retention and logging redaction.
- [ ] Add end-to-end Playwright test for the full text workflow.
- [ ] Record actual results and failure analysis in docs/evaluation.md.
**Acceptance:** automated tests pass; benchmark output includes sample size, metrics, versions and failure cases.
**Explain:** What does precision/recall mean here? Why are synthetic results not classroom validation?

### Day 7 — Deployment, documentation and demo (4–6 hours)
- [ ] Deploy frontend, API, persistent DB/Redis and voice worker (worker must support persistent connections).
- [ ] Configure HTTPS, CORS allowlist, environment secrets, budgets and health checks.
- [ ] Smoke-test from a clean browser; test text fallback without microphone permission.
- [ ] Complete all docs and create one-command or clearly documented local setup.
- [ ] Record two-minute demo and architecture walkthrough.
- [ ] Add GitHub README screenshots, actual results, limitations and independent-prototype disclaimer.
**Acceptance:** another engineer can clone, run text demo and understand architecture from README; hosted demo contains synthetic data only.
**Explain:** Trace deployment topology, rollback and failure modes; defend two tradeoffs and one limitation.

If schedule slips, prioritize Days 1–3 and 5 over voice polish. A reliable text workflow plus a small working voice integration is better than a beautiful broken agent.

## 7. Local setup blueprint

These are target commands for the repository you will build, not commands for an already-generated codebase. Windows users can use PowerShell or WSL2; use the appropriate shell activation command.

```bash
mkdir kira-verbal
cd kira-verbal
git init
code .
# From root after placing this plan in PROJECT_PLAN.md:
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --use-npm
mkdir backend
cd backend
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# Bash: source .venv/bin/activate
python -m pip install --upgrade pip
```
Then create `pyproject.toml` with compatible pinned dependencies (FastAPI, uvicorn, Pydantic settings, SQLAlchemy, psycopg, Alembic, redis, pytest, httpx and selected provider SDKs); install with `pip install -e ".[dev]"` after defining the dev extra. Generate `compose.yaml` with Postgres and Redis, health checks, named DB volume, and local-only port exposure. Add Alembic migrations before running seed.

Expected daily commands after scaffold:
```bash
# root
docker compose up -d
# backend, activated venv
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
# separate terminal, frontend
npm run dev
# backend tests
pytest -q
# frontend tests (configure scripts first)
npm run lint
npm run test
npm run test:e2e
```

### Environment template (placeholders only)
```dotenv
APP_ENV=development
DEMO_MODE=true
EVALUATOR_PROVIDER=fake
DATABASE_URL=postgresql+psycopg://kira:kira@localhost:5432/kira
REDIS_URL=redis://localhost:6379/0
FRONTEND_ORIGIN=http://localhost:3000
LLM_API_KEY=
LLM_MODEL=
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
SESSION_MAX_SECONDS=300
TRANSCRIPT_RETENTION_DAYS=7
```
Keep actual secrets in ignored `.env` files or deployment secret store. Only expose the API base URL to frontend; never expose provider keys. Fake mode must run without external credentials. Configure separate public and server-only env files as needed. Implement retention cleanup before any persisted public demo.

## 8. Test and benchmark matrix

| Test | Expected behavior |
|---|---|
| Correct independent explanation | Appropriate rubric suggestion and exact evidence |
| Carbon dioxide from roots | Diagnostic follow-up; misconception evidence |
| Correct answer after hint | Assisted evidence only; independent level unchanged |
| Empty / ambiguous answer | Clarification or unknown, no automatic zero |
| Prompt injection in transcript | No policy change, no tool execution |
| Fabricated evidence quote | Rejected and abstained |
| Duplicate turn / simultaneous turns | One committed result; stale request conflicts |
| Crash after evaluator returns | Recoverable claim; no duplicate evidence |
| STT partial or interrupted response | No partial turn committed unless explicitly finalized |
| Model timeout / invalid JSON | Bounded retry or unknown; no fabricated result |
| Unauthorized report or export | Denied |
| Unapproved report export | Denied |
| Duplicate export | Same event, no duplicate downstream update |
| Microphone denied | Text workflow remains available |
| Learner exits early | Incomplete report; no fabricated mastery |

### Evaluation plan
Compare fixed-question baseline and adaptive policy on identical scripted learner profiles; report differences in misconception coverage, question count and abstention. Synthetic scripts are limited proxies and cannot establish causal learning outcomes. Keep held-out profiles separate from prompt tuning. Manually review disagreements and label provenance.

| Metric | Aspirational target | Actual |
|---|---|---|
| Misconception detection macro F1 | ≥0.85 | TBD |
| Rubric agreement within one level | ≥85% on non-abstained examples; report coverage | TBD |
| Accepted quotes grounded in transcript | 100% (validator invariant) | TBD |
| Evidence semantically supports criterion | ≥95% manually reviewed | TBD |
| Duplicate committed events | 0 in retry/concurrency tests | TBD |
| Voice end-of-speech to first audio p95 | ≤1.5 s stretch goal; report observed | TBD |
| Assessment duration | 3–5 min target | TBD |

Report exact sample counts, hardware/network/provider/model version, percentile method and estimated provider cost from measured usage. Do not market targets as achieved. Record text and voice latency separately; include timeout and failure rates. No accuracy claims for children or accessibility populations based on synthetic tests.

## 9. Documentation checklist

| File | Required content |
|---|---|
| README.md | Problem, demo, screenshots, quickstart, stack, actual results, disclaimer |
| architecture.md | Diagram, component responsibilities, request flow, tradeoffs |
| api.md | Endpoints, auth, example payloads, errors, idempotency |
| data-model.md | Entity relationships, constraints, migrations and retention |
| assessment-policy.md | State machine, question rules, hints, scoring, abstention |
| voice-pipeline.md | STT/LLM/TTS flow, VAD, cancellation, reconnect, latency |
| evaluation.md | Dataset provenance, baseline, metrics, failure cases, limitations |
| privacy-and-safety.md | Synthetic-only scope, access, retention, deletion, provider risks |
| deployment.md | Setup, secret names, service topology, smoke test, rollback |
| engineering-journal.md | Daily decisions, debugging notes, what you learned |

- [ ] Every module has a concise docstring describing responsibility, inputs/outputs and invariants where non-obvious.
- [ ] Public functions have types; comments explain WHY rather than narrating syntax.
- [ ] Each major feature includes tests and an example of failure behavior.
- [ ] Architecture decision records cover deterministic policy vs free-form agent; separate evaluator; database idempotency; text-first development.
- [ ] Documentation matches current code; no invented features or benchmark claims.
- [ ] Privacy review confirms no real learner records, no raw audio storage, safe demo logs and deletion path. Real school deployment would require separate FERPA/COPPA and other applicable legal, security and accessibility review; no compliance claim.

### Engineering journal template (copy daily)
```markdown
## YYYY-MM-DD — Milestone
- [ ] I can explain each changed module.
- [ ] I ran tests and recorded results.
- [ ] I updated docs and committed code.

### What I built
### Request flow (files and functions)
### Why this design
### Bug, root cause, fix, regression test
### Tradeoff and alternative
### What I still do not understand
### Actual results / next task
```

## 10. Coding-agent prompt (paste into Codex or Cursor)

> You are my senior engineering pair programmer. Read PROJECT_PLAN.md before changing anything. Build only the next unchecked milestone, starting with Day 1. Inspect the existing repository first. State the files you intend to create or modify and why; then implement small, reviewable changes. Use typed interfaces, explicit errors, dependency injection where useful, and tests for invariants. Keep fake provider mode runnable without paid credentials. Never invent SDK methods or claim tests passed without running them. Do not add unrequested features or hide failures. Explain each file's role, the request flow, and key tradeoffs in plain English. Update README/docs and the engineering journal. At the end, give exact commands to reproduce your tests, actual results, remaining gaps and three comprehension questions. Do not mark my comprehension checkboxes complete for me. Do not implement subsequent milestones until I ask.

### Review every AI-generated change
- [ ] Read diff and identify entry point, inputs, outputs, dependencies and failure modes.
- [ ] Run tests yourself; deliberately break one invariant and verify its test fails, then restore code.
- [ ] Explain the change aloud without reading the AI summary.
- [ ] Remove unused abstractions and secrets; commit only reviewed changes.

## 11. Demo script and outreach deliverables

**0:00–0:20:** Explain the gap: written work is one signal; oral reasoning adds evidence.
**0:20–0:55:** Start photosynthesis assessment, answer with the roots misconception, show adaptive follow-up and hint tracking.
**0:55–1:25:** Teacher reviews transcript-backed rubric, revises/approves it, exports mock event.
**1:25–1:45:** Show architecture and actual measured results, including one failure case.
**1:45–2:00:** Explain proposed Kira activity integration and teacher ownership; acknowledge synthetic-only validation.

- [ ] Public GitHub repo with clean README and architecture diagram.
- [ ] Hosted synthetic-data demo with a text fallback.
- [ ] Two-minute video plus optional five-minute technical walkthrough.
- [ ] Benchmark report and sample approved export.
- [ ] Brief outreach to Kira engineering/product team asking for technical feedback, not claiming partnership.

## 12. Interview readiness — final self-check

- [ ] Draw the architecture from memory in two minutes.
- [ ] Explain why a question policy is deterministic and scoring uses evidence.
- [ ] Trace one voice turn through all services and database writes.
- [ ] Explain what happens if two requests arrive together or a model call times out.
- [ ] Explain why assisted evidence differs from independent evidence.
- [ ] Explain limitations of evaluation, privacy, and how you would validate with educators.
- [ ] Explain how to scale to hundreds of simultaneous sessions: worker capacity, bounded queues, rate limits, backpressure and provider quotas.
- [ ] Demonstrate a real bug you fixed and its regression test.
- [ ] Describe how an actual Kira integration would need authorized APIs and security review.

**First action:** open VS Code, place this plan at repository root, initialize Git and complete Day 1. Do not begin with voice or UI polish. Build the assessment domain first.
