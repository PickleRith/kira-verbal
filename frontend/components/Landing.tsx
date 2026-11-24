"use client";

// Landing page pieces that depend on the browser: auth-aware calls to action, the tabs,
// and the lesson showcase (lessons come from the API).

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import type { LessonSummary } from "@/lib/types";

import { FolderTabs } from "./FolderTabs";
import { LessonArt } from "./LessonArt";
import { ButtonLink, Icon } from "./ui";

export function HeroActions() {
  const { user, ready } = useAuth();
  if (ready && user) {
    return (
      <ButtonLink href={homeFor(user.role)} className="px-5 py-3 text-[15px]">
        {user.role === "teacher" ? "Open review queue" : "Go to my check-ins"} <Icon.ArrowRight className="h-4 w-4" />
      </ButtonLink>
    );
  }
  return (
    <div className="flex flex-wrap justify-center gap-3">
      <ButtonLink href="/register?role=teacher" className="px-5 py-3 text-[15px]">
        Start as a teacher
      </ButtonLink>
      <ButtonLink href="/register?role=student" variant="secondary" className="px-5 py-3 text-[15px]">
        Join a class
      </ButtonLink>
    </div>
  );
}

const HOW: Record<string, { title: string; steps: { title: string; body: string }[] }> = {
  students: {
    title: "Explain it out loud, in your own words.",
    steps: [
      { title: "Join your class", body: "Sign up and enter the six-character code your teacher shares." },
      { title: "Pick a lesson", body: "A few short questions, about three to five minutes. Speak or type." },
      { title: "Think aloud", body: "Ask for a hint, what a question means, or to hear it again. Follow-ups depend on what you say." },
    ],
  },
  teachers: {
    title: "Every answer, with the evidence behind it.",
    steps: [
      { title: "Share a code", body: "Your account comes with a class. Students who join it appear in your review queue." },
      { title: "Read each answer", body: "Question by question, with the student's exact words and the quote behind each suggested level." },
      { title: "Make the call", body: "Approve, change a level with a reason, or reject. The student sees their grade only after you approve." },
    ],
  },
  engine: {
    title: "The model proposes; code decides.",
    steps: [
      { title: "Grounded evidence", body: "Claude proposes a level and an exact quote. Code checks the quote against the transcript before it counts." },
      { title: "Deterministic policy", body: "Which question comes next, and when to stop, is fixed code. Unknown stays unknown, never zero." },
      { title: "Safe to retry", body: "Every answer has an id. Double clicks, reloads and two tabs can't save a turn twice." },
    ],
  },
};

export function HowItWorks() {
  const [tab, setTab] = useState("students");
  const content = HOW[tab];
  return (
    <FolderTabs
      active={tab}
      onChange={setTab}
      tabs={[
        { id: "students", label: "For students" },
        { id: "teachers", label: "For teachers" },
        { id: "engine", label: "Under the hood" },
      ]}
    >
      <div className="grid gap-6 md:grid-cols-[1fr_2fr] md:gap-10">
        <h3 className="text-[28px] text-ink md:text-[32px]">{content.title}</h3>
        <ol className="grid gap-3 sm:grid-cols-3">
          {content.steps.map((step, i) => (
            <li key={`${tab}-${step.title}`} className="rounded-lg border border-line bg-raised p-4">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-ink text-xs font-semibold text-white">
                {i + 1}
              </span>
              <p className="mt-4 font-medium text-ink">{step.title}</p>
              <p className="mt-1 text-sm text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </FolderTabs>
  );
}

export function LessonShowcase() {
  const { user } = useAuth();
  const [lessons, setLessons] = useState<LessonSummary[] | null>(null);
  useEffect(() => {
    api
      .listLessons()
      .then(setLessons)
      .catch(() => setLessons([]));
  }, []);
  const href = user ? homeFor(user.role) : "/register?role=student";

  if (lessons === null) return <div className="h-[260px]" aria-hidden="true" />;
  if (lessons.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-line-strong p-8 text-center text-sm text-muted">
        Lessons appear here once the API is running and seeded (<code>python -m app.seed</code>).
      </p>
    );
  }
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {lessons.map((lesson, i) => (
        <li key={lesson.id}>
          <Link
            href={href}
            className="kv-ease group block overflow-hidden rounded-xl border border-line bg-surface transition-colors hover:border-ink"
          >
            <div className="aspect-[3/2] border-b border-line">
              <LessonArt index={i} />
            </div>
            <div className="flex items-center justify-between gap-3 p-4">
              <div>
                <p className="font-serif text-[22px] text-ink">{lesson.title}</p>
                <p className="text-sm text-muted">{lesson.objective_count} objectives · 3–5 minutes</p>
              </div>
              <Icon.ArrowRight className="h-5 w-5 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
