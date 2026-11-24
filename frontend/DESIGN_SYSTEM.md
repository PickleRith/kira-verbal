# Kira Verbal design system

A light, editorial interface for spoken check-ins. It is designed to sit comfortably next to
modern K-12 tools (cream pages, serif headlines, a deep-purple app rail) while keeping its own
identity: its own name, mark (a microphone on a black square with a mint dot) and voice
interface. It does not use Kira Learning's logo and implies no partnership.

Tokens live in `app/globals.css` (`@theme`), primitives in `components/ui.tsx`.

## Principles

1. **Editorial, not decorative.** Serif headlines, generous whitespace, thin borders. A
   highlight or a hand-drawn mark appears at most once per screen.
2. **Colour has a job.** Black for primary actions, purple for AI (voice, suggestions),
   green for success and positive learning outcomes, amber for "look at this", red for
   errors and wellbeing flags. Lavender and mint are decorative fills, never text.
3. **State is always visible and always real.** Every loading, empty, error and voice state
   has its own copy, and every state shown comes from a real backend or LiveKit event.
4. **Text is always an option.** Nothing depends on voice working.

## Colour

| Token | Value | Use | Contrast (measured) |
|---|---|---|---|
| `paper` | `#FEFDF0` | Marketing page background | |
| `app` | `#FCFBFF` | Workspace background | |
| `surface` | `#FFFFFF` | Cards | |
| `raised` | `#F7F5FB` | Fills inside cards | |
| `sunken` | `#F1EEF7` | Tracks, inactive segments, neutral counters | |
| `line` / `line-strong` | `#E2DFE7` / `#C9C4D3` | Borders / input and secondary-button borders | |
| `ink` | `#1A1A1A` | Primary text, primary buttons | 17.4:1 on white |
| `muted` | `#575757` | Secondary text | 7.2:1 on white |
| `faint` | `#6E6A76` | Captions only | 5.3:1 on white; 4.46:1 on lavender-soft (don't) |
| `purple` | `#8156FF` | AI accents: icons, rings, waveform line, fills | 4.46:1 on white: **not for text**, no white text on it |
| `purple-ink` | `#5B30D9` | Purple text; purple buttons with white text | 7.3:1 |
| `purple-deep` | `#1C0845` | Sidebar | white on it 18:1 |
| `lavender` / `lavender-soft` | `#B196FF` / `#EFE9FF` | Title highlight, AI fills, waveform bars | ink on lavender 7.2:1 |
| `mint` / `mint-soft` | `#74EBAD` / `#E4F9EE` | Highlight, success fills, note cards | ink on mint 11.8:1 |
| `ok`, `warn`, `bad`, `info` (+ `-soft`) | | Status text on its soft fill | all ≥ 5.4:1 |

Ratios were computed with the WCAG formula (script in the engineering journal); re-check
any new pairing before using it for text.

## Typography

| Role | Font | Size | Weight |
|---|---|---|---|
| Hero | Lora | 44 px phone, 68 px desktop | 400 |
| Page title (`h1`) | Lora | 36–44 px | 400 |
| Section (`h2`) | Lora | 28–36 px | 400 |
| Card title | Lora | 20–26 px | 400 |
| Body | Inter | 16 px, line-height 1.6 | 400 |
| Labels, pills, dashboard metadata | Inter | 12–14 px | 500 |

- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows.
- Bold is rare: buttons and labels use 500, counters 600.
- In an `h1`, an `<em>` becomes a lavender rectangle (one word, e.g. a name). For other
  emphasis use `.hl-lavender` (rectangle) or `.hl-mint` (rounded); in `h2`/`h3` an `<em>`
  is plain italic.
- Fonts load through `next/font` and their CSS variables are set on `<html>`. They must be
  on `<html>`, not `<body>`: Tailwind defines `--font-serif: var(--font-lora)` on `:root`, and
  a variable defined only on `<body>` is undefined there, so every font silently falls back.

## Spacing, shape, depth

- 8 px grid (Tailwind steps 2, 4, 6, 8 …). Cards use 20–32 px padding.
- Radii: 6 px (`rounded-md`) for buttons, pills, inputs; 8 px for inner panels; 12 px
  (`rounded-xl`) for cards. Full circles only for the microphone, avatars and status dots.
- Depth comes from 1 px borders, not shadows. The note card uses a 1 px ink border.
- Graph paper (`.kv-grid`, `.kv-grid-light`) only in decorative bands and lesson art.

## Components (`components/ui.tsx` unless noted)

| Component | Use | Notes |
|---|---|---|
| `Button` / `ButtonLink` | `primary` (black) for the main action; `secondary` (outline); `ghost`; `ai` (purple-ink) for AI actions such as "Retry voice"; `success`; `danger` (outlined red) for ending a session | One primary per region |
| `Card` | Every module | White, 1 px border, 12 px radius |
| `NoteCard` | One highlight per page (class code, call to action) | Mint or lavender with an ink border |
| `Pill` | Statuses | `green` success, `amber` needs attention, `red` error/flag, `purple` AI, `blue` neutral info, `gray` |
| `Count` | Counters next to headings ("Review queue 3") | |
| `Callout` | Inline messages | `role="alert"` for errors, `role="status"` for progress |
| `Field` | Labelled inputs | The label wraps the input; hints are visible text |
| `Stat` | Key numbers | `accent` for the one that needs action |
| `EmptyState`, `Spinner` | Loading and empty lists | Spinner stops for reduced motion |
| `FolderTabs` (`FolderTabs.tsx`) | Switching views of one object | `role="tablist"`, arrow keys |
| `ScoreSummary`, `ScoreChip`, `BandPill`, `CriterionResults` (`Score.tsx`) | Grades | Bands: mastered/proficient green, developing amber, beginning blue (never red: students see it) |
| `VoicePanel`, `Waveform` | Voice check-in | See below |
| `MarketingShell`, `AppShell`, `FocusShell` (`shell.tsx`) | Page chrome | See layout |

Icons: Lucide outline icons through `Icon.*` (stroke 1.75, 20 px default, always
`aria-hidden`; the control gets the accessible name).

## Layout

- **MarketingShell:** landing, login, register. Cream background, top bar with the wordmark,
  section links (desktop) and "Log in" / "Get started".
- **AppShell:** signed-in pages. A 72 px deep-purple sidebar with outlined icons, a tooltip
  and `aria-current` on the active item, the user's initial and sign out at the bottom. Below
  768 px it becomes a top bar with a menu button that opens a drawer (`role="dialog"`,
  Escape closes it).
- **FocusShell:** the check-in itself. A white top bar with the lesson and time left; nothing
  else to navigate to.

## Voice interface

One central microphone, one status badge, the waveform while connected, and explicit
controls. States are derived in `lib/voice-state.ts` from real events only, and unit-tested.

| State | Comes from | Microphone button | Controls |
|---|---|---|---|
| Idle | Voice not started, or ended by the learner | Purple, starts voice | |
| Connecting | Token request / room join / agent `initializing` | Spinner | Mute, End once in the room |
| Listening | Agent attribute `lk.agent.state` = `listening` or `idle` | Purple with a soft lavender pulse; toggles mute | Mute, End |
| Processing | Agent `thinking` (waiting on the assessment API) | Purple, three dots below | Mute, End |
| Speaking | Agent `speaking` | Speaker icon | Mute, End |
| Completed | Assessment API reports the session finished | Green check | |
| Error | Token 503/network error, connect failure, microphone blocked | Red retry | Retry voice |

Muted is a modifier shown in the badge ("Muted") and on the button (`aria-pressed`). The
waveform draws the microphone (purple line over lavender bars) and the agent (grey line)
from the live tracks; it is never recorded.

## Accessibility

- Text contrast ≥ 4.5:1 (table above). Purple `#8156FF` is never used for text.
- Every control has a visible label or an `aria-label`; icons are `aria-hidden`.
- Focus: 2 px purple outline with offset on every interactive element.
- Live regions: the voice badge and progress callouts are `role="status"`, errors
  `role="alert"`.
- Keyboard: tabs use arrow keys; the mobile drawer closes with Escape; Ctrl+Enter sends an answer.
- Motion is limited to a pulse, typing dots and short fades, all off under
  `prefers-reduced-motion`.
- Layouts work at 390 px wide without horizontal scrolling (checked in screenshots).

## Don't

Heavy shadows, glass/blur, gradients on surfaces, large rounded cards, pill-shaped everything,
neon colours, all-caps labels, more than one highlight per heading, decorative elements in
the middle of a task, Kira Learning's logo or wording that suggests a partnership.

## Reference screens

Captured from the running app (synthetic data) after the redesign:
[landing](../docs/screenshots/landing.png) ·
[register](../docs/screenshots/register.png) ·
[student home](../docs/screenshots/student-home.png) ·
[check-in](../docs/screenshots/learner.png) ·
[check-in finished](../docs/screenshots/learner-finished.png) ·
[voice live](../docs/screenshots/voice-live.png) ·
[waveform](../docs/screenshots/voice-waveform.png) ·
[voice error](../docs/screenshots/voice-error.png) ·
[teacher board](../docs/screenshots/teacher-dashboard.png) ·
[review by question](../docs/screenshots/review.png) ·
[rubric, approved](../docs/screenshots/review-rubric.png) ·
[student results](../docs/screenshots/student-results.png) ·
phone: [landing](../docs/screenshots/mobile-landing.png), [student](../docs/screenshots/mobile-student.png), [menu](../docs/screenshots/mobile-menu.png)
