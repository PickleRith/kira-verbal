# Security and privacy notes

Scope: a public demo with **synthetic data only**. This is what the prototype does and does
not protect. It makes no compliance claim. A school deployment would need its own FERPA /
COPPA, security, privacy and accessibility review.

## Who can do what

| Credential | Issued by | Grants | Stored as |
|---|---|---|---|
| Sign-in token (`kvu_…`) | `POST /v1/auth/register` or `/login` | The account's own pages; for a teacher, their class on every teacher route; for a student, starting and resuming their own check-ins | SHA-256 hash, expires after 7 days, deleted on sign-out |
| Learner `session_token` | `POST /v1/sessions`, `/v1/me/sessions` or a teacher launch | One session: read it, answer it, finish it, get a voice token | SHA-256 hash |
| Teacher `teacher_token` (`kvt_…`) | `POST /v1/teacher/workspaces` | One classroom: launch, list, report, review, export | SHA-256 hash |
| Voice worker credential (`v1.<session>.<expiry>.<hmac>`) | `POST …/voice-token` | The same access as that learner's token, until the session deadline | Not stored; verified by HMAC |

- Wrong token, another classroom's session and an unknown id all answer `404`, so ids
  can't be probed. A learner token on a teacher route is `401`.
- Learners never receive evaluator output (levels, misconception tags, intents). A test
  asserts the student responses, and the browser test checks the page.
- Tokens live in the browser's `localStorage` for the demo. Anyone with the browser profile
  has them. Real accounts with SSO are out of scope.
- **Accounts are demo accounts.** Passwords (8–128 characters) are hashed with scrypt and a
  per-user salt; the plain password is never stored or logged. Wrong email and wrong
  password give the same error, and an unknown email still runs a hash so timing doesn't
  reveal it. Registering with a taken email does say so (`409 email_taken`), which lets
  someone test whether an address has an account; acceptable for a demo, not for real use.
  No email verification, password reset, lockout or SSO.
- A student sees whether a check-in was reviewed, never the levels. Exports carry an opaque
  `user-…` id, never a student's name or email (the browser test checks this).
- **Not protected:** anyone can register, create a classroom or an anonymous session. That is the
  demo's purpose; rate limits bound the abuse.

## Limits

| Limit | Default | Setting |
|---|---|---|
| Sign-in / registration attempts per client IP | 10 per minute | `RATE_LIMIT_AUTH_PER_MINUTE` |
| New sessions / classrooms per client IP | 30 per minute | `RATE_LIMIT_CREATE_PER_MINUTE` |
| Answers per session | 40 per minute | `RATE_LIMIT_TURNS_PER_MINUTE` |
| Other API requests per client IP | 600 per minute | `RATE_LIMIT_REQUESTS_PER_MINUTE` |
| Request body | 16 KB | `MAX_BODY_BYTES` |
| Answer text | 2,000 characters | fixed |
| Answers per session | 5, plus 4 free side turns | `MAX_TURNS`, `MAX_SIDE_TURNS` |
| Session length | 5 minutes + 1 minute grace | `SESSION_MAX_SECONDS` |
| Model call time | 20 s per attempt, 45 s per answer; reply line 5 s | `LLM_TIMEOUT_SECONDS`, … |

Over a rate limit → `429 rate_limited` with `Retry-After`. The limiter uses Redis and
**fails open** if Redis is down (logged): rate limiting is protection, not correctness.
Behind a proxy, run uvicorn with `--proxy-headers` (the container does) so limits apply to
the real client address. **Set a spend limit on the Anthropic account as well:** rate limits
bound request counts, not the bill.

## Untrusted input

- A learner's words go to the evaluator and responder inside delimiter tags, with closing
  tags neutralised. No tools are offered to either model, so an injected instruction has
  nothing to call.
- Model output is never trusted: structured output is schema-checked, then every evidence
  item is validated against the lesson and the exact transcript. Replies pass deterministic
  guardrails or are replaced by a template.
- Request bodies reject unknown fields; ids are pattern-checked; sizes are capped.

## Data kept, and for how long

| Data | Kept | Notes |
|---|---|---|
| Transcripts (typed or transcribed speech) | Until purged | `python -m app.purge` deletes sessions older than `TRANSCRIPT_RETENTION_DAYS` (default 7) with their turns, evidence, reports, reviews and exports. **Nothing runs it automatically:** schedule it |
| Audio | Never stored by this app | Audio passes through LiveKit Cloud and its speech providers; their retention is governed by that account's settings, not this code |
| Learner identity | A made-up `demo-…` id, or an account's `user-…` id | Accounts hold an email and display name; the UI asks for made-up ones. The purge job deletes old check-ins but keeps accounts and their classes |
| Logs | Timing, ids, error types | No transcripts, no tokens. A test checks every log line of a full session |
| Model provider | Each answer and the rubric go to Anthropic when `EVALUATOR_PROVIDER=llm` | Synthetic data only; check the provider's data terms before any real use |

## Secrets

- All in environment variables / `.env` (git-ignored; verified absent from history).
  `.env.example` has names only.
- `VOICE_WORKER_SECRET` must be 32+ characters (startup fails otherwise).
- Tests pin fake providers and blank credentials, so the suite can't make paid calls or
  read a developer's `.env`.

## Known gaps

- Demo authentication only (see above); no audit of *reads*; no account deletion endpoint.
- No CSRF concern today (bearer tokens in headers, no cookies), but tokens in
  `localStorage` are exposed to any XSS. The UI renders text only, never HTML.
- Rate limits are per IP: users behind one NAT share a bucket, and an attacker with many
  IPs is not stopped.
- No automated dependency or container scanning.
- The wellbeing flag is a prompt for the teacher, not a safeguarding process.
