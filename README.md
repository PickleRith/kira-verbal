# Kira Verbal

> **Independent portfolio prototype.** Proposes an oral-assessment activity for Kira Learning 2.0.
> Not affiliated with Kira; no private API access or integration. Synthetic learners and adult testers only.

A short, adaptive oral assessment. It asks rubric-grounded questions, follows up on likely
misconceptions, and gives the teacher transcript-backed evidence to approve or revise.
The hypothesis (not a validated result) is that this surfaces actionable misconceptions with less
teacher effort than running oral assessments by hand.

## Status

| Milestone | State |
|---|---|
| Day 1: scaffold, lesson schema, state machine, question policy, health/ready, CI | Built |
| Day 2: end-to-end text assessment (sessions, turns, fake evaluator, student UI, idempotency) | Built |
| Day 3: Claude evaluator, evidence validation, abstention, independent/assisted scoring | Built; live API run pending credentials |
| Day 4: voice via LiveKit (worker, room tokens, voice panel, text fallback) | Built; live voice run pending LiveKit credentials |
| Conversation layer: side turns, guarded responder replies (text and voice) | Built; live Claude responder run pending credentials |
| Day 5–7: teacher review, evaluation, deploy | Not started |

Progress and real test results are in the [engineering journal](docs/engineering-journal.md).

No benchmark results exist yet. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full plan.

## Stack

Next.js + TypeScript + Tailwind (frontend) · FastAPI + Pydantic (API) · PostgreSQL + SQLAlchemy +
Alembic (durable records) · Redis (coordination only, never the source of truth) · pytest.
Evaluator: Claude (`claude-opus-5-5`) via the official `anthropic` SDK, or a free keyword fake.
Voice (optional): LiveKit Agents worker with LiveKit Inference for speech-to-text and
text-to-speech, and `livekit-client` in the browser. See [voice-pipeline.md](docs/voice-pipeline.md).

## Local setup

Prerequisites: Python 3.11+, Node.js 20.15+ (22 LTS recommended), Docker Desktop running.

```powershell
# 1. Dependencies (from repo root)
docker compose up -d
Copy-Item .env.example .env          # bash: cp .env.example .env

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1            # bash: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed                    # publishes the 3 synthetic lessons; safe to rerun
uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                           # http://localhost:3000
```

Open http://localhost:3000, pick a lesson, and answer as a demo learner. Try the roots
misconception on photosynthesis ("From the soil through its roots.") to see the adaptive
follow-up. No API keys are needed: by default the evaluator is a deterministic keyword fake.
To use Claude instead, set `EVALUATOR_PROVIDER=llm` and either `LLM_API_KEY` or
`ANTHROPIC_API_KEY` (each answer is one paid API call). Set `RESPONDER_PROVIDER=llm` as well
to let Claude write the agent's conversational replies (one more call per turn; see
[conversation.md](docs/conversation.md)). Try "What are stomata?" or "Can you repeat that?"
to see a side turn: the question is asked again and no answer is used up. Inspect what was recorded for a session
with `python -m app.inspect_session <session_id>`.
The frontend calls `http://127.0.0.1:8000` by default (override with
`NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`).

Check it: `GET http://localhost:8000/health` → `{"status":"ok"}`;
`GET http://localhost:8000/ready` → 200 when Postgres, Redis and lessons are all OK, otherwise 503.
OpenAPI docs: http://localhost:8000/docs.

## Tests

```powershell
cd backend
pytest -q              # unit tests always run; integration tests skip if Postgres/Redis are down
ruff check . ; ruff format --check .
$env:REQUIRE_SERVICES="1"; pytest -q   # make missing services a failure (CI does this)

cd ../frontend
npm run lint ; npm run build
```

Integration tests create and drop their own `kira_test` database; they never touch `kira`.

## Repository layout

```text
backend/app/domain/      pure rules: lesson schema, state machine, question policy (no framework imports)
backend/app/services/    orchestrator (turn algorithm), lesson store
backend/app/providers/   evaluator interface + deterministic fake
backend/app/api/         HTTP handlers, auth dependency, error mapping
backend/app/db/          SQLAlchemy models, engine factory
backend/app/repositories/ database read/write boundaries
backend/migrations/      Alembic migrations
data/lessons/            versioned lesson fixtures: <id>.v<version>.json
frontend/lib/            typed API client, browser storage helpers
frontend/components/     lesson picker, student session
docs/                    architecture, journal; more docs per milestone
```

## Documentation

- [Architecture](docs/architecture.md)
- [API, errors, idempotency and transactions](docs/api.md)
- [Assessment policy, evidence validation and scoring](docs/assessment-policy.md)
- [Voice pipeline](docs/voice-pipeline.md)
- [Conversation layer and guardrails](docs/conversation.md)
- [ADR 0001: idempotency in Postgres, not Redis](docs/adr/0001-database-idempotency.md)
- [Engineering journal](docs/engineering-journal.md)

## Limitations

Synthetic data only. No real student accounts, SSO, high-stakes grading, cheating detection,
emotion/accent scoring or biometrics. A real school deployment would need separate FERPA/COPPA,
security and accessibility review; this project makes no compliance claim.
