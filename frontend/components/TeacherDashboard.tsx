"use client";

// A signed-in teacher's home: the class code to share, and the review board. Every
// check-in a student in this class starts appears here on its own (polled), moving from
// "In progress" to "Needs review" when it ends and to "Reviewed" once the teacher decides.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import { sessionStore } from "@/lib/storage";
import type { LessonSummary, ReportStatus, TeacherSessionItem } from "@/lib/types";

import { ScoreChip } from "./Score";
import { AppShell } from "./shell";
import {
  Button,
  Callout,
  Card,
  Disclaimer,
  Icon,
  PageHeader,
  Pill,
  Spinner,
  Stat,
  NoteCard,
  type Tone,
  cx,
} from "./ui";

const REFRESH_MS = 5000;

export const REPORT_BADGE: Record<ReportStatus, { label: string; tone: Tone; icon: React.ReactNode }> = {
  pending: { label: "In progress", tone: "purple", icon: <Icon.Clock className="h-3.5 w-3.5" /> },
  ready_for_review: { label: "Needs review", tone: "amber", icon: <Icon.Clock className="h-3.5 w-3.5" /> },
  approved: { label: "Approved", tone: "green", icon: <Icon.Check className="h-3.5 w-3.5" /> },
  rejected: { label: "Rejected", tone: "red", icon: <Icon.X className="h-3.5 w-3.5" /> },
};

type Column = { id: "review" | "progress" | "done"; title: React.ReactNode; hint: string; statuses: ReportStatus[] };
const COLUMNS: Column[] = [
  { id: "review", title: "Needs review", hint: "Finished. Waiting for your decision.", statuses: ["ready_for_review"] },
  { id: "progress", title: "In progress", hint: "Students answering right now.", statuses: ["pending"] },
  { id: "done", title: "Reviewed", hint: "Approved or rejected by you.", statuses: ["approved", "rejected"] },
];

export function learnerLabel(s: { learner_name: string | null; synthetic_learner_id: string }) {
  return s.learner_name ?? s.synthetic_learner_id;
}

export function TeacherDashboard() {
  const auth = useRequireRole("teacher");
  const { setUser } = useAuth();
  const token = auth?.token ?? null;
  const user = auth?.user ?? null;
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [sessions, setSessions] = useState<TeacherSessionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);
  const [previewLesson, setPreviewLesson] = useState("");
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    api
      .listLessons()
      .then((list) => {
        setLessons(list);
        if (list.length) setPreviewLesson((current) => current || list[0].id);
      })
      .catch(() => undefined);
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const [list, me] = await Promise.all([api.teacherSessions(token), api.me(token)]);
      setSessions(list);
      setUser(me); // keeps the student count fresh
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load your review queue.");
    }
  }, [token, setUser]);

  useEffect(() => {
    if (!token) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [token, refresh]);

  const stats = useMemo(() => {
    const list = sessions ?? [];
    return {
      total: list.length,
      review: list.filter((s) => s.report_status === "ready_for_review").length,
      approved: list.filter((s) => s.report_status === "approved").length,
      followUp: list.filter((s) => s.wellbeing_flags > 0).length,
    };
  }, [sessions]);

  if (!auth || !user || !token) {
    return (
      <AppShell>
        <p className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-16 text-sm text-muted md:px-8" role="status">
          <Spinner /> Loading…
        </p>
      </AppShell>
    );
  }

  const klass = user.class;
  const code = klass?.join_code ?? "";

  async function copy(kind: "code" | "link") {
    const text = kind === "code" ? code : `${window.location.origin}/register?role=student&code=${code}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      window.prompt("Copy this:", text);
    }
  }

  async function preview() {
    if (!token || !previewLesson) return;
    setLaunching(true);
    try {
      const created = await api.teacherCreateSession(token, previewLesson, "demo-teacher-preview");
      sessionStore.setToken(created.session_id, created.session_token);
      window.open(`/student/${created.session_id}`, "_blank", "noopener");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start a preview.");
    } finally {
      setLaunching(false);
    }
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-7xl px-4 pb-20 pt-10 md:px-8 md:pt-14">
        <div className="grid gap-10 lg:grid-cols-[7fr_5fr] lg:items-start">
          <div>
            <PageHeader
              eyebrow={klass ? `Teacher · ${klass.name}` : "Teacher"}
              title={
                <>
                  Good to see you, <em>{user.display_name}</em>.
                </>
              }
              subtitle="Every check-in your students take arrives here. Read each answer, check the evidence, and make the call."
            />
            <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Check-ins">{stats.total}</Stat>
              <Stat label="Needs review" accent={stats.review > 0}>
                {stats.review}
              </Stat>
              <Stat label="Approved">{stats.approved}</Stat>
              <Stat label="Students">{klass?.student_count ?? 0}</Stat>
            </dl>
          </div>

          {klass ? (
            <NoteCard
              className="lg:mt-6"
              title={
                <>
                  Your class code
                </>
              }
              footer={
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void copy("code")}
                    className="kv-ease inline-flex items-center gap-1.5 rounded-md bg-ink px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#333333]"
                  >
                    <Icon.Copy className="h-4 w-4" /> {copied === "code" ? "Copied" : "Copy code"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void copy("link")}
                    className="kv-ease inline-flex items-center gap-1.5 rounded-md border border-ink px-4 py-2 text-sm font-medium transition-colors hover:bg-ink/10"
                  >
                    {copied === "link" ? "Copied" : "Copy sign-up link"}
                  </button>
                </div>
              }
            >
              <p className="font-mono text-[40px] font-semibold leading-none tracking-[0.2em] text-ink" data-testid="class-code">
                {code}
              </p>
              <p className="mt-3">
                Students enter it when they sign up (or later from their page). Their check-ins then appear on your
                board automatically.
              </p>
            </NoteCard>
          ) : null}
        </div>

        {error ? (
          <div className="mt-8">
            <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
              {error}
            </Callout>
          </div>
        ) : null}

        <section aria-labelledby="board-title" className="mt-14">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <h2 id="board-title" className="text-[34px] leading-none text-ink">
              Review <em>board</em>
            </h2>
            <span className="flex items-center gap-2 text-xs text-faint">
              <span className="relative flex h-2 w-2">
                <span className="kv-pulse absolute inset-0 rounded-full bg-purple" />
                <span className="relative h-2 w-2 rounded-full bg-purple" />
              </span>
              Live · updates every few seconds
            </span>
          </div>

          {sessions === null ? (
            <p className="flex items-center gap-2 text-sm text-muted" role="status">
              <Spinner /> Loading…
            </p>
          ) : (
            <div className="grid gap-5 lg:grid-cols-3">
              {COLUMNS.map((column) => {
                const items = sessions
                  .filter((s) => column.statuses.includes(s.report_status))
                  .sort((a, b) => b.created_at.localeCompare(a.created_at));
                return (
                  <section
                    key={column.id}
                    aria-label={column.id === "review" ? "Needs review" : column.id === "progress" ? "In progress" : "Reviewed"}
                    className={cx(
                      "rounded-xl border p-3",
                      column.id === "review" ? "border-purple/40 bg-lavender-soft" : "border-line bg-surface",
                    )}
                  >
                    <header className="flex items-start justify-between gap-3 px-2 pb-3 pt-2">
                      <div>
                        <h3 className="text-[22px] text-ink">{column.title}</h3>
                        <p className="mt-1.5 text-xs text-faint">{column.hint}</p>
                      </div>
                      <span
                        className={cx(
                          "rounded-md px-2 py-0.5 text-xs font-semibold",
                          column.id === "review" && items.length ? "bg-ink text-white" : "bg-sunken text-muted",
                        )}
                      >
                        {items.length}
                      </span>
                    </header>
                    {items.length === 0 ? (
                      <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-faint">
                        {column.id === "review"
                          ? "Nothing to review yet."
                          : column.id === "progress"
                            ? "No one is answering right now."
                            : "Reviewed check-ins land here."}
                      </p>
                    ) : (
                      <ul className="space-y-2">
                        {items.map((s) => {
                          const badge = REPORT_BADGE[s.report_status];
                          return (
                            <li key={s.session_id}>
                              <Link
                                href={`/teacher/${s.session_id}`}
                                className="kv-ease group block rounded-lg border border-line bg-raised p-4 transition-colors hover:border-purple/40 hover:bg-raised"
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <p className="truncate font-serif text-[20px] leading-tight text-ink">
                                      {learnerLabel(s)}
                                    </p>
                                    <p className="mt-0.5 truncate text-sm text-muted">{s.lesson.title}</p>
                                    {s.score ? (
                                      <div className="mt-2" data-testid="board-score">
                                        <ScoreChip score={s.score} suggested={s.report_status === "ready_for_review"} />
                                      </div>
                                    ) : null}
                                  </div>
                                  <span className="kv-ease flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-muted transition-all group-hover:border-purple group-hover:bg-purple group-hover:text-white">
                                    <Icon.ArrowRight className="h-4 w-4" />
                                  </span>
                                </div>
                                <div className="mt-3 flex flex-wrap items-center gap-2">
                                  <Pill tone={badge.tone} icon={badge.icon}>
                                    {badge.label}
                                  </Pill>
                                  {s.wellbeing_flags > 0 ? (
                                    <Pill tone="red" icon={<Icon.Flag className="h-3.5 w-3.5" />}>
                                      Follow up
                                    </Pill>
                                  ) : null}
                                  <span className="ml-auto text-xs text-faint">
                                    {s.answer_turns} ans ·{" "}
                                    {new Date(s.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                                  </span>
                                </div>
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </section>
                );
              })}
            </div>
          )}
        </section>

        <div className="mt-14 grid gap-5 lg:grid-cols-[1fr_1fr]">
          <Card className="p-6 md:p-7">
            <h3 className="text-[24px] leading-tight text-ink">
              Try it as a <em>student</em>
            </h3>
            <p className="mt-2 text-sm text-muted">
              Open a check-in in a new tab to see what students see. It lands on your board as a demo learner.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {lessons.map((lesson) => (
                <button
                  key={lesson.id}
                  type="button"
                  onClick={() => setPreviewLesson(lesson.id)}
                  aria-pressed={previewLesson === lesson.id}
                  className={cx(
                    "kv-ease rounded-md border px-3 py-1.5 text-sm transition-colors",
                    previewLesson === lesson.id ? "border-ink bg-ink text-white" : "border-line text-muted hover:text-ink",
                  )}
                >
                  {lesson.title}
                </button>
              ))}
              <Button variant="secondary" onClick={() => void preview()} disabled={launching || !previewLesson} className="py-1.5">
                {launching ? <Spinner /> : <Icon.ArrowUpRight className="h-4 w-4" />} Open preview
              </Button>
            </div>
          </Card>
          <Card className="p-6 md:p-7">
            <h3 className="text-[24px] leading-tight text-ink">
              How review <em>works</em>
            </h3>
            <ul className="mt-4 grid gap-3 text-sm text-muted sm:grid-cols-2">
              {[
                { icon: <Icon.Quote className="h-4 w-4" />, text: "Every suggested level is backed by the student's exact words." },
                { icon: <Icon.Check className="h-4 w-4" />, text: "Change any level; a short reason is required." },
                { icon: <Icon.History className="h-4 w-4" />, text: "Each decision is saved as a new revision." },
                { icon: <Icon.Download className="h-4 w-4" />, text: "Only approved results can be exported." },
              ].map((item) => (
                <li key={item.text} className="flex gap-2.5">
                  <span className="mt-0.5 text-purple-ink">{item.icon}</span>
                  {item.text}
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <Disclaimer className="mt-12" />
      </main>
    </AppShell>
  );
}
