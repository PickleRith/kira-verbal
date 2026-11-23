# ADR 0001: Turn idempotency and concurrency live in Postgres, not Redis

Date: 2026-11-23 · Status: accepted

## Context

A learner's answer can arrive more than once (double click, network retry, voice worker
reconnect) or concurrently with another answer (two tabs). Each answer triggers a slow,
possibly paid evaluator call. We must never commit the same answer twice or let two answers
both advance the session from the same state.

## Decision

- Each answer carries a client-generated `client_turn_id` and the `expected_state_version`.
- A short transaction locks the session row, looks up the turn id, checks the version and
  inserts the turn as `processing`. Partial unique indexes on `(session_id, client_turn_id)` and
  `(session_id, sequence)` for non-failed turns are the backstop.
- The evaluator runs with no transaction open. A second short transaction commits only if the
  claim is unchanged.
- An expired processing lease is recovered by the next request for that session.
- Redis is not used for correctness. It may later hold an optional lock to reduce duplicate
  evaluator calls, with token-safe release and a TTL.

## Why not a Redis lock alone

A Redis lock can expire while the holder is still working (GC pause, slow model), after which a
second worker also "holds" it. Redis can lose the lock on failover. The lock also says nothing
about whether the work was already committed. Only the database that stores the turn can make
"commit at most once" true.

## Consequences

- After a crash, the evaluator may be called twice for one answer (cost, not correctness).
- `state_version` advances by 2 per accepted turn (claim + commit). Clients treat it as opaque.
- Tests cover concurrent submissions, retries, evaluator failure, timeout, crash recovery and a
  late commit after recovery.
