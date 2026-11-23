# Engineering journal

## 2026-11-23 — Day 1: scaffold and domain

- [ ] I can explain each changed module.
- [ ] I ran tests and recorded results.
- [ ] I updated docs and committed code.

### What I built
- Repo skeleton: `README.md`, `.gitignore`, `.gitattributes`, `.env.example`, `compose.yaml`
  (Postgres 16 + Redis 7, health checks, named volume, ports bound to 127.0.0.1), GitHub Actions CI.
- Lesson schema with cross-reference validation (`app/domain/models.py`) and three synthetic
  fixtures in `data/lessons/` (photosynthesis, fractions, python_loops; 3 objectives each, one
  diagnostic per misconception).
- Catalog loader that checks filename = `<id>.v<version>.json` and hashes canonical content.
- Session state machine as a read-only transition table (`app/domain/state.py`).
- Deterministic question policy (`app/domain/policy.py`).
- `lesson_versions` table, Alembic migration 0001 with an immutability trigger, idempotent seed.
- `/health` (liveness) and `/ready` (Postgres, Redis, catalog) with injectable checks.
- Next.js 15 scaffold with a plain landing page and disclaimer.

### Request flow (files and functions)
`uvicorn app.main:app` → `create_app()` → lifespan `load_catalog()` (fails startup on bad fixture)
→ `GET /ready` → `api/health.py:ready()` → each check in `app.state.readiness_checks`.
Seed: `app/seed.py:main()` → `load_catalog()` → `repositories/lessons.py:publish_lesson()` per lesson,
all in one transaction.

### Why this design
- Domain code has no framework imports, so policy and state rules are unit-tested without services.
- Lesson versions are immutable (frozen models, hash check, DB trigger) because sessions will pin
  a version; editing in place would change the meaning of past evidence.
- The policy's termination does not depend on the turn budget: every follow-up path is bounded
  (one open per objective, one diagnostic per misconception, one clarification per question,
  finite hints). The budget is a second, independent bound.

### Bug, root cause, fix, regression test
- **Slow test run (271 s).** Root cause: the integration fixture's probe connection to Postgres
  had no `connect_timeout`, so when Docker was down each attempt hung for minutes. Fix: 3 s
  `connect_timeout` in `tests/integration/conftest.py`. Run time dropped to ~8 s.
- **`next build` failed** with `ERR_REQUIRE_ESM` for `magic-string`. Root cause: Tailwind 4.3.5
  depends on ESM-only `magic-string` 1.x, which Node 20.15 cannot `require()`. Fix: pinned
  `tailwindcss` and `@tailwindcss/postcss` to 4.1.18. Better long-term fix: upgrade to Node 22 LTS
  (Node 20 is past end-of-life).

- **Docker commands hung.** Root cause: Docker Desktop 4.24.2 (Oct 2023) could not start its
  engine on WSL 3.0.5 / kernel 6.18; the engine pipe existed but nothing answered. Fix: updated
  Docker Desktop (engine now 29.9.3).
- **Integration tests hung in `alembic upgrade`.** Root cause: on Windows `localhost` resolves to
  IPv6 `::1` first; compose binds ports to IPv4 `127.0.0.1` only, so each connection stalled until
  a timeout before falling back (measured: `127.0.0.1` 0.02 s, `localhost` 5.01 s, `::1` timeout).
  Alembic's connection had no timeout, so it hung. Fix: use `127.0.0.1` in all default URLs and
  add a 5 s `connect_timeout` to `migrations/env.py`. Regression check: integration suite runs in
  ~2.5 s with `REQUIRE_SERVICES=1`.

### Tradeoff and alternative
- Turn budget counts every learner turn, including hint requests and clarifications. Alternative:
  count only distinct questions. Chosen to keep sessions near 3–5 minutes; cost is that heavy hint
  use may leave objectives uncovered (reported as unknown, not zero).
- The state diagram has no `created → incomplete` edge, so a learner who never starts cannot be
  marked incomplete. Kept exactly as the plan's diagram; revisit on Day 2 with the finish endpoint.

### Mutation check
Removed the "diagnostic asked at most once" guard in `policy.py`:
`test_diagnostic_is_asked_at_most_once` failed (1 failed, 217 passed); restored, all passed.
The random property test did **not** catch this mutation on its own, because random learners
eventually change signal. The targeted test is what protects that invariant.

### What I still do not understand
_(fill in yourself)_

### Actual results / next task
- `docker compose ps`: postgres and redis both `healthy` (Docker engine 29.9.3).
- `alembic upgrade head`: applied 0001. `python -m app.seed`: 3 × `inserted`; second run 3 × `unchanged`.
- `REQUIRE_SERVICES=1 pytest -q`: **291 passed, 0 skipped** in 2.5 s (Windows 11, Python 3.11.9),
  including migration downgrade/upgrade, the immutability trigger, duplicate-key rejection and
  `/ready` against real Postgres and Redis.
- `ruff check .` and `ruff format --check .`: clean.
- Frontend `npm run lint`: clean. `npm run build`: succeeds (Next.js 15.5.29).
- Next: Day 2, end-to-end text assessment.
