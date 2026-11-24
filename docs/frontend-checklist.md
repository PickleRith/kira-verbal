# Frontend redesign checklist (light editorial)

Scope: frontend only. Backend behaviour and API contracts unchanged. Items are ticked only
after they were verified (command output or a screenshot reviewed), not when written.

## Inventory (what exists)

- Next.js 15 App Router, React 19, TypeScript, Tailwind 4 (`@theme` tokens in `app/globals.css`).
- Pages: `/` landing, `/login`, `/register`, `/student`, `/student/[sessionId]`, `/teacher`,
  `/teacher/[sessionId]`.
- Presentation components in `components/`; API calls only in `lib/api.ts`; auth state in
  `lib/auth.tsx`; storage in `lib/storage.ts`; scoring rule in `lib/grading.ts`.
- Voice: `VoicePanel.tsx` (LiveKit room, agent state attribute), `Waveform.tsx` (Web Audio).
- Tests: Playwright (`e2e/`). No unit test runner yet.

## Files to change

| File | Change |
|---|---|
| `app/globals.css`, `app/layout.tsx` | New tokens, Lora + Inter, light theme, highlights, grid |
| `components/ui.tsx` | Primitives restyled; icons from Lucide |
| `components/shell.tsx` | Marketing top bar; app shell with deep-purple sidebar + mobile drawer; focus shell |
| `lib/voice-state.ts` (new) | Pure mapping from real voice events to UI states |
| `components/VoicePanel.tsx`, `Waveform.tsx` | Central mic, explicit states, lavender/purple waveform, mute/retry/end |
| Pages and feature components | Restyle to the new system |
| `vitest.config.ts`, `lib/*.test.ts` (new) | Unit tests for voice states and grading |
| `e2e/workflow.spec.ts` | Selectors updated; voice error state + text fallback test |
| `DESIGN_SYSTEM.md`, `README.md`, `docs/architecture.md` | Documentation |

## Checklist

Not done: an automated accessibility audit (axe or similar) and screen-reader testing; a
voice run with a real human voice.


- [x] Tokens and typography established before pages (globals.css, layout.tsx). Fonts confirmed in the browser (computed `Lora`/`Inter`) after fixing the variable scope bug
- [x] UI primitives rebuilt (button, card, pill, callout, field, tabs, stat, score)
- [x] Lucide icons replace the inline icon set (lucide-react 1.78.0; names checked against its type definitions)
- [x] App shell: deep-purple sidebar, outlined icons, mobile/tablet navigation (drawer screenshot at 390 px)
- [x] Landing page (hero highlights, grid band, product preview)
- [x] Login / register
- [x] Student home and results
- [x] Check-in page and voice interface. Live run against LiveKit recorded idle → connecting → listening → speaking → idle (end), muted badge; error state from a real 503 in the browser test. Processing and completed are covered by unit tests only (the test tone never produced an answer)
- [x] Teacher board and review page
- [x] Unit tests for voice states and grading (Vitest 3.2.7: 13 passed)
- [x] Browser tests pass (incl. voice error state with text fallback): 3 passed
- [x] Lint, type check, production build
- [x] Screenshots reviewed at desktop and phone width
- [x] Contrast checked against WCAG AA for text tokens (computed; purple `#8156FF` fails for text at 4.46:1, so text uses `purple-ink`)
- [x] DESIGN_SYSTEM.md, README, architecture notes
