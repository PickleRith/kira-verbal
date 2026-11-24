// Score display: a percentage ring, the grade band, and the points behind it. Unknown
// criteria are never shown as zero; they make the grade "Incomplete".

import { BAND_HINT, BAND_LABEL } from "@/lib/grading";
import type { GradeBand, ScoreView, StudentCriterionResult } from "@/lib/types";

import { Pill, type Tone, cx } from "./ui";

export const BAND_TONE: Record<GradeBand, Tone> = {
  mastered: "green", // green = positive learning outcome
  proficient: "green",
  developing: "amber",
  beginning: "blue", // neutral, not an alarm: this is shown to students too
  incomplete: "gray",
};

export function BandPill({ band, className }: { band: GradeBand; className?: string }) {
  return (
    <Pill tone={BAND_TONE[band]} className={className}>
      {BAND_LABEL[band]}
    </Pill>
  );
}

export function ScoreRing({ score, size = 112 }: { score: ScoreView; size?: number }) {
  const stroke = size >= 100 ? 8 : 6;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const fraction = score.percent === null ? 0 : score.percent / 100;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-sunken)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={score.band === "mastered" || score.band === "proficient" ? "var(--color-mint)" : "var(--color-lavender)"}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          className="kv-ease transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cx("font-serif leading-none text-ink", size >= 100 ? "text-[32px]" : "text-[22px]")}>
          {score.percent === null ? "–" : `${score.percent}%`}
        </span>
        <span className="mt-1 text-xs text-muted">
          {score.points}/{score.max_points} pts
        </span>
      </div>
    </div>
  );
}

// Ring + band + the sentence that explains the number.
export function ScoreSummary({
  score,
  title,
  note,
  size = 112,
}: {
  score: ScoreView;
  title?: React.ReactNode;
  note?: React.ReactNode;
  size?: number;
}) {
  return (
    <div className="flex items-center gap-5" data-testid="score-summary">
      <ScoreRing score={score} size={size} />
      <div className="min-w-0">
        {title ? <p className="text-xs font-medium text-muted">{title}</p> : null}
        <p className="mt-1 font-serif text-[26px] leading-none text-ink" data-testid="score-band">
          {BAND_LABEL[score.band]}
        </p>
        <p className="mt-2 text-sm text-muted">
          {score.points} of {score.max_points} points
          {score.assessed < score.total
            ? ` on ${score.assessed} of ${score.total} criteria`
            : ` · all ${score.total} criteria`}
        </p>
        <p className="mt-0.5 text-xs text-muted">{note ?? BAND_HINT[score.band]}</p>
      </div>
    </div>
  );
}

// Compact "78% · Proficient" for lists.
export function ScoreChip({ score, suggested = false }: { score: ScoreView; suggested?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-serif text-[18px] text-ink">{score.percent === null ? "–" : `${score.percent}%`}</span>
      <BandPill band={score.band} />
      {suggested ? <span className="text-xs text-muted">suggested</span> : null}
    </span>
  );
}

export function titleCase(id: string) {
  const text = id.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// One row per criterion: the level as filled segments, and what that level means.
export function CriterionResults({ criteria }: { criteria: StudentCriterionResult[] }) {
  return (
    <ul className="space-y-4">
      {criteria.map((c) => (
        <li key={c.criterion_id}>
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-ink">{titleCase(c.criterion_id)}</p>
            <span className="text-xs text-muted">
              {c.level === null ? "Not assessed" : `${c.level} / ${c.max_level}`}
            </span>
          </div>
          <div className="mt-2 flex gap-1.5" aria-hidden="true">
            {Array.from({ length: c.max_level }, (_, i) => (
              <span
                key={i}
                className={cx("h-2 flex-1 rounded-sm", c.level !== null && i < c.level ? "bg-purple" : "bg-sunken")}
              />
            ))}
          </div>
          <p className="mt-1.5 text-sm text-muted">
            {c.descriptor ?? "Your teacher didn't have enough from this check-in to judge this one."}
          </p>
        </li>
      ))}
    </ul>
  );
}
