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
| Day 1: scaffold, lesson schema, state machine, question policy, health/ready, CI | Built (see [journal](docs/engineering-journal.md)) |
| Day 2–7: text assessment, LLM evaluator, voice, teacher review, evaluation, deploy | Not started |

No benchmark results exist yet. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full plan.

## Stack

Next.js + TypeScript + Tailwind (frontend) · FastAPI + Pydantic (API) · PostgreSQL + SQLAlchemy +
Alembic (durable records) · Redis (coordination only, never the source of truth) · pytest.
Voice (LiveKit, Deepgram, ElevenLabs) and the LLM evaluator arrive in later milestones.

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
backend/app/api/         HTTP handlers (health/ready so far)
backend/app/db/          SQLAlchemy models, engine factory
backend/app/repositories/ database read/write boundaries
backend/migrations/      Alembic migrations
data/lessons/            versioned lesson fixtures: <id>.v<version>.json
frontend/                Next.js app (landing page only so far)
docs/                    architecture, journal; more docs per milestone
```

## Documentation

- [Architecture](docs/architecture.md)
- [Engineering journal](docs/engineering-journal.md)

## Limitations

Synthetic data only. No real student accounts, SSO, high-stakes grading, cheating detection,
emotion/accent scoring or biometrics. A real school deployment would need separate FERPA/COPPA,
security and accessibility review; this project makes no compliance claim.
