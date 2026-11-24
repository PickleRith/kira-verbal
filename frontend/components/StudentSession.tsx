"use client";

// Student check-in (text and optional voice). The server owns all assessment state; this
// component only displays the latest session view and sends finalized answers.
//
// Recovery rules (see docs/api.md):
// - An answer keeps its client_turn_id until the server confirms it, so resending after a
//   network error or a reload is recognised as the same turn and never counted twice.
// - stale_state_version / question_mismatch: someone else moved the session on -> refetch.
// - evaluation_unavailable / claim_lost: the answer was released -> refetch, keep the draft,
//   let the learner resend (same client_turn_id, new expected_state_version).
// - turn_in_progress: retry the same request after a short wait.
// - No session token in this browser: a signed-in student who owns the session gets a
//   fresh one from the server (POST /v1/me/sessions/{id}/resume).

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { sessionStore, type PendingTurn } from "@/lib/storage";
import type { SessionView, TurnInput } from "@/lib/types";

import { FocusShell } from "./shell";
import { BrandMark, Button, ButtonLink, Callout, Card, Disclaimer, Eyebrow, Icon, Pill, Spinner, cx } from "./ui";
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
  const auth = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [fatal, setFatal] = useState<"no_access" | string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState(false);
  const [sending, setSending] = useState<string | null>(null); // answer shown while it is processed
  const [now, setNow] = useState(() => Date.now());
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const homeHref = auth.user?.role === "student" ? "/student" : "/";

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

  // Initial load / resume. Waits for the sign-in check so a student can recover the token.
  useEffect(() => {
    if (!auth.ready) return;
    let cancelled = false;

    async function recover(): Promise<string | null> {
      if (auth.user?.role !== "student" || !auth.token) return null;
      try {
        const fresh = await api.resumeSession(auth.token, sessionId);
        sessionStore.setToken(sessionId, fresh.session_token);
        return fresh.session_token;
      } catch {
        return null;
      }
    }

    async function load() {
      let tok = sessionStore.getToken(sessionId) ?? (await recover());
      if (!tok) return setFatal("no_access");
      let latest: SessionView;
      try {
        latest = await refresh(tok);
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "session_not_found")) {
          return setFatal(e instanceof ApiError ? e.message : "Could not load this assessment.");
        }
        tok = await recover(); // the stored token was replaced (e.g. resumed on another device)
        if (!tok) return setFatal("no_access");
        latest = await refresh(tok);
      }
      if (cancelled) return;
      setToken(tok);
      if (latest.transcript.length > 0) setStarted(true);
      const pending = sessionStore.getPending(sessionId);
      if (pending && latest.prompt?.question_id === pending.questionId) {
        setDraft(pending.transcript);
        setStarted(true);
      } else {
        sessionStore.setPending(sessionId, null);
      }
    }

    load().catch(() => setFatal("Could not load this assessment."));
    return () => {
      cancelled = true;
    };
  }, [sessionId, refresh, auth.ready, auth.user?.role, auth.token]);

  // Move focus to the answer box whenever a new prompt appears.
  const promptKey = view ? `${view.state_version}` : "";
  useEffect(() => {
    if (started && view?.prompt && !busy) answerRef.current?.focus();
  }, [started, promptKey, busy, view?.prompt]);

  // Keep the newest message in view, like a chat.
  useEffect(() => {
    if (started) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [started, promptKey, sending]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

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
    setSending(text);
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
      setSending(null);
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
        <Card className="mt-8 p-8 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-raised text-purple-ink">
            <Icon.Shield className="h-6 w-6" />
          </span>
          <p className="mt-4 font-serif text-[24px] text-ink">This check-in isn&apos;t available here</p>
          <p className="mt-1 text-sm text-muted">
            Log in with the student account that started it, or start a new one.
          </p>
          <ButtonLink href={auth.user ? homeFor(auth.user.role) : "/login"} variant="secondary" className="mt-5">
            {auth.user ? "Back to my page" : "Log in"}
          </ButtonLink>
        </Card>
      </Shell>
    );
  }
  if (fatal) {
    return (
      <Shell>
        <div className="mt-8">
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
        <p className="mt-8 flex items-center gap-2 text-sm text-muted" role="status">
          <Spinner /> Loading check-in…
        </p>
      </Shell>
    );
  }

  const terminal = view.status === "completed" || view.status === "incomplete";
  const minutesLeft = Math.ceil((new Date(view.deadline_at).getTime() - now) / 60_000);
  const showComposer = started && !terminal && view.prompt && view.status === "awaiting_answer";

  return (
    <Shell title={view.lesson.title} minutesLeft={started && !terminal ? minutesLeft : undefined}>
      {!started && !terminal ? (
        <Card className="kv-rise mt-8 overflow-hidden">
          <div className="relative overflow-hidden bg-raised px-6 py-8 md:px-8">
            <Eyebrow>Before you start</Eyebrow>
            <h2 className="mt-3 max-w-lg text-[34px] leading-tight text-ink">
              A short conversation about <em>{view.lesson.title}</em>
            </h2>
            <span className="absolute -right-10 -top-10 h-40 w-40 rounded-full border border-purple/40" aria-hidden="true" />
            <span className="absolute -right-2 top-6 h-24 w-24 rounded-full border border-purple/40" aria-hidden="true" />
          </div>
          <div className=" -mt-2 bg-surface">
            <ul className="grid gap-4 p-6 pt-8 sm:grid-cols-2 md:p-8">
              {[
                { icon: <Icon.Clock className="h-4 w-4" />, text: "A few short questions, about 3–5 minutes. Answer in your own words." },
                { icon: <Icon.Chat className="h-4 w-4" />, text: "Follow-up questions depend on what you say. There are no trick questions." },
                { icon: <Icon.Check className="h-4 w-4" />, text: "Nothing is graded automatically. Your teacher reviews your answers." },
                { icon: <Icon.Lightbulb className="h-4 w-4" />, text: "You can ask for a hint. Your teacher will see that a hint was used." },
                { icon: <Icon.Sparkle className="h-4 w-4" />, text: "Ask to hear a question again or what it means. That doesn’t use up a question." },
                { icon: <Icon.Mic className="h-4 w-4" />, text: "Type your answers, or speak them and watch your voice on screen." },
              ].map((item) => (
                <li key={item.text} className="flex gap-3 text-[15px] leading-relaxed text-ink/90">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-purple-ink">
                    {item.icon}
                  </span>
                  {item.text}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-5 md:px-8">
              <p className="text-xs text-muted">You can stop any time with &ldquo;Finish early&rdquo;.</p>
              <Button onClick={() => setStarted(true)}>
                Begin <Icon.ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      {view.transcript.length > 0 ? (
        <ol className="mt-8 space-y-5" aria-label="Your answers so far">
          {view.transcript.map((entry, index) => (
            <li key={entry.sequence}>
              <AgentBubble>{entry.question_text}</AgentBubble>
              <div className="mt-2 flex flex-col items-end">
                <UserBubble>{entry.answer || <em>(no answer)</em>}</UserBubble>
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

      {sending !== null && view.prompt ? (
        <div className="mt-5" aria-live="polite">
          <AgentBubble>{view.prompt.text}</AgentBubble>
          <div className="mt-2 flex justify-end">
            <UserBubble className="opacity-85">{sending}</UserBubble>
          </div>
          <div className="mt-3 flex gap-2.5" role="status" aria-label="Thinking">
            <BrandMark size="sm" />
            <div className="flex items-center gap-1 rounded-lg rounded-tl-md border border-line bg-surface px-4 py-3">
              <span className="kv-dot" />
              <span className="kv-dot" style={{ animationDelay: "150ms" }} />
              <span className="kv-dot" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        </div>
      ) : null}

      {terminal ? <Done view={view} homeHref={homeHref} /> : null}

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

      {showComposer && view.prompt && sending === null ? (
        <section className="mt-8" aria-live="polite">
          {view.prompt.lead_in ? <AgentBubble soft>{view.prompt.lead_in}</AgentBubble> : null}
          <div className="kv-rise relative mt-4 overflow-hidden rounded-xl border border-purple/40 bg-surface p-6 md:p-7">
            <span className="absolute inset-y-0 left-0 w-1 bg-purple" aria-hidden="true" />
            <div className="flex items-center justify-between gap-3">
              <Eyebrow>Current question</Eyebrow>
              {view.prompt.purpose !== "open" ? (
                <span className="text-xs text-faint">Follow-up</span>
              ) : null}
            </div>
            <h2 className="mt-3 text-[28px] leading-snug text-ink md:text-[32px]">{view.prompt.text}</h2>
          </div>
        </section>
      ) : null}

      {/* Stays mounted after the session ends so the spoken closing line isn't cut off. */}
      {started && token ? (
        <VoicePanel sessionId={sessionId} token={token} finished={terminal} onActivity={safeRefresh} />
      ) : null}

      {showComposer && view.prompt && sending === null ? (
        <form
          className="mt-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) void send(draft.trim());
          }}
        >
          <div className="kv-ease rounded-xl border border-line bg-surface p-2 transition-colors focus-within:border-purple/40">
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
              className="block w-full resize-none rounded-lg bg-transparent px-4 py-3 text-[17px] leading-relaxed text-ink outline-none placeholder:text-faint focus-visible:outline-none disabled:opacity-60"
            />
            <div className="flex flex-wrap items-center gap-1 border-t border-line px-1 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => void send(HINT_REQUEST, { keepDraft: true })}
                disabled={busy}
                className="px-3.5 py-2"
              >
                <Icon.Lightbulb className="h-4 w-4" /> Hint
              </Button>
              <Button type="button" variant="ghost" onClick={() => void finishEarly()} disabled={busy} className="px-3.5 py-2">
                <Icon.Flag className="h-4 w-4" /> Finish early
              </Button>
              <span className="ml-auto mr-2 hidden font-mono text-xs text-faint sm:inline">
                {draft.length}/{MAX_CHARS}
              </span>
              <Button type="submit" disabled={busy || !draft.trim()} className="ml-auto px-5 py-2 sm:ml-0">
                {busy ? <Spinner /> : <Icon.Send className="h-4 w-4" />}
                {busy ? "Sending…" : "Send"}
              </Button>
            </div>
          </div>
          <p className="mt-2 text-right text-xs text-faint">Ctrl + Enter to send</p>
        </form>
      ) : null}

      {notice ? (
        <div className="mt-4">
          <Callout tone="amber" role="status" icon={<Icon.Alert className="h-4 w-4" />}>
            {notice}
          </Callout>
        </div>
      ) : null}
      <div ref={endRef} className="h-px scroll-mb-8" />
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
            ? "max-w-[85%] rounded-lg rounded-tl-md border border-line bg-raised px-4 py-2.5 font-serif text-[17px] italic text-ink/85"
            : "max-w-[85%] rounded-lg rounded-tl-md border border-line bg-surface px-4 py-3 text-[16px] leading-relaxed text-ink"
        }
      >
        {children}
      </div>
    </div>
  );
}

function UserBubble({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        "max-w-[85%] whitespace-pre-wrap rounded-lg rounded-tr-sm border border-purple/30 bg-lavender-soft px-4 py-3 text-[16px] text-ink",
        className,
      )}
    >
      {children}
    </div>
  );
}

function Done({ view, homeHref }: { view: SessionView; homeHref: string }) {
  const message =
    view.finish_reason === "timeout"
      ? "Time ran out. Your teacher will review the answers you gave and decide your results."
      : view.finish_reason === "learner_exit"
        ? "You finished early. Your teacher will review the answers you gave and decide your results."
        : "That was the last question. Your teacher will review your answers and decide your results.";
  return (
    <div className="kv-rise mt-10 rounded-xl border border-ink bg-mint p-8 text-ink md:p-10" role="status">
      <span className="flex h-11 w-11 items-center justify-center rounded-md bg-ink text-white">
        <Icon.Check className="h-6 w-6" />
      </span>
      <h2 className="mt-5 text-[36px] text-ink">Check-in finished.</h2>
      <p className="mt-2 max-w-lg text-base text-ink/80">{message}</p>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-ink/20 pt-5">
        <p className="text-sm text-ink/80">Nothing was graded automatically.</p>
        <ButtonLink href={homeHref} variant="primary">
          {homeHref === "/student" ? "Back to my check-ins" : "Back to start"} <Icon.ArrowRight className="h-4 w-4" />
        </ButtonLink>
      </div>
    </div>
  );
}

function Shell({
  title,
  minutesLeft,
  children,
}: {
  title?: string;
  minutesLeft?: number;
  children: React.ReactNode;
}) {
  return (
    <FocusShell
      label={title ? `Check-in · ${title}` : "Check-in"}
      right={
        minutesLeft !== undefined ? (
          <Pill tone={minutesLeft <= 1 ? "amber" : "gray"} icon={<Icon.Clock className="h-3.5 w-3.5" />}>
            {minutesLeft <= 0 ? "Time is up" : minutesLeft === 1 ? "Under a minute left" : `About ${minutesLeft} min left`}
          </Pill>
        ) : undefined
      }
    >
      <main className="mx-auto max-w-3xl px-4 pb-20 pt-10 md:px-8">
        <Eyebrow>Oral check-in</Eyebrow>
        <h1 className="mt-3 text-[44px] leading-[1.05] text-ink md:text-[52px]">{title ?? "Check-in"}</h1>
        {children}
        <Disclaimer className="mt-14" />
      </main>
    </FocusShell>
  );
}
