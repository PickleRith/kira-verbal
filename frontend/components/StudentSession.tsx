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

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { sessionStore, type PendingTurn } from "@/lib/storage";
import type { SessionView, TurnInput } from "@/lib/types";

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
        <p className="mt-6">
          This assessment isn&apos;t available in this browser. A demo session can only be resumed
          in the browser that started it.
        </p>
        <Link href="/" className="mt-4 inline-block underline">
          Start a new demo assessment
        </Link>
      </Shell>
    );
  }
  if (fatal) {
    return (
      <Shell>
        <p role="alert" className="mt-6 text-red-800">{fatal}</p>
      </Shell>
    );
  }
  if (!view) {
    return (
      <Shell>
        <p className="mt-6 text-gray-600" role="status">Loading assessment…</p>
      </Shell>
    );
  }

  const terminal = view.status === "completed" || view.status === "incomplete";

  return (
    <Shell title={view.lesson.title}>
      {!started && !terminal ? (
        <section className="mt-6 rounded-md border border-gray-200 p-5">
          <h2 className="text-lg font-semibold">What to expect</h2>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-relaxed">
            <li>A few short questions, about 3–5 minutes. Answer in your own words.</li>
            <li>Follow-up questions depend on what you say. There are no trick questions.</li>
            <li>Nothing is graded automatically. Your teacher reviews your answers.</li>
            <li>You can ask for a hint. Your teacher will see that a hint was used.</li>
            <li>
              You can ask to hear a question again or ask what it means. That doesn&rsquo;t use up a
              question.
            </li>
            <li>You can stop at any time with &ldquo;Finish early&rdquo;.</li>
          </ul>
          <p className="mt-3 text-sm text-gray-600">
            You can answer by typing or, if your browser allows the microphone, by voice.
          </p>
          <button
            type="button"
            onClick={() => setStarted(true)}
            className="mt-4 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
          >
            Begin
          </button>
        </section>
      ) : null}

      {view.transcript.length > 0 ? (
        <ol className="mt-6 space-y-4" aria-label="Your answers so far">
          {view.transcript.map((entry, index) => (
            <li key={entry.sequence} className="rounded-md bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-700">{entry.question_text}</p>
              <p className="mt-1 whitespace-pre-wrap">{entry.answer || <em>(no answer)</em>}</p>
              {entry.assisted ? (
                <p className="mt-1 text-xs text-gray-500">Answered after a hint</p>
              ) : null}
              {/* The newest reply is shown above the current question instead. */}
              {entry.reply && !(index === view.transcript.length - 1 && view.prompt?.lead_in) ? (
                <p className="mt-2 border-l-2 border-blue-200 pl-3 text-sm text-blue-900">
                  {entry.reply}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {terminal ? <Done view={view} /> : null}

      {started && !terminal && view.status === "evaluating" ? (
        <div className="mt-6" role="status">
          <p>Your last answer is still being processed.</p>
          <button type="button" onClick={safeRefresh} className="mt-2 underline">
            Check again
          </button>
        </div>
      ) : null}

      {started && !terminal && token ? (
        <VoicePanel sessionId={sessionId} token={token} onActivity={safeRefresh} />
      ) : null}

      {started && !terminal && view.prompt && view.status === "awaiting_answer" ? (
        <section className="mt-6" aria-live="polite">
          {view.prompt.lead_in ? (
            <p className="mb-2 rounded-md bg-blue-50 p-3 text-sm text-blue-900">{view.prompt.lead_in}</p>
          ) : null}
          <h2 className="text-lg font-semibold">{view.prompt.text}</h2>

          <form
            className="mt-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (draft.trim()) void send(draft.trim());
            }}
          >
            <label htmlFor="answer" className="text-sm font-medium">
              Your answer
            </label>
            <textarea
              id="answer"
              ref={answerRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={MAX_CHARS}
              rows={4}
              disabled={busy}
              className="mt-1 block w-full rounded-md border border-gray-300 p-3 disabled:bg-gray-100"
            />
            <p className="mt-1 text-right text-xs text-gray-500">
              {draft.length}/{MAX_CHARS}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "Sending…" : "Send"}
              </button>
              <button
                type="button"
                onClick={() => void send(HINT_REQUEST, { keepDraft: true })}
                disabled={busy}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm disabled:opacity-50"
              >
                Ask for a hint
              </button>
              <button
                type="button"
                onClick={() => void finishEarly()}
                disabled={busy}
                className="ml-auto rounded-md px-4 py-2 text-sm text-gray-700 underline disabled:opacity-50"
              >
                Finish early
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {notice ? (
        <p role="status" className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {notice}
        </p>
      ) : null}
    </Shell>
  );
}

function Done({ view }: { view: SessionView }) {
  const message =
    view.finish_reason === "timeout"
      ? "Time ran out for this assessment. Your teacher can see the answers you gave."
      : view.finish_reason === "learner_exit"
        ? "You finished early. Your teacher can see the answers you gave."
        : "Thanks, you're done. Your teacher will review your answers.";
  return (
    <section className="mt-6 rounded-md border border-green-300 bg-green-50 p-5" role="status">
      <h2 className="text-lg font-semibold text-green-900">Assessment finished</h2>
      <p className="mt-1 text-green-900">{message}</p>
      <Link href="/" className="mt-3 inline-block text-sm underline">
        Back to start
      </Link>
    </section>
  );
}

function Shell({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <p className="text-sm text-gray-500">
        <Link href="/" className="underline">Kira Verbal</Link> · demo learner
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{title ?? "Assessment"}</h1>
      {children}
    </main>
  );
}
