import { LessonPicker } from "@/components/LessonPicker";
import { AppShell, BrandMark, Card, Disclaimer, Icon, SectionHeader, ToolTile } from "@/components/ui";

const STEPS = [
  {
    icon: <Icon.Chat className="h-4 w-4" />,
    title: "A short spoken or typed check-in",
    body: "Rubric-grounded questions, about 3–5 minutes. Follow-ups adapt to what the learner says.",
  },
  {
    icon: <Icon.Sparkle className="h-4 w-4" />,
    title: "Evidence, not guesses",
    body: "Every suggested level is backed by the learner's exact words. Unknown stays unknown.",
  },
  {
    icon: <Icon.Check className="h-4 w-4" />,
    title: "The teacher decides",
    body: "Approve, revise with a reason, or reject. Only approved results can be exported.",
  },
];

export default function Home() {
  return (
    <AppShell active="home">
      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-8 md:px-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-8">
          <header>
            <p className="text-sm font-medium text-brand-600">Oral assessment prototype</p>
            <h1 className="mt-1 text-[30px] font-semibold leading-tight tracking-tight text-ink">
              Hear what learners understand.
            </h1>
            <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">
              Kira Verbal runs a short adaptive conversation, surfaces likely misconceptions, and gives
              teachers transcript-backed evidence to approve or revise.
            </p>
          </header>

          <section aria-labelledby="tools">
            <SectionHeader id="tools" title="Start here" />
            <div className="grid gap-3 sm:grid-cols-3">
              <ToolTile
                active
                href="/teacher"
                icon={<Icon.Clipboard />}
                label="Teacher dashboard"
                hint="Launch, review, export"
              />
              <ToolTile
                href="#lessons"
                icon={<Icon.Chat />}
                label="Try as a learner"
                hint="Anonymous demo session"
                tint="bg-sky-50 text-sky-600"
              />
              <ToolTile
                href="/teacher"
                icon={<Icon.Mic />}
                label="Voice answers"
                hint="Speak instead of typing"
                tint="bg-rose-50 text-rose-500"
              />
            </div>
          </section>

          <section aria-labelledby="lessons" id="lessons" className="scroll-mt-6">
            <SectionHeader id="lessons-title" title="Lessons" />
            <Card className="p-3">
              <LessonPicker />
            </Card>
            <p className="mt-2 text-xs text-faint">
              Sessions started here belong to no classroom, so no teacher can review them. Use the
              teacher dashboard for the full flow.
            </p>
          </section>
        </div>

        <aside className="space-y-4">
          <Card className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-line px-5 py-4">
              <BrandMark size="sm" />
              <p className="font-semibold text-ink">How it works</p>
            </div>
            <div className="relative h-28 overflow-hidden bg-gradient-to-br from-brand-200 via-brand-100 to-sky-100">
              <div className="absolute -left-6 top-4 h-24 w-24 rounded-full bg-brand-400/40 blur-2xl" />
              <div className="absolute right-4 -top-6 h-28 w-28 rounded-full bg-sky-300/50 blur-2xl" />
              <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-end gap-1" aria-hidden="true">
                {[10, 22, 34, 18, 28, 40, 24, 14, 30, 20, 12].map((h, i) => (
                  <span key={i} className="w-1.5 rounded-full bg-brand-600/70" style={{ height: h }} />
                ))}
              </div>
            </div>
            <ol className="space-y-4 px-5 py-5">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                    {step.icon}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-ink">
                      {i + 1}. {step.title}
                    </p>
                    <p className="mt-0.5 text-sm leading-relaxed text-muted">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
          <Disclaimer className="px-1" />
        </aside>
      </main>
    </AppShell>
  );
}
