// Browser copy of backend/app/domain/grading.py, so the teacher sees the score change while
// choosing levels. The server's score is the record; the browser test checks they agree.

import type { GradeBand, ScoreView } from "./types";

export const MAX_LEVEL = 3;

const BANDS: [number, Exclude<GradeBand, "incomplete">][] = [
  [85, "mastered"],
  [65, "proficient"],
  [40, "developing"],
  [0, "beginning"],
];

export const BAND_LABEL: Record<GradeBand, string> = {
  mastered: "Mastered",
  proficient: "Proficient",
  developing: "Developing",
  beginning: "Beginning",
  incomplete: "Incomplete",
};

export const BAND_HINT: Record<GradeBand, string> = {
  mastered: "85% or more of the rubric points",
  proficient: "65–84% of the rubric points",
  developing: "40–64% of the rubric points",
  beginning: "Under 40% of the rubric points",
  incomplete: "Some criteria have no level yet",
};

export function gradeLevels(levels: Record<string, number | null>): ScoreView {
  const values = Object.values(levels);
  const scored = values.filter((v): v is number => v !== null);
  const points = scored.reduce((sum, v) => sum + v, 0);
  const maxPoints = MAX_LEVEL * scored.length;
  // Round half up in integers, exactly like the server.
  const percent = maxPoints ? Math.floor((200 * points + maxPoints) / (2 * maxPoints)) : null;
  const complete = values.length > 0 && scored.length === values.length;
  const band: GradeBand =
    complete && percent !== null ? BANDS.find(([floor]) => percent >= floor)![1] : "incomplete";
  return { points, max_points: maxPoints, percent, assessed: scored.length, total: values.length, band };
}
