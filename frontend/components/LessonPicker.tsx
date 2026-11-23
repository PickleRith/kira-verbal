"use client";

// Demo entry point: pick a synthetic lesson and start a text assessment.
// (On Day 5 the teacher dashboard becomes the place sessions are launched from.)

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { sessionStore } from "@/lib/storage";
import type { LessonSummary } from "@/lib/types";

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
      <p role="alert" className="mt-8 rounded-md border border-red-300 bg-red-50 p-4 text-sm text-red-900">
        {error} Is the API running on port 8000, and has <code>python -m app.seed</code> been run?
      </p>
    );
  }
  if (lessons === null) return <p className="mt-8 text-sm text-gray-600">Loading lessons…</p>;
  if (lessons.length === 0) {
    return <p className="mt-8 text-sm">No lessons published yet. Run <code>python -m app.seed</code>.</p>;
  }

  return (
    <ul className="mt-8 space-y-3">
      {lessons.map((lesson) => (
        <li
          key={lesson.id}
          className="flex items-center justify-between gap-4 rounded-md border border-gray-200 p-4"
        >
          <div>
            <p className="font-medium">{lesson.title}</p>
            <p className="text-sm text-gray-600">
              {lesson.objective_count} objectives · version {lesson.version}
            </p>
          </div>
          <button
            type="button"
            onClick={() => start(lesson.id)}
            disabled={starting !== null}
            className="shrink-0 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {starting === lesson.id ? "Starting…" : "Start as demo learner"}
          </button>
        </li>
      ))}
    </ul>
  );
}
