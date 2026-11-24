"use client";

// Demo teacher dashboard: create a classroom (workspace), launch sessions for synthetic
// learners, and work through the review queue. The teacher token stays in this browser.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { sessionStore, teacherStore } from "@/lib/storage";
import type { LessonSummary, ReportStatus, TeacherSessionItem } from "@/lib/types";

import {
  AppShell,
  Button,
  Callout,
  Card,
  Disclaimer,
  Icon,
  PageHeader,
  Pill,
  SectionHeader,
  Spinner,
  ToolTile,
  type Tone,
} from "./ui";

const LEARNER_PATTERN = /^demo-[a-z0-9-]{1,40}$/;
const REFRESH_MS = 5000;

export const REPORT_BADGE: Record<ReportStatus, { label: string; tone: Tone; icon: React.ReactNode }> = {
  pending: { label: "In progress", tone: "purple", icon: <Icon.Clock className="h-3.5 w-3.5" /> },
  ready_for_review: { label: "Needs review", tone: "amber", icon: <Icon.Clock className="h-3.5 w-3.5" /> },
  approved: { label: "Approved", tone: "green", icon: <Icon.Check className="h-3.5 w-3.5" /> },
  rejected: { label: "Rejected", tone: "red", icon: <Icon.X className="h-3.5 w-3.5" /> },
};
const LESSON_TINT = ["bg-emerald-50 text-emerald-600", "bg-amber-50 text-amber-600", "bg-sky-50 text-sky-600"];
const QUEUE_ORDER: Record<ReportStatus, number> = { ready_for_review: 0, pending: 1, rejected: 2, approved: 3 };

export function TeacherDashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [sessions, setSessions] = useState<TeacherSessionItem[] | null>(null);
  const [lessonId, setLessonId] = useState("");
  const [learnerId, setLearnerId] = useState("demo-learner-1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [launched, setLaunched] = useState<{ id: string; learner: string } | null>(null);

  useEffect(() => {
    setToken(teacherStore.getToken());
    setLoaded(true);
    api
      .listLessons()
      .then((list) => {
        setLessons(list);
        if (list.length) setLessonId((current) => current || list[0].id);
      })
      .catch(() => setError("Could not load lessons. Is the API running on port 8000?"));
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setSessions(await api.teacherSessions(token));
    } catch (e) {
      if (e instanceof ApiError && e.code === "teacher_not_found") {
        teacherStore.setToken(null); // classroom no longer exists (e.g. database reset)
        setToken(null);
        setSessions(null);
        return;
      }
      setError(e instanceof ApiError ? e.message : "Could not load sessions.");
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [token, refresh]);

  const queue = useMemo(
    () =>
      [...(sessions ?? [])].sort(
        (a, b) =>
          QUEUE_ORDER[a.report_status] - QUEUE_ORDER[b.report_status] ||
          b.created_at.localeCompare(a.created_at),
      ),
    [sessions],
  );
  const stats = useMemo(() => {
    const list = sessions ?? [];
    return {
      total: list.length,
      review: list.filter((s) => s.report_status === "ready_for_review").length,
      approved: list.filter((s) => s.report_status === "approved").length,
      followUp: list.filter((s) => s.wellbeing_flags > 0).length,
    };
  }, [sessions]);

  async function createClassroom() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createWorkspace();
      teacherStore.setToken(created.teacher_token);
      setToken(created.teacher_token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create a classroom.");
    } finally {
      setBusy(false);
    }
  }

  async function launch(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (!LEARNER_PATTERN.test(learnerId)) {
      setError('Learner ID must look like "demo-ana" (lowercase letters, digits, dashes).');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.teacherCreateSession(token, lessonId, learnerId);
      // Same browser plays the learner: store their token where the student page looks.
      sessionStore.setToken(created.session_id, created.session_token);
      setLaunched({ id: created.session_id, learner: created.synthetic_learner_id });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the session.");
    } finally {
      setBusy(false);
    }
  }

  function leave() {
    if (!window.confirm("Forget this classroom in this browser? You won't be able to reopen its reports.")) return;
    teacherStore.setToken(null);
    setToken(null);
    setSessions(null);
    setLaunched(null);
  }

  if (!loaded) return <AppShell active="teacher">{null}</AppShell>;

  return (
    <AppShell active="teacher">
      <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
        <PageHeader
          eyebrow="Demo teacher"
          title="Teacher dashboard"
          subtitle="Launch oral check-ins, review the evidence, and export approved results."
        />

        {error ? (
          <div className="mt-5">
            <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
              {error}
            </Callout>
          </div>
        ) : null}

        {!token ? (
          <Card className="mt-6 overflow-hidden">
            <div className="grid md:grid-cols-[1fr_280px]">
              <div className="p-6 md:p-8">
                <h2 className="text-xl font-semibold text-ink">Start a demo classroom</h2>
                <p className="mt-2 max-w-lg text-[15px] leading-relaxed text-muted">
                  Your classroom is private to this browser. Launch assessments for synthetic learners,
                  then review the evidence, approve or revise suggested rubric levels, and export approved
                  results. Nothing is graded automatically.
                </p>
                <Button onClick={() => void createClassroom()} disabled={busy} className="mt-5">
                  {busy ? <Spinner /> : <Icon.Plus className="h-4 w-4" />}
                  {busy ? "Creating…" : "Create classroom"}
                </Button>
              </div>
              <div className="relative hidden min-h-48 overflow-hidden bg-gradient-to-br from-brand-300 via-brand-200 to-sky-200 md:block">
                <div className="absolute left-6 top-6 h-32 w-32 rounded-full bg-brand-500/40 blur-2xl" />
                <div className="absolute bottom-0 right-0 h-36 w-36 rounded-full bg-rose-300/50 blur-2xl" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/70 text-brand-600 shadow-lift backdrop-blur">
                    <Icon.Clipboard className="h-8 w-8" />
                  </span>
                </div>
              </div>
            </div>
          </Card>
        ) : (
          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0 space-y-8">
              <section aria-labelledby="launch-title">
                <SectionHeader id="launch-title" title="Launch an assessment" />
                <form onSubmit={launch}>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {lessons.map((lesson, i) => (
                      <ToolTile
                        key={lesson.id}
                        active={lesson.id === lessonId}
                        onClick={() => setLessonId(lesson.id)}
                        icon={<Icon.Book className="h-4 w-4" />}
                        label={lesson.title}
                        hint={`${lesson.objective_count} objectives · v${lesson.version}`}
                        tint={LESSON_TINT[i % LESSON_TINT.length]}
                      />
                    ))}
                  </div>
                  <Card className="mt-3 flex flex-wrap items-end gap-3 p-4">
                    <label className="min-w-[220px] flex-1 text-sm">
                      <span className="block font-medium text-ink">Synthetic learner ID</span>
                      <span className="mt-1 flex items-center rounded-xl border border-line bg-white focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100">
                        <Icon.User className="ml-3 h-4 w-4 text-faint" />
                        <input
                          value={learnerId}
                          onChange={(e) => setLearnerId(e.target.value.trim().toLowerCase())}
                          className="w-full rounded-xl bg-transparent px-2.5 py-2.5 font-mono text-sm outline-none focus-visible:outline-none"
                          aria-describedby="learner-help"
                        />
                      </span>
                    </label>
                    <Button type="submit" disabled={busy || !lessonId}>
                      {busy ? <Spinner /> : <Icon.ArrowRight className="h-4 w-4" />}
                      {busy ? "Starting…" : "Launch"}
                    </Button>
                    <p id="learner-help" className="w-full text-xs text-faint">
                      Use made-up IDs only, such as demo-ana. Never a real student&rsquo;s name.
                    </p>
                  </Card>
                </form>
                {launched ? (
                  <div className="mt-3">
                    <Callout tone="green" role="status" icon={<Icon.Check className="h-4 w-4" />} title={`Session ready for ${launched.learner}`}>
                      <a
                        href={`/student/${launched.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium underline underline-offset-2"
                      >
                        Open the learner view in a new tab
                      </a>
                      , answer as the learner, then come back here to review.
                    </Callout>
                  </div>
                ) : null}
              </section>

              <section aria-labelledby="queue-title">
                <SectionHeader
                  id="queue-title"
                  title="Review queue"
                  count={stats.review}
                  action={
                    <Button variant="pill" onClick={() => void refresh()} className="py-1.5">
                      Refresh
                    </Button>
                  }
                />
                <Card className="p-3">
                  {sessions === null ? (
                    <p className="flex items-center gap-2 p-3 text-sm text-muted" role="status">
                      <Spinner /> Loading…
                    </p>
                  ) : queue.length === 0 ? (
                    <div className="flex flex-col items-center px-4 py-10 text-center">
                      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-500">
                        <Icon.Clipboard className="h-6 w-6" />
                      </span>
                      <p className="mt-3 font-medium text-ink">No sessions yet</p>
                      <p className="mt-1 text-sm text-muted">Launch an assessment above to fill your queue.</p>
                    </div>
                  ) : (
                    <ul className="space-y-2">
                      {queue.map((s) => {
                        const badge = REPORT_BADGE[s.report_status];
                        return (
                          <li key={s.session_id}>
                            <Link
                              href={`/teacher/${s.session_id}`}
                              className="group flex items-center justify-between gap-4 rounded-xl bg-row px-4 py-3 transition hover:bg-brand-50"
                            >
                              <div className="min-w-0">
                                <p className="truncate font-medium text-ink">
                                  {s.lesson.title} <span className="text-muted">·</span>{" "}
                                  <span className="font-mono text-[13px]">{s.synthetic_learner_id}</span>
                                </p>
                                <p className="mt-0.5 text-sm text-muted">
                                  {s.answer_turns} answer{s.answer_turns === 1 ? "" : "s"} · started{" "}
                                  {new Date(s.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                                  {s.report_revision ? ` · revision ${s.report_revision}` : ""}
                                </p>
                              </div>
                              <div className="flex shrink-0 items-center gap-2">
                                {s.wellbeing_flags > 0 ? (
                                  <Pill tone="red" icon={<Icon.Flag className="h-3.5 w-3.5" />}>
                                    Follow up
                                  </Pill>
                                ) : null}
                                <Pill tone={badge.tone} icon={badge.icon}>
                                  {badge.label}
                                </Pill>
                                <Icon.ChevronRight className="h-4 w-4 text-faint transition group-hover:translate-x-0.5 group-hover:text-brand-500" />
                              </div>
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </Card>
              </section>
            </div>

            <aside className="space-y-4">
              <Card className="p-5">
                <p className="font-semibold text-ink">Your classroom</p>
                <dl className="mt-4 grid grid-cols-2 gap-3">
                  {[
                    { label: "Sessions", value: stats.total, tone: "text-ink" },
                    { label: "Needs review", value: stats.review, tone: "text-amber-700" },
                    { label: "Approved", value: stats.approved, tone: "text-emerald-700" },
                    { label: "Follow up", value: stats.followUp, tone: "text-rose-700" },
                  ].map((s) => (
                    <div key={s.label} className="rounded-xl bg-row p-3">
                      <dt className="text-xs text-muted">{s.label}</dt>
                      <dd className={`mt-0.5 text-2xl font-semibold ${s.tone}`}>{s.value}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
              <Card className="p-5">
                <p className="font-semibold text-ink">How review works</p>
                <ul className="mt-3 space-y-2.5 text-sm text-muted">
                  <li className="flex gap-2">
                    <Icon.Sparkle className="mt-0.5 h-4 w-4 text-brand-500" />
                    Levels are suggestions backed by exact quotes.
                  </li>
                  <li className="flex gap-2">
                    <Icon.Check className="mt-0.5 h-4 w-4 text-brand-500" />
                    Changing a level needs a short reason.
                  </li>
                  <li className="flex gap-2">
                    <Icon.History className="mt-0.5 h-4 w-4 text-brand-500" />
                    Every decision is kept as a new revision.
                  </li>
                  <li className="flex gap-2">
                    <Icon.Download className="mt-0.5 h-4 w-4 text-brand-500" />
                    Only approved results can be exported.
                  </li>
                </ul>
              </Card>
              <Disclaimer className="px-1" />
              <button type="button" onClick={leave} className="px-1 text-xs text-faint underline hover:text-muted">
                Forget this classroom
              </button>
            </aside>
          </div>
        )}
      </main>
    </AppShell>
  );
}
