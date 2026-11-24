"use client";

// A signed-in student's home: their class, lessons to start, and their past check-ins.
// Starting a lesson creates the session in the student's class, so it appears in the
// teacher's review queue straight away. Results stay with the teacher; the student sees
// only whether their check-in has been reviewed.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import { sessionStore } from "@/lib/storage";
import type { LessonSummary, ReviewStatus, StudentSessionItem } from "@/lib/types";

import { LessonArt } from "./LessonArt";
import { CriterionResults, ScoreChip, ScoreSummary } from "./Score";
import { AppShell } from "./shell";
import {
  Button,
  MediaLabel,
  Callout,
  Card,
  Disclaimer,
  Eyebrow,
  Field,
  Icon,
  PageHeader,
  Pill,
  SectionHeader,
  Spinner,
  type Tone,
} from "./ui";

const REVIEW_BADGE: Record<ReviewStatus, { label: string; tone: Tone }> = {
  in_progress: { label: "In progress", tone: "purple" },
  awaiting_review: { label: "Waiting for your teacher", tone: "amber" },
  reviewed: { label: "Reviewed", tone: "green" },
};
const REFRESH_MS = 8000;

export function StudentHome() {
  const auth = useRequireRole("student");
  const { setUser } = useAuth();
  const router = useRouter();
  const [lessons, setLessons] = useState<LessonSummary[] | null>(null);
  const [sessions, setSessions] = useState<StudentSessionItem[] | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openResult, setOpenResult] = useState<string | null>(null);

  const token = auth?.token ?? null;
  const user = auth?.user ?? null;

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setSessions(await api.mySessions(token));
    } catch {
      // keep the last list; a banner would be noise for a background refresh
    }
  }, [token]);

  useEffect(() => {
    api
      .listLessons()
      .then(setLessons)
      .catch(() => setError("Could not load lessons. Is the API running on port 8000?"));
  }, []);

  useEffect(() => {
    if (!token) return;
    void refresh();
    const id = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [token, refresh]);

  if (!auth || !user || !token) {
    return (
      <AppShell>
        <p className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-16 text-sm text-muted md:px-8" role="status">
          <Spinner /> Loading…
        </p>
      </AppShell>
    );
  }

  async function join(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy("join");
    setError(null);
    try {
      setUser(await api.joinClass(token, code));
      setCode("");
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "class_not_found"
          ? "No class has that code. Check it with your teacher."
          : e instanceof ApiError
            ? e.message
            : "Could not join the class.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function start(lessonId: string) {
    if (!token) return;
    setBusy(lessonId);
    setError(null);
    try {
      const created = await api.startLesson(token, lessonId);
      sessionStore.setToken(created.id, created.session_token);
      router.push(`/student/${created.id}`);
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "no_class"
          ? "Join your teacher's class first, using the code they shared."
          : e instanceof ApiError
            ? e.message
            : "Could not start the lesson.",
      );
      setBusy(null);
    }
  }

  function resume(sessionId: string) {
    // The check-in page recovers the session token itself if this browser doesn't hold it.
    setBusy(sessionId);
    router.push(`/student/${sessionId}`);
  }

  const klass = user.class;
  const inProgress = sessions?.filter((s) => s.review_status === "in_progress") ?? [];
  const done = sessions?.filter((s) => s.review_status !== "in_progress") ?? [];

  return (
    <AppShell>
      <main className="mx-auto max-w-6xl px-4 pb-20 pt-10 md:px-8 md:pt-14">
        <PageHeader
          eyebrow="Student"
          title={
            <>
              Hello, <em>{user.display_name}</em>.
            </>
          }
          subtitle={
            klass ? (
              <>
                You&rsquo;re in <span className="text-ink">{klass.name}</span>
                {klass.teacher_name ? (
                  <>
                    {" "}
                    with <span className="text-ink">{klass.teacher_name}</span>
                  </>
                ) : null}
                . Pick a lesson and explain it in your own words.
              </>
            ) : (
              "Join your teacher's class to start a check-in."
            )
          }
        />

        {error ? (
          <div className="mt-6">
            <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
              {error}
            </Callout>
          </div>
        ) : null}

        {!klass ? (
          <Card className="mt-8 grid gap-6 p-6 md:grid-cols-[1fr_auto] md:items-end md:p-8">
            <div>
              <h2 className="text-[28px] leading-tight text-ink">
                Join a <em>class</em>
              </h2>
              <p className="mt-2 max-w-md text-sm text-muted">
                Ask your teacher for their six-character class code. Your check-ins then go straight to them.
              </p>
            </div>
            <form onSubmit={join} className="flex flex-wrap items-end gap-3">
              <Field
                label="Class code"
                name="join_code"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="K7Q4MZ"
                maxLength={16}
                autoComplete="off"
                required
                icon={<Icon.Key className="h-4 w-4" />}
                className="w-56"
              />
              <Button type="submit" disabled={busy === "join" || code.trim().length < 4}>
                {busy === "join" ? <Spinner /> : <Icon.ArrowRight className="h-4 w-4" />} Join
              </Button>
            </form>
          </Card>
        ) : null}

        {inProgress.length ? (
          <section className="mt-10">
            <Callout tone="purple" icon={<Icon.Clock className="h-4 w-4" />} title="You have a check-in in progress">
              <div className="mt-2 flex flex-wrap gap-2">
                {inProgress.map((s) => (
                  <Button key={s.session_id} onClick={() => void resume(s.session_id)} disabled={busy !== null} className="py-2">
                    {busy === s.session_id ? <Spinner /> : <Icon.ArrowRight className="h-4 w-4" />}
                    Continue {s.lesson.title}
                  </Button>
                ))}
              </div>
            </Callout>
          </section>
        ) : null}

        <section aria-labelledby="lessons-title" className="mt-12">
          <SectionHeader
            id="lessons-title"
            title={
              <>
                Lessons <em className="text-purple-ink">to explain</em>
              </>
            }
          />
          {lessons === null ? (
            <p className="flex items-center gap-2 text-sm text-muted" role="status">
              <Spinner /> Loading lessons…
            </p>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {lessons.map((lesson, i) => (
                <li key={lesson.id}>
                  <button
                    type="button"
                    onClick={() => void start(lesson.id)}
                    disabled={!klass || busy !== null}
                    className="kv-ease group block w-full overflow-hidden rounded-xl border border-line bg-surface text-left transition-colors enabled:hover:border-ink disabled:cursor-not-allowed disabled:opacity-60"
                    aria-label={`Start ${lesson.title}`}
                  >
                    <span className="relative block aspect-[3/2] border-b border-line">
                      <LessonArt index={i} />
                      <MediaLabel className="absolute left-3 top-3">
                        {lesson.objective_count} objectives
                      </MediaLabel>
                    </span>
                    <span className="flex items-center justify-between gap-3 p-4">
                      <span>
                        <span className="block font-serif text-[22px] text-ink">{lesson.title}</span>
                        <span className="block text-sm text-muted">3–5 minutes · speak or type</span>
                      </span>
                      <span className="flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-ink px-3 text-sm font-medium text-white">
                        {busy === lesson.id ? <Spinner /> : null} Start
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="history-title" className="mt-24">
          <SectionHeader id="history-title" title="Your check-ins" count={sessions?.length} />
          <Card className="p-2">
            {sessions === null ? (
              <p className="flex items-center gap-2 p-4 text-sm text-muted" role="status">
                <Spinner /> Loading…
              </p>
            ) : sessions.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <p className="font-serif text-[22px] italic text-ink">Nothing yet.</p>
                <p className="mt-1 text-sm text-muted">Your finished check-ins will appear here.</p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {[...inProgress, ...done].map((s) => {
                  const badge = REVIEW_BADGE[s.review_status];
                  const expanded = s.result !== null && openResult === s.session_id;
                  return (
                    <li key={s.session_id} className="px-4 py-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-serif text-[20px] text-ink">{s.lesson.title}</p>
                          <p className="mt-0.5 text-sm text-muted">
                            {new Date(s.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} ·{" "}
                            {s.answers} answer{s.answers === 1 ? "" : "s"}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-3">
                          {s.result ? (
                            <>
                              <ScoreChip score={s.result.score} />
                              <Button
                                variant={expanded ? "secondary" : "ai"}
                                onClick={() => setOpenResult(expanded ? null : s.session_id)}
                                aria-expanded={expanded}
                                className="py-1.5"
                              >
                                {expanded ? "Hide results" : "See results"}
                              </Button>
                            </>
                          ) : (
                            <Pill tone={badge.tone}>
                              {s.review_status === "reviewed" ? "Reviewed · not graded" : badge.label}
                            </Pill>
                          )}
                          {s.review_status === "in_progress" ? (
                            <Button
                              variant="secondary"
                              onClick={() => void resume(s.session_id)}
                              disabled={busy !== null}
                              className="py-1.5"
                            >
                              Continue
                            </Button>
                          ) : null}
                        </div>
                      </div>
                      {expanded && s.result ? (
                        <div className="kv-rise mt-5 grid gap-8 rounded-xl border border-line bg-raised p-5 md:grid-cols-[auto_1fr] md:p-7">
                          <div>
                            <ScoreSummary
                              score={s.result.score}
                              title={`Graded by your teacher · ${new Date(s.result.approved_at).toLocaleDateString([], { dateStyle: "medium" })}`}
                            />
                          </div>
                          <CriterionResults criteria={s.result.criteria} />
                        </div>
                      ) : null}
                      {s.review_status === "reviewed" && !s.result ? (
                        <p className="mt-2 text-xs text-faint">Your teacher reviewed this check-in without a grade. Ask them about it.</p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <p className="mt-3 text-xs text-faint">
            Your teacher reviews every check-in and decides your grade. Scores appear here once they approve it:
            each rubric criterion is worth 3 points, and the grade band comes from the percentage of points.
          </p>
        </section>

        <div className="mt-16 flex items-center justify-between gap-4 border-t border-line pt-6">
          <Eyebrow>Synthetic data only</Eyebrow>
          <Disclaimer className="max-w-xl" />
        </div>
      </main>
    </AppShell>
  );
}
