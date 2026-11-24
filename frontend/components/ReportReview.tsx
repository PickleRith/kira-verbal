"use client";

// Teacher review of one check-in. Three views of the same report:
//   By question - every answer the student gave, with the evidence it produced and the
//                 levels for the criteria that answer speaks to (gradable in place);
//   Rubric      - one card per criterion with all its evidence and the level picker;
//   Transcript  - the conversation as it happened.
// Levels chosen in any view are the same selection. The decision panel saves them as a new
// revision (a reason is required for any change, or to reject); approved results export.

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { gradeLevels } from "@/lib/grading";
import type { CriterionReport, EvidenceItem, ExportEntry, ReportView, TeacherTranscriptTurn } from "@/lib/types";

import { FolderTabs } from "./FolderTabs";
import { BandPill, ScoreSummary } from "./Score";
import { AppShell } from "./shell";
import { REPORT_BADGE, learnerLabel } from "./TeacherDashboard";
import {
  BrandMark,
  Button,
  ButtonLink,
  Callout,
  Card,
  Eyebrow,
  Icon,
  LevelDots,
  Pill,
  Spinner,
  Stat,
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
type View = "questions" | "rubric" | "transcript";

function levelText(level: number | null) {
  return level === null ? "Unknown" : String(level);
}

// What this one answer earned: the levels of its accepted evidence, out of 3 each.
function answerScore(evidence: { item: EvidenceItem }[]) {
  const levels = evidence.filter((e) => e.item.status === "accepted").map((e) => e.item.proposed_level ?? 0);
  if (!levels.length) return <Pill>No score</Pill>;
  const points = levels.reduce((a, b) => a + b, 0);
  return (
    <span className="rounded-md bg-lavender-soft px-2 py-0.5 text-xs font-semibold text-purple-ink" title="Suggested level for this answer">
      {points}/{levels.length * 3}
    </span>
  );
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
  const auth = useRequireRole("teacher");
  const token = auth?.token ?? null;
  const [report, setReport] = useState<ReportView | null>(null);
  const [choice, setChoice] = useState<LevelChoice>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<View>("questions");

  const adopt = useCallback((next: ReportView) => {
    setReport(next);
    setChoice(Object.fromEntries(next.criteria.map((c) => [c.criterion_id, c.level])));
  }, []);

  const load = useCallback(
    async (teacherToken: string, { keepChoice = false } = {}) => {
      try {
        const next = await api.getReport(teacherToken, sessionId);
        if (keepChoice) setReport(next);
        else adopt(next);
        setError(null);
      } catch (e) {
        if (e instanceof ApiError && (e.code === "teacher_not_found" || e.code === "session_not_found")) {
          setError("This check-in isn't in your class.");
        } else {
          setError(e instanceof ApiError ? e.message : "Could not load the report.");
        }
      }
    },
    [sessionId, adopt],
  );

  useEffect(() => {
    if (token) void load(token);
  }, [token, load]);

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
  const evidenceByTurn = useMemo(() => {
    const map = new Map<number, { criterion: CriterionReport; item: EvidenceItem }[]>();
    for (const c of report?.criteria ?? [])
      for (const item of c.evidence) map.set(item.turn_sequence, [...(map.get(item.turn_sequence) ?? []), { criterion: c, item }]);
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
        reviewer_id: reviewerId(auth?.user.display_name),
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
      await load(token, { keepChoice: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not export.");
    } finally {
      setBusy(false);
    }
  }

  const reviewable = report !== null && report.status !== "pending" && report.report_id !== null;
  // The score of the levels currently selected: it moves as the teacher changes a level.
  const liveScore = report ? gradeLevels(choice) : null;
  const exportedThisRevision = report?.exports.some((x) => x.report_id === report.report_id) ?? false;
  const setLevel = (criterionId: string, v: number | null) => setChoice((prev) => ({ ...prev, [criterionId]: v }));
  const answers = report?.transcript.filter((t) => t.signal !== "conversation") ?? [];

  return (
    <AppShell>
      <main className="mx-auto max-w-7xl px-4 pb-20 pt-8 md:px-8 md:pt-10">
        <ButtonLink href="/teacher" variant="ghost" className="-ml-3 mb-4 px-3 py-1.5">
          <Icon.ChevronLeft className="h-4 w-4" /> Review board
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
            <Header report={report} answers={answers.length} />
            {notice ? (
              <div className="mt-5">
                <Callout tone="purple" role="status" icon={<Icon.Check className="h-4 w-4" />}>
                  {notice}
                </Callout>
              </div>
            ) : null}

            <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="min-w-0">
                <FolderTabs
                  active={view}
                  onChange={(id) => setView(id as View)}
                  tabs={[
                    { id: "questions", label: "By question", count: answers.length },
                    { id: "rubric", label: "Rubric", count: report.criteria.length },
                    { id: "transcript", label: "Transcript" },
                  ]}
                >
                  {view === "questions" ? (
                    <QuestionsView
                      turns={report.transcript}
                      evidenceByTurn={evidenceByTurn}
                      quotesByTurn={quotesByTurn}
                      wellbeing={report.wellbeing_turns}
                      choice={choice}
                      editable={reviewable && !busy}
                      onLevel={setLevel}
                    />
                  ) : view === "rubric" ? (
                    <div className="space-y-4">
                      {report.criteria.map((c) => (
                        <CriterionCard
                          key={c.criterion_id}
                          criterion={c}
                          value={choice[c.criterion_id] ?? null}
                          editable={reviewable && !busy}
                          onChange={(v) => setLevel(c.criterion_id, v)}
                          onJump={(sequence) => {
                            setView("questions");
                            window.setTimeout(
                              () => document.getElementById(`turn-${sequence}`)?.scrollIntoView({ behavior: "smooth" }),
                              60,
                            );
                          }}
                        />
                      ))}
                    </div>
                  ) : (
                    <Transcript turns={report.transcript} quotesByTurn={quotesByTurn} wellbeing={report.wellbeing_turns} />
                  )}
                </FolderTabs>
              </div>

              <aside className="space-y-4 lg:sticky lg:top-[92px] lg:self-start">
                {reviewable ? (
                  <Card className="p-5 md:p-6">
                    <Eyebrow>Your decision · revision {report.revision}</Eyebrow>
                    <h2 className="mt-3 text-[28px] leading-none text-ink">
                      Grade this <em>check-in</em>
                    </h2>
                    <div className="mt-5 rounded-lg border border-line bg-raised p-4">
                      <ScoreSummary
                        score={liveScore!}
                        title={report.status === "ready_for_review" ? "Grade if you approve" : "Grade"}
                        size={96}
                        note={
                          liveScore!.band === "incomplete"
                            ? "Set a level for every criterion (0 counts) to give a grade."
                            : changed.length
                              ? `Suggested was ${report.suggested_score.percent ?? "–"}%. Your changes update this.`
                              : undefined
                        }
                      />
                    </div>
                    <ul className="mt-5 space-y-2.5">
                      {report.criteria.map((c) => {
                        const value = choice[c.criterion_id] ?? null;
                        const isChanged = value !== c.level;
                        return (
                          <li key={c.criterion_id} className="flex items-center justify-between gap-3 text-sm">
                            <span className={cx("truncate", isChanged ? "text-warn" : "text-ink")}>
                              {titleCase(c.criterion_id)}
                            </span>
                            <span className="flex items-center gap-2.5">
                              <LevelDots level={value} />
                              <span className="w-14 text-right font-mono text-xs text-muted">{levelText(value)}</span>
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                    {changed.length ? (
                      <ul className="mt-4 space-y-1 rounded-lg border border-warn/25 bg-warn/[0.07] p-3 text-sm text-warn">
                        {changed.map((c) => (
                          <li key={c.criterion_id}>
                            {titleCase(c.criterion_id)}: {levelText(c.level)} → <strong>{levelText(choice[c.criterion_id])}</strong>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <label htmlFor="reason" className="mt-5 block text-sm font-medium text-ink">
                      Reason{" "}
                      <span className="font-normal text-faint">
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
                      className="kv-ease mt-1.5 block w-full resize-y rounded-lg border border-line bg-raised p-3.5 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-purple/40 focus-visible:outline-none"
                    />
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <Button onClick={() => void submit("approve")} disabled={busy || (changed.length > 0 && !reason.trim())}>
                        <Icon.Check className="h-4 w-4" />
                        {changed.length ? "Approve edits" : "Approve"}
                      </Button>
                      <Button variant="secondary" onClick={() => void submit("reject")} disabled={busy || !reason.trim()}>
                        <Icon.X className="h-4 w-4" /> Reject
                      </Button>
                    </div>
                    {report.status === "approved" ? (
                      <div className="mt-5 border-t border-line pt-5">
                        <Button variant="ai" onClick={() => void exportApproved()} disabled={busy} className="w-full">
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
                  <Card className="p-5 md:p-6">
                    <div className="flex items-center gap-2.5">
                      <span className="relative flex h-2.5 w-2.5">
                        <span className="kv-pulse absolute inline-flex h-full w-full rounded-full bg-purple" />
                        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-purple" />
                      </span>
                      <p className="font-serif text-[22px] text-ink">Student is answering</p>
                    </div>
                    <p className="mt-2 text-sm text-muted">This is a live preview. You can grade once the check-in ends.</p>
                    <div className="mt-4 rounded-lg border border-line bg-raised p-4">
                      <ScoreSummary score={report.suggested_score} title="Suggested so far" size={84} />
                    </div>
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

// Reviewer ids are short slugs (backend pattern ^[a-z0-9][a-z0-9-]{0,39}$).
function reviewerId(name: string | undefined) {
  const slug = (name ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return slug || "teacher";
}

function Header({ report, answers }: { report: ReportView; answers: number }) {
  const badge = REPORT_BADGE[report.status];
  return (
    <section>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={badge.tone} icon={badge.icon}>
          {report.status === "pending" ? "In progress · live preview" : badge.label}
        </Pill>
        {report.revision ? <span className="text-xs text-faint">Revision {report.revision}</span> : null}
        <span className="text-xs text-faint">
          · {new Date(report.session_created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
        </span>
      </div>
      <h1 className="mt-4 text-[44px] leading-[1.03] text-ink md:text-[58px]">
        {learnerLabel(report)} <span className="text-muted">on</span> <em>{report.lesson.title}</em>
      </h1>
      <p className="mt-3 text-[15px] text-muted">
        Check-in {report.session_status}
        {report.finish_reason ? ` · ${report.finish_reason.replace(/_/g, " ")}` : ""}. Levels are suggestions from the
        student&rsquo;s words, not proof of mastery. Unknown means not enough evidence, never zero.
      </p>
      <div className="mt-7 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={report.status === "approved" ? "Approved score" : report.status === "pending" ? "Score so far" : "Suggested score"} accent>
          <span className="flex flex-wrap items-baseline gap-2">
            {report.score.percent === null ? "–" : `${report.score.percent}%`}
            <BandPill band={report.score.band} className="font-sans" />
          </span>
        </Stat>
        <Stat label="Points">
          {report.score.points}/{report.score.max_points}
        </Stat>
        <Stat label="Criteria with evidence">
          {report.coverage.with_evidence}/{report.coverage.total}
        </Stat>
        <Stat label="Answers · hints">
          {answers} · {report.hints_used}
        </Stat>
      </div>
      {report.wellbeing_turns.length ? (
        <div className="mt-4">
          <Callout tone="red" role="alert" icon={<Icon.Flag className="h-4 w-4" />} title="This student may need a check-in">
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
    </section>
  );
}

function LevelPicker({
  label,
  value,
  descriptors,
  editable,
  onChange,
  size = "md",
}: {
  label: string;
  value: number | null;
  descriptors: Record<string, string>;
  editable: boolean;
  onChange: (v: number | null) => void;
  size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-raised p-0.5">
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
            title={option === null ? "Not enough evidence" : descriptors[String(option)]}
            className={cx(
              "kv-ease rounded font-medium tabular-nums transition-colors disabled:cursor-default",
              size === "sm" ? "min-w-8 px-2 py-1 text-xs" : "min-w-10 px-3 py-1.5 text-sm",
              selected ? "bg-ink text-white" : "text-muted enabled:hover:text-ink",
            )}
          >
            {option === null ? "?" : option}
          </button>
        );
      })}
    </div>
  );
}

function highlight(answer: string, quotes: string[]) {
  const quote = quotes.find((q) => q && answer.toLowerCase().includes(q.toLowerCase()));
  if (!quote) return answer;
  const start = answer.toLowerCase().indexOf(quote.toLowerCase());
  return (
    <>
      {answer.slice(0, start)}
      <mark className="rounded bg-lavender-soft px-0.5 text-ink underline decoration-purple underline-offset-4">
        {answer.slice(start, start + quote.length)}
      </mark>
      {answer.slice(start + quote.length)}
    </>
  );
}

function QuestionsView({
  turns,
  evidenceByTurn,
  quotesByTurn,
  wellbeing,
  choice,
  editable,
  onLevel,
}: {
  turns: TeacherTranscriptTurn[];
  evidenceByTurn: Map<number, { criterion: CriterionReport; item: EvidenceItem }[]>;
  quotesByTurn: Map<number, string[]>;
  wellbeing: number[];
  choice: LevelChoice;
  editable: boolean;
  onLevel: (criterionId: string, v: number | null) => void;
}) {
  if (turns.length === 0) {
    return (
      <p className="py-8 text-center font-serif text-[22px] italic text-muted">No answers yet.</p>
    );
  }
  let answerNumber = 0;
  return (
    <ol className="space-y-5">
      {turns.map((t) => {
        const side = t.signal === "conversation";
        if (!side) answerNumber += 1;
        const evidence = evidenceByTurn.get(t.sequence) ?? [];
        const criteria = [...new Map(evidence.map((e) => [e.criterion.criterion_id, e.criterion])).values()];
        const flagged = wellbeing.includes(t.sequence);
        if (side) {
          return (
            <li key={t.sequence} id={`turn-${t.sequence}`} className="scroll-mt-28 rounded-lg border border-dashed border-line px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-faint">Turn {t.sequence} · not scored</span>
                {t.intent && INTENT_LABEL[t.intent] ? <Pill tone={flagged ? "red" : "gray"}>{INTENT_LABEL[t.intent]}</Pill> : null}
              </div>
              <p className={cx("mt-2 text-[15px]", flagged ? "text-bad" : "text-ink/85")}>&ldquo;{t.answer}&rdquo;</p>
              {t.reply ? <p className="mt-1.5 font-serif text-[16px] italic text-muted">Reply: {t.reply}</p> : null}
            </li>
          );
        }
        return (
          <li
            key={t.sequence}
            id={`turn-${t.sequence}`}
            className={cx(
              "scroll-mt-28 overflow-hidden rounded-xl border bg-raised",
              flagged ? "border-bad/40" : "border-line",
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4 md:px-6">
              <div className="min-w-0">
                <p className="text-xs text-purple-ink">
                  Question {answerNumber} · turn {t.sequence}
                </p>
                <h3 className="mt-1.5 text-[22px] leading-snug text-ink">{t.question_text}</h3>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {answerScore(evidence)}
                <Pill icon={t.modality === "voice" ? <Icon.Mic className="h-3 w-3" /> : <Icon.Chat className="h-3 w-3" />}>
                  {t.modality === "voice" ? "Spoken" : "Typed"}
                </Pill>
                {t.assisted ? <Pill tone="blue">After a hint</Pill> : null}
                {t.intent && INTENT_LABEL[t.intent] ? <Pill tone={flagged ? "red" : "gray"}>{INTENT_LABEL[t.intent]}</Pill> : null}
              </div>
            </div>

            <div className="px-5 py-5 md:px-6">
              <p className="text-xs text-faint">Student&rsquo;s answer</p>
              <blockquote className={cx("mt-2 whitespace-pre-wrap font-serif text-[21px] leading-relaxed", flagged ? "text-bad" : "text-ink")}>
                {t.answer ? <>&ldquo;{highlight(t.answer, quotesByTurn.get(t.sequence) ?? [])}&rdquo;</> : <em>(no answer)</em>}
              </blockquote>
              {t.reply ? <p className="mt-3 text-sm text-muted">Then Kira Verbal said: <span className="italic">{t.reply}</span></p> : null}
            </div>

            {evidence.length ? (
              <div className="space-y-3 border-t border-line bg-raised px-5 py-5 md:px-6">
                <p className="text-xs text-faint">What this answer shows</p>
                {evidence.map(({ criterion, item }) => (
                  <div key={item.id} className="flex flex-wrap items-start gap-x-3 gap-y-1.5 text-sm">
                    <Pill tone={item.status === "accepted" ? "green" : item.status === "rejected" ? "red" : "gray"}>
                      {item.status === "accepted" ? `Level ${item.proposed_level}` : item.status === "rejected" ? "Rejected" : "Unclear"}
                    </Pill>
                    <span className="text-ink">{titleCase(criterion.criterion_id)}</span>
                    {item.misconception_tag ? <Pill tone="red">Misconception</Pill> : null}
                    <p className="w-full text-muted">
                      {item.reason}
                      {item.rejection_reason ? ` Rejected: ${item.rejection_reason}.` : ""}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="border-t border-line bg-raised px-6 py-4 text-sm text-faint">No rubric evidence from this answer.</p>
            )}

            {criteria.length ? (
              <div className="space-y-3 border-t border-line px-5 py-4 md:px-6">
                {criteria.map((c) => {
                  const value = choice[c.criterion_id] ?? null;
                  return (
                    <div key={c.criterion_id} className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">
                          {titleCase(c.criterion_id)}{" "}
                          <span className="font-normal text-faint">· suggested {levelText(c.suggested_level)}</span>
                        </p>
                        <p className="text-xs text-muted">
                          {value === null ? "Not enough evidence to judge." : c.level_descriptors[String(value)]}
                        </p>
                      </div>
                      <LevelPicker
                        label={`Level for ${titleCase(c.criterion_id)} (question ${answerNumber})`}
                        value={value}
                        descriptors={c.level_descriptors}
                        editable={editable}
                        onChange={(v) => onLevel(c.criterion_id, v)}
                        size="sm"
                      />
                    </div>
                  );
                })}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function CriterionCard({
  criterion: c,
  value,
  editable,
  onChange,
  onJump,
}: {
  criterion: CriterionReport;
  value: number | null;
  editable: boolean;
  onChange: (v: number | null) => void;
  onJump: (turnSequence: number) => void;
}) {
  const changed = value !== c.level;
  return (
    <div className={cx("rounded-xl border bg-raised p-5 md:p-6", changed ? "border-warn/50" : "border-line")}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-xl">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[24px] leading-tight text-ink">{titleCase(c.criterion_id)}</h3>
            <Pill tone={c.suggested_level === null ? "gray" : "purple"}>Suggested {levelText(c.suggested_level)}</Pill>
            {c.conflicting ? <Pill tone="amber">Conflicting</Pill> : null}
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">{c.objective_description}</p>
        </div>
        <LevelPicker
          label={`Level for ${titleCase(c.criterion_id)}`}
          value={value}
          descriptors={c.level_descriptors}
          editable={editable}
          onChange={onChange}
        />
      </div>

      <div className="mt-4 rounded-lg border border-line bg-raised p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-ink">
            Level {levelText(value)}
            {value !== null && value === c.suggested_level ? <span className="text-faint"> · suggested</span> : null}
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

      <p className="mt-3 font-mono text-xs text-faint">
        Independent: {c.independent_levels.length ? c.independent_levels.join(", ") : "none"} · After a hint:{" "}
        {c.assisted_levels.length ? c.assisted_levels.join(", ") : "none"}
        {c.abstentions ? ` · ${c.abstentions} unclear` : ""}
        {c.rejected ? ` · ${c.rejected} rejected` : ""}
      </p>

      {c.evidence.length ? (
        <ul className="mt-3 space-y-2">
          {c.evidence.map((e) => (
            <li key={e.id} className="rounded-lg border border-line bg-surface p-3.5 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={e.status === "accepted" ? "green" : e.status === "rejected" ? "red" : "gray"}>
                  {e.status}
                  {e.proposed_level !== null ? ` · level ${e.proposed_level}` : ""}
                </Pill>
                {e.assisted ? <Pill tone="blue">after hint</Pill> : null}
                <a
                  href={`#turn-${e.turn_sequence}`}
                  onClick={(event) => {
                    event.preventDefault();
                    onJump(e.turn_sequence);
                  }}
                  className="ml-auto text-xs text-purple-ink hover:underline"
                >
                  Turn {e.turn_sequence} →
                </a>
              </div>
              {e.quote ? (
                <blockquote className="mt-2 border-l-2 border-purple/40 pl-3 font-serif text-[17px] italic text-ink">
                  &ldquo;{e.quote}&rdquo;
                </blockquote>
              ) : null}
              <p className="mt-1.5 text-xs text-muted">
                {e.reason}
                {e.rejection_reason ? ` Rejected: ${e.rejection_reason}.` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-line p-3.5 text-sm text-faint">
          No evidence collected for this criterion.
        </p>
      )}
    </div>
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
  if (turns.length === 0) {
    return <p className="py-8 text-center font-serif text-[22px] italic text-muted">No answers yet.</p>;
  }
  return (
    <ol className="space-y-5">
      {turns.map((t) => (
        <li key={t.sequence} className="rounded-lg p-1">
          <div className="flex gap-2.5">
            <BrandMark size="sm" />
            <div className="max-w-[85%] rounded-lg rounded-tl-md border border-line bg-raised px-4 py-2.5 text-[15px] text-ink">
              {t.question_text}
            </div>
          </div>
          <div className="mt-2 flex flex-col items-end">
            <div
              className={cx(
                "max-w-[85%] whitespace-pre-wrap rounded-lg rounded-tr-md px-4 py-2.5 text-[15px]",
                wellbeing.includes(t.sequence) ? "border border-bad/30 bg-bad-soft text-bad" : "border border-purple/30 bg-lavender-soft text-ink",
              )}
            >
              {t.answer ? highlightPlain(t.answer, quotesByTurn.get(t.sequence) ?? []) : <em>(no answer)</em>}
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
              <p className="max-w-[85%] rounded-lg rounded-tl-md border border-line bg-surface px-4 py-2 font-serif text-[16px] italic text-ink/85">
                {t.reply}
              </p>
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

// Inside answer bubbles the highlight is an underline only.
function highlightPlain(answer: string, quotes: string[]) {
  const quote = quotes.find((q) => q && answer.toLowerCase().includes(q.toLowerCase()));
  if (!quote) return answer;
  const start = answer.toLowerCase().indexOf(quote.toLowerCase());
  return (
    <>
      {answer.slice(0, start)}
      <mark className="bg-transparent text-inherit underline decoration-ink/50 decoration-2 underline-offset-4">
        {answer.slice(start, start + quote.length)}
      </mark>
      {answer.slice(start + quote.length)}
    </>
  );
}

function AuditTrail({ report }: { report: ReportView }) {
  if (!report.revisions.length) return null;
  return (
    <Card className="p-5 md:p-6">
      <p className="flex items-center gap-2 font-serif text-[22px] text-ink">
        <Icon.History className="h-4 w-4 text-purple-ink" /> Audit trail
      </p>
      <p className="mt-1 text-xs text-faint">Revisions are never edited; each decision adds one.</p>
      <ol className="relative mt-5 space-y-4 border-l border-line pl-5">
        {[...report.revisions].reverse().map((r) => {
          const review = report.reviews.find((v) => v.to_revision === r.revision);
          const exported = report.exports.find((x) => x.report_revision === r.revision);
          const badge = REPORT_BADGE[r.status];
          return (
            <li key={r.report_id} className="relative">
              <span
                className={cx(
                  "absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-surface",
                  r.status === "approved" ? "bg-ok" : r.status === "rejected" ? "bg-bad" : "bg-purple",
                )}
              />
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-ink">Revision {r.revision}</p>
                <Pill tone={badge.tone}>{badge.label}</Pill>
              </div>
              <p className="mt-0.5 font-mono text-xs text-faint">
                {r.created_by} · {new Date(r.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
              </p>
              {review?.reason ? <p className="mt-1 text-sm text-ink/85">&ldquo;{review.reason}&rdquo;</p> : null}
              {exported ? (
                <button
                  type="button"
                  onClick={() => download(exported)}
                  className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-purple-ink hover:underline"
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
