"use client";

// Teacher review of one session: transcript-backed evidence per rubric criterion,
// editable levels (with a reason when changed), approve / reject, export, audit trail.

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { teacherStore } from "@/lib/storage";
import type { CriterionReport, ExportEntry, ReportView, TeacherTranscriptTurn } from "@/lib/types";

import { REPORT_BADGE } from "./TeacherDashboard";
import {
  AppShell,
  BrandMark,
  Button,
  ButtonLink,
  Callout,
  Card,
  Icon,
  LevelDots,
  PageHeader,
  Pill,
  SectionHeader,
  Spinner,
  cx,
} from "./ui";

const PENDING_REFRESH_MS = 4000;
const LEVEL_OPTIONS: (number | null)[] = [null, 0, 1, 2, 3];
const INTENT_LABEL: Record<string, string> = {
  subject_question: "Asked about the topic",
  clarification_request: "Asked to repeat",
  off_topic: "Off topic",
  wellbeing_concern: "Wellbeing concern",
  help_request: "Asked for a hint",
  stop_request: "Asked to stop",
};

type LevelChoice = Record<string, number | null>;

function levelText(level: number | null) {
  return level === null ? "Unknown" : String(level);
}

function titleCase(id: string) {
  const text = id.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function download(entry: ExportEntry) {
  const blob = new Blob([JSON.stringify(entry.payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `kira-verbal-export-${entry.payload["idempotency_key"] ?? entry.id}.json`.replace(/:/g, "_");
  link.click();
  URL.revokeObjectURL(url);
}

export function ReportReview({ sessionId }: { sessionId: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [report, setReport] = useState<ReportView | null>(null);
  const [choice, setChoice] = useState<LevelChoice>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const adopt = useCallback((next: ReportView) => {
    setReport(next);
    setChoice(Object.fromEntries(next.criteria.map((c) => [c.criterion_id, c.level])));
  }, []);

  const load = useCallback(
    async (teacherToken: string) => {
      try {
        adopt(await api.getReport(teacherToken, sessionId));
        setError(null);
      } catch (e) {
        if (e instanceof ApiError && (e.code === "teacher_not_found" || e.code === "session_not_found")) {
          setError("This session isn't in your classroom (or the classroom was reset).");
        } else {
          setError(e instanceof ApiError ? e.message : "Could not load the report.");
        }
      }
    },
    [sessionId, adopt],
  );

  useEffect(() => {
    const stored = teacherStore.getToken();
    setToken(stored);
    if (stored) void load(stored);
    else setError("Open the teacher dashboard first to create or reopen your classroom.");
  }, [load]);

  // While the learner is still answering, keep the live preview fresh.
  useEffect(() => {
    if (!token || report?.status !== "pending") return;
    const timer = window.setInterval(() => void load(token), PENDING_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [token, report?.status, load]);

  const changed = useMemo(
    () => (report ? report.criteria.filter((c) => choice[c.criterion_id] !== c.level) : []),
    [report, choice],
  );
  const quotesByTurn = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const c of report?.criteria ?? [])
      for (const e of c.evidence)
        if (e.status === "accepted") map.set(e.turn_sequence, [...(map.get(e.turn_sequence) ?? []), e.quote]);
    return map;
  }, [report]);

  async function submit(decision: "approve" | "reject") {
    if (!token || !report?.report_id) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await api.reviewReport(token, report.report_id, {
        decision,
        levels: decision === "approve" ? choice : undefined,
        reason,
      });
      adopt(next);
      setReason("");
      setNotice(decision === "approve" ? `Approved as revision ${next.revision}.` : `Rejected (revision ${next.revision}).`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "stale_revision") {
        setNotice("Someone saved a newer review. The latest version is shown; check it and review again.");
        await load(token);
      } else {
        setError(e instanceof ApiError ? e.message : "Could not save the review.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function exportApproved() {
    if (!token || !report?.report_id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.exportReport(token, report.report_id);
      setNotice(result.replayed ? "Already exported; this is the same export event." : "Exported to the mock Kira adapter.");
      download(result);
      await load(token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not export.");
    } finally {
      setBusy(false);
    }
  }

  const reviewable = report !== null && report.status !== "pending" && report.report_id !== null;
  const exportedThisRevision = report?.exports.some((x) => x.report_id === report.report_id) ?? false;

  return (
    <AppShell active="teacher">
      <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
        <ButtonLink href="/teacher" variant="ghost" className="-ml-3 mb-3 px-3 py-1.5">
          <Icon.ChevronRight className="h-4 w-4 rotate-180" /> Review queue
        </ButtonLink>

        {error ? (
          <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
            {error}
          </Callout>
        ) : null}

        {!report ? (
          error ? null : (
            <p className="flex items-center gap-2 text-sm text-muted" role="status">
              <Spinner /> Loading report…
            </p>
          )
        ) : (
          <>
            <Header report={report} />
            {notice ? (
              <div className="mt-4">
                <Callout tone="purple" role="status" icon={<Icon.Check className="h-4 w-4" />}>
                  {notice}
                </Callout>
              </div>
            ) : null}

            <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="min-w-0 space-y-8">
                <section aria-labelledby="criteria-title">
                  <SectionHeader id="criteria-title" title="Rubric evidence" />
                  <div className="space-y-4">
                    {report.criteria.map((c) => (
                      <CriterionCard
                        key={c.criterion_id}
                        criterion={c}
                        value={choice[c.criterion_id] ?? null}
                        editable={reviewable && !busy}
                        onChange={(v) => setChoice((prev) => ({ ...prev, [c.criterion_id]: v }))}
                      />
                    ))}
                  </div>
                </section>
                <Transcript turns={report.transcript} quotesByTurn={quotesByTurn} wellbeing={report.wellbeing_turns} />
              </div>

              <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
                {reviewable ? (
                  <Card className="p-5">
                    <p className="font-semibold text-ink">Your decision</p>
                    <p className="mt-1 text-sm text-muted">
                      Reviewing revision {report.revision}. Approving saves your levels as a new revision.
                    </p>
                    {changed.length ? (
                      <ul className="mt-3 space-y-1 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                        {changed.map((c) => (
                          <li key={c.criterion_id}>
                            {titleCase(c.criterion_id)}: {levelText(c.level)} → <strong>{levelText(choice[c.criterion_id])}</strong>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <label htmlFor="reason" className="mt-4 block text-sm font-medium text-ink">
                      Reason{" "}
                      <span className="font-normal text-muted">
                        {changed.length ? "(required for changes)" : "(required to reject)"}
                      </span>
                    </label>
                    <textarea
                      id="reason"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={2000}
                      rows={3}
                      placeholder="What did you see or hear that supports this?"
                      className="mt-1.5 block w-full resize-y rounded-xl border border-line bg-white p-3 text-sm outline-none placeholder:text-faint focus:border-brand-400 focus:ring-2 focus:ring-brand-100 focus-visible:outline-none"
                    />
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <Button
                        onClick={() => void submit("approve")}
                        disabled={busy || (changed.length > 0 && !reason.trim())}
                      >
                        <Icon.Check className="h-4 w-4" />
                        {changed.length ? "Approve edits" : "Approve"}
                      </Button>
                      <Button variant="secondary" onClick={() => void submit("reject")} disabled={busy || !reason.trim()}>
                        <Icon.X className="h-4 w-4" /> Reject
                      </Button>
                    </div>
                    {report.status === "approved" ? (
                      <div className="mt-4 border-t border-line pt-4">
                        <Button variant="success" onClick={() => void exportApproved()} disabled={busy} className="w-full">
                          <Icon.Download className="h-4 w-4" />
                          {exportedThisRevision ? "Download export again" : "Export to mock Kira"}
                        </Button>
                        <p className="mt-2 text-xs text-faint">
                          Sends nothing anywhere: builds the proposed integration payload and downloads it.
                        </p>
                      </div>
                    ) : null}
                  </Card>
                ) : (
                  <Card className="p-5">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2.5 w-2.5">
                        <span className="kv-pulse absolute inline-flex h-full w-full rounded-full bg-brand-400" />
                        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-500" />
                      </span>
                      <p className="font-semibold text-ink">Learner is answering</p>
                    </div>
                    <p className="mt-2 text-sm text-muted">
                      This is a live preview. You can review once the session ends.
                    </p>
                  </Card>
                )}
                <AuditTrail report={report} />
              </aside>
            </div>
          </>
        )}
      </main>
    </AppShell>
  );
}

function Header({ report }: { report: ReportView }) {
  const badge = REPORT_BADGE[report.status];
  return (
    <Card className="p-5 md:p-6">
      <PageHeader
        eyebrow={
          <span className="flex flex-wrap items-center gap-2">
            <Pill tone={badge.tone} icon={badge.icon}>
              {report.status === "pending" ? "In progress · live preview" : badge.label}
            </Pill>
            {report.revision ? <span>Revision {report.revision}</span> : null}
          </span>
        }
        title={
          <>
            {report.lesson.title}
            <span className="ml-2 align-middle font-mono text-base font-normal text-muted">
              {report.synthetic_learner_id}
            </span>
          </>
        }
        subtitle={
          <>
            Session {report.session_status}
            {report.finish_reason ? ` · ${report.finish_reason.replace(/_/g, " ")}` : ""}
          </>
        }
      />
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Stat label="Criteria with evidence">
          {report.coverage.with_evidence} of {report.coverage.total}
          <span className="mt-1.5 flex gap-1" aria-hidden="true">
            {Array.from({ length: report.coverage.total }, (_, i) => (
              <span key={i} className={cx("h-1.5 flex-1 rounded-full", i < report.coverage.with_evidence ? "bg-brand-500" : "bg-line")} />
            ))}
          </span>
        </Stat>
        <Stat label="Hints used">{report.hints_used}</Stat>
        <Stat label="Side questions">{report.side_turns}</Stat>
      </div>
      {report.wellbeing_turns.length ? (
        <div className="mt-4">
          <Callout tone="red" role="alert" icon={<Icon.Flag className="h-4 w-4" />} title="This learner may need a check-in">
            They said something worrying in turn{" "}
            {report.wellbeing_turns.map((n, i) => (
              <span key={n}>
                {i ? ", " : ""}
                <a href={`#turn-${n}`} className="font-medium underline underline-offset-2">
                  {n}
                </a>
              </span>
            ))}
            . Follow your school&rsquo;s procedures; this tool doesn&rsquo;t replace them.
          </Callout>
        </div>
      ) : null}
      {report.needs_review ? (
        <div className="mt-3">
          <Callout tone="amber" icon={<Icon.Alert className="h-4 w-4" />}>
            Look carefully: some answers suggested different levels, or some evidence was rejected.
          </Callout>
        </div>
      ) : null}
      <p className="mt-4 text-xs text-faint">
        Levels are suggestions from transcript evidence, not proof of mastery. Unknown means not enough
        evidence, never zero.
      </p>
    </Card>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-row p-3">
      <p className="text-xs text-muted">{label}</p>
      <div className="mt-0.5 text-lg font-semibold text-ink">{children}</div>
    </div>
  );
}

function CriterionCard({
  criterion: c,
  value,
  editable,
  onChange,
}: {
  criterion: CriterionReport;
  value: number | null;
  editable: boolean;
  onChange: (v: number | null) => void;
}) {
  const changed = value !== c.level;
  return (
    <Card className={cx("p-5", changed && "ring-2 ring-amber-200")}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-xl">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-ink">{titleCase(c.criterion_id)}</h3>
            <Pill tone={c.suggested_level === null ? "gray" : "purple"}>
              Suggested {levelText(c.suggested_level)}
            </Pill>
            {c.conflicting ? <Pill tone="amber">Conflicting</Pill> : null}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-muted">{c.objective_description}</p>
        </div>
        <div role="radiogroup" aria-label={`Level for ${titleCase(c.criterion_id)}`} className="flex rounded-xl bg-row p-1">
          {LEVEL_OPTIONS.map((option) => {
            const selected = value === option;
            return (
              <button
                key={String(option)}
                type="button"
                role="radio"
                aria-checked={selected}
                disabled={!editable}
                onClick={() => onChange(option)}
                title={option === null ? "Not enough evidence" : c.level_descriptors[String(option)]}
                className={cx(
                  "min-w-9 rounded-lg px-2.5 py-1.5 text-sm font-medium transition disabled:cursor-default",
                  selected ? "bg-white text-brand-700 shadow-card ring-1 ring-brand-200" : "text-muted hover:text-ink",
                )}
              >
                {option === null ? "?" : option}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-line p-3.5">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-ink">
            Level {levelText(value)}
            {value !== null && value === c.suggested_level ? <span className="text-muted"> · suggested</span> : null}
          </p>
          <LevelDots level={value} />
        </div>
        <p className="mt-1 text-sm text-muted">
          {value === null ? "Not enough evidence to judge this criterion." : c.level_descriptors[String(value)]}
        </p>
      </div>

      {c.misconceptions.map((m) => (
        <div key={m.tag} className="mt-3">
          <Callout tone="red" icon={<Icon.Lightbulb className="h-4 w-4" />} title="Possible misconception">
            {m.description}
          </Callout>
        </div>
      ))}

      <p className="mt-3 text-xs text-faint">
        Independent: {c.independent_levels.length ? c.independent_levels.join(", ") : "none"} · After a hint:{" "}
        {c.assisted_levels.length ? c.assisted_levels.join(", ") : "none"}
        {c.abstentions ? ` · ${c.abstentions} unclear` : ""}
        {c.rejected ? ` · ${c.rejected} rejected` : ""}
      </p>

      {c.evidence.length ? (
        <ul className="mt-3 space-y-2">
          {c.evidence.map((e) => (
            <li key={e.id} className="rounded-xl bg-row p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={e.status === "accepted" ? "green" : e.status === "rejected" ? "red" : "gray"}>
                  {e.status}
                  {e.proposed_level !== null ? ` · level ${e.proposed_level}` : ""}
                </Pill>
                {e.assisted ? <Pill tone="blue">after hint</Pill> : null}
                <a href={`#turn-${e.turn_sequence}`} className="ml-auto text-xs font-medium text-brand-600 hover:underline">
                  Turn {e.turn_sequence} →
                </a>
              </div>
              {e.quote ? (
                <blockquote className="mt-2 border-l-2 border-brand-300 pl-3 text-ink">&ldquo;{e.quote}&rdquo;</blockquote>
              ) : null}
              <p className="mt-1.5 text-xs text-muted">
                {e.reason}
                {e.rejection_reason ? ` Rejected: ${e.rejection_reason}.` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-xl border border-dashed border-line p-3 text-sm text-muted">
          No evidence collected for this criterion.
        </p>
      )}
    </Card>
  );
}

function highlight(answer: string, quotes: string[]) {
  const quote = quotes.find((q) => q && answer.toLowerCase().includes(q.toLowerCase()));
  if (!quote) return answer;
  const start = answer.toLowerCase().indexOf(quote.toLowerCase());
  return (
    <>
      {answer.slice(0, start)}
      <mark className="rounded bg-white/25 px-0.5 text-inherit underline decoration-white/70 underline-offset-2">
        {answer.slice(start, start + quote.length)}
      </mark>
      {answer.slice(start + quote.length)}
    </>
  );
}

function Transcript({
  turns,
  quotesByTurn,
  wellbeing,
}: {
  turns: TeacherTranscriptTurn[];
  quotesByTurn: Map<number, string[]>;
  wellbeing: number[];
}) {
  return (
    <section aria-labelledby="transcript-title">
      <SectionHeader id="transcript-title" title="Transcript" />
      <Card className="p-4 md:p-5">
        {turns.length === 0 ? (
          <p className="text-sm text-muted">No answers yet.</p>
        ) : (
          <ol className="space-y-5">
            {turns.map((t) => (
              <li key={t.sequence} id={`turn-${t.sequence}`} className="scroll-mt-6 rounded-xl p-1 target:bg-brand-50">
                <div className="flex gap-2.5">
                  <BrandMark size="sm" />
                  <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-row px-4 py-2.5 text-sm text-ink">
                    {t.question_text}
                  </div>
                </div>
                <div className="mt-2 flex flex-col items-end">
                  <div
                    className={cx(
                      "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-md px-4 py-2.5 text-sm text-white",
                      wellbeing.includes(t.sequence) ? "bg-rose-600" : "bg-gradient-to-br from-brand-500 to-brand-700",
                    )}
                  >
                    {t.answer ? highlight(t.answer, quotesByTurn.get(t.sequence) ?? []) : <em>(no answer)</em>}
                  </div>
                  <p className="mt-1 flex flex-wrap justify-end gap-1.5 text-xs text-faint">
                    <span>Turn {t.sequence}</span>
                    <span>· {t.modality === "voice" ? "spoken" : "typed"}</span>
                    {t.assisted ? <span>· after a hint</span> : null}
                    {t.intent && INTENT_LABEL[t.intent] ? <span>· {INTENT_LABEL[t.intent]}</span> : null}
                  </p>
                </div>
                {t.reply ? (
                  <div className="mt-2 flex gap-2.5 pl-[42px]">
                    <p className="max-w-[85%] rounded-2xl rounded-tl-md border border-brand-100 bg-brand-50 px-4 py-2 text-sm text-brand-900">
                      {t.reply}
                    </p>
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </section>
  );
}

function AuditTrail({ report }: { report: ReportView }) {
  if (!report.revisions.length) return null;
  return (
    <Card className="p-5">
      <p className="flex items-center gap-2 font-semibold text-ink">
        <Icon.History className="h-4 w-4 text-brand-500" /> Audit trail
      </p>
      <p className="mt-1 text-xs text-faint">Revisions are never edited; each decision adds one.</p>
      <ol className="relative mt-4 space-y-4 border-l border-line pl-5">
        {[...report.revisions].reverse().map((r) => {
          const review = report.reviews.find((v) => v.to_revision === r.revision);
          const exported = report.exports.find((x) => x.report_revision === r.revision);
          const badge = REPORT_BADGE[r.status];
          return (
            <li key={r.report_id} className="relative">
              <span
                className={cx(
                  "absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-white",
                  r.status === "approved" ? "bg-emerald-500" : r.status === "rejected" ? "bg-rose-500" : "bg-brand-400",
                )}
              />
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-ink">Revision {r.revision}</p>
                <Pill tone={badge.tone}>{badge.label}</Pill>
              </div>
              <p className="mt-0.5 text-xs text-muted">
                {r.created_by} · {new Date(r.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
              </p>
              {review?.reason ? <p className="mt-1 text-sm text-ink">&ldquo;{review.reason}&rdquo;</p> : null}
              {exported ? (
                <button
                  type="button"
                  onClick={() => download(exported)}
                  className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 hover:underline"
                >
                  <Icon.Download className="h-3.5 w-3.5" /> Exported · download JSON
                </button>
              ) : null}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
