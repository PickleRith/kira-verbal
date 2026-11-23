# Engineering journal

## 2026-11-23 — Day 3: real evaluation

- [ ] I can explain each changed module.
- [ ] I ran tests and recorded results.
- [ ] I updated docs and committed code.

### What I built
- New evaluator contract: an evaluator returns learner intent plus *proposed* evidence
  (criterion, level 0–3 or none, exact quote, tag, reason, abstain).
- `AnthropicEvaluator` (`providers/llm.py`): official `anthropic` SDK 2.13.0, `claude-opus-5-5`
  at effort medium. Per-request JSON schema with enums, `output_config.format`, Pydantic re-parse.
  SDK retry (1) plus one re-ask on truncated or unparseable output. Refusal → no evidence.
  Server-side refusal fallbacks are enabled.
- Versioned prompt `evaluator-v1` (`providers/prompts.py`) with a rubric context block and an
  untrusted `<learner_transcript>` boundary whose closing tag is neutralised.
- Deterministic validator (`services/evaluator.py`): accept / abstain / reject; normalised exact
  quote matching; signal from accepted evidence only.
- `domain/scoring.py`: suggested level = latest accepted independent evidence; unknown otherwise;
  assisted kept separate; conflicts and rejections flag review; coverage as a count pair.
- Migration 0003: `evidence` table (status, rejection reason, assisted, evaluator version, model)
  written in the same transaction as its turn.
- Fake evaluator moved onto the same contract (`fake-keyword-v2`).
- 22 labelled cases in `data/evals/evaluator_cases.v1.json` (correct, partial, incorrect,
  ambiguous, adversarial, help, stop) and `scripts/run_evaluator_cases.py`.
- `python -m app.inspect_session <id>`: developer view of evidence and suggested levels.
- Settings check: processing lease > evaluator timeout ≥ LLM timeout × (retries + 1).

### Request flow (files and functions)
`submit_turn` T1 claim → `_evaluate` (thread pool, 45 s cap) → `AnthropicEvaluator.evaluate` →
`client.beta.messages.create(...)` → `_LlmEvaluation.model_validate_json` →
`services/evaluator.py:validate_output` → T2: `next_action` on the validated signal, turn
committed, `EvidenceRow`s inserted → `domain/scoring.py:summarize` when read.

### Why this design
The model is good at reading an explanation; it is not trusted to keep rules. Everything that
must be true (the quote exists, the criterion applies, the level is in range, assisted is not
independent, unknown is not zero) is enforced by code that tests can pin down.

### Bug, root cause, fix, regression test
- **Latent bug avoided by a new invariant.** Day 2 had a 30 s lease and a 10 s evaluator timeout.
  An LLM call can take longer than that, and if the lease expired first, a healthy slow call
  would have been "recovered" and then lost its claim. Now `AssessmentConfig` and `Settings`
  reject any configuration where the lease does not outlast the evaluator timeout. Defaults:
  lease 60 s, timeout 45 s.
- Mutation checks: disabling the quote-not-found rule failed 5 unit tests; letting assisted
  evidence set the suggested level failed 2. Both were restored.

### Tradeoff and alternative
- Structured outputs alone would guarantee valid JSON shape but not truth; the validator
  duplicates some checks on purpose (defence in depth).
- On evaluator failure the turn is released (503) rather than committed as "unknown", so the
  learner's answer is never silently dropped. Cost: repeated outages block progress on that
  question; the learner can still finish early.
- Rejected evidence is stored, not discarded, so the rate of invented quotes can be measured.

### What I still do not understand
_(fill in yourself)_

### Actual results / next task
- `REQUIRE_SERVICES=1 pytest -q`: **402 passed** in 10.9 s. New or changed files:
  23 validation tests, 7 scoring tests, 9 Claude-adapter tests (stub client), 24 fixture
  consistency tests, 12 fake-evaluator tests, and 23 orchestrator tests (including fabricated
  quote → rejected, evidence persisted with the assisted flag, and crash recovery with the
  evaluator called twice but evidence committed once).
- `ruff check` / `ruff format --check`: clean.
- Fake evaluator on the 22 cases: signal 20/22, tag 22/22, level 14/22. That is the fake's
  baseline, not system accuracy.
- Live stack: a session with hint → assisted answer showed `purpose` as **unknown** (assisted
  only), `carbon_dioxide` **conflict** (1 then 2), coverage 2 of 3, needs review.
- **Not run:** the Claude evaluator against the live API (no credentials on this machine). Run
  `python scripts/run_evaluator_cases.py --provider llm --confirm-cost` and record the result here.
- Next: Day 4, streaming voice.

## 2026-11-23 — Day 2: end-to-end text assessment

- [ ] I can explain each changed module.
- [ ] I ran tests and recorded results.
- [ ] I updated docs and committed code.

### What I built
- Migration 0002: `sessions` (pinned to a lesson version by FK, token hash, `state_version`,
  processing lease, deadline) and `turns` (partial unique indexes on live
  `(session_id, client_turn_id)` and `(session_id, sequence)`, cached response).
- `Evaluator` protocol and a deterministic keyword `FakeEvaluator`.
- `AssessmentService`: create, get/resume, submit turn (refresh → claim → evaluate → commit),
  finish early, lease recovery, deadline timeout, evaluator timeout, sanitising evaluator tags.
- REST routes `/v1/lessons`, `/v1/sessions`, `.../turns`, `.../finish`; bearer-token demo auth;
  typed error bodies; CORS allowlist.
- Frontend: lesson picker, student page (intro, transcript, hint, finish, loading and error
  states, resume after reload), typed API client.

### Request flow (files and functions)
`StudentSession.send()` → `lib/api.ts:submitTurn` → `api/sessions.py:submit_turn` →
`services/assessment.py:AssessmentService.submit_turn` → `_refresh` (T0) → claim (T1, row lock,
`repositories/sessions.py:find_live_turn`) → `_evaluate` (thread pool, timeout) → commit (T2,
`domain/policy.py:next_action`, `_apply_action`) → `TurnResponse` stored on the turn row.

### Why this design
See [api.md](api.md#transaction-design-why-it-is-safe) and
[ADR 0001](adr/0001-database-idempotency.md). In short: the database row lock, `state_version`
and partial unique indexes guarantee "commit at most once"; no transaction is held during the
evaluator call.

### Bug, root cause, fix, regression test
- None found by the tests in this milestone: all 336 passed on the first run. Lint issues were
  FastAPI's `Depends` idiom flagged by ruff B008 (configured as allowed) and one long line.
- SQLAlchemy 2.1 deprecated `Result.tuples()`; replaced with plain row unpacking.

### Tradeoff and alternative
- **Hint requests count toward the 5-turn budget.** In the live smoke test a hint plus the
  diagnostic follow-up used the budget before the light objective was asked, so the session
  ended with `budget`. Alternative: don't count help requests. Kept for now; revisit with the
  evaluation on Day 6.
- **Saying "stop" → `completed/learner_request`; "Finish early" → `incomplete/learner_exit`.**
  The plan's state diagram has no evaluating → incomplete edge for a learner request.
- **Fake evaluator ignores negation** ("not from the roots" still matches "root"). Acceptable for
  a fake; the Day 3 LLM evaluator replaces it.
- Hint requests go through the evaluator as text ("Can I have a hint?") rather than a separate
  API field, so voice and text behave the same.

### What I still do not understand
_(fill in yourself)_

### Actual results / next task
- `REQUIRE_SERVICES=1 pytest -q`: **336 passed** in 8.6 s (Windows 11, Python 3.11.9,
  Postgres 16, Docker engine 29.9.3). New: 21 orchestrator tests (flow, hint, budget, stop,
  idempotent retry, payload mismatch, stale version, 8-thread races, evaluator error/timeout,
  crash recovery, late commit after recovery, deadline, finish), 13 HTTP contract tests,
  11 fake-evaluator tests.
- `ruff check` / `ruff format --check`: clean. Frontend `npm run lint`, `tsc --noEmit`,
  `npm run build`: clean.
- Live smoke test (uvicorn + Next dev, HTTP with browser Origin header): hint → assisted answer;
  duplicate submit replayed identically; stale request 409; roots → diagnostic q3; session
  completed; student page 200.
- **Not yet verified by hand:** clicking through the student page in a real browser.
- Gaps: no frontend unit tests yet (Vitest), no rate limiting (Day 6), Redis unused beyond
  readiness.
- Next: Day 3, real LLM evaluation.

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
