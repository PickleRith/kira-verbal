"use client";

// Student text assessment. The server owns all assessment state; this component only
// displays the latest session view and sends finalized answers.
//
// Recovery rules (see docs/api.md):
// - An answer keeps its client_turn_id until the server confirms it, so resending after a
//   network error or a reload is recognised as the same turn and never counted twice.
// - stale_state_version / question_mismatch: someone else moved the session on -> refetch.
// - evaluation_unavailable / claim_lost: the answer was released -> refetch, keep the draft,
//   let the learner resend (same client_turn_id, new expected_state_version).
// - turn_in_progress: retry the same request after a short wait.

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { sessionStore, type PendingTurn } from "@/lib/storage";
import type { SessionView, TurnInput } from "@/lib/types";

import {
  AppShell,
  BrandMark,
  Button,
  ButtonLink,
  Callout,
  Card,
  Disclaimer,
  Icon,
  PageHeader,
  Pill,
  Spinner,
} from "./ui";
import { VoicePanel } from "./VoicePanel";

const HINT_REQUEST = "Can I have a hint?";
const MAX_CHARS = 2000;
const IN_PROGRESS_RETRIES = 5;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function newTurnId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function StudentSession({ sessionId }: { sessionId: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [fatal, setFatal] = useState<"no_access" | string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const answerRef = useRef<HTMLTextAreaElement>(null);

  const refresh = useCallback(
    async (tok: string) => {
      const latest = await api.getSession(sessionId, tok);
      setView(latest);
      return latest;
    },
    [sessionId],
  );

  const safeRefresh = useCallback(async () => {
    if (!token) return;
    try {
      await refresh(token);
    } catch {
      // keep showing the last known state; the notice already explains the problem
    }
  }, [refresh, token]);

  // Initial load / resume.
  useEffect(() => {
    const tok = sessionStore.getToken(sessionId);
    if (!tok) {
      setFatal("no_access");
      return;
    }
    setToken(tok);
    refresh(tok)
      .then((latest) => {
        if (latest.transcript.length > 0) setStarted(true);
        const pending = sessionStore.getPending(sessionId);
        if (pending && latest.prompt?.question_id === pending.questionId) {
          setDraft(pending.transcript);
          setStarted(true);
        } else {
          sessionStore.setPending(sessionId, null);
        }
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.code === "session_not_found") setFatal("no_access");
        else setFatal(e instanceof ApiError ? e.message : "Could not load this assessment.");
      });
  }, [sessionId, refresh]);

  // Move focus to the answer box whenever a new prompt appears.
  const promptKey = view ? `${view.state_version}` : "";
  useEffect(() => {
    if (started && view?.prompt && !busy) answerRef.current?.focus();
  }, [started, promptKey, busy, view?.prompt]);

  async function submitWithRetry(turn: TurnInput) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await api.submitTurn(sessionId, token!, turn);
      } catch (e) {
        if (e instanceof ApiError && e.code === "turn_in_progress" && attempt < IN_PROGRESS_RETRIES) {
          await sleep(1000);
          continue;
        }
        throw e;
      }
    }
  }

  async function send(text: string, { keepDraft = false } = {}) {
    if (!token || !view?.prompt || busy) return;
    const prompt = view.prompt;
    const saved = sessionStore.getPending(sessionId);
    const pending: PendingTurn =
      saved && saved.questionId === prompt.question_id && saved.transcript === text
        ? saved
        : { clientTurnId: newTurnId(), questionId: prompt.question_id, transcript: text };
    sessionStore.setPending(sessionId, pending);

    setBusy(true);
    setNotice(null);
    try {
      await submitWithRetry({
        client_turn_id: pending.clientTurnId,
        expected_state_version: view.state_version,
        transcript: text,
        modality: "text",
        question_id: prompt.question_id,
      });
      sessionStore.setPending(sessionId, null);
      if (!keepDraft) setDraft("");
      await refresh(token);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "unknown_error";
      switch (code) {
        case "network_error":
          setNotice("Couldn't reach the server. Your answer is kept. Press Send to try again.");
          break;
        case "evaluation_unavailable":
        case "claim_lost":
          setNotice("We couldn't process that answer just now. Your answer is kept. Press Send to try again.");
          await safeRefresh();
          break;
        case "stale_state_version":
        case "question_mismatch":
        case "idempotency_mismatch":
          sessionStore.setPending(sessionId, null);
          setNotice("This assessment was updated elsewhere (another tab?). Showing the latest question.");
          await safeRefresh();
          break;
        case "session_closed":
        case "session_expired":
          sessionStore.setPending(sessionId, null);
          await safeRefresh();
          break;
        case "turn_in_progress":
          setNotice("Your previous answer is still being processed. Try again in a moment.");
          break;
        default:
          setNotice(e instanceof Error ? e.message : "Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function finishEarly() {
    if (!token || !view || busy) return;
    if (!window.confirm("Finish now? You won't be able to answer more questions.")) return;
    setBusy(true);
    setNotice(null);
    try {
      setView(await api.finish(sessionId, token, view.state_version));
      sessionStore.setPending(sessionId, null);
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not finish. Please try again.");
      await safeRefresh();
    } finally {
      setBusy(false);
    }
  }

  // --- render ------------------------------------------------------------------------

  if (fatal === "no_access") {
    return (
      <Shell>
        <Card className="mt-6 p-6 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-500">
            <Icon.Shield className="h-6 w-6" />
          </span>
          <p className="mt-3 font-medium text-ink">This assessment isn&apos;t available in this browser</p>
          <p className="mt-1 text-sm text-muted">A demo session can only be resumed in the browser that started it.</p>
          <ButtonLink href="/" variant="secondary" className="mt-4">
            Start a new demo assessment
          </ButtonLink>
        </Card>
      </Shell>
    );
  }
  if (fatal) {
    return (
      <Shell>
        <div className="mt-6">
          <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
            {fatal}
          </Callout>
        </div>
      </Shell>
    );
  }
  if (!view) {
    return (
      <Shell>
        <p className="mt-6 flex items-center gap-2 text-sm text-muted" role="status">
          <Spinner /> Loading assessment…
        </p>
      </Shell>
    );
  }

  const terminal = view.status === "completed" || view.status === "incomplete";
  const answered = view.transcript.length;

  return (
    <Shell title={view.lesson.title} progress={terminal ? undefined : answered}>
      {!started && !terminal ? (
        <Card className="mt-6 overflow-hidden">
          <div className="bg-gradient-to-br from-brand-600 to-brand-800 px-6 py-6 text-white">
            <p className="text-sm text-brand-100">Before you start</p>
            <h2 className="mt-1 text-xl font-semibold">A short conversation about {view.lesson.title}</h2>
          </div>
          <ul className="grid gap-3 p-6 sm:grid-cols-2">
            {[
              { icon: <Icon.Clock className="h-4 w-4" />, text: "A few short questions, about 3–5 minutes. Answer in your own words." },
              { icon: <Icon.Chat className="h-4 w-4" />, text: "Follow-up questions depend on what you say. There are no trick questions." },
              { icon: <Icon.Check className="h-4 w-4" />, text: "Nothing is graded automatically. Your teacher reviews your answers." },
              { icon: <Icon.Lightbulb className="h-4 w-4" />, text: "You can ask for a hint. Your teacher will see that a hint was used." },
              { icon: <Icon.Sparkle className="h-4 w-4" />, text: "Ask to hear a question again or what it means. That doesn’t use up a question." },
              { icon: <Icon.Mic className="h-4 w-4" />, text: "Type your answers, or speak them if your browser allows the microphone." },
            ].map((item) => (
              <li key={item.text} className="flex gap-3 text-sm leading-relaxed text-ink">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  {item.icon}
                </span>
                {item.text}
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
            <p className="text-xs text-muted">You can stop any time with &ldquo;Finish early&rdquo;.</p>
            <Button onClick={() => setStarted(true)}>
              Begin <Icon.ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      ) : null}

      {view.transcript.length > 0 ? (
        <ol className="mt-6 space-y-4" aria-label="Your answers so far">
          {view.transcript.map((entry, index) => (
            <li key={entry.sequence}>
              <AgentBubble>{entry.question_text}</AgentBubble>
              <div className="mt-2 flex flex-col items-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-md bg-gradient-to-br from-brand-500 to-brand-700 px-4 py-2.5 text-[15px] text-white">
                  {entry.answer || <em>(no answer)</em>}
                </div>
                <p className="mt-1 text-xs text-faint">
                  {entry.modality === "voice" ? "Spoken" : "Typed"}
                  {entry.assisted ? " · after a hint" : ""}
                </p>
              </div>
              {/* The newest reply is shown above the current question instead. */}
              {entry.reply && !(index === view.transcript.length - 1 && view.prompt?.lead_in) ? (
                <AgentBubble soft>{entry.reply}</AgentBubble>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {terminal ? <Done view={view} /> : null}

      {started && !terminal && view.status === "evaluating" ? (
        <div className="mt-6">
          <Callout tone="purple" role="status" icon={<Spinner />}>
            Your last answer is still being processed.{" "}
            <button type="button" onClick={safeRefresh} className="font-medium underline underline-offset-2">
              Check again
            </button>
          </Callout>
        </div>
      ) : null}

      {started && !terminal && view.prompt && view.status === "awaiting_answer" ? (
        <section className="mt-6" aria-live="polite">
          {view.prompt.lead_in ? <AgentBubble soft>{view.prompt.lead_in}</AgentBubble> : null}
          <Card className="mt-3 border-brand-200 p-5 ring-4 ring-brand-50">
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-brand-600">
              <Icon.Sparkle className="h-4 w-4" /> Current question
            </p>
            <h2 className="mt-2 text-xl font-semibold leading-snug text-ink">{view.prompt.text}</h2>
          </Card>
        </section>
      ) : null}

      {/* Stays mounted after the session ends so the spoken closing line isn't cut off. */}
      {started && token ? (
        <VoicePanel sessionId={sessionId} token={token} finished={terminal} onActivity={safeRefresh} />
      ) : null}

      {started && !terminal && view.prompt && view.status === "awaiting_answer" ? (
        <form
          className="mt-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) void send(draft.trim());
          }}
        >
          <Card className="p-2 focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
            <label htmlFor="answer" className="sr-only">
              Your answer
            </label>
            <textarea
              id="answer"
              ref={answerRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && draft.trim()) {
                  event.preventDefault();
                  void send(draft.trim());
                }
              }}
              maxLength={MAX_CHARS}
              rows={3}
              disabled={busy}
              placeholder="Type your answer in your own words…"
              className="block w-full resize-none rounded-xl bg-transparent px-3 py-2.5 text-[15px] outline-none placeholder:text-faint focus-visible:outline-none disabled:opacity-60"
            />
            <div className="flex flex-wrap items-center gap-1 border-t border-line px-1 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => void send(HINT_REQUEST, { keepDraft: true })}
                disabled={busy}
                className="px-3 py-2"
              >
                <Icon.Lightbulb className="h-4 w-4" /> Hint
              </Button>
              <Button type="button" variant="ghost" onClick={() => void finishEarly()} disabled={busy} className="px-3 py-2">
                <Icon.Flag className="h-4 w-4" /> Finish early
              </Button>
              <span className="ml-auto mr-2 hidden text-xs text-faint sm:inline">
                {draft.length}/{MAX_CHARS}
              </span>
              <Button type="submit" disabled={busy || !draft.trim()} className="ml-auto px-4 py-2 sm:ml-0">
                {busy ? <Spinner /> : <Icon.Send className="h-4 w-4" />}
                {busy ? "Sending…" : "Send"}
              </Button>
            </div>
          </Card>
          <p className="mt-1.5 text-right text-xs text-faint">Ctrl + Enter to send</p>
        </form>
      ) : null}

      {notice ? (
        <div className="mt-4">
          <Callout tone="amber" role="status" icon={<Icon.Alert className="h-4 w-4" />}>
            {notice}
          </Callout>
        </div>
      ) : null}
    </Shell>
  );
}

function AgentBubble({ children, soft = false }: { children: React.ReactNode; soft?: boolean }) {
  return (
    <div className={soft ? "mt-2 flex gap-2.5" : "flex gap-2.5"}>
      {soft ? <span className="w-8 shrink-0" /> : <BrandMark size="sm" />}
      <div
        className={
          soft
            ? "max-w-[85%] rounded-2xl rounded-tl-md border border-brand-100 bg-brand-50 px-4 py-2 text-sm text-brand-900"
            : "max-w-[85%] rounded-2xl rounded-tl-md border border-line bg-white px-4 py-2.5 text-[15px] text-ink shadow-card"
        }
      >
        {children}
      </div>
    </div>
  );
}

function Done({ view }: { view: SessionView }) {
  const message =
    view.finish_reason === "timeout"
      ? "Time ran out. Your teacher will review the answers you gave and decide your results."
      : view.finish_reason === "learner_exit"
        ? "You finished early. Your teacher will review the answers you gave and decide your results."
        : "That was the last question. Your teacher will review your answers and decide your results.";
  return (
    <Card className="mt-6 p-6 text-center" role="status">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
        <Icon.Check className="h-7 w-7" />
      </span>
      <h2 className="mt-3 text-lg font-semibold text-ink">Assessment finished</h2>
      <p className="mt-1 text-sm text-muted">{message}</p>
      <ButtonLink href="/" variant="secondary" className="mt-4">
        Back to start
      </ButtonLink>
    </Card>
  );
}

function Shell({
  title,
  progress,
  children,
}: {
  title?: string;
  progress?: number;
  children: React.ReactNode;
}) {
  return (
    <AppShell active={null}>
      <main className="mx-auto max-w-3xl px-4 pb-16 pt-8 md:px-8">
        <PageHeader
          eyebrow={
            <span className="flex items-center gap-2">
              <Icon.User className="h-4 w-4" /> Demo learner
            </span>
          }
          title={title ?? "Assessment"}
          actions={
            progress !== undefined && progress > 0 ? (
              <Pill tone="purple">
                {progress} turn{progress === 1 ? "" : "s"} so far
              </Pill>
            ) : undefined
          }
        />
        {children}
        <Disclaimer className="mt-10" />
      </main>
    </AppShell>
  );
}
