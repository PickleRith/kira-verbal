import { HeroActions, HowItWorks, LessonShowcase } from "@/components/Landing";
import { MarketingShell } from "@/components/shell";
import { BrandMark, ButtonLink, Disclaimer, Icon, NoteCard } from "@/components/ui";

// Bar heights for the preview's waveform (fixed, so server and client render the same).
const BARS = [6, 10, 16, 12, 22, 30, 18, 36, 44, 30, 52, 40, 58, 46, 34, 50, 38, 28, 42, 24, 18, 26, 14, 10, 8];

function Squiggle({ className }: { className?: string }) {
  // A hand-drawn mark (decorative).
  return (
    <svg viewBox="0 0 140 60" className={className} aria-hidden="true" fill="none">
      <path
        d="M6 40 C 30 12, 52 52, 74 26 S 112 8, 134 30"
        stroke="#1a1a1a"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M18 52 C 46 34, 80 54, 120 44" stroke="#1a1a1a" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

// A static, decorative picture of the product (example data, not live).
function ProductPreview() {
  return (
    <div className="mx-auto max-w-5xl overflow-hidden rounded-t-xl border border-b-0 border-ink/80 bg-app" aria-hidden="true">
      <div className="flex">
        <div className="hidden w-14 shrink-0 flex-col items-center gap-4 bg-purple-deep py-4 sm:flex">
          <BrandMark inverted size="sm" />
          {[Icon.Home, Icon.Mic, Icon.Clipboard].map((Glyph, i) => (
            <span key={i} className={i === 1 ? "rounded-md bg-white/15 p-2 text-white" : "p-2 text-white/70"}>
              <Glyph className="h-4 w-4" />
            </span>
          ))}
        </div>
        <div className="grid flex-1 gap-4 p-4 md:grid-cols-[3fr_2fr] md:p-6">
          <div className="rounded-xl border border-line bg-surface p-5">
            <div className="flex items-center justify-between">
              <p className="font-serif text-[20px] text-ink">Photosynthesis</p>
              <span className="rounded-md bg-lavender-soft px-2 py-0.5 text-xs font-medium text-purple-ink">Listening</span>
            </div>
            <p className="mt-3 text-sm text-muted">Where does a plant get carbon dioxide?</p>
            <div className="mt-5 flex justify-center">
              <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-purple text-white">
                <Icon.Mic className="h-6 w-6" />
              </span>
            </div>
            <div className="mt-5 flex h-16 items-center justify-center gap-[3px] rounded-lg border border-line bg-raised px-3">
              {BARS.map((h, i) => (
                <span key={i} className="w-[5px] rounded-sm bg-lavender" style={{ height: h }} />
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <div className="rounded-xl border border-line bg-surface p-5">
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                Review queue <span className="rounded-md bg-ink px-1.5 text-xs text-white">3</span>
              </p>
              {[
                ["Sam", "78%", "Proficient"],
                ["Lee", "56%", "Developing"],
              ].map(([name, pct, band]) => (
                <div key={name} className="mt-3 flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm">
                  <span className="text-ink">{name}</span>
                  <span className="text-muted">
                    {pct} · {band}
                  </span>
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-line bg-surface p-5">
              <p className="text-xs font-medium text-muted">Evidence</p>
              <p className="mt-1 font-serif text-[17px] text-ink">&ldquo;Through tiny holes called stomata on the leaves.&rdquo;</p>
              <span className="mt-2 inline-block rounded-md bg-ok-soft px-2 py-0.5 text-xs font-medium text-ok">Level 3 · carbon dioxide</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <MarketingShell>
      {/* --- hero --------------------------------------------------------------------- */}
      <section className="mx-auto max-w-5xl px-4 pb-16 pt-16 text-center md:pt-24">
        <h1 className="text-[44px] leading-[1.1] text-ink md:text-[68px]">
          Hear what learners <span className="hl-lavender">actually</span>
          <br className="hidden sm:block" /> <span className="hl-mint">understand</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-[17px] text-muted">
          Kira Verbal runs short spoken check-ins. Students explain an idea in their own words; teachers get every
          answer, the evidence behind each suggested level, and the final say on the grade.
        </p>
        <div className="mt-9">
          <HeroActions />
        </div>
        <p className="mt-6 text-xs text-faint">Independent prototype · synthetic data only · not affiliated with Kira Learning</p>
      </section>

      {/* --- product band ------------------------------------------------------------- */}
      <section className="kv-grid-light relative overflow-hidden border-y border-ink/80 bg-lavender px-4 pt-12">
        <Squiggle className="absolute right-[6%] top-8 hidden w-32 md:block" />
        <ProductPreview />
      </section>

      {/* --- how it works ------------------------------------------------------------- */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-8 px-4 py-20 md:px-8">
        <p className="text-sm font-medium text-muted">How it works</p>
        <h2 className="mt-2 max-w-2xl text-[36px] text-ink md:text-[44px]">
          Three minutes of talking, a page of <em>evidence</em>.
        </h2>
        <div className="mt-8">
          <HowItWorks />
        </div>
      </section>

      {/* --- voice ---------------------------------------------------------------------- */}
      <section id="voice" className="scroll-mt-8 border-y border-line bg-surface">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 md:grid-cols-2 md:px-8">
          <div>
            <p className="text-sm font-medium text-muted">Voice check-ins</p>
            <h2 className="mt-2 text-[36px] text-ink md:text-[44px]">A conversation, not a quiz.</h2>
            <p className="mt-4 text-muted">
              Students press the microphone and talk. They see their own voice as a live waveform and always know
              what is happening: connecting, listening, thinking, speaking, finished. Typing works at every step,
              and audio is never stored.
            </p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {[
              { icon: <Icon.Mic className="h-5 w-5" />, title: "One clear control", body: "A single microphone to start, mute, and end." },
              { icon: <Icon.Waveform className="h-5 w-5" />, title: "Live waveform", body: "Drawn in the browser from the microphone; nothing is recorded." },
              { icon: <Icon.Lightbulb className="h-5 w-5" />, title: "Hints and questions", body: "Asking doesn't use up a question; hints are noted for the teacher." },
              { icon: <Icon.Chat className="h-5 w-5" />, title: "Always a text fallback", body: "If voice fails, the same check-in continues by typing." },
            ].map((item) => (
              <li key={item.title} className="rounded-xl border border-line bg-app p-5">
                <span className="flex h-9 w-9 items-center justify-center rounded-md bg-lavender-soft text-purple-ink">{item.icon}</span>
                <p className="mt-4 font-medium text-ink">{item.title}</p>
                <p className="mt-1 text-sm text-muted">{item.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* --- teachers + lessons ------------------------------------------------------- */}
      <section id="teachers" className="mx-auto max-w-6xl scroll-mt-8 px-4 py-20 md:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="text-sm font-medium text-muted">Lessons</p>
            <h2 className="mt-2 text-[36px] text-ink md:text-[44px]">
              Three topics, <em>explained</em> aloud.
            </h2>
          </div>
          <p className="max-w-sm text-muted">
            Rubric-grounded questions, with approved follow-ups for common misconceptions.
          </p>
        </div>
        <div className="mt-8">
          <LessonShowcase />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 md:px-8">
        <NoteCard
          title="Start with a class code."
          footer={
            <div className="flex flex-wrap gap-3">
              <ButtonLink href="/register?role=teacher">
                Create a class <Icon.ArrowRight className="h-4 w-4" />
              </ButtonLink>
              <ButtonLink href="/login" variant="secondary" className="border-ink">
                Log in
              </ButtonLink>
            </div>
          }
        >
          Teachers sign up and get a code. Students join with it, and every check-in they finish lands in the
          teacher&rsquo;s review queue, answer by answer.
        </NoteCard>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 md:px-8">
          <p className="font-serif text-[18px] text-ink">Kira Verbal</p>
          <Disclaimer className="max-w-xl" />
        </div>
      </footer>
    </MarketingShell>
  );
}
