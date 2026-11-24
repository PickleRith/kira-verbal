"use client";

// Demo entry point: pick a synthetic lesson and start an anonymous learner session.
// Sessions started here belong to no teacher workspace; use /teacher to launch reviewable ones.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { sessionStore } from "@/lib/storage";
import type { LessonSummary } from "@/lib/types";

import { Button, Callout, Icon, Spinner } from "./ui";

const LESSON_TINT = ["bg-emerald-50 text-emerald-600", "bg-amber-50 text-amber-600", "bg-sky-50 text-sky-600"];

export function LessonPicker() {
  const router = useRouter();
  const [lessons, setLessons] = useState<LessonSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    api
      .listLessons()
      .then(setLessons)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load lessons."),
      );
  }, []);

  async function start(lessonId: string) {
    setStarting(lessonId);
    setError(null);
    try {
      const session = await api.createSession(lessonId);
      sessionStore.setToken(session.id, session.session_token);
      router.push(`/student/${session.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the assessment.");
      setStarting(null);
    }
  }

  if (error) {
    return (
      <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />} title="Can't load lessons">
        {error} Is the API running on port 8000, and has <code>python -m app.seed</code> been run?
      </Callout>
    );
  }
  if (lessons === null) {
    return (
      <p className="flex items-center gap-2 p-3 text-sm text-muted" role="status">
        <Spinner /> Loading lessons…
      </p>
    );
  }
  if (lessons.length === 0) {
    return (
      <p className="p-3 text-sm text-muted">
        No lessons published yet. Run <code>python -m app.seed</code>.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {lessons.map((lesson, i) => (
        <li
          key={lesson.id}
          className="flex items-center justify-between gap-4 rounded-xl bg-row px-4 py-3"
        >
          <div className="flex min-w-0 items-center gap-3">
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${LESSON_TINT[i % LESSON_TINT.length]}`}
            >
              <Icon.Book className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">{lesson.title}</p>
              <p className="text-sm text-muted">
                {lesson.objective_count} objectives · version {lesson.version}
              </p>
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={() => void start(lesson.id)}
            disabled={starting !== null}
            className="shrink-0"
          >
            {starting === lesson.id ? <Spinner /> : <Icon.ArrowRight className="h-4 w-4" />}
            {starting === lesson.id ? "Starting…" : "Start"}
          </Button>
        </li>
      ))}
    </ul>
  );
}
